# RAG 与检索优化手册

客服 Agent 的 RAG 不是“向量检索 top-k 塞进 prompt”。生产里更重要的是可诊断。

## RetrievalTrace 示例

```json
{
  "query": "退换货政策 质量问题 30 天",
  "rewritten_queries": [
    "退换货政策 质量问题 30 天",
    "退换货政策 质量问题 30 天 退换货 质量问题 30 天"
  ],
  "selected_sources": ["kb://policies/return_policy_v3"],
  "candidates_by_stage": {
    "hybrid": 3,
    "reranked": 3
  },
  "selected_context": [
    {
      "document_id": "return_policy_v3",
      "title": "退换货政策 v3",
      "score": 4.2
    }
  ]
}
```

如果 eval 报 `missing citation doc`，第一步就是看这个 trace。

## 当前实现

`KnowledgeIndex.search` 做了三件事：

1. Query rewrite：根据退款、物流、发票、耳机等主题扩展 query。
2. Hybrid-ish scoring：关键词/CJK token + phrase bonus。
3. RetrievalTrace：记录 query、rewritten queries、候选数量、选中来源。

这不是最终生产检索，但它保留了生产系统该有的形状。

## 中文召回不足的真实例子

最初 tokenizer 把“耳机单边无声”当成一个长 token，知识库里是“单边无声”“蓝牙”“故障排查”，导致没有候选。

修复方式不是换模型，而是先修 tokenizer：

- 对 CJK 文本拆单字。
- 加 bigram。
- 保留英文/数字 token。
- 再看 query rewrite 和 chunk。

对应代码：`src/support_agent_lab/memory/store.py`

## 排查清单

| 症状 | 可能原因 | 修复 |
| --- | --- | --- |
| 无候选 | tokenizer、索引缺失、过滤过严 | 检查 `candidates_by_stage` |
| 候选有但答案错 | rerank 弱、上下文装配差 | 加 answerability rerank |
| 引用不支持答案 | 生成阶段没有绑定 citation | 强制 unsupported claim 检查 |
| 引用过期政策 | metadata 未参与排序 | 加 effective/version filter |
| 多语言差 | query rewrite 单语言 | 加双语 rewrite 或跨语言 embedding |

## 生产建议

- Postgres 存文档、chunk、metadata、版本。
- pgvector 做 dense retrieval。
- OpenSearch/Elasticsearch 做 BM25。
- reranker 统一输入 query + chunk + metadata。
- 所有回答带 citation。
- 用户点“没解决”后，把 query、候选、答案放入 hard query set。
