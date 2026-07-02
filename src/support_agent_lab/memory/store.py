from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from math import log
from typing import Iterable

from support_agent_lab.data.fixtures import KNOWLEDGE_DOCUMENTS
from support_agent_lab.models import (
    ConversationState,
    Message,
    RetrievalHit,
    RetrievalTrace,
    Role,
    utc_now,
)


TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for token in TOKEN_RE.findall(text):
        lowered = token.lower()
        if any("\u4e00" <= char <= "\u9fff" for char in lowered):
            cjk_chars = [char for char in lowered if "\u4e00" <= char <= "\u9fff"]
            tokens.extend(cjk_chars)
            tokens.extend("".join(cjk_chars[index : index + 2]) for index in range(max(len(cjk_chars) - 1, 0)))
        else:
            tokens.append(lowered)
    return tokens


@dataclass
class ConversationMemory:
    states: dict[str, ConversationState] = field(default_factory=dict)
    profile_facts: dict[str, dict[str, str]] = field(default_factory=lambda: defaultdict(dict))

    def get_or_create(self, tenant_id: str, conversation_id: str, user_id: str) -> ConversationState:
        if conversation_id not in self.states:
            self.states[conversation_id] = ConversationState(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                user_id=user_id,
            )
        return self.states[conversation_id]

    def add_message(self, message: Message) -> ConversationState:
        state = self.get_or_create(message.tenant_id, message.conversation_id, message.user_id)
        state.messages.append(message)
        state.updated_at = utc_now()
        if message.role == Role.user:
            self._update_thread_state(state, message.content)
        return state

    def _update_thread_state(self, state: ConversationState, content: str) -> None:
        order_match = re.search(r"\b[A-Z]\d{4,}\b", content.upper())
        if order_match:
            state.facts["last_order_id"] = order_match.group(0)
        if any(word in content for word in ["发票", "invoice"]):
            state.facts["billing_topic"] = "invoice"
        if len(state.messages) >= 4:
            recent = " / ".join(msg.content for msg in state.messages[-4:] if msg.role == Role.user)
            state.working_summary = f"Recent user concerns: {recent[:240]}"

    def visible_context(self, conversation_id: str, window: int = 6) -> list[Message]:
        state = self.states[conversation_id]
        return state.messages[-window:]

    def remember_profile_fact(self, user_id: str, key: str, value: str) -> None:
        self.profile_facts[user_id][key] = value


@dataclass
class KnowledgeIndex:
    documents: list[dict] = field(default_factory=lambda: list(KNOWLEDGE_DOCUMENTS))

    def search(self, query: str, limit: int = 4) -> RetrievalTrace:
        rewritten = self.rewrite_query(query)
        candidates: list[RetrievalHit] = []
        for doc in self.documents:
            score = max(self._score(q, doc["content"] + " " + doc["title"]) for q in rewritten)
            if score > 0:
                candidates.append(
                    RetrievalHit(
                        document_id=doc["document_id"],
                        chunk_id=f"{doc['document_id']}:0",
                        title=doc["title"],
                        content=doc["content"],
                        score=round(score, 4),
                        source_uri=doc["source_uri"],
                        metadata=doc["metadata"],
                    )
                )
        candidates.sort(key=lambda hit: hit.score, reverse=True)
        selected = candidates[:limit]
        dropped = [hit.chunk_id for hit in candidates[limit:]]
        return RetrievalTrace(
            query=query,
            rewritten_queries=rewritten,
            selected_sources=[hit.source_uri for hit in selected],
            candidates_by_stage={"hybrid": len(candidates), "reranked": len(selected)},
            selected_context=selected,
            dropped_candidates=dropped,
        )

    def rewrite_query(self, query: str) -> list[str]:
        expansions = [query]
        if any(word in query for word in ["退", "退款", "退货", "坏", "质量"]):
            expansions.append(f"{query} 退换货 质量问题 30 天")
        if any(word in query for word in ["物流", "快递", "到哪", "发货"]):
            expansions.append(f"{query} 物流 延迟 单号")
        if any(word in query for word in ["发票", "账单", "税号"]):
            expansions.append(f"{query} 发票 税号 抬头")
        if any(word in query.lower() for word in ["耳机", "headphone", "bluetooth", "蓝牙"]):
            expansions.append(f"{query} 耳机 故障 排查 蓝牙")
        return list(dict.fromkeys(expansions))

    def _score(self, query: str, text: str) -> float:
        q_tokens = tokenize(query)
        t_tokens = tokenize(text)
        if not q_tokens or not t_tokens:
            return 0.0
        t_freq = defaultdict(int)
        for token in t_tokens:
            t_freq[token] += 1
        overlap = sum(1 for token in q_tokens if token in t_freq)
        phrase_bonus = 2.0 if query in text else 0.0
        density = overlap / max(len(set(q_tokens)), 1)
        length_penalty = 1 / (1 + log(max(len(t_tokens), 2)))
        return density + phrase_bonus + length_penalty * overlap

    def add_documents(self, docs: Iterable[dict]) -> None:
        self.documents.extend(docs)
