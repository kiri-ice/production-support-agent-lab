from __future__ import annotations

import inspect
from typing import Any

from support_agent_lab.models import RetrievalContext


def call_knowledge_search(
    knowledge: Any,
    query: str,
    *,
    limit: int = 4,
    context: RetrievalContext | None = None,
) -> Any:
    search = knowledge.search
    if context is not None and _accepts_context(search):
        return search(query, limit=limit, context=context)
    return search(query, limit=limit)


def _accepts_context(callable_obj: Any) -> bool:
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return False
    return any(
        parameter.name == "context" or parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
