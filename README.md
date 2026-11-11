# Vidullanka IDSS — Plant Operations Assistant

A RAG-based AI agent (LangGraph + Claude + ChromaDB) that answers troubleshooting,
startup/stop, safety, and maintenance questions from the SOPs of two mini hydro
plants — **Batathota (BTO)** and **Wembiyagoda (WMB)** — with a Streamlit chat UI.

## How it works

```
data/BTO_SOP.pdf ──┐
data/WMB_SOP.pdf ──┴──► ingest.py ──► ChromaDB (chroma_db/, one collection,
                        (pdfplumber,     "plant" metadata field separates
                         section-aware   BTO vs WMB so a BTO question can
                         chunking,       never surface WMB chunks)
                         sentence-
                         transformers)
                              │
                              ▼
                     retriever.py (plant-scoped, cosine-distance filtered)
                              │
                              ▼
                     agent.py — LangGraph ReAct agent (Claude) with one
                     tool, search_sop, hard-bound to the selected plant
                              │
                              ▼
                     app.py — Streamlit chat UI: plant selector, chat,
                     source citation cards, reindex button
```

## 1. Setup (Windows / PowerShell)

```powershell
cd vidullanka_idss
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. Add your API key

```powershell
copy .env.example .env
notepad .env
```
Paste your `OPEN_AI_API_KEY` in. (Get one from the Claude Console if you
don't already have one wired up in your other IDSS modules.)

## 3. Add the SOP PDFs

Put the two SOP PDFs in `data/`, named exactly:

```
data/BTO_SOP.pdf
data/WMB_SOP.pdf
```

(If you want to add a third plant later, add one entry to `plant_registry.py`
and drop its PDF in `data/` — nothing else needs to change.)

## 4. Build the index

```powershell
python ingest.py
```

First run downloads the small `all-MiniLM-L6-v2` embedding model (~90MB) from
Hugging Face, then indexes both plants into `chroma_db/`. You should see:

```
Indexing into .../chroma_db ...
  BTO: 37 chunks indexed
  WMB: 37 chunks indexed
Done.
```

(You can also trigger this later from inside the app via the **Reindex**
buttons in the sidebar — useful whenever you update an SOP PDF.)

## 5. Run the app

```powershell
streamlit run app.py
```

Opens at `http://localhost:8501`. Pick a plant in the sidebar, then ask
things like:

- "What's the startup procedure after a short suspension under 24 hours?"
- "What do I do if there's abnormal water leakage in the turbine?"
- "What's the governor pressure range and what if it's out of range?"
- "Who approves a plant shutdown if it's longer than 24 hours?"

Each answer shows an expandable **Sources** panel with the exact SOP
section number/title and the retrieved excerpt, so an operator can always
verify against the underlying document.

## Notes on tuning

- **Chunking**: `ingest.py` splits on each numbered top-level SOP heading
  (`SECTION_RE`), then sub-splits any section longer than
  `CHUNK_MAX_CHARS` (1200 chars) with a small overlap. This was verified
  against both real PDFs — 21 clean SOP sections detected per plant, TOC
  noise filtered by `MIN_SECTION_CHARS`.
- **Retrieval threshold**: `retriever.py`'s `DEFAULT_DISTANCE_THRESHOLD`
  (cosine distance, 0.55 by default) controls how strict matching is. If
  the assistant too often says "not covered by the SOPs," raise it
  slightly (e.g. 0.65–0.75); if it starts citing irrelevant sections,
  lower it.
- **Memory**: conversation memory is per Streamlit session + plant
  (`thread_id` resets when you switch plants or hit "Clear this chat"),
  via LangGraph's `MemorySaver`. Swap in a SQLite/Postgres checkpointer
  later if you want memory to survive app restarts.
- **Model**: set `VIDULLANKA_MODEL` in `.env` to change the Claude model
  used by the agent (defaults to `claude-sonnet-5`).

## File overview

| File | Purpose |
|---|---|
| `plant_registry.py` | Plant metadata (name, location, SOP PDF path) |
| `ingest.py` | PDF → section-aware chunks → ChromaDB |
| `retriever.py` | Plant-scoped, distance-filtered retrieval |
| `agent.py` | LangGraph ReAct agent + `search_sop` tool + memory |
| `app.py` | Streamlit UI |
| `requirements.txt` | Dependencies |
| `.env.example` | Copy to `.env` and fill in your API key |
