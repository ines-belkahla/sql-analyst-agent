"""Find the tables of a database that are relevant to a question."""

from functools import lru_cache

from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

from src.config import EMBEDDING_MODEL, TOP_K, VECTOR_STORE_DIR


@lru_cache(maxsize=1)
def get_vector_store():
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    # allow_dangerous_deserialization: safe here, we load the index we built ourselves
    return FAISS.load_local(
        str(VECTOR_STORE_DIR), embeddings, allow_dangerous_deserialization=True
    )


def search_schema(db_id, question, k=TOP_K):
    """Top-k table documents of database `db_id` for the question (metadata filter)."""
    return get_vector_store().similarity_search(
        question, k=k, filter={"db_id": db_id}, fetch_k=200
    )
