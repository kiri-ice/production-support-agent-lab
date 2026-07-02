from support_agent_lab.memory.store import KnowledgeIndex


def test_knowledge_search_returns_source_backed_trace():
    knowledge = KnowledgeIndex()

    trace = knowledge.search("耳机坏了 能不能退货")

    assert trace.selected_context
    assert trace.selected_context[0].source_uri.startswith("kb://")
    assert trace.candidates_by_stage["hybrid"] >= 1

