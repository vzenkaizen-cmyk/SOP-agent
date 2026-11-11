from dataclasses import dataclass

from ingest import (
    get_client_and_collection,
)

TOP_K = 5


@dataclass
class SOPChunk:
    sop_number: int
    sop_title: str
    source_file: str
    distance: float
    text: str


def retrieve(query: str, plant: str, top_k: int = TOP_K):
    """
    Search the Chroma database for SOP chunks belonging only
    to the requested plant.
    """

    _, collection = get_client_and_collection()

    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        where={"plant": plant},
    )

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    chunks = []

    for doc, meta, dist in zip(documents, metadatas, distances):

        chunks.append(
            SOPChunk(
                sop_number=meta.get("sop_number", ""),
                sop_title=meta.get("sop_title", ""),
                source_file=meta.get("source_file", ""),
                distance=float(dist),
                text=doc,
            )
        )

    return chunks


def collection_stats() -> dict:
    """Quick sanity check used by the Streamlit sidebar."""
    _, collection = get_client_and_collection()
    total = collection.count()

    per_plant = {}
    for code in ("BTO", "WMB"):
        try:
            per_plant[code] = len(collection.get(where={"plant": code})["ids"])
        except Exception:
            per_plant[code] = 0

    return {
        "total": total,
        "per_plant": per_plant,
    }
