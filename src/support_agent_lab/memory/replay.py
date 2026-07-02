from __future__ import annotations

from pydantic import BaseModel

from support_agent_lab.memory.event_store import StoredEvent
from support_agent_lab.memory.store import ConversationMemory
from support_agent_lab.models import ConversationState, IntentType, Message


class MemoryReplayResult(BaseModel):
    conversation_id: str
    state: ConversationState
    event_count: int
    replayed_message_count: int
    replayed_run_count: int
    ignored_event_count: int


def replay_conversation_memory(events: list[StoredEvent]) -> MemoryReplayResult:
    if not events:
        raise ValueError("Cannot replay memory without events")

    conversation_id = events[0].conversation_id
    if not conversation_id:
        raise ValueError("First event has no conversation_id")

    memory = ConversationMemory()
    replayed = 0
    replayed_runs = 0
    ignored = 0
    for event in events:
        if event.conversation_id != conversation_id:
            raise ValueError("Replay events must belong to one conversation")
        if event.event_type.startswith("message."):
            message = Message.model_validate(event.payload)
            _validate_message_event(event, message)
            memory.add_message(message)
            replayed += 1
            continue
        if event.event_type == "agent.run.completed":
            _validate_run_event(event)
            state = memory.states.get(conversation_id)
            primary_intent = (event.payload.get("intent") or {}).get("primary")
            if state and primary_intent:
                state.last_intent = IntentType(primary_intent)
            replayed_runs += 1
            continue
        if event.event_type == "monitor.reviewed":
            ignored += 1
            continue
        ignored += 1

    if conversation_id not in memory.states:
        raise ValueError("Replay events did not contain any message events")

    return MemoryReplayResult(
        conversation_id=conversation_id,
        state=memory.states[conversation_id],
        event_count=len(events),
        replayed_message_count=replayed,
        replayed_run_count=replayed_runs,
        ignored_event_count=ignored,
    )


def _validate_message_event(event: StoredEvent, message: Message) -> None:
    if event.tenant_id != message.tenant_id:
        raise ValueError("Event tenant_id does not match message payload")
    if event.conversation_id != message.conversation_id:
        raise ValueError("Event conversation_id does not match message payload")
    if event.user_id and event.user_id != message.user_id:
        raise ValueError("Event user_id does not match message payload")


def _validate_run_event(event: StoredEvent) -> None:
    if event.tenant_id != event.payload.get("tenant_id"):
        raise ValueError("Event tenant_id does not match run payload")
    if event.conversation_id != event.payload.get("conversation_id"):
        raise ValueError("Event conversation_id does not match run payload")
    if event.user_id and event.user_id != event.payload.get("user_id"):
        raise ValueError("Event user_id does not match run payload")
