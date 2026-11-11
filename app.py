
"""
app.py
------
Vidullanka IDSS — Plant Operations Assistant (Streamlit UI)

Run with:
    streamlit run app.py
"""

import uuid
import re
from pathlib import Path

import pdfplumber
import streamlit as st

from plant_registry import PLANTS, list_plant_codes
from ingest import reindex_all, reindex_plant, CHROMA_DIR
from retriever import collection_stats
from agent import build_agent, run_agent


st.set_page_config(
    page_title="Vidullanka IDSS — Plant Operations Assistant",
    page_icon="💧",
    layout="wide"
)


# ---------------------------------------------------------------------------
# Layout and automatic light/dark appearance
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    [data-testid="stMainBlockContainer"],
    [data-testid="stAppViewBlockContainer"],
    .main .block-container {
        padding-top: 2.5rem !important;
    }

    [data-testid="stMainBlockContainer"] h1,
    [data-testid="stAppViewBlockContainer"] h1,
    .main .block-container h1 {
        margin-top: 0 !important;
        padding-top: 0 !important;
        line-height: 1.25 !important;
        overflow: visible !important;
    }

    @media (prefers-color-scheme: dark) {
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stSidebar"] {
            background-color: #0e1117 !important;
            color: #fafafa !important;
        }

        [data-testid="stHeader"] {
            background-color: rgba(14, 17, 23, 0.95) !important;
        }

        [data-testid="stAppViewContainer"] *,
        [data-testid="stSidebar"] * {
            color: #fafafa;
        }

        [data-testid="stChatMessage"],
        [data-testid="stChatInput"] {
            background-color: #1b2029 !important;
            border-color: #424956 !important;
        }

        [data-testid="stChatInput"] textarea,
        [data-testid="stTextInput"] input,
        [data-testid="stSelectbox"] > div > div {
            background-color: #1b2029 !important;
            color: #fafafa !important;
        }

        [data-testid="stChatInput"] textarea::placeholder,
        [data-testid="stTextInput"] input::placeholder {
            color: #b7c0cc !important;
        }

        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] code {
            background-color: #252c37 !important;
        }

        [data-testid="stAppViewContainer"] hr,
        [data-testid="stSidebar"] hr {
            border-color: #424956 !important;
        }
    }

    .sop-intro {
        font-size: 13px;
        opacity: 0.75;
        line-height: 1.5;
    }

    .sop-document {
        font-size: 14px;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Sinhala language detection
# ---------------------------------------------------------------------------

def contains_sinhala(text: str) -> bool:
    """Detect Sinhala Unicode characters."""
    return bool(re.search(r"[\u0D80-\u0DFF]", text))


def prepare_agent_prompt(user_prompt: str) -> str:

    if contains_sinhala(user_prompt):

        return f"""
LANGUAGE INSTRUCTION:

The user has asked the question using Sinhala characters.

You MUST:

1. Understand the original Sinhala question.
2. Understand Sinhala-English mixed technical terminology.
3. Answer entirely in natural and clear Sinhala.
4. Keep important engineering terms, equipment names,
   SOP numbers and abbreviations in English where appropriate.
5. Preserve all technical values, numerical limits and units.
6. Explain procedures using numbered steps.
7. Use only the SOP information retrieved for the selected plant.
8. Never invent an operating procedure, technical setting,
   safety limit or approval authority.
9. If the selected SOP does not contain the answer,
   clearly explain this in Sinhala.
10. Do not mix BTO and WMB procedures.

ORIGINAL USER QUESTION:

{user_prompt}

Provide the answer in Sinhala.
"""

    return user_prompt


# ---------------------------------------------------------------------------
# SOP PDF document configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"

SOP_DOCUMENTS = {
    "BTO": {
        "filename": "BTO_SOP.pdf",
        "name": "Batathota Mini Hydro Power Plant",
        "location": "Batathota",
    },
    "WMB": {
        "filename": "WMB_SOP.pdf",
        "name": "Wembiyagoda Mini Hydro Power Plant",
        "location": "Kalawana, Rathnapura",
    },
}


# ---------------------------------------------------------------------------
# Find the actual SOP PDF
# ---------------------------------------------------------------------------

def find_sop_pdf(plant_code: str):

    document = SOP_DOCUMENTS[plant_code]

    expected = document["filename"]

    possible_paths = [
        DATA_DIR / expected,
        DATA_DIR / f"{plant_code}-SOP.pdf",
        DATA_DIR / f"{plant_code}.pdf",
    ]

    for path in possible_paths:
        if path.is_file():
            return path

    # Case-insensitive filename search
    if DATA_DIR.exists():

        for path in DATA_DIR.iterdir():

            if (
                path.is_file()
                and path.suffix.lower() == ".pdf"
                and path.stem.upper().replace("-", "_")
                in {
                    f"{plant_code}_SOP",
                    plant_code,
                }
            ):
                return path

    return None


# ---------------------------------------------------------------------------
# Extract actual SOP topics from PDF documents
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def extract_sop_topics(pdf_path: str, modified_time: float):

    """
    Extract numbered SOP headings from the actual PDF.

    Reads all pages to identify the procedures contained in each
    plant's SOP instead of using manually invented topic lists.
    """

    topics = []
    seen = set()

    heading_pattern = re.compile(
        r"^\s*(\d{1,2})\s*[\.\)]\s*(.+)$",
        re.IGNORECASE
    )

    relevant_words = (
        "standard",
        "procedure",
        "responsibilities",
        "inventory",
        "authority",
    )

    try:

        with pdfplumber.open(pdf_path) as pdf:

            for page in pdf.pages:

                page_text = page.extract_text() or ""

                for raw_line in page_text.splitlines():

                    line = raw_line.strip()

                    if not line:
                        continue

                    match = heading_pattern.match(line)

                    if not match:
                        continue

                    title = match.group(2).strip()

                    # Remove table-of-contents dotted leaders and page numbers.
                    title = re.sub(r"\.{2,}.*$", "", title).strip()

                    title = re.sub(r"\s+", " ", title)

                    if len(title) < 8:
                        continue

                    if not any(
                        word in title.lower()
                        for word in relevant_words
                    ):
                        continue

                    # Remove duplicate headings from repeated PDF pages.
                    clean_title = title.rstrip(" .:-")

                    key = re.sub(
                        r"[^a-z0-9]+",
                        "",
                        clean_title.lower()
                    )

                    if key in seen:
                        continue

                    seen.add(key)

                    topics.append(clean_title)

        return topics, None

    except Exception as e:

        return [], str(e)


# ---------------------------------------------------------------------------
# Generate a question for each extracted SOP heading
# ---------------------------------------------------------------------------

def generate_example_question(topic: str, plant_code: str):

    return (
        f"According to the {plant_code} SOP, "
        f"please explain the procedure for {topic}. "
        f"Include the purpose, prerequisites, responsibilities, "
        f"safety precautions and operating steps where available "
        f"in the selected SOP."
    )


# ---------------------------------------------------------------------------
# Render both plant SOP documents in the sidebar
# ---------------------------------------------------------------------------

def render_sop_documents():

    st.markdown("---")

    st.subheader("📚 SOP Topics & Example Questions")

    st.markdown(
        """
        <div class="sop-intro">
        Explore the actual contents of the BTO and WMB SOP documents.
        Select a procedure to see what you can ask the Operations Assistant.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.caption(
        "Choose a topic to automatically ask the agent."
    )

    for plant_code, document in SOP_DOCUMENTS.items():

        pdf_path = find_sop_pdf(plant_code)

        with st.expander(
            f"📘 {plant_code} — {document['name']}",
            expanded=False
        ):

            st.caption(
                f"Location: {document['location']}"
            )

            if pdf_path is None:

                st.warning(
                    f"{document['filename']} was not found "
                    f"in the data folder."
                )

                continue

            st.caption(
                f"Source document: {pdf_path.name}"
            )

            with st.spinner(
                f"Reading {plant_code} SOP contents..."
            ):

                topics, error = extract_sop_topics(
                    str(pdf_path),
                    pdf_path.stat().st_mtime
                )

            if error:

                st.error(
                    f"Could not read this SOP: {error}"
                )

                continue

            if not topics:

                st.warning(
                    "No numbered SOP headings could be extracted "
                    "from this PDF. Please check its text extraction."
                )

                continue

            st.success(
                f"{len(topics)} SOP topics identified"
            )

            st.markdown("**Procedures included in this document:**")

            for index, topic in enumerate(topics, start=1):

                question = generate_example_question(
                    topic,
                    plant_code
                )

                if st.button(
                    f"{index}. {topic}",
                    key=f"sop_{plant_code}_{index}",
                    use_container_width=True
                ):

                    # Switch to the correct plant before asking.
                    if (
                        st.session_state.selected_plant
                        != plant_code
                    ):

                        st.session_state.selected_plant = plant_code
                        st.session_state.thread_id = str(uuid.uuid4())

                    st.session_state.pending_question = question

                    st.rerun()

            st.markdown("---")

            st.caption(
                "You can also type your own question in Sinhala, "
                "English or Sinhala-English."
            )


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

if "chat_history" not in st.session_state:
    st.session_state.chat_history = {}

if "selected_plant" not in st.session_state:
    st.session_state.selected_plant = list_plant_codes()[0]

if "pending_question" not in st.session_state:
    st.session_state.pending_question = None


def get_history(plant_code: str):

    return st.session_state.chat_history.setdefault(
        plant_code,
        []
    )


@st.cache_resource(show_spinner=False)
def get_agent(plant_code: str):

    return build_agent(plant_code)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:

    st.title("Vidullanka IDSS")

    st.caption("Plant Operations Assistant")

    plant_labels = {
        code: f"{code} — {PLANTS[code]['name']}"
        for code in list_plant_codes()
    }

    selected = st.selectbox(
        "Select plant",
        options=list_plant_codes(),
        format_func=lambda c: plant_labels[c],
        index=list_plant_codes().index(
            st.session_state.selected_plant
        ),
    )

    if selected != st.session_state.selected_plant:

        st.session_state.selected_plant = selected

        st.session_state.thread_id = str(uuid.uuid4())

        st.rerun()

    plant = PLANTS[st.session_state.selected_plant]

    st.markdown(
        f"**{plant['name']}**  \n{plant['location']}"
    )

    # -------------------------------------------------------
    # Actual contents of both SOP PDF documents
    # -------------------------------------------------------

    render_sop_documents()

    # -------------------------------------------------------
    # Existing index status
    # -------------------------------------------------------

    st.divider()

    st.subheader("Index status")

    try:

        stats = collection_stats()

        st.write(
            f"Total chunks indexed: **{stats['total']}**"
        )

        for code, n in stats["per_plant"].items():

            st.write(f"- {code}: {n} chunks")

        index_ready = (
            stats["per_plant"].get(
                st.session_state.selected_plant,
                0
            ) > 0
        )

    except Exception as e:

        st.warning(
            f"Index not built yet ({e})."
        )

        index_ready = False

    col1, col2 = st.columns(2)

    with col1:

        if st.button(
            "Reindex this plant",
            use_container_width=True
        ):

            with st.spinner(
                f"Re-indexing {st.session_state.selected_plant} SOP..."
            ):

                n = reindex_plant(
                    st.session_state.selected_plant
                )

            st.success(f"Indexed {n} chunks.")

            get_agent.clear()

            st.rerun()

    with col2:

        if st.button(
            "Reindex all",
            use_container_width=True
        ):

            with st.spinner("Re-indexing all plants..."):

                counts = reindex_all()

            st.success(f"Indexed: {counts}")

            get_agent.clear()

            st.rerun()

    st.caption(
        f"Chroma DB path: `{CHROMA_DIR}`"
    )

    st.divider()

    if st.button(
        "Clear this chat",
        use_container_width=True
    ):

        st.session_state.chat_history[
            st.session_state.selected_plant
        ] = []

        st.session_state.thread_id = str(uuid.uuid4())

        st.rerun()


# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------

plant = PLANTS[st.session_state.selected_plant]

st.header(
    f"{plant['name']} — Operations Assistant"
)

if not index_ready:

    st.info(
        "This plant hasn't been indexed yet. Put its SOP PDF "
        "in the `data/` folder (see README) and click "
        "**Reindex this plant** in the sidebar."
    )


history = get_history(
    st.session_state.selected_plant
)


# ---------------------------------------------------------------------------
# Display previous chat messages
# ---------------------------------------------------------------------------

for turn in history:

    with st.chat_message(turn["role"]):

        st.markdown(turn["content"])

        if turn.get("sources"):

            with st.expander(
                f"Sources ({len(turn['sources'])})"
            ):

                for s in turn["sources"]:

                    st.markdown(
                        f"**SOP {s['sop_number']}: "
                        f"{s['sop_title']}**  \n"
                        f"*{s['source_file']} · "
                        f"similarity distance {s['distance']}*"
                    )

                    st.text(
                        s["text"][:600]
                        + (
                            "..."
                            if len(s["text"]) > 600
                            else ""
                        )
                    )

                    st.markdown("---")


# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------

pending_question = st.session_state.pending_question

prompt = st.chat_input(
    f"Ask about {plant['code']} procedures, safety, or equipment..."
)

# Use a question selected from the SOP sidebar.
if pending_question is not None:

    prompt = pending_question

    st.session_state.pending_question = None


# ---------------------------------------------------------------------------
# Process user question
# ---------------------------------------------------------------------------

if prompt:

    history.append(
        {
            "role": "user",
            "content": prompt,
            "sources": None
        }
    )

    with st.chat_message("user"):

        st.markdown(prompt)

    with st.chat_message("assistant"):

        if not index_ready:

            answer_text = (
                "This plant hasn't been indexed yet — "
                "please reindex it from the sidebar first."
            )

            sources = []

            st.markdown(answer_text)

        else:

            with st.spinner("Checking the SOPs..."):

                agent = get_agent(
                    st.session_state.selected_plant
                )

                agent_prompt = prepare_agent_prompt(
                    prompt
                )

                result = run_agent(
                    agent,
                    agent_prompt,
                    thread_id=st.session_state.thread_id
                )

            answer_text = result["answer"]

            sources = result["sources"]

            st.markdown(answer_text)

            if sources:

                with st.expander(
                    f"Sources ({len(sources)})"
                ):

                    for s in sources:

                        st.markdown(
                            f"**SOP {s['sop_number']}: "
                            f"{s['sop_title']}**  \n"
                            f"*{s['source_file']} · "
                            f"similarity distance {s['distance']}*"
                        )

                        st.text(
                            s["text"][:600]
                            + (
                                "..."
                                if len(s["text"]) > 600
                                else ""
                            )
                        )

                        st.markdown("---")

    history.append(
        {
            "role": "assistant",
            "content": answer_text,
            "sources": sources
        }
    )
