"""
plant_details.py
----------------
Structured plant technical details transcribed from the supplied
Power Plant Details.xlsx (Hydro worksheet).

Only BTO and WMB are included. Values are kept as recorded in the workbook.
"""

PLANT_DETAILS = {
    "BTO": {
        "plant_name": "Batathota MHPP",
        "plant_code": "BTO",
        "total_capacity": "2.6 MW",
        "machine_combination": "800 kW x 2 Nos + 1000 kW x 1 Nos",
        "generators": [
            {
                "generator": "Generator 1",
                "capacity": "800 kW"
            },
            {
                "generator": "Generator 2",
                "capacity": "800 kW"
            },
            {
                "generator": "Generator 3",
                "capacity": "1000 kW"
            }
        ],
        "turbine_type": "Francis",
        "rated_head": "41 m",
        "design_flow": "8.03 m3/s",
        "environmental_flow": "600 l/s",
        "weir_height": "2.5 m",
        "weir_length": "22.9 m",
        "channel_length": "1700 m",
        "penstock_lines": "1",
        "penstock_diameter": "1330 mm",
        "penstock_path_length": "140 m",
        "speed": "750 rpm",
        "generator_voltage": "400 V",
        "transformer_capacities": "1000 kVA x 2 Nos + 1200 kVA x 1 Nos",
        "river": "Kuru Ganga",
        "catchment_area": "64 sq. km",
        "aae": "10.3 GWh",
        "plant_factor": "0.58",
        "project_company": "Vidullanka PLC",
        "ownership": "1",
        "commissioned": "2007",
        "project_cost": "USD Mn 2.5"
    },
    "WMB": {
        "plant_name": "Wembiyagoda MHPP",
        "plant_code": "WMB",
        "total_capacity": "1.3 MW",
        "machine_combination": "650 kW x 2 Nos",
        "generators": [
            {
                "generator": "Generator 1",
                "capacity": "650 kW"
            },
            {
                "generator": "Generator 2",
                "capacity": "650 kW"
            }
        ],
        "turbine_type": "Francis",
        "rated_head": "22.5 m",
        "design_flow": "7.28 m3/s",
        "environmental_flow": "550 l/s",
        "weir_height": "1.5 m",
        "weir_length": "19 m",
        "channel_length": "440 m",
        "penstock_lines": "2",
        "penstock_diameter": "1610 mm",
        "penstock_path_length": "40 m",
        "speed": "500 rpm",
        "generator_voltage": "400 V",
        "transformer_capacities": "800 kVA x 2 Nos",
        "river": "Koswathu Ganga",
        "catchment_area": "77 sq. km",
        "aae": "4.5 GWh",
        "plant_factor": "0.4",
        "project_company": "Vidullanka PLC",
        "ownership": "1",
        "commissioned": "2013",
        "project_cost": "USD Mn 2"
    }
}


def get_plant_details(plant_codes=None):
    """Return details for one or more supported hydro plants."""
    codes = plant_codes or ["BTO", "WMB"]
    return {
        code: PLANT_DETAILS[code]
        for code in codes
        if code in PLANT_DETAILS
    }
