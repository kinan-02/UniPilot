# Legacy RAG (unused in live path)

The following modules implement the **previous** BM25 + embedding hybrid wiki
retrieval stack. They remain in the tree for regression benchmarks and
reference but are **not imported** by the orchestrator or context builder.

| Module | Role |
|--------|------|
| `hybrid_wiki_retriever.py` | BM25 + vector hybrid search |
| `obsidian_wiki_retriever.py` | Re-export shim |
| `wiki_vector_index.py` | Embedding index cache |
| `embedding_service.py` | Embedding API client |
| `reranker.py` | Chunk reranking + link expansion |
| `obsidian_wiki_indexer.py` | Wiki chunk loader |
| `build_wiki_vector_index.py` | Offline index builder |
| `metadata_filter.py` | User-context metadata filters |

**Live retrieval:** `graph_retriever.py` + `graph_engine/` (wiki graph +
semester JSON), ported from `services/ai`.
