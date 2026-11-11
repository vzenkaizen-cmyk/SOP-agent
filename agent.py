"""
agent.py

Builds a LangGraph ReAct agent for a selected Vidullanka plant.

The agent:
- Uses OpenAI GPT-4.1
- Searches only the selected plant's SOPs
- Maintains conversation memory using LangGraph MemorySaver
- Returns both the final answer and the SOP passages used
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


# --------------------------------------------------------
# Load Environment Variables
# --------------------------------------------------------

dotenv_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path)

print("OpenAI Key Loaded:", bool(os.getenv("OPENAI_API_KEY")))


# --------------------------------------------------------
# System Prompt
# --------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """
You are the Vidullanka IDSS Plant Operations Assistant.

You are assisting engineers and operators working at:

Plant : {plant_name}
Code  : {plant_code}
Location : {plant_location}

Your responsibilities:

• Answer ONLY using the plant's SOP documents.
• Always use the search_sop tool before answering plant-specific questions.
• Never invent procedures.
• If the SOP does not contain the answer, clearly state that the information was not found.
• Do not guess.

When giving procedures:

- Use numbered steps.
- Preserve important values such as pressure, voltage, temperature and timing.
- Mention the SOP section and title.
- Mention the source document.

For emergency questions:

Always provide safety-critical actions first before normal operating procedures.
"""


# --------------------------------------------------------
# Tool Factory
# --------------------------------------------------------

def make_search_tool(plant_code: str):

    @tool
    def search_sop(query: str) -> str:
        """
        Search the SOP documents of the selected plant.
        """

        chunks = retrieve(query, plant=plant_code)

        if not chunks:
            return json.dumps(
                {
                    "plant": plant_code,
                    "results": [],
                    "note": "No relevant SOP section found."
                }
            )

        results = []

        for c in chunks:
            results.append(
                {
                    "sop_number": c.sop_number,
                    "sop_title": c.sop_title,
                    "source_file": c.source_file,
                    "distance": round(c.distance, 3),
                    "text": c.text,
                }
            )

        return json.dumps(
            {
                "plant": plant_code,
                "results": results,
            }
        )

    return search_sop


# --------------------------------------------------------
# Memory
# --------------------------------------------------------

memory = MemorySaver()


# --------------------------------------------------------
# Build Agent
# --------------------------------------------------------

def build_agent(plant_code: str):

    plant = get_plant(plant_code)

    llm = ChatOpenAI(
        model="gpt-4.1",
        temperature=0,
    )

    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        plant_name=plant["name"],
        plant_code=plant["code"],
        plant_location=plant["location"],
    )

    return create_react_agent(
        model=llm,
        tools=[make_search_tool(plant_code)],
        prompt=prompt,
        checkpointer=memory,
    )


# --------------------------------------------------------
# Run Agent
# --------------------------------------------------------

def run_agent(
    agent,
    user_message: str,
    thread_id: str,
):
    """
    Runs one conversation turn.

    Returns
    -------
    {
        "answer": "...",
        "sources": [...]
    }
    """

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    state = agent.invoke(
        {
            "messages": [
                ("user", user_message)
            ]
        },
        config=config,
    )

    messages = state["messages"]

    answer = ""

    if messages:
        answer = messages[-1].content

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

                sources.extend(
                    payload.get("results", [])
                )

            except Exception:
                pass

    return {
        "answer": answer,
        "sources": sources,
    }