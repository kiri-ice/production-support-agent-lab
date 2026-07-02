import pytest

from support_agent_lab.memory.store import ConversationMemory, KnowledgeIndex
from support_agent_lab.models import Message, Role


def test_knowledge_search_returns_source_backed_trace():
    knowledge = KnowledgeIndex()

    trace = knowledge.search("耳机坏了 能不能退货")

    assert trace.selected_context
    assert trace.selected_context[0].source_uri.startswith("kb://")
    assert trace.candidates_by_stage["hybrid"] >= 1


def test_conversation_memory_rejects_cross_user_reuse():
    memory = ConversationMemory()
    memory.add_message(
        Message(
            tenant_id="tenant_1",
            conversation_id="conv_owned",
            user_id="user_a",
            role=Role.user,
            content="hello",
        )
    )

    with pytest.raises(PermissionError):
        memory.add_message(
            Message(
                tenant_id="tenant_1",
                conversation_id="conv_owned",
                user_id="user_b",
                role=Role.user,
                content="continue",
            )
        )
