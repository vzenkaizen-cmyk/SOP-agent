
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

import streamlit as st

from plant_registry import PLANTS, list_plant_codes
from ingest import reindex_all, reindex_plant, CHROMA_DIR
from retriever import collection_stats
from agent import build_agent, run_agent

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


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


# ---------------------------------------------------------------------------
# Plant-specific agent instructions
# ---------------------------------------------------------------------------

def prepare_agent_prompt(user_prompt: str, plant_code: str) -> str:

    plant_name = PLANTS[plant_code]["name"]

    if contains_sinhala(user_prompt):
        language_instruction = """
        Answer entirely in grammatically correct, natural Sinhala.

        Understand Sinhala-only and Sinhala-English mixed questions.

        Retain important English technical terminology, equipment names,
        abbreviations and engineering terms where appropriate.

        Never reproduce corrupted Sinhala OCR text from a PDF.
        Understand the original English meaning and explain it in
        correct Sinhala.
        """
    else:
        language_instruction = """
        Answer in clear, professional English.
        """

    common_instructions = """
VIDULLANKA IDSS - PLANT OPERATIONS ASSISTANT

SELECTED PLANT:
{plant_code} - {plant_name}

LANGUAGE INSTRUCTIONS:
{language_instruction}

IMPORTANT RULES:

1. Use the retrieved SOP documents belonging to the selected plant.

2. Understand Sinhala, English and Sinhala-English mixed questions.

3. Answer in the language used by the user.

4. If the user asks in Sinhala, use correct Sinhala grammar,
   spelling and engineering terminology.

5. Do not copy corrupted Sinhala characters or OCR errors
   from the original PDF.

6. Preserve technical values, numerical limits, units,
   equipment names and SOP references exactly as documented.

7. Do not invent procedures, approval authorities, technical
   settings, maintenance frequencies or safety instructions.

8. Do not combine BTO and WMB procedures.

9. Do not assume that procedures and responsibilities are
   identical across different plants.

10. If the requested information is unavailable in the
    selected plant's SOP, clearly state that it is not
    specified in the available document.

11. If the question concerns another plant, ask the user
    to select that plant first.

12. Use the following Sinhala terminology:

    Responsibilities = වගකීම්
    Prerequisites = පූර්ව අවශ්‍යතා
    Scope = විෂය පථය
    Purpose = අරමුණ
    Procedure = ක්‍රියාපටිපාටිය
    Operation = මෙහෙයුම් කටයුතු
    Engineering Department = ඉංජිනේරු දෙපාර්තමේන්තුව
    Operations Department = මෙහෙයුම් දෙපාර්තමේන්තුව
    Head Office = ප්‍රධාන කාර්යාලය
    Supervisor = අධීක්ෂක
    Operator = ක්‍රියාකරු
    Helper = සහායක සේවකයා
    Area Engineer = ප්‍රාදේශීය ඉංජිනේරු
    Operations Manager = මෙහෙයුම් කළමනාකරු
    Maintenance = නඩත්තු කටයුතු
    Emergency Shutdown = හදිසි නැවැත්වීම
    Normal Shutdown = සාමාන්‍ය නැවැත්වීම
    Lockout Tagout = බලශක්ති හුදකලා කිරීම සහ අගුලු දැමීමේ ක්‍රමවේදය

13. When explaining a procedure, use these sections
    where the source provides the information:

    - අරමුණ (Purpose)
    - විෂය පථය (Scope)
    - පූර්ව අවශ්‍යතා (Prerequisites)
    - වගකීම් (Responsibilities)
    - ආරක්ෂක පියවර (Safety Precautions)
    - ක්‍රියාපටිපාටිය (Procedure)
    - වාර්තා සහ ලේඛන (Records)

14. Explain only the steps supported by the retrieved SOP.
    Do not create missing steps to complete an answer.

15. Do not confuse general company responsibilities with
    responsibilities assigned to a particular plant procedure.
"""

    if plant_code == "WMB":

        plant_specific_instructions = """
ADDITIONAL WMB SOP INSTRUCTIONS:

The WMB SOP contains Function Responsibilities and
Location Responsibilities documents.

Section 3 - Prerequisites:

Use the following accurate Sinhala explanation:

"සියලුම වගකීම් එක් එක් බලාගාරයට අදාළ වන අතර,
ප්‍රධාන කාර්යාලයේ මෙහෙයුම් දෙපාර්තමේන්තුව විසින්
ලබා දී ඇති ආකෘති පමණක් භාවිත කළ යුතුය."

Section 4 - Responsibilities:

The original English text states:

"Engineering department directly responsible for the
operation procedures and all helpers, operators and
supervisor will be responsible with the operation."

Use the following accurate Sinhala explanation:

"මෙහෙයුම් ක්‍රියාපටිපාටි සම්බන්ධයෙන් ඉංජිනේරු
දෙපාර්තමේන්තුව සෘජුවම වගකිව යුතුය.
මෙහෙයුම් කටයුතු සම්බන්ධයෙන් සියලුම සහායක
සේවකයින්, ක්‍රියාකරුවන් සහ අධීක්ෂකවරුන්
වගකිව යුතුය."

The Function Responsibilities document identifies
functions involving direct workers, supervisors,
Area Engineers, Operations Manager and service departments.

The Location Responsibilities document identifies
work locations and the relevant persons responsible.

Use the actual function and location tables when answering.
Do not invent names or assign responsibility to a person
when the document does not specify that information.

The WMB document also refers to guidelines provided
by the Operations Department - HOF.

Apply these WMB instructions only when answering
questions about WMB.
"""

    else:
        plant_specific_instructions = ""

    return f"""
{common_instructions.format(
    plant_code=plant_code,
    plant_name=plant_name,
    language_instruction=language_instruction
)}

{plant_specific_instructions}

ORIGINAL USER QUESTION:

{user_prompt}

Answer based on the retrieved SOP content.
"""


# ---------------------------------------------------------------------------
# SOP document configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"

SOP_METADATA = {

    "BTO": {
        "filenames": [
            "BTO SOP Final.pdf",
            "BTO_SOP.pdf",
            "BTO-SOP.pdf",
            "BTO.pdf",
        ],
        "owner": "Batathota MHPP (BTO)",
        "pages": "34 pages",
        "review_date": "25/11/2024",
        "implementation_date": "Not specified in the document",
        "references": [
            "VLL\\BTO\\SOP-001 to SOP-017"
        ],
        "description": (
            "Batathota Mini Hydro Power Plant Standard Operating "
            "Procedures. Includes startup, stopping, emergency stopping, "
            "short-term restart, transformer testing and cleaning, "
            "HVCB, CT/PT, intake gate, forebay sand removal, sand gate, "
            "MIV, cooling, governor, crane, trash machine, penstock "
            "leakage, turbine leakage and flood-related procedures."
        ),
    },

    "WMB": {
        "filenames": [
            "WMB_SOP.pdf",
            "WMB SOP.pdf",
            "WMB-SOP.pdf",
            "WMB.pdf",
        ],
        "owner": "Wembiyagoda MHPP (WMB)",
        "pages": "46 pages",
        "review_date": (
            "Function and Location Responsibilities: 01/01/2020. "
            "Operational SOP review dates vary by document."
        ),
        "implementation_date": (
            "Function and Location Responsibilities: 01/01/2019. "
            "Operational SOP implementation dates vary by document."
        ),
        "references": [
            "VLL\\WMB\\SOP-001 - Function Responsibilities",
            "VLL\\WMB\\SOP-002 - Location Responsibilities",
            "VLL\\WMB\\SOP-003 onwards - Operational Procedures",
        ],
        "description": (
            "Wembiyagoda Mini Hydro Power Plant SOP. Includes Function "
            "Responsibilities, Location Responsibilities and operating "
            "procedures covering Lockout Tagout, startup, shutdown, "
            "emergency shutdown, short-term restart, transformer, HVCB, "
            "CT/PT, intake gate, forebay sand removal, sand gate, MIV, "
            "cooling, governor, crane, trash machine, penstock leakage, "
            "turbine leakage, flooding, electrical fire, channel "
            "inspection, shutdown authority and inventory."
        ),
    },
}


# Include all registered plants without assuming that they
# have the same SOP content.

SOP_DOCUMENTS = {}

for code in list_plant_codes():

    metadata = SOP_METADATA.get(code, {})

    SOP_DOCUMENTS[code] = {
        "name": PLANTS[code]["name"],
        "location": PLANTS[code].get("location", ""),
        "filenames": metadata.get(
            "filenames",
            [
                f"{code}_SOP.pdf",
                f"{code} SOP Final.pdf",
                f"{code}-SOP.pdf",
                f"{code}.pdf",
            ]
        ),
        "owner": metadata.get(
            "owner",
            "Refer to the original SOP"
        ),
        "pages": metadata.get(
            "pages",
            "Refer to the original SOP"
        ),
        "review_date": metadata.get(
            "review_date",
            "Refer to individual SOP"
        ),
        "implementation_date": metadata.get(
            "implementation_date",
            "Refer to individual SOP"
        ),
        "references": metadata.get("references", []),
        "description": metadata.get(
            "description",
            "Refer to the original plant SOP document."
        ),
    }


# ---------------------------------------------------------------------------
# Find SOP PDF
# ---------------------------------------------------------------------------

def find_sop_pdf(plant_code: str):

    document = SOP_DOCUMENTS.get(plant_code)

    if not document:
        return None

    for filename in document["filenames"]:

        path = DATA_DIR / filename

        if path.is_file():
            return path

    if DATA_DIR.exists():

        for path in DATA_DIR.iterdir():

            if not path.is_file():
                continue

            if path.suffix.lower() != ".pdf":
                continue

            normalized = re.sub(
                r"[^a-z0-9]",
                "",
                path.stem.lower()
            )

            code = plant_code.lower()

            if normalized in {
                code,
                f"{code}sop",
                f"{code}sopfinal",
            }:
                return path

    return None


# ---------------------------------------------------------------------------
# Extract actual SOP headings from PDF
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def extract_sop_topics(pdf_path: str, modified_time: float):

    """
    Extract numbered procedure headings from the original PDF.

    The function reads the PDF itself, rather than relying on
    manually invented procedure categories.
    """

    if PdfReader is None:
        return [], "pypdf is not installed. Run: pip install pypdf"

    topics = []
    seen = set()

    heading_pattern = re.compile(
        r"^\s*(\d{1,2})\s*[\.\)]\s*(.+)$"
    )

    subheading_pattern = re.compile(
        r"^\s*\d{1,2}\.\d+"
    )

    try:

        reader = PdfReader(pdf_path)

        for page in reader.pages:

            page_text = page.extract_text() or ""

            lines = page_text.splitlines()

            for i, raw_line in enumerate(lines):

                line = raw_line.strip()

                match = heading_pattern.match(line)

                if not match:
                    continue

                title = match.group(2).strip()

                # Keep only actual procedure/document headings.
                if not re.search(
                    r"\b(standard|procedure)\b",
                    title,
                    re.IGNORECASE
                ):
                    continue

                # Remove dotted leaders and page numbers.
                title = re.sub(
                    r"\.{2,}.*$",
                    "",
                    title
                ).strip()

                # Join a wrapped heading, for example:
                # "Startup, Stop and Emergency Stop"
                # "Procedure"
                if i + 1 < len(lines):

                    next_line = lines[i + 1].strip()

                    if (
                        next_line
                        and not heading_pattern.match(next_line)
                        and not subheading_pattern.match(next_line)
                        and len(title) < 100
                        and len(next_line) < 55
                        and not re.match(
                            r"^(purpose|scope|prerequisites|"
                            r"responsibilities|procedure|"
                            r"sop owner|implementation date|"
                            r"last reviewed|page)",
                            next_line,
                            re.IGNORECASE
                        )
                    ):

                        if re.match(
                            r"^(procedure|operation|work|system|"
                            r"cleaning|within\s+\d+)",
                            next_line,
                            re.IGNORECASE
                        ):
                            title += " " + next_line

                title = re.sub(
                    r"\s+",
                    " ",
                    title
                ).strip(" .:-")

                key = re.sub(
                    r"[^\w]+",
                    "",
                    title.casefold(),
                    flags=re.UNICODE
                )

                if key and key not in seen:

                    seen.add(key)
                    topics.append(title)

        # WMB's two responsibility documents have
        # unnumbered headings in their respective pages.

        if Path(pdf_path).name.lower() in {
            "wmb_sop.pdf",
            "wmb sop.pdf",
            "wmb-sop.pdf",
            "wmb.pdf",
        }:

            responsibility_topics = [
                "Function Responsibilities",
                "Location Responsibilities",
            ]

            for topic in responsibility_topics:

                key = re.sub(
                    r"[^\w]+",
                    "",
                    topic.casefold()
                )

                if key not in seen:
                    seen.add(key)
                    topics.insert(
                        0 if topic == "Location Responsibilities" else 0,
                        topic
                    )

        return topics, None

    except Exception as e:

        return [], str(e)


# ---------------------------------------------------------------------------
# Generate Sinhala example questions
# ---------------------------------------------------------------------------

def generate_example_question(topic: str, plant_code: str):

    return (
        f"{plant_code} බලාගාරයට අදාළ SOP ලේඛනය අනුව "
        f"'{topic}' සම්බන්ධ ක්‍රියාපටිපාටිය සිංහලෙන් "
        f"පැහැදිලි කරන්න. එහි අරමුණ, විෂය පථය, "
        f"පූර්ව අවශ්‍යතා, වගකීම්, ආරක්ෂක පියවර සහ "
        f"පියවරෙන් පියවර අනුගමනය කළ යුතු ක්‍රමවේදය "
        f"ලේඛනයේ සඳහන් කරුණු අනුව පැහැදිලි කරන්න."
    )


# ---------------------------------------------------------------------------
# Display actual SOP documents in sidebar
# ---------------------------------------------------------------------------

def render_sop_documents():

    st.markdown("---")

    st.subheader("📚 SOP Topics & Example Questions")

    st.markdown(
        """
        <div class="sop-intro">
        Explore the actual contents of each plant's SOP documents.
        Select a procedure to ask the Operations Assistant.
        </div>
        """,
        unsafe_allow_html=True
    )

    st.caption(
        "Choose a plant and explore the procedures included in its SOP."
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
                    f"SOP PDF not found for {plant_code}. "
                    "Please check the data folder."
                )

                continue

            st.caption(
                f"Source document: {pdf_path.name}"
            )

            # ---------------------------------------------------
            # Document information
            # ---------------------------------------------------

            st.markdown("**Document Information**")

            st.markdown(
                f"""
                - **SOP Owner:** {document['owner']}
                - **Document Length:** {document['pages']}
                - **Implementation Date:** {document['implementation_date']}
                - **Last Reviewed / Updated:** {document['review_date']}
                """
            )

            if document["references"]:

                st.markdown("**SOP References**")

                for reference in document["references"]:
                    st.markdown(f"- `{reference}`")

            st.markdown("**Document Coverage**")

            st.write(
                document["description"]
            )

            # ---------------------------------------------------
            # Extract actual topics
            # ---------------------------------------------------

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
                    "No numbered procedure headings could be "
                    "extracted from this PDF. Please check the "
                    "document text extraction."
                )

                continue

            st.success(
                f"{len(topics)} SOP topics identified"
            )

            st.markdown(
                "**Procedures included in this document:**"
            )

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

                    # Automatically switch to the relevant plant.

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
                "You can ask your own questions in Sinhala, "
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
    # Actual BTO, WMB and other registered plant SOP contents
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

# Process a question selected from the sidebar.

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

                # Sinhala and English language handling.

                agent_prompt = prepare_agent_prompt(
                    prompt,
                    st.session_state.selected_plant
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
