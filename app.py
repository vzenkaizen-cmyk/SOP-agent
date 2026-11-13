"""
app.py
------
Vidullanka IDSS — Plant Operations Assistant

Run:
    streamlit run app.py
"""

import uuid
import re
import streamlit as st

from plant_registry import PLANTS, list_plant_codes
from ingest import reindex_all, reindex_plant, CHROMA_DIR
from retriever import collection_stats
from agent import build_agent, run_agent


st.set_page_config(
    page_title="Vidullanka IDSS — Plant Operations Assistant",
    page_icon="💧",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Sinhala:wght@400;500;600;700&display=swap');

    html, body, [class*="css"], button, input, textarea {
        font-family: "Noto Sans Sinhala", "Iskoola Pota", "Nirmala UI",
                     "Segoe UI", sans-serif !important;
    }

    /* Follow the active Streamlit theme, including dark-theme laptops. */
    :root {
        color-scheme: light dark;
    }

    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stSidebar"],
    [data-testid="stHeader"] {
        background-color: var(--background-color) !important;
        color: var(--text-color) !important;
    }

    [data-testid="stAppViewContainer"] *,
    [data-testid="stSidebar"] * {
        color: inherit;
    }

    [data-testid="stChatMessage"],
    [data-testid="stTextArea"] textarea,
    [data-testid="stTextInput"] input,
    [data-testid="stSelectbox"] [data-baseweb="select"] > div,
    [data-testid="stExpander"] {
        background-color: var(--secondary-background-color) !important;
        color: var(--text-color) !important;
        border-color: rgba(128, 128, 128, 0.45) !important;
    }

    [data-testid="stTextArea"] textarea,
    [data-testid="stTextInput"] input {
        caret-color: var(--text-color) !important;
    }

    [data-testid="stButton"] button,
    [data-testid="stDownloadButton"] button {
        color: var(--text-color) !important;
        border-color: rgba(128, 128, 128, 0.5) !important;
    }

    [data-testid="stButton"] button:hover,
    [data-testid="stDownloadButton"] button:hover {
        border-color: var(--primary-color) !important;
        color: var(--primary-color) !important;
    }

    [data-testid="stMainBlockContainer"],
    [data-testid="stAppViewBlockContainer"],
    .main .block-container {
        padding-top: 2rem !important;
    }

    [data-testid="stMainBlockContainer"] h1,
    [data-testid="stAppViewBlockContainer"] h1,
    .main .block-container h1 {
        margin-top: 0 !important;
        padding-top: 0 !important;
        line-height: 1.25 !important;
    }

    [data-testid="stSidebar"] {
        min-width: 300px;
        max-width: 340px;
    }

    .sop-help {
        font-size: 0.86rem;
        line-height: 1.45;
        color: var(--text-color);
        opacity: 0.78;
    }

    .welcome-card {
        padding: 1.1rem 1.2rem;
        border: 1px solid rgba(128, 128, 128, 0.25);
        border-radius: 12px;
        margin: 0.8rem 0 1rem 0;
        background: rgba(128, 128, 128, 0.045);
    }

    /* Theme-aware controls: follows Streamlit light or dark theme. */
    [data-testid="stChatMessage"],
    [data-testid="stTextArea"] textarea,
    [data-testid="stTextInput"] input {
        background: var(--secondary-background-color) !important;
        color: var(--text-color) !important;
        border-color: rgba(128, 128, 128, 0.45) !important;
    }

    [data-testid="stTextArea"] textarea::placeholder,
    [data-testid="stTextInput"] input::placeholder {
        color: var(--text-color) !important;
        opacity: 0.65;
    }

    [data-testid="stButton"] button {
        color: var(--text-color);
        border-color: rgba(128, 128, 128, 0.45);
    }

    .sinhala-keyboard-note {
        color: var(--text-color);
        opacity: 0.75;
        font-size: 0.85rem;
    }

    /* Hide only the virtual Sinhala keyboard on phone-sized screens. */
    @media screen and (max-width: 768px) {
        .st-key-sinhala_keyboard_section {
            display: none !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# SOP contents
# These titles are taken from the supplied BTO and WMB SOP contents pages.
# No PDF parsing package is required to display them.
# ---------------------------------------------------------------------------

BTO_TOPICS = [
    ("SOP-001", "Startup, Stop and Emergency Stop Procedure", "Emergency & Machine Operation"),
    ("SOP-002", "Startup after short-term suspension (within 24 hours)", "Machine Operation"),
    ("SOP-003", "Power Transformer Testing and Cleaning", "Electrical Equipment & Maintenance"),
    ("SOP-004", "HVCB Testing and Cleaning", "Electrical Equipment & Maintenance"),
    ("SOP-005", "CT/PT Cleaning", "Electrical Equipment & Maintenance"),
    ("SOP-006", "Intake Gate Operation", "Water Management & Hydraulic Systems"),
    ("SOP-007", "Forebay Sand Removing", "Water Management & Hydraulic Systems"),
    ("SOP-008", "Sand Gate Operation", "Water Management & Hydraulic Systems"),
    ("SOP-009", "MIV Operation", "Water Management & Hydraulic Systems"),
    ("SOP-010", "Cooling Operation", "Machine Operation"),
    ("SOP-011", "Governor Operation", "Machine Operation"),
    ("SOP-012", "Crane Operation", "Machine Operation"),
    ("SOP-013", "Trash Machine Operation", "Water Management & Hydraulic Systems"),
    ("SOP-014", "Water Leakage in Penstock", "Emergency & Safety Procedures"),
    ("SOP-015", "Abnormal Water Leakage in Turbine", "Emergency & Safety Procedures"),
    ("SOP-016", "Water Leakage to Powerhouse due to Flood", "Emergency & Safety Procedures"),
    ("SOP-017", "Electrical Fire", "Emergency & Safety Procedures"),
]

WMB_TOPICS = [
    ("SOP-001", "Function Responsibilities", "Management, Approvals & Documentation"),
    ("SOP-002", "Location Responsibilities", "Management, Approvals & Documentation"),
    ("SOP-003", "Lockout Tagout System", "Electrical Equipment & Maintenance"),
    ("SOP-004", "Startup, Stop and Emergency Stop Procedure", "Emergency & Machine Operation"),
    ("SOP-005", "Startup after short-term suspension (within 24 hours)", "Machine Operation"),
    ("SOP-006", "Power Transformer Testing and Cleaning", "Electrical Equipment & Maintenance"),
    ("SOP-007", "HVCB Testing and Cleaning", "Electrical Equipment & Maintenance"),
    ("SOP-008", "CT/PT Cleaning", "Electrical Equipment & Maintenance"),
    ("SOP-009", "Intake Gate Operation", "Water Management & Hydraulic Systems"),
    ("SOP-010", "Forebay Sand Removing", "Water Management & Hydraulic Systems"),
    ("SOP-011", "Sand Gate Operation", "Water Management & Hydraulic Systems"),
    ("SOP-012", "MIV Operation", "Water Management & Hydraulic Systems"),
    ("SOP-013", "Cooling Operation", "Machine Operation"),
    ("SOP-014", "Governor Operation", "Machine Operation"),
    ("SOP-015", "Crane Operation", "Machine Operation"),
    ("SOP-016", "Trash Machine Operation", "Water Management & Hydraulic Systems"),
    ("SOP-017", "Water Leakage in Penstock", "Emergency & Safety Procedures"),
    ("SOP-018", "Abnormal Water Leakage in Turbine", "Emergency & Safety Procedures"),
    ("SOP-019", "Water Leakage to Powerhouse due to Flood", "Emergency & Safety Procedures"),
    ("SOP-020", "Electrical Fire", "Emergency & Safety Procedures"),
    ("SOP-021", "Channel Inspection", "Water Management & Hydraulic Systems"),
    ("SOP-022", "Authority Level for Plant Shutdown", "Management, Approvals & Documentation"),
    ("SOP-023", "Inventory Process", "Management, Approvals & Documentation"),
]

SOP_TOPICS = {
    "BTO": BTO_TOPICS,
    "WMB": WMB_TOPICS,
}

SOP_METADATA = {
    "BTO": {
        "owner": "Batathota MHPP (BTO)",
        "pages": "34",
        "last_reviewed": "25/11/2024",
        "note": "The supplied BTO SOP lists SOP-001 to SOP-017.",
    },
    "WMB": {
        "owner": "Wembiyagoda MHPP (WMB)",
        "pages": "46",
        "note": (
            "SOP-001 and SOP-002: implementation 01/01/2019; "
            "last reviewed 01/01/2020. Operational SOPs: "
            "implementation 01/01/2023; last reviewed 25/11/2024."
        ),
    },
}

ALL_PLANT_MODE = "BTO_WMB"


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

if "chat_history" not in st.session_state:
    st.session_state.chat_history = {}

if "default_scope_initialized" not in st.session_state:
    available_plant_codes = list_plant_codes()
    st.session_state.selected_plant = (
        ALL_PLANT_MODE
        if all(code in available_plant_codes for code in ("BTO", "WMB"))
        else available_plant_codes[0]
    )
    st.session_state.default_scope_initialized = True

if "pending_question" not in st.session_state:
    st.session_state.pending_question = None


def get_history(plant_code):
    return st.session_state.chat_history.setdefault(plant_code, [])


@st.cache_resource(show_spinner=False)
def get_agent(plant_code):
    return build_agent(plant_code)


def detect_plant_scope(question, fallback_scope=ALL_PLANT_MODE):
    """Detect BTO, WMB, or both from the user's question automatically."""
    question_lower = question.lower()

    mentions_bto = bool(
        re.search(r"\bbto\b", question_lower)
        or "batathota" in question_lower
    )
    mentions_wmb = bool(
        re.search(r"\bwmb\b", question_lower)
        or "wembiyagoda" in question_lower
    )

    if mentions_bto and mentions_wmb:
        return ALL_PLANT_MODE
    if "both plants" in question_lower or "overall" in question_lower:
        return ALL_PLANT_MODE
    if mentions_bto:
        return "BTO"
    if mentions_wmb:
        return "WMB"

    return fallback_scope


# ---------------------------------------------------------------------------
# Question builder
# ---------------------------------------------------------------------------

def make_example_question(plant_code, sop_number, topic):
    """Build a focused question that retrieves the exact clicked SOP section."""
    plant_name = PLANTS[plant_code]["name"]

    # Keep the exact plant, SOP number and title at the beginning of the query.
    # This makes the clicked navigation topic much easier for semantic retrieval
    # to match than a broad request for a "complete procedure".
    if sop_number in ("SOP-001", "SOP-002") and plant_code == "WMB":
        return (
            f"{plant_code} ({plant_name}) — {sop_number}: {topic}. "
            f"Find and use the exact {sop_number} section titled '{topic}' "
            f"in the {plant_code} SOP. Explain the responsibilities, roles, "
            "and requirements stated in that section. Search the supplied "
            "SOP content for this SOP number and title before answering. "
            "Answer fully in English and use only the supplied SOP."
        )

    return (
        f"{plant_code} ({plant_name}) — {sop_number}: {topic}. "
        f"Find and use the exact {sop_number} section titled '{topic}' "
        f"in the {plant_code} plant SOP. Retrieve the relevant content for "
        f"'{topic}' and explain what that section actually says, including "
        "its purpose, scope, prerequisites, responsibilities, safety "
        "precautions and operational steps wherever these are stated. "
        "Search by both the SOP number and the exact topic title. Do not "
        "substitute another SOP or another plant's procedure. Do not claim "
        "the section is unavailable until the supplied SOP content has been "
        "checked for this SOP number, title and close wording. If the section "
        "is genuinely absent, clearly state that. Answer fully in English "
        "using only the supplied SOP content; do not invent missing steps."
    )


def append_question_text(value):
    """Append a Sinhala character or other key to the question input."""
    st.session_state.question_input = (
        st.session_state.get("question_input", "") + value
    )


def delete_question_character():
    """Delete the last Unicode character from the question input."""
    current = st.session_state.get("question_input", "")
    st.session_state.question_input = current[:-1]


def clear_question_input():
    st.session_state.question_input = ""


def submit_typed_question():
    """Queue the typed question before the next Streamlit rerun."""
    question = st.session_state.get("question_input", "").strip()
    if question:
        st.session_state.pending_question = question
        st.session_state.question_input = ""


def select_sop_question(plant_code, question):
    """
    Queue a topic question and switch plants if required.

    Do not assign to the selectbox widget key here. Streamlit does not allow
    changing a widget's session-state value after that widget has been
    instantiated during the current run.
    """
    if plant_code != st.session_state.selected_plant:
        st.session_state.selected_plant = plant_code
        st.session_state.thread_id = str(uuid.uuid4())

    st.session_state.pending_question = question
    st.rerun()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("Vidullanka IDSS")
    st.caption("Plant Operations Assistant")

    plant_codes = list_plant_codes()
    selection_options = list(plant_codes)
    if "BTO" in plant_codes and "WMB" in plant_codes:
        selection_options.append(ALL_PLANT_MODE)

    plant_labels = {
        code: f"{code} — {PLANTS[code]['name']}"
        for code in plant_codes
    }
    plant_labels[ALL_PLANT_MODE] = "BTO + WMB — Overall / Both Plants"

    # Use a plant-specific key so a topic click can switch plants safely.
    # This avoids changing a widget's state after it has been instantiated.
    selector_key = f"plant_selector_{st.session_state.selected_plant}"

    selected = st.selectbox(
        "Select plant",
        options=selection_options,
        format_func=lambda code: plant_labels[code],
        index=selection_options.index(st.session_state.selected_plant)
        if st.session_state.selected_plant in selection_options else 0,
        key=selector_key,
    )

    if selected != st.session_state.selected_plant:
        st.session_state.selected_plant = selected
        st.session_state.thread_id = str(uuid.uuid4())
        st.rerun()

    if st.session_state.selected_plant == ALL_PLANT_MODE:
        st.markdown(
            "**BTO — Batathota MHPP**  \\n"
            "**WMB — Wembiyagoda MHPP**  \\n"
            "Combined hydro plant knowledge"
        )
    else:
        current_plant = PLANTS[st.session_state.selected_plant]
        st.markdown(
            f"**{current_plant['name']}**  \\n"
            f"{current_plant.get('location', '')}"
        )

    # -------------------------------------------------------
    # SOP topics: compact, grouped, and no runtime PDF parser
    # -------------------------------------------------------

    st.divider()
    st.subheader("📚 SOP Topics & Example Questions")

    st.markdown(
        '<div class="sop-help">Not sure what to ask? '
        'Choose a topic below to send an example question to the agent. '
        'Questions can be asked in Sinhala, English or both.</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "BTO and WMB are searched together by default. "
        "Choose an individual plant only when you want a plant-specific answer."
    )

    for code in plant_codes:
        topics = SOP_TOPICS.get(code, [])
        metadata = SOP_METADATA.get(code)

        with st.expander(
            f"📘 {code} — {PLANTS[code]['name']}",
            expanded=(code == st.session_state.selected_plant),
        ):
            if metadata:
                st.caption(
                    f"Document owner: {metadata['owner']} · "
                    f"{metadata['pages']} pages"
                )
                if code == "BTO":
                    st.caption(
                        f"Last reviewed: {metadata['last_reviewed']}"
                    )
                st.caption(metadata["note"])

            if topics:
                categories = []
                for _, _, category in topics:
                    if category not in categories:
                        categories.append(category)

                for category in categories:
                    st.markdown(f"**{category}**")

                    for sop_number, topic, topic_category in topics:
                        if topic_category != category:
                            continue

                        question = make_example_question(
                            code, sop_number, topic
                        )

                        if st.button(
                            f"{sop_number}: {topic}",
                            key=f"topic_{code}_{sop_number}",
                            use_container_width=True,
                        ):
                            select_sop_question(code, question)
            else:
                st.info(
                    "The SOP topic list has not yet been configured "
                    "for this plant. Its indexed SOP can still be queried "
                    "after selecting the plant."
                )

    # -------------------------------------------------------
    # Index status and existing controls
    # -------------------------------------------------------

    st.divider()
    st.subheader("Index status")

    try:
        stats = collection_stats()
        st.write(f"Total chunks indexed: **{stats['total']}**")

        for code, count in stats["per_plant"].items():
            st.write(f"- {code}: {count} chunks")

        if st.session_state.selected_plant == ALL_PLANT_MODE:
            index_ready = all(
                stats["per_plant"].get(code, 0) > 0
                for code in ("BTO", "WMB")
            )
        else:
            index_ready = (
                stats["per_plant"].get(
                    st.session_state.selected_plant, 0
                ) > 0
            )

    except Exception as exc:
        st.warning(f"Index not built yet ({exc}).")
        index_ready = False

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Reindex this plant", use_container_width=True):
            selected_scope = st.session_state.selected_plant
            with st.spinner(f"Re-indexing {selected_scope} SOP..."):
                if selected_scope == ALL_PLANT_MODE:
                    counts = {
                        code: reindex_plant(code)
                        for code in ("BTO", "WMB")
                    }
                    count = sum(counts.values())
                else:
                    count = reindex_plant(selected_scope)

            st.success(f"Indexed {count} chunks.")
            get_agent.clear()
            st.rerun()

    with col2:
        if st.button("Reindex all", use_container_width=True):
            with st.spinner("Re-indexing all plants..."):
                counts = reindex_all()

            st.success(f"Indexed: {counts}")
            get_agent.clear()
            st.rerun()

    st.caption(f"Chroma DB path: `{CHROMA_DIR}`")

    st.divider()

    if st.button("Clear this chat", use_container_width=True):
        st.session_state.chat_history[
            st.session_state.selected_plant
        ] = []
        st.session_state.thread_id = str(uuid.uuid4())
        st.rerun()


# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------

# If the pending question names a plant, automatically use that plant's
# knowledge base. Questions mentioning both plants use the combined index.
if st.session_state.pending_question:
    detected_scope = detect_plant_scope(
        st.session_state.pending_question,
        st.session_state.selected_plant,
    )
    if detected_scope != st.session_state.selected_plant:
        st.session_state.selected_plant = detected_scope
        st.session_state.thread_id = str(uuid.uuid4())

plant_code = st.session_state.selected_plant
if plant_code == ALL_PLANT_MODE:
    plant = {
        "name": "BTO + WMB — Overall Hydro Operations",
        "location": "Batathota MHPP and Wembiyagoda MHPP",
    }
else:
    plant = PLANTS[plant_code]
history = get_history(plant_code)

st.header(f"{plant['name']} — Operations Assistant")

if not index_ready:
    if plant_code == ALL_PLANT_MODE:
        st.info(
            "One or both plant SOP indexes are not ready. Add the BTO and WMB "
            "SOP PDFs to the `data/` folder and click **Reindex this plant**."
        )
    else:
        st.info(
            "This plant has not been indexed yet. Add its SOP PDF to the "
            "`data/` folder and click **Reindex this plant** in the sidebar."
        )

# Welcome screen prevents a blank main area before the first question.
if not history and st.session_state.pending_question is None:
    st.markdown(
        """
        <div class="welcome-card">
            <h3>Welcome to Vidullanka IDSS</h3>
            <p>
                Ask questions about plant operations, safety, equipment,
                maintenance, water management and responsibilities.
            </p>
            <p>
                You can type in <b>English</b>, <b>සිංහල</b>, or
                <b>සිංහල + English</b>. You can also select an SOP topic
                from the left navigation panel.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("**Example questions**")

    examples = [
        (
            "How do I stop the machine during an emergency?",
            "How should the machine be stopped during an emergency? "
            "Explain the applicable SOP steps fully in English.",
        ),
        (
            "How do I operate the MIV valve?",
            "Explain the MIV valve opening and closing procedure "
            "according to the selected plant SOP, in English.",
        ),
        (
            "What are the prerequisites for crane operation?",
            "What are the prerequisites and safety precautions "
            "for crane operation according to the selected plant SOP? "
            "Answer fully in English.",
        ),
    ]

    example_cols = st.columns(3)
    for index, (label, question) in enumerate(examples):
        with example_cols[index]:
            if st.button(label, use_container_width=True):
                st.session_state.pending_question = question
                st.rerun()


# ---------------------------------------------------------------------------
# Previous conversation
# ---------------------------------------------------------------------------

for turn in history:
    with st.chat_message(turn["role"]):
        st.markdown(turn["content"])

        if turn.get("sources"):
            with st.expander(f"Sources ({len(turn['sources'])})"):
                for source in turn["sources"]:
                    st.markdown(
                        f"**SOP {source['sop_number']}: "
                        f"{source['sop_title']}**  \n"
                        f"*{source['source_file']} · "
                        f"similarity distance {source['distance']}*"
                    )
                    source_text = source["text"]
                    st.text(
                        source_text[:600]
                        + ("..." if len(source_text) > 600 else "")
                    )
                    st.markdown("---")


# ---------------------------------------------------------------------------
# Chat input and question processing
# ---------------------------------------------------------------------------

pending_question = st.session_state.pending_question

prompt = None
if pending_question is not None:
    prompt = pending_question
    st.session_state.pending_question = None


if prompt:
    history.append(
        {"role": "user", "content": prompt, "sources": None}
    )

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        if True:
            # English-only question -> English-only answer
            # Sinhala-only question -> Sinhala-only answer
            # Mixed Sinhala + English question -> bilingual answer
            sinhala_chars = any(
                "\u0D80" <= char <= "\u0DFF" for char in prompt
            )
            english_chars = any(
                ("A" <= char <= "Z") or ("a" <= char <= "z")
                for char in prompt
            )

            if sinhala_chars and english_chars:
                language_instruction = (
                    "The user asked in both Sinhala and English. "
                    "Answer bilingually: provide the explanation in Sinhala "
                    "and English, keeping the same meaning and all important "
                    "SOP steps in both languages. Use clear, grammatically "
                    "correct Sinhala and clear English."
                )
            elif sinhala_chars:
                language_instruction = (
                    "The user asked in Sinhala only. Answer only in clear, "
                    "grammatically correct Sinhala. Do not add an English "
                    "translation or English summary. Keep technical terms "
                    "in English only when necessary for accuracy."
                )
            else:
                language_instruction = (
                    "The user asked in English only. Answer only in clear, "
                    "complete English. Do not add Sinhala translations or "
                    "Sinhala summaries."
                )

            agent_question = (
                prompt
                + "\n\n"
                + language_instruction
                + (
                    " The selected scope includes both BTO and WMB. "
                    "Search both plants for overall questions and comparisons, "
                    "and clearly identify each plant's values. "
                    if plant_code == ALL_PLANT_MODE else
                    " Use the selected plant's SOP and technical details. "
                )
                + "Use only the supplied workbook and relevant SOP sources. "
                "Do not invent procedures or technical values."
            )

            try:
                with st.spinner("Checking the SOPs..."):
                    agent = get_agent(plant_code)
                    result = run_agent(
                        agent,
                        agent_question,
                        thread_id=st.session_state.thread_id,
                    )

                answer_text = result.get(
                    "answer",
                    "The agent did not return an answer."
                )
                # Hide redundant workbook/SOP source-attribution lines in the
                # answer while keeping the existing source details available.
                answer_text = re.sub(
                    r"(?im)^\s*source\s*:\s*.*(?:\n|$)",
                    "",
                    answer_text,
                ).strip()
                sources = result.get("sources", []) or []

                st.markdown(answer_text)

                if sources:
                    with st.expander(f"Sources ({len(sources)})"):
                        for source in sources:
                            st.markdown(
                                f"**SOP {source['sop_number']}: "
                                f"{source['sop_title']}**  \n"
                                f"*{source['source_file']} · "
                                f"similarity distance {source['distance']}*"
                            )
                            source_text = source["text"]
                            st.text(
                                source_text[:600]
                                + ("..." if len(source_text) > 600 else "")
                            )
                            st.markdown("---")

            except Exception as exc:
                answer_text = (
                    "An error occurred while processing your question. "
                    f"Please check the agent configuration. Details: {exc}"
                )
                sources = []
                st.error(answer_text)

    history.append(
        {
            "role": "assistant",
            "content": answer_text,
            "sources": sources,
        }
    )

# ---------------------------------------------------------------------------
# Sinhala keyboard and bottom-anchored question area
# ---------------------------------------------------------------------------

# Keep the Sinhala keyboard at the bottom so it remains visible after answers.
with st.container(key="sinhala_keyboard_section"):
    with st.expander("සිංහල යතුරුපුවරුව / Sinhala Keyboard", expanded=False):
        st.markdown(
            '<div class="sinhala-keyboard-note">'
            'අවශ්‍ය අකුරු තෝරන්න. අකුරු ප්‍රශ්න කොටුවට එක් වේ. '
            'Select Sinhala characters to insert them into the question box.'
            '</div>',
            unsafe_allow_html=True,
        )

        sinhala_keyboard_rows = [
            list("අආඇඈඉඊඋඌඑඒඓඔඕඖ"),
            list("කඛගඝඞඟචඡජඣඤ"),
            list("ටඨඩඪණඬතථදධනඳ"),
            list("පඵබභමඹයරලව"),
            list("ශෂසහළෆ"),
            list("ාැෑිීුූෘෙේෛොෝෞංඃ්"),
        ]

        for row_index, keyboard_row in enumerate(sinhala_keyboard_rows):
            key_columns = st.columns(min(10, len(keyboard_row)))
            for key_index, character in enumerate(keyboard_row):
                with key_columns[key_index % len(key_columns)]:
                    st.button(
                        character,
                        key=f"sinhala_key_{row_index}_{key_index}",
                        use_container_width=True,
                        on_click=append_question_text,
                        args=(character,),
                    )

        utility_columns = st.columns(3)
        with utility_columns[0]:
            st.button(
                "Space",
                key="sinhala_key_space",
                use_container_width=True,
                on_click=append_question_text,
                args=(" ",),
            )
        with utility_columns[1]:
            st.button(
                "⌫ Backspace",
                key="sinhala_key_backspace",
                use_container_width=True,
                on_click=delete_question_character,
            )
        with utility_columns[2]:
            st.button(
                "Clear",
                key="sinhala_key_clear",
                use_container_width=True,
                on_click=clear_question_input,
            )



question_scope_label = (
    "BTO and WMB"
    if plant_code == ALL_PLANT_MODE
    else plant_code
)

st.text_area(
    f"Ask about {question_scope_label} plant details, procedures, safety, or equipment...",
    key="question_input",
    height=100,
    placeholder=(
        "Type your question in English or Sinhala. "
        "Use the Sinhala keyboard above if your device does not have "
        "a Sinhala keyboard installed."
    ),
)

st.button(
    "Send question",
    key="send_typed_question",
    type="primary",
    on_click=submit_typed_question,
)

