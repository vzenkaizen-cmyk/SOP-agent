"""
agent.py

Vidullanka IDSS agent for BTO, WMB, and combined BTO + WMB questions.
Uses SOP retrieval plus structured technical details from plant_details.py.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from plant_registry import get_plant
from retriever import retrieve
from plant_details import get_plant_details


dotenv_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path)

print("OpenAI Key Loaded:", bool(os.getenv("OPENAI_API_KEY")))

ALL_PLANT_MODE = "BTO_WMB"
SUPPORTED_PLANTS = ("BTO", "WMB")

SYSTEM_PROMPT_TEMPLATE = """
You are the Vidullanka IDSS Plant Operations Assistant.

Selected plant scope:
{plant_scope}

You can access two authoritative internal knowledge sources:
1. search_plant_details: structured technical and project details transcribed
   from the supplied Power Plant Details.xlsx workbook.
2. search_sop: operational procedures retrieved from the selected plant's
   indexed SOP documents.

Knowledge and source rules:
- For questions about plant identity, location, installed capacity, generators,
  turbine type, rated head, design flow, environmental flow, weir, channel,
  penstock, speed, voltage, transformers, river, catchment area, AAE,
  plant factor, project company, ownership, commissioning year or project cost,
  ALWAYS use search_plant_details before answering.
- For SOP procedures, responsibilities, safety, operation, maintenance,
  shutdown, emergency actions or document-specific requirements, ALWAYS use
  search_sop before answering.
- If a question requires both technical details and SOP information, use both tools.
- In combined BTO + WMB mode, search both plants' SOPs and retrieve both plants'
  technical records. Clearly identify which facts belong to BTO and WMB.
- Answer comparisons and overall questions using both plants when the user
  asks about both, all selected plants, overall, differences, totals or comparisons.
- Do not attribute one plant's values to the other plant.
- Do not invent, estimate, or silently correct source values.
- If a requested fact is not present in the workbook or relevant SOP result,
  clearly say that it is not available in the supplied source.
- For numerical totals or comparisons, calculate only from source values with
  compatible units. Explain the calculation when useful.
- Cite the source naturally in the answer, e.g. "Source: Power Plant Details.xlsx"
  or the relevant SOP title/source file.

Language:
- Follow the language of the user's question.
- English question: answer in English only.
- Sinhala question: answer in Sinhala only.
- Mixed Sinhala and English question: answer bilingually in Sinhala and English.
- Preserve technical names, abbreviations and units accurately.

When explaining procedures:
- Use numbered steps.
- Preserve important values such as pressure, voltage, temperature and timing.
- Mention the SOP number, title and source document where available.
- For emergency questions, present safety-critical actions first.
"""

memory = MemorySaver()


def _selected_plant_codes(plant_code):
    if plant_code == ALL_PLANT_MODE:
        return list(SUPPORTED_PLANTS)
    if plant_code in SUPPORTED_PLANTS:
        return [plant_code]
    raise ValueError(
        f"Unsupported agent plant scope: {plant_code}. "
        f"Use BTO, WMB, or {ALL_PLANT_MODE}."
    )


def make_search_tool(plant_codes):
    @tool
    def search_sop(query: str) -> str:
        """Search the SOP documents for every plant in the selected scope."""
        all_results = []
        for code in plant_codes:
            chunks = retrieve(query, plant=code)
            for chunk in chunks:
                all_results.append({
                    "plant": code,
                    "sop_number": chunk.sop_number,
                    "sop_title": chunk.sop_title,
                    "source_file": chunk.source_file,
                    "distance": round(chunk.distance, 3),
                    "text": chunk.text,
                })

        return json.dumps(
            {
                "plants_searched": plant_codes,
                "results": all_results,
                "note": (
                    "No relevant SOP section found in the selected plants."
                    if not all_results else ""
                ),
            },
            ensure_ascii=False,
        )

    return search_sop


def make_plant_details_tool(plant_codes):
    @tool
    def search_plant_details(query: str) -> str:
        """
        Search the structured hydro power plant technical details.
        Use for plant specifications, generation capacity, generators,
        turbines, rivers, civil structures, electrical equipment,
        annual energy, plant factor and project details.
        """
        records = get_plant_details(plant_codes)
        return json.dumps(
            {
                "source": "Power Plant Details.xlsx — Hydro worksheet",
                "plant_details": records,
            },
            ensure_ascii=False,
        )

    return search_plant_details


def build_agent(plant_code: str):
    plant_codes = _selected_plant_codes(plant_code)

    if plant_code == ALL_PLANT_MODE:
        plant_scope = (
            "BTO — Batathota MHPP and WMB — Wembiyagoda MHPP. "
            "The user may ask about either plant or both plants together."
        )
    else:
        plant = get_plant(plant_code)
        plant_scope = (
            f"{plant['name']} (Code: {plant['code']}; "
            f"Location: {plant['location']})."
        )

    llm = ChatOpenAI(model="gpt-4.1", temperature=0)
    prompt = SYSTEM_PROMPT_TEMPLATE.format(plant_scope=plant_scope)

    return create_react_agent(
        model=llm,
        tools=[
            make_search_tool(plant_codes),
            make_plant_details_tool(plant_codes),
        ],
        prompt=prompt,
        checkpointer=memory,
    )


def run_agent(agent, user_message: str, thread_id: str):
    """Run one turn and return the answer plus retrieved SOP source passages."""
    config = {"configurable": {"thread_id": thread_id}}
    state = agent.invoke(
        {"messages": [("user", user_message)]},
        config=config,
    )

    messages = state["messages"]
    answer = messages[-1].content if messages else ""

    if isinstance(answer, list):
        answer = "".join(
            part.get("text", "")
            for part in answer
            if isinstance(part, dict)
        )

    sources = []
    for message in messages:
        if (
            getattr(message, "type", None) == "tool"
            or message.__class__.__name__ == "ToolMessage"
        ):
            try:
                payload = json.loads(message.content)
                sources.extend(payload.get("results", []))
            except Exception:
                pass

    return {"answer": answer, "sources": sources}
