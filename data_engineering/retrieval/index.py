"""STEP 2 - Store the table documents in Qdrant (as in the course, lab 04-rag).

Before: docker compose up -d        (starts Qdrant on http://localhost:6333)
Run:    python -m data_engineering.retrieval.index

Like the course's metadata lab, every document carries a hash: running this again
only re-embeds documents whose text changed, and removes documents that no longer exist.
"""
import json
import uuid

from langchain_core.documents import Document
from qdrant_client import models

from data_engineering.config import COLLECTION_NAME, PROCESSED_DIR
from data_engineering.data_api import get_client, get_embeddings, get_vector_store


def point_id(doc_id):
    """Qdrant needs UUID ids: derive a stable one from 'db.table'."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, doc_id))


def main():
    docs = [json.loads(line) for line in open(PROCESSED_DIR / "documents.jsonl", encoding="utf-8")]
    client = get_client()

    if not client.collection_exists(COLLECTION_NAME):
        size = len(get_embeddings().embed_query("size"))
        client.create_collection(
            COLLECTION_NAME,
            vectors_config=models.VectorParams(size=size, distance=models.Distance.COSINE),
        )

    # What is already stored: id -> hash
    stored, _ = client.scroll(COLLECTION_NAME, limit=10_000, with_payload=True)
    stored_hash = {p.id: p.payload["metadata"]["hash"] for p in stored}

    new = [d for d in docs if stored_hash.get(point_id(d["id"])) != d["metadata"]["hash"]]
    if new:
        get_vector_store().add_documents(
            [Document(page_content=d["text"], metadata=d["metadata"]) for d in new],
            ids=[point_id(d["id"]) for d in new],
        )

    wanted = {point_id(d["id"]) for d in docs}
    stale = [i for i in stored_hash if i not in wanted]
    if stale:
        client.delete(COLLECTION_NAME, points_selector=models.PointIdsList(points=stale))

    print(f"{len(docs)} documents: {len(new)} embedded, {len(docs) - len(new)} unchanged, "
          f"{len(stale)} removed. Collection '{COLLECTION_NAME}' now has "
          f"{client.count(COLLECTION_NAME).count} documents.")


if __name__ == "__main__":
    main()
