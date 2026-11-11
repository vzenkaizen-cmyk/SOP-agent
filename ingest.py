"""
ingest.py
---------
Extracts each plant's SOP PDF, splits it into section-aware chunks (one
chunk per numbered SOP, sub-split further if long), and indexes everything
into a single persistent ChromaDB collection with a `plant` metadata field
used for plant-scoped retrieval.

Run directly to (re)build the index for both plants:
    python ingest.py

Or import `reindex_plant(code)` / `reindex_all()` from the Streamlit app's
"Reindex" button.
"""

import re
import shutil
from pathlib import Path

import pdfplumber
import chromadb
from chromadb.utils import embedding_functions

from plant_registry import PLANTS, get_plant

CHROMA_DIR = str(Path(__file__).parent / "chroma_db")
COLLECTION_NAME = "vidullanka_sops"
EMBED_MODEL = "all-MiniLM-L6-v2"

# Matches top-level SOP headers like "1.Standard Operation..." or
# "21 Standard Operating Procedure ..." (with or without a period).
SECTION_RE = re.compile(r"^(\d{1,2})[\.\s]+Standard\b", re.IGNORECASE)

# Lines that are just repeated header/footer boilerplate on every page —
# stripped out before chunking so they don't pollute embeddings.
_DROP_PATTERNS = [
    r"^SOP\s*[:#]?.*$", r"^Revision.*$", r"^Implementation Date.*$",
    r"^Page\s*[:#]?\s*\d+.*$", r"^Last Reviewed.*$", r"^SOP Owner.*$",
    r"^Approval.*$", r"^Operations?\s*Manager.*$", r"^\(?BTO\)?$", r"^\(?WMB\)?$",
    r"^Batathota MHPP.*$", r"^Wembiyagoda.*$", r"^VLL\\.*$",
    r"^\d+\s*\|\s*P\s*a\s*g\s*e$",
]
_DROP_RE = [re.compile(p, re.IGNORECASE) for p in _DROP_PATTERNS]

CHUNK_MAX_CHARS = 1200
CHUNK_OVERLAP = 150
MIN_SECTION_CHARS = 200  # filters out stray TOC-line matches


def _extract_pages(pdf_path: Path) -> list[str]:
    with pdfplumber.open(pdf_path) as pdf:
        return [(page.extract_text() or "") for page in pdf.pages]


def _clean_page(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        ls = line.strip()
        if not ls:
            continue
        if any(rx.match(ls) for rx in _DROP_RE):
            continue
        lines.append(ls)
    return "\n".join(lines)


def _split_into_sections(full_text: str) -> list[dict]:
    """Split cleaned full-document text into one block per numbered SOP,
    keeping the longest occurrence of each section number (the first,
    shorter occurrence is almost always the Table of Contents line)."""
    lines = full_text.split("\n")
    raw = []
    num, title, buf = None, None, []
    for line in lines:
        m = SECTION_RE.match(line)
        if m:
            if num is not None:
                raw.append((num, title, "\n".join(buf)))
            num = int(m.group(1))
            title = line
            buf = [line]
        else:
            if num is not None:
                buf.append(line)
    if num is not None:
        raw.append((num, title, "\n".join(buf)))

    best: dict[int, tuple[str, str]] = {}
    for n, t, body in raw:
        if len(body) < MIN_SECTION_CHARS:
            continue
        if n not in best or len(body) > len(best[n][1]):
            best[n] = (t, body)

    sections = []
    for n in sorted(best):
        title, body = best[n]
        clean_title = re.sub(r"\s+", " ", title).strip(" .")
        sections.append({"sop_number": n, "sop_title": clean_title, "text": body})
    return sections


def _sub_chunk(text: str, max_chars=CHUNK_MAX_CHARS, overlap=CHUNK_OVERLAP) -> list[str]:
    """Further split a long section on paragraph-ish boundaries so each
    chunk stays embedding-friendly, with a little overlap for context."""
    if len(text) <= max_chars:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        # try to break on a newline near the end for cleaner chunks
        if end < len(text):
            nl = text.rfind("\n", start, end)
            if nl > start + 200:
                end = nl
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


def build_documents_for_plant(code: str) -> list[dict]:
    """Returns a list of {id, text, metadata} ready for Chroma for one plant."""
    plant = get_plant(code)
    pdf_path = Path(plant["sop_pdf"])
    if not pdf_path.exists():
        raise FileNotFoundError(
            f"SOP PDF not found for {code} at {pdf_path}. "
            f"Put the plant's SOP PDF there (see README)."
        )

    pages = _extract_pages(pdf_path)
    cleaned_pages = [_clean_page(p) for p in pages]
    full_text = "\n".join(cleaned_pages)
    sections = _split_into_sections(full_text)

    docs = []
    for sec in sections:
        sub_chunks = _sub_chunk(sec["text"])
        for i, chunk_text in enumerate(sub_chunks):
            doc_id = f"{code}-SOP{sec['sop_number']:02d}-{i}"
            docs.append({
                "id": doc_id,
                "text": chunk_text,
                "metadata": {
                    "plant": code,
                    "plant_name": plant["name"],
                    "sop_number": sec["sop_number"],
                    "sop_title": sec["sop_title"],
                    "source_file": pdf_path.name,
                    "chunk_index": i,
                },
            })
    return docs


def get_client_and_collection():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )
    return client, collection


def reindex_plant(code: str) -> int:
    """(Re)index a single plant's SOP into the shared collection.
    Existing chunks for that plant are deleted first, so this is safe to
    re-run whenever the source PDF changes."""
    _, collection = get_client_and_collection()
    collection.delete(where={"plant": code})

    docs = build_documents_for_plant(code)
    if not docs:
        return 0

    collection.add(
        ids=[d["id"] for d in docs],
        documents=[d["text"] for d in docs],
        metadatas=[d["metadata"] for d in docs],
    )
    return len(docs)


def reindex_all() -> dict:
    return {code: reindex_plant(code) for code in PLANTS}


def wipe_index():
    shutil.rmtree(CHROMA_DIR, ignore_errors=True)


if __name__ == "__main__":
    print(f"Indexing into {CHROMA_DIR} ...")
    counts = reindex_all()
    for code, n in counts.items():
        print(f"  {code}: {n} chunks indexed")
    print("Done.")
