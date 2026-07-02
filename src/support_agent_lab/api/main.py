from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from support_agent_lab.api.auth import DemoActor, get_demo_actor, require_admin, require_same_user
from support_agent_lab.bootstrap import AppContainer, create_container
from support_agent_lab.models import AgentResponse, Message, MonitorEvent, new_id


class CreateSessionRequest(BaseModel):
    user_id: str = "user_demo"


class CreateSessionResponse(BaseModel):
    conversation_id: str
    user_id: str


class ChatMessageRequest(BaseModel):
    conversation_id: str
    user_id: str = "user_demo"
    content: str = Field(min_length=1, max_length=5000)


class ChatMessageResponse(BaseModel):
    message: Message
    trace_id: str
    handoff_required: bool
    citations: list[dict]


container = create_container()


def get_container() -> AppContainer:
    return container


def create_app() -> FastAPI:
    app = FastAPI(
        title="Production Support Agent Lab",
        version="0.1.0",
        description="A production-shaped customer support agent for learning agent engineering.",
    )

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/chat/sessions")
    def create_session(
        body: CreateSessionRequest,
        actor: Annotated[DemoActor, Depends(get_demo_actor)],
    ) -> CreateSessionResponse:
        require_same_user(body.user_id, actor)
        return CreateSessionResponse(conversation_id=new_id("conv"), user_id=actor.user_id)

    @app.post("/api/v1/chat/messages")
    async def chat(
        body: ChatMessageRequest,
        deps: Annotated[AppContainer, Depends(get_container)],
        actor: Annotated[DemoActor, Depends(get_demo_actor)],
    ) -> ChatMessageResponse:
        require_same_user(body.user_id, actor)
        response = await deps.orchestrator.handle_message(
            conversation_id=body.conversation_id,
            user_id=actor.user_id,
            text=body.content,
        )
        return ChatMessageResponse(
            message=response.message,
            trace_id=response.trace.id,
            handoff_required=response.handoff_required,
            citations=[hit.model_dump(mode="json") for hit in response.citations],
        )

    @app.get("/api/v1/conversations/{conversation_id}/messages")
    def list_messages(
        conversation_id: str,
        deps: Annotated[AppContainer, Depends(get_container)],
        actor: Annotated[DemoActor, Depends(get_demo_actor)],
    ) -> list[Message]:
        if conversation_id not in deps.memory.states:
            raise HTTPException(status_code=404, detail="Conversation not found")
        state = deps.memory.states[conversation_id]
        require_same_user(state.user_id, actor)
        return state.messages

    @app.get("/api/v1/agent/runs/{run_id}")
    def get_run(
        run_id: str,
        deps: Annotated[AppContainer, Depends(get_container)],
        actor: Annotated[DemoActor, Depends(get_demo_actor)],
    ):
        if run_id not in deps.orchestrator.runs:
            raise HTTPException(status_code=404, detail="Run not found")
        run = deps.orchestrator.runs[run_id]
        require_same_user(run.user_id, actor)
        return run

    @app.get("/api/v1/admin/tools")
    def list_tools(
        deps: Annotated[AppContainer, Depends(get_container)],
        actor: Annotated[DemoActor, Depends(get_demo_actor)],
    ):
        require_admin(actor)
        return deps.tools.registry.list_tools()

    @app.get("/api/v1/admin/monitor/events")
    def monitor_events(
        deps: Annotated[AppContainer, Depends(get_container)],
        actor: Annotated[DemoActor, Depends(get_demo_actor)],
    ) -> list[MonitorEvent]:
        require_admin(actor)
        return deps.monitor.events

    @app.post("/api/v1/admin/evals/golden")
    async def run_golden_eval(
        deps: Annotated[AppContainer, Depends(get_container)],
        actor: Annotated[DemoActor, Depends(get_demo_actor)],
    ):
        require_admin(actor)
        from support_agent_lab.evals.runner import load_cases, run_cases

        cases = load_cases("examples/evals/golden_core.json")
        return await run_cases(cases, deps.orchestrator)

    return app


app = create_app()
