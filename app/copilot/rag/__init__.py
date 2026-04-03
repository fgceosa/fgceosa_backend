# RAG (Retrieval-Augmented Generation) Pipeline
from app.copilot.rag.storage import upload_to_r2, download_from_r2, delete_from_r2
from app.copilot.rag.extractor import extract_text
from app.copilot.rag.chunker import chunk_text
from app.copilot.rag.embeddings import generate_embeddings, generate_batch_embeddings

__all__ = [
    "upload_to_r2",
    "download_from_r2",
    "delete_from_r2",
    "extract_text",
    "chunk_text",
    "generate_embeddings",
    "generate_batch_embeddings",
]
