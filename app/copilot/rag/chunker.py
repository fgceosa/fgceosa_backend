"""
Text Chunking for RAG Pipeline
Implements semantic chunking with configurable overlap
"""
import re
from typing import Optional


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 200,
    separator: str | None = None,
) -> list[dict]:
    """
    Split text into chunks with overlap for better retrieval.

    Args:
        text: Input text to chunk
        chunk_size: Target size of each chunk in characters
        overlap: Number of overlapping characters between chunks
        separator: Optional separator to split on (default: paragraphs/sentences)

    Returns:
        List of chunk dictionaries with content and metadata
    """
    if not text or not text.strip():
        return []

    # Clean the text
    text = clean_text(text)

    # Use semantic chunking by default
    if separator is None:
        return semantic_chunk(text, chunk_size, overlap)
    else:
        return simple_chunk(text, chunk_size, overlap, separator)


def clean_text(text: str) -> str:
    """
    Clean and normalize text.
    """
    # Replace multiple newlines with double newline
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Replace multiple spaces with single space
    text = re.sub(r" {2,}", " ", text)

    # Remove leading/trailing whitespace from each line
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    return text.strip()


def semantic_chunk(text: str, chunk_size: int, overlap: int) -> list[dict]:
    """
    Chunk text semantically, preserving paragraph and sentence boundaries.
    """
    chunks = []
    current_pos = 0

    # Split into paragraphs first
    paragraphs = re.split(r"\n\n+", text)

    current_chunk = ""
    chunk_start = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # If adding this paragraph exceeds chunk size
        if len(current_chunk) + len(para) + 2 > chunk_size and current_chunk:
            # Save current chunk
            chunks.append({
                "content": current_chunk.strip(),
                "start_char": chunk_start,
                "end_char": chunk_start + len(current_chunk),
                "metadata": {},
            })

            # Start new chunk with overlap
            overlap_text = get_overlap_text(current_chunk, overlap)
            chunk_start = chunk_start + len(current_chunk) - len(overlap_text)
            current_chunk = overlap_text + "\n\n" + para if overlap_text else para
        else:
            # Add paragraph to current chunk
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para
                chunk_start = current_pos

        current_pos += len(para) + 2  # +2 for paragraph separator

    # Add final chunk
    if current_chunk.strip():
        chunks.append({
            "content": current_chunk.strip(),
            "start_char": chunk_start,
            "end_char": chunk_start + len(current_chunk),
            "metadata": {},
        })

    # Handle case where single paragraph is too long
    final_chunks = []
    for chunk in chunks:
        if len(chunk["content"]) > chunk_size * 1.5:
            # Split long chunk by sentences
            sub_chunks = split_by_sentences(chunk["content"], chunk_size, overlap)
            for i, sub in enumerate(sub_chunks):
                final_chunks.append({
                    "content": sub,
                    "start_char": chunk["start_char"],
                    "end_char": chunk["end_char"],
                    "metadata": {"sub_chunk": i},
                })
        else:
            final_chunks.append(chunk)

    return final_chunks


def split_by_sentences(text: str, chunk_size: int, overlap: int) -> list[str]:
    """
    Split text by sentence boundaries.
    """
    # Sentence ending patterns
    sentence_endings = re.compile(r"(?<=[.!?])\s+")
    sentences = sentence_endings.split(text)

    chunks = []
    current_chunk = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(current_chunk) + len(sentence) + 1 > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())

            # Get overlap from end of current chunk
            overlap_text = get_overlap_text(current_chunk, overlap)
            current_chunk = overlap_text + " " + sentence if overlap_text else sentence
        else:
            current_chunk = current_chunk + " " + sentence if current_chunk else sentence

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def simple_chunk(text: str, chunk_size: int, overlap: int, separator: str) -> list[dict]:
    """
    Simple chunking with a specific separator.
    """
    parts = text.split(separator)
    chunks = []
    current_chunk = ""
    chunk_start = 0
    current_pos = 0

    for part in parts:
        part = part.strip()
        if not part:
            current_pos += len(separator)
            continue

        if len(current_chunk) + len(part) + len(separator) > chunk_size and current_chunk:
            chunks.append({
                "content": current_chunk.strip(),
                "start_char": chunk_start,
                "end_char": chunk_start + len(current_chunk),
                "metadata": {},
            })

            overlap_text = get_overlap_text(current_chunk, overlap)
            chunk_start = current_pos - len(overlap_text)
            current_chunk = overlap_text + separator + part if overlap_text else part
        else:
            if current_chunk:
                current_chunk += separator + part
            else:
                current_chunk = part
                chunk_start = current_pos

        current_pos += len(part) + len(separator)

    if current_chunk.strip():
        chunks.append({
            "content": current_chunk.strip(),
            "start_char": chunk_start,
            "end_char": chunk_start + len(current_chunk),
            "metadata": {},
        })

    return chunks


def get_overlap_text(text: str, overlap: int) -> str:
    """
    Get the last 'overlap' characters of text, preferring sentence boundaries.
    """
    if len(text) <= overlap:
        return text

    overlap_region = text[-overlap:]

    # Try to find a sentence boundary
    sentence_match = re.search(r"[.!?]\s+", overlap_region)
    if sentence_match:
        return overlap_region[sentence_match.end():]

    # Try to find a paragraph boundary
    para_match = overlap_region.find("\n\n")
    if para_match != -1:
        return overlap_region[para_match + 2:]

    # Fall back to word boundary
    word_match = re.search(r"\s+", overlap_region)
    if word_match:
        return overlap_region[word_match.end():]

    return overlap_region


def chunk_with_page_info(
    text: str,
    pages: list[dict],
    chunk_size: int = 1000,
    overlap: int = 200,
) -> list[dict]:
    """
    Chunk text while preserving page number information from PDF extraction.

    Args:
        text: Full document text
        pages: List of page dicts with 'page_number', 'content', 'char_start'
        chunk_size: Target chunk size
        overlap: Overlap between chunks

    Returns:
        Chunks with page_number in metadata
    """
    chunks = semantic_chunk(text, chunk_size, overlap)

    # Map chunks to page numbers
    for chunk in chunks:
        chunk_start = chunk["start_char"]
        chunk_end = chunk["end_char"]

        # Find which page(s) this chunk belongs to
        chunk_pages = []
        for page in pages:
            page_start = page["char_start"]
            page_end = page_start + len(page["content"])

            if chunk_start < page_end and chunk_end > page_start:
                chunk_pages.append(page["page_number"])

        if chunk_pages:
            chunk["page_number"] = chunk_pages[0]  # Primary page
            if len(chunk_pages) > 1:
                chunk["metadata"]["pages"] = chunk_pages

    return chunks
