"""STEP 2a - BUILD THE VECTOR INDEX from data/processed/documents.jsonl. Owner: Person A.
Incremental: only new/changed documents (by hash) are embedded, stale ones are deleted.
Run: python -m data_engineering.retrieval.index
"""
import json
from data_engineering import config
from . import embeddings

COLLECTION = "schema_docs"


def get_collection():
    import chromadb
    client = chromadb.PersistentClient(path=str(config.index_dir()))
    return client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})


def run() -> dict:
    f = config.processed_dir() / "documents.jsonl"
    if not f.exists():
        raise FileNotFoundError(f"{f} missing. Run `python -m data_engineering.processing.clean` first.")
    docs = [json.loads(l) for l in open(f, encoding="utf-8")]
    col = get_collection()
    existing = col.get(include=["metadatas"])
    old = {i: m.get("hash") for i, m in zip(existing["ids"], existing["metadatas"])}
    stale = [i for i in old if i not in {d["id"] for d in docs}]
    if stale:
        col.delete(ids=stale)
    todo = [d for d in docs if old.get(d["id"]) != d["metadata"]["hash"]]
    for i in range(0, len(todo), 256):
        b = todo[i:i + 256]
        col.upsert(ids=[d["id"] for d in b], documents=[d["text"] for d in b],
                   metadatas=[d["metadata"] for d in b], embeddings=embeddings.embed_documents([d["text"] for d in b]))
    stats = {"documents": len(docs), "embedded": len(todo), "deleted": len(stale), "index_size": col.count()}
    print(stats)
    return stats


if __name__ == "__main__":
    run()
