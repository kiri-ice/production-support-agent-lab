from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ValidationError

from support_agent_lab.models import ToolResult, ToolStatus, new_id
from support_agent_lab.tools.errors import (
    CONFLICT,
    FORBIDDEN,
    IDEMPOTENCY_CONFLICT,
    INTERNAL_ERROR,
    TIMEOUT,
    ToolError,
    VALIDATION_ERROR,
)


class Actor(BaseModel):
    user_id: str
    tenant_id: str
    roles: list[str] = ["agent"]
    scopes: list[str] = []


class ToolContext(BaseModel):
    actor: Actor
    request_id: str
    trace_id: str
    tenant_id: str
    idempotency_key: str | None = None


ToolHandler = Callable[[BaseModel, ToolContext], Awaitable[BaseModel]]


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    required_scopes: list[str]
    timeout_ms: int
    idempotent: bool
    handler: ToolHandler

    def input_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()

    def output_schema(self) -> dict[str, Any]:
        return self.output_model.model_json_schema()


@dataclass
class ToolRegistry:
    tools: dict[str, ToolDefinition] = field(default_factory=dict)

    def register(self, tool: ToolDefinition) -> None:
        self.tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition:
        if name not in self.tools:
            raise ToolError("TOOL_NOT_FOUND", f"Unknown tool: {name}")
        return self.tools[name]

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema(),
                "output_schema": tool.output_schema(),
                "required_scopes": tool.required_scopes,
                "timeout_ms": tool.timeout_ms,
                "idempotent": tool.idempotent,
            }
            for tool in sorted(self.tools.values(), key=lambda item: item.name)
        ]


@dataclass
class ToolAuditRecord:
    id: str
    tool_name: str
    tenant_id: str
    actor_user_id: str
    request_id: str
    trace_id: str
    argument_hash: str
    status: ToolStatus
    latency_ms: int
    error_code: str | None
    idempotency_key_hash: str | None = None
    replayed: bool = False
    created_at: str | None = None


@dataclass
class IdempotencyDecision:
    status: Literal["reserved", "replay", "conflict", "in_progress"]
    result: ToolResult | None = None


class ToolIdempotencyStore(Protocol):
    def reserve(self, key: str, arg_hash: str) -> IdempotencyDecision:
        ...

    def complete(self, key: str, arg_hash: str, result: ToolResult) -> None:
        ...

    def release(self, key: str, arg_hash: str) -> None:
        ...


class ToolAuditSink(Protocol):
    def append_tool_audit(self, record: ToolAuditRecord) -> None:
        ...


@dataclass
class InMemoryToolIdempotencyStore:
    entries: dict[str, dict[str, Any]]

    def reserve(self, key: str, arg_hash: str) -> IdempotencyDecision:
        existing = self.entries.get(key)
        if not existing:
            self.entries[key] = {
                "arg_hash": arg_hash,
                "status": "in_progress",
                "result": None,
            }
            return IdempotencyDecision(status="reserved")
        if existing["arg_hash"] != arg_hash:
            return IdempotencyDecision(status="conflict")
        result = existing.get("result")
        if result:
            return IdempotencyDecision(status="replay", result=ToolResult.model_validate(result))
        return IdempotencyDecision(status="in_progress")

    def complete(self, key: str, arg_hash: str, result: ToolResult) -> None:
        self.entries[key] = {
            "arg_hash": arg_hash,
            "status": "completed",
            "result": result.model_dump(mode="json"),
        }

    def release(self, key: str, arg_hash: str) -> None:
        existing = self.entries.get(key)
        if (
            existing
            and existing.get("arg_hash") == arg_hash
            and existing.get("status") == "in_progress"
        ):
            self.entries.pop(key, None)


@dataclass
class ToolFault:
    error_code: str
    message: str
    retryable: bool = False
    delay_ms: int = 0


@dataclass
class ToolFaultProfile:
    faults_by_tool: dict[str, list[ToolFault]] = field(default_factory=dict)

    def add(self, tool_name: str, fault: ToolFault) -> "ToolFaultProfile":
        self.faults_by_tool.setdefault(tool_name, []).append(fault)
        return self

    def pop(self, tool_name: str) -> ToolFault | None:
        faults = self.faults_by_tool.get(tool_name)
        if not faults:
            return None
        fault = faults.pop(0)
        if not faults:
            self.faults_by_tool.pop(tool_name, None)
        return fault


@dataclass
class ToolBroker:
    registry: ToolRegistry
    idempotency_store: dict[str, dict[str, Any]] | ToolIdempotencyStore
    audit_log: list[ToolAuditRecord] = field(default_factory=list)
    audit_sink: ToolAuditSink | None = None
    fault_profile: ToolFaultProfile | None = None

    def __post_init__(self) -> None:
        if isinstance(self.idempotency_store, dict):
            self.idempotency_store = InMemoryToolIdempotencyStore(self.idempotency_store)

    async def call(self, name: str, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = perf_counter()
        arg_hash = self._hash(arguments)
        tool: ToolDefinition | None = None
        reserved_key: str | None = None
        try:
            tool = self.registry.get(name)
            self._authorize(tool, ctx)
            parsed = tool.input_model.model_validate(arguments)
            arg_hash = self._hash(parsed.model_dump(mode="json"))
            if not tool.idempotent:
                self._require_idempotency(ctx)
            cached, reserved_key = self._reserve_idempotency(tool, ctx, arg_hash)
            if cached:
                cached.latency_ms = self._elapsed_ms(started)
                self._audit(name, arg_hash, cached, ctx, replayed=True)
                return cached
            fault = self._pop_fault(name)
            if fault:
                if fault.delay_ms:
                    await asyncio.sleep(fault.delay_ms / 1000)
                raise ToolError(fault.error_code, fault.message, retryable=fault.retryable)
            output = await asyncio.wait_for(
                tool.handler(parsed, ctx),
                timeout=tool.timeout_ms / 1000,
            )
            validated = tool.output_model.model_validate(output)
            result = ToolResult(
                name=name,
                status=ToolStatus.success,
                data=validated.model_dump(),
                latency_ms=self._elapsed_ms(started),
            )
            self._complete_idempotency(reserved_key, arg_hash, result)
            self._audit(name, arg_hash, result, ctx)
            return result
        except ValidationError as exc:
            result = ToolResult(
                name=name,
                status=ToolStatus.failed,
                error_code=VALIDATION_ERROR,
                error_message=str(exc),
                retryable=False,
                latency_ms=self._elapsed_ms(started),
            )
        except asyncio.TimeoutError:
            result = ToolResult(
                name=name,
                status=ToolStatus.failed,
                error_code=TIMEOUT,
                error_message=f"Tool {name} exceeded {tool.timeout_ms if tool else 0}ms",
                retryable=True,
                latency_ms=self._elapsed_ms(started),
            )
        except ToolError as exc:
            result = ToolResult(
                name=name,
                status=ToolStatus.failed,
                error_code=exc.code,
                error_message=exc.message,
                retryable=exc.retryable,
                latency_ms=self._elapsed_ms(started),
            )
        except Exception as exc:
            result = ToolResult(
                name=name,
                status=ToolStatus.failed,
                error_code=INTERNAL_ERROR,
                error_message=str(exc),
                retryable=False,
                latency_ms=self._elapsed_ms(started),
            )
        self._release_idempotency(reserved_key, arg_hash)
        self._audit(name, arg_hash, result, ctx)
        return result

    def _authorize(self, tool: ToolDefinition, ctx: ToolContext) -> None:
        missing = [scope for scope in tool.required_scopes if scope not in ctx.actor.scopes]
        if missing:
            raise ToolError(FORBIDDEN, f"Missing scopes: {', '.join(missing)}")
        if ctx.actor.tenant_id != ctx.tenant_id:
            raise ToolError(FORBIDDEN, "Actor tenant does not match request tenant")

    def _require_idempotency(self, ctx: ToolContext) -> None:
        if not ctx.idempotency_key:
            raise ToolError(VALIDATION_ERROR, "Write tool requires idempotency_key")

    def _reserve_idempotency(
        self,
        tool: ToolDefinition,
        ctx: ToolContext,
        arg_hash: str,
    ) -> tuple[ToolResult | None, str | None]:
        if tool.idempotent or not ctx.idempotency_key:
            return None, None
        key = self._idempotency_key(tool.name, ctx)
        decision = self.idempotency_store.reserve(key, arg_hash)
        if decision.status == "reserved":
            return None, key
        if decision.status == "replay" and decision.result:
            return decision.result, None
        if decision.status == "conflict":
            raise ToolError(IDEMPOTENCY_CONFLICT, "Same idempotency key used with different payload")
        raise ToolError(CONFLICT, "Same idempotency key is already in progress", retryable=True)

    def _complete_idempotency(
        self,
        reserved_key: str | None,
        arg_hash: str,
        result: ToolResult,
    ) -> None:
        if not reserved_key:
            return
        self.idempotency_store.complete(reserved_key, arg_hash, result)

    def _release_idempotency(self, reserved_key: str | None, arg_hash: str) -> None:
        if reserved_key:
            self.idempotency_store.release(reserved_key, arg_hash)

    def _idempotency_key(self, tool_name: str, ctx: ToolContext) -> str:
        key_hash = self._hash_text(ctx.idempotency_key or "")
        return f"{ctx.tenant_id}:{ctx.actor.user_id}:{tool_name}:{key_hash}"

    def _audit(
        self,
        name: str,
        arg_hash: str,
        result: ToolResult,
        ctx: ToolContext,
        *,
        replayed: bool = False,
    ) -> None:
        record = ToolAuditRecord(
            id=new_id("audit"),
            tool_name=name,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.actor.user_id,
            request_id=ctx.request_id,
            trace_id=ctx.trace_id,
            argument_hash=arg_hash,
            status=result.status,
            latency_ms=result.latency_ms,
            error_code=result.error_code,
            idempotency_key_hash=(
                self._hash_text(ctx.idempotency_key) if ctx.idempotency_key else None
            ),
            replayed=replayed,
        )
        self.audit_log.append(record)
        if self.audit_sink:
            try:
                self.audit_sink.append_tool_audit(record)
            except Exception:
                # Keep the tool result truthful; readiness should catch durable audit sink failures.
                pass

    def _hash(self, arguments: dict[str, Any]) -> str:
        payload = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _hash_text(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _elapsed_ms(self, started: float) -> int:
        return int((perf_counter() - started) * 1000)

    def _pop_fault(self, name: str) -> ToolFault | None:
        if not self.fault_profile:
            return None
        return self.fault_profile.pop(name)
