"""
app.py
------
Vidullanka IDSS — Plant Operations Assistant (Streamlit UI)

Run with:
    streamlit run app.py
"""
import uuid
import streamlit as st

from plant_registry import PLANTS, list_plant_codes
from ingest import reindex_all, reindex_plant, CHROMA_DIR
from retriever import collection_stats
from agent import build_agent, run_agent

st.set_page_config(page_title="Vidullanka IDSS — Plant Operations Assistant", page_icon="💧", layout="wide")

# ---------------------------------------------------------------------------
# Layout and automatic light/dark appearance
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* Keep the heading near the top while leaving room below Streamlit's toolbar. */
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

    /* Follow the computer/browser appearance preference. */
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
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "chat_history" not in st.session_state:
    st.session_state.chat_history = {}  # plant_code -> list[{"role","content","sources"}]
if "selected_plant" not in st.session_state:
    st.session_state.selected_plant = list_plant_codes()[0]


def get_history(plant_code: str):
    return st.session_state.chat_history.setdefault(plant_code, [])


@st.cache_resource(show_spinner=False)
def get_agent(plant_code: str):
    return build_agent(plant_code)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("Vidullanka IDSS")
    st.caption("Plant Operations Assistant")

    plant_labels = {code: f"{code} — {PLANTS[code]['name']}" for code in list_plant_codes()}
    selected = st.selectbox(
        "Select plant",
        options=list_plant_codes(),
        format_func=lambda c: plant_labels[c],
        index=list_plant_codes().index(st.session_state.selected_plant),
    )
    if selected != st.session_state.selected_plant:
        st.session_state.selected_plant = selected
        st.session_state.thread_id = str(uuid.uuid4())  # fresh memory thread per plant switch
        st.rerun()

    plant = PLANTS[st.session_state.selected_plant]
    st.markdown(f"**{plant['name']}**  \n{plant['location']}")

    st.divider()
    st.subheader("Index status")
    try:
        stats = collection_stats()
        st.write(f"Total chunks indexed: **{stats['total']}**")
        for code, n in stats["per_plant"].items():
            st.write(f"- {code}: {n} chunks")
        index_ready = stats["per_plant"].get(st.session_state.selected_plant, 0) > 0
    except Exception as e:
        st.warning(f"Index not built yet ({e}).")
        index_ready = False

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Reindex this plant", use_container_width=True):
            with st.spinner(f"Re-indexing {st.session_state.selected_plant} SOP..."):
                n = reindex_plant(st.session_state.selected_plant)
            st.success(f"Indexed {n} chunks.")
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
        st.session_state.chat_history[st.session_state.selected_plant] = []
        st.session_state.thread_id = str(uuid.uuid4())
        st.rerun()

# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------
st.header(f"{plant['name']} — Operations Assistant")

if not index_ready:
    st.info(
        "This plant hasn't been indexed yet. Put its SOP PDF in the `data/` folder "
        "(see README) and click **Reindex this plant** in the sidebar."
    )

history = get_history(st.session_state.selected_plant)

for turn in history:
    with st.chat_message(turn["role"]):
        st.markdown(turn["content"])
        if turn.get("sources"):
            with st.expander(f" Sources ({len(turn['sources'])})"):
                for s in turn["sources"]:
                    st.markdown(
                        f"**SOP {s['sop_number']}: {s['sop_title']}**  \n"
                        f"*{s['source_file']} · similarity distance {s['distance']}*"
                    )
                    st.text(s["text"][:600] + ("..." if len(s["text"]) > 600 else ""))
                    st.markdown("---")

prompt = st.chat_input(f"Ask about {plant['code']} procedures, safety, or equipment...")

if prompt:
    history.append({"role": "user", "content": prompt, "sources": None})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        if not index_ready:
            answer_text = "This plant hasn't been indexed yet — please reindex it from the sidebar first."
            sources = []
            st.markdown(answer_text)
        else:
            with st.spinner("Checking the SOPs..."):
                agent = get_agent(st.session_state.selected_plant)
                result = run_agent(agent, prompt, thread_id=st.session_state.thread_id)
            answer_text = result["answer"]
            sources = result["sources"]
            st.markdown(answer_text)
            if sources:
                with st.expander(f" Sources ({len(sources)})"):
                    for s in sources:
                        st.markdown(
                            f"**SOP {s['sop_number']}: {s['sop_title']}**  \n"
                            f"*{s['source_file']} · similarity distance {s['distance']}*"
                        )
                        st.text(s["text"][:600] + ("..." if len(s["text"]) > 600 else ""))
                        st.markdown("---")

    history.append({"role": "assistant", "content": answer_text, "sources": sources})
