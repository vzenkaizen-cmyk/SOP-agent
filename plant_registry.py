"""
plant_registry.py
------------------
Single source of truth for which plants the Plant Operations Assistant knows
about. Add a new plant by adding one entry here and dropping its SOP PDF
into the `data/` folder — nothing else needs to change.
"""

from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

PLANTS = {
    "BTO": {
        "code": "BTO",
        "name": "Batathota Mini Hydro Power Plant",
        "location": "Kuruwita, Rathnapura",
        "sop_pdf": DATA_DIR / "BTO_SOP.pdf",
    },
    "WMB": {
        "code": "WMB",
        "name": "Wembiyagoda Mini Hydro Power Plant",
        "location": "Kalawana, Rathnapura",
        "sop_pdf": DATA_DIR / "WMB_SOP.pdf",
    },
}


def get_plant(code: str) -> dict:
    code = code.upper().strip()
    if code not in PLANTS:
        raise KeyError(f"Unknown plant code '{code}'. Known plants: {list(PLANTS)}")
    return PLANTS[code]


def list_plant_codes():
    return list(PLANTS.keys())
