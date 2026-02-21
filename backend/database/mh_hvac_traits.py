#!/usr/bin/env python3
"""
HVAC Trait Seed Script — Initializes Meta-Graph with Abstract Traits

Seeds Layer 2.5 (Trait Layer) into the existing Neo4j graph:
- PhysicalTrait nodes (product capabilities abstracted from features)
- EnvironmentalStressor nodes (attack vectors from environments)
- CausalRule relationships (NEUTRALIZED_BY, DEMANDS_TRAIT)
- Bridging relationships to existing ProductFamily, Material, Application, Environment nodes

This is ADDITIVE — it does NOT modify or delete any existing nodes/relationships.

Usage:
    cd backend && source venv/bin/activate && python database/mh_hvac_traits.py
"""

import os
import sys
from dotenv import load_dotenv
from db_result_helpers import result_to_dicts, result_single, result_value

load_dotenv(dotenv_path="../.env")


# =============================================================================
# PHYSICAL TRAITS — Product Capabilities
# =============================================================================

PHYSICAL_TRAITS = [
    {
        "id": "TRAIT_POROUS_ADSORPTION",
        "name": "Porous Adsorption",
        "description": "Uses activated carbon pores to capture gas molecules via Van der Waals forces",
        "category": "filtration",
        "keywords": ["carbon", "adsorption", "gas", "odor", "voc", "activated carbon"],
    },
    {
        "id": "TRAIT_MECHANICAL_FILTRATION",
        "name": "Mechanical Filtration",
        "description": "Captures particles via inertial impaction, interception, and diffusion",
        "category": "filtration",
        "keywords": ["particle", "dust", "bag filter", "panel filter", "mechanical"],
    },
    {
        "id": "TRAIT_THERMAL_INSULATION",
        "name": "Thermal Insulation",
        "description": "Double-wall construction prevents condensation via thermal break",
        "category": "protection",
        "keywords": ["insulated", "double-wall", "condensation protection"],
    },
    {
        "id": "TRAIT_CORROSION_RESISTANCE_C5",
        "name": "Corrosion Resistance C5",
        "description": "Material withstands aggressive chemical environments (ISO 12944 C5)",
        "category": "material",
        "keywords": ["stainless", "C5", "corrosion resistant", "RF", "SF"],
    },
    {
        "id": "TRAIT_CORROSION_RESISTANCE_C5M",
        "name": "Corrosion Resistance C5-M",
        "description": "Marine-grade corrosion resistance (ISO 12944 C5-M)",
        "category": "material",
        "keywords": ["marine grade", "C5-M", "acid proof", "SF"],
    },
    {
        "id": "TRAIT_CORROSION_RESISTANCE_C3",
        "name": "Corrosion Resistance C3",
        "description": "Standard indoor corrosion resistance (ISO 12944 C3)",
        "category": "material",
        "keywords": ["galvanized", "zinc", "C3", "FZ", "standard"],
    },
    {
        "id": "TRAIT_ELECTROSTATIC_GROUNDING",
        "name": "Electrostatic Grounding",
        "description": "Prevents static charge buildup in explosive atmospheres",
        "category": "safety",
        "keywords": ["ATEX", "grounding", "conductive", "anti-static", "explosion proof"],
    },
    {
        "id": "TRAIT_HEPA_FILTRATION",
        "name": "HEPA Filtration",
        "description": "High-efficiency particulate air filtration (H13/H14, 99.95%+)",
        "category": "filtration",
        "keywords": ["HEPA", "H13", "H14", "cleanroom", "sterile"],
    },
    {
        "id": "TRAIT_BAYONET_MOUNT",
        "name": "Bayonet Mount",
        "description": "Quick-release cartridge mounting system for carbon filter cylinders",
        "category": "mechanical",
        "keywords": ["bayonet", "cartridge", "quick release", "cylinder mount"],
    },
    {
        "id": "TRAIT_EXCENTRIC_LOCK",
        "name": "Excentric Lock",
        "description": "Cam-type locking mechanism for tool-free door opening",
        "category": "mechanical",
        "keywords": ["EXL", "excentric", "cam lock", "tool-free"],
    },
    {
        "id": "TRAIT_EXTRACTABLE_RAIL",
        "name": "Extractable Rail",
        "description": "Slide-out rail for heavy filter service (reduces maintenance time)",
        "category": "mechanical",
        "keywords": ["rail", "polis", "polisfilter", "slide-out", "extractable"],
    },
    {
        "id": "TRAIT_MODULAR_ASSEMBLY",
        "name": "Modular Assembly",
        "description": "Can be combined into multi-module configurations for high airflow",
        "category": "structural",
        "keywords": ["modular", "multi-module", "combinable", "scalable"],
    },
]


# =============================================================================
# ENVIRONMENTAL STRESSORS — Attack Vectors
# =============================================================================

ENVIRONMENTAL_STRESSORS = [
    {
        "id": "STRESSOR_CHLORINE",
        "name": "Chlorine Exposure",
        "description": "Chlorine from disinfection or pool water attacks metal surfaces",
        "category": "chemical",
        "keywords": ["chlorine", "disinfection", "pool", "bleach", "klor"],
    },
    {
        "id": "STRESSOR_OUTDOOR_CONDENSATION",
        "name": "Outdoor Condensation",
        "description": "Temperature differential between indoor/outdoor air causes water condensation on cold metal surfaces",
        "category": "environmental",
        "keywords": ["outdoor", "roof", "rooftop", "dach", "zewnątrz", "outside", "exterior", "weather", "condensation"],
    },
    {
        "id": "STRESSOR_HIGH_TEMPERATURE",
        "name": "High Temperature",
        "description": "Elevated operating temperatures degrade filter media and seals",
        "category": "environmental",
        "keywords": ["high temperature", "hot", "heat", "thermal", "ciepło"],
    },
    {
        "id": "STRESSOR_PARTICULATE_EXPOSURE",
        "name": "Particulate Exposure",
        "description": "Dust, soot, or mist blocks filter pores and reduces adsorption capacity",
        "category": "substance",
        "keywords": ["dust", "soot", "particle", "particulate", "pollen", "kurz", "pył", "sadza", "mist", "overspray", "powder", "powder coating"],
    },
    {
        "id": "STRESSOR_GREASE_EXPOSURE",
        "name": "Grease/Oil Exposure",
        "description": "Grease and oil permanently coat activated carbon pores, deactivating adsorption",
        "category": "substance",
        "keywords": ["grease", "oil", "fat", "lipid", "kitchen", "kuchnia", "fryer", "restaurant"],
    },
    {
        "id": "STRESSOR_EXPLOSIVE_ATMOSPHERE",
        "name": "Explosive Atmosphere",
        "description": "Dust or gas concentrations that can ignite from spark or static discharge",
        "category": "safety",
        "keywords": ["ATEX", "explosion", "explosive", "ex zone", "wybuch", "spark", "ignition", "powder", "combustible dust"],
    },
    {
        "id": "STRESSOR_SALT_SPRAY",
        "name": "Salt Spray",
        "description": "Marine or coastal salt spray accelerates corrosion of standard metals",
        "category": "environmental",
        "keywords": ["salt", "marine", "sea", "coastal", "offshore", "ship", "morski"],
    },
    {
        "id": "STRESSOR_CHEMICAL_VAPORS",
        "name": "Chemical Vapor Exposure",
        "description": "VOCs, solvents, or acidic gases that require adsorption-based removal",
        "category": "substance",
        "keywords": ["smell", "odor", "odors", "odour", "odours", "fume", "fumes",
                      "gas", "voc", "volatile", "exhaust", "chemical", "zapach",
                      "spaliny", "gaz", "solvent", "fuel", "kerosene", "vapor", "vapors"],
    },
    {
        "id": "STRESSOR_HUMIDITY",
        "name": "High Humidity",
        "description": "Persistent moisture causes mold growth, corrosion, and filter degradation",
        "category": "environmental",
        "keywords": ["humidity", "moisture", "wet", "damp", "wilgoć"],
    },
    {
        "id": "STRESSOR_HYGIENE_REQUIREMENTS",
        "name": "Hygiene Requirements",
        "description": "Regulatory demands for medical/cleanroom-grade cleanliness (VDI 6022)",
        "category": "regulatory",
        "keywords": ["hospital", "szpital", "medical", "clinic", "surgery", "cleanroom",
                      "pharma", "sterile", "hygiene", "VDI 6022"],
    },
]


# =============================================================================
# CAUSAL RULES — Trait-Stressor Interactions
# =============================================================================

# NEUTRALIZED_BY: Trait becomes useless when stressor is present
NEUTRALIZED_BY_RULES = [
    {
        "trait_id": "TRAIT_POROUS_ADSORPTION",
        "stressor_id": "STRESSOR_PARTICULATE_EXPOSURE",
        "severity": "CRITICAL",
        "explanation": "Activated carbon pores get physically blocked by particles, rendering gas adsorption useless. Pre-filtration is mandatory.",
    },
    {
        "trait_id": "TRAIT_POROUS_ADSORPTION",
        "stressor_id": "STRESSOR_GREASE_EXPOSURE",
        "severity": "CRITICAL",
        "explanation": "Lipids permanently coat activated carbon pores via irreversible adsorption. Grease separator required upstream.",
    },
    {
        "trait_id": "TRAIT_CORROSION_RESISTANCE_C3",
        "stressor_id": "STRESSOR_CHLORINE",
        "severity": "CRITICAL",
        "explanation": "Zinc coating (C3) dissolves in chlorinated environments within months. Upgrade to C5 (stainless) required.",
    },
    {
        "trait_id": "TRAIT_CORROSION_RESISTANCE_C3",
        "stressor_id": "STRESSOR_SALT_SPRAY",
        "severity": "CRITICAL",
        "explanation": "Salt spray accelerates zinc corrosion. C3-rated materials fail prematurely in marine/coastal environments.",
    },
    {
        "trait_id": "TRAIT_CORROSION_RESISTANCE_C3",
        "stressor_id": "STRESSOR_HUMIDITY",
        "severity": "WARNING",
        "explanation": "Persistent humidity accelerates zinc corrosion, reducing service life. Consider C4 or C5 materials.",
    },
    {
        "trait_id": "TRAIT_POROUS_ADSORPTION",
        "stressor_id": "STRESSOR_HUMIDITY",
        "severity": "WARNING",
        "explanation": "High humidity reduces carbon adsorption efficiency. Keep relative humidity below 70% for optimal performance.",
    },
]

# DEMANDS_TRAIT: Stressor requires this trait for safe operation
DEMANDS_TRAIT_RULES = [
    {
        "stressor_id": "STRESSOR_OUTDOOR_CONDENSATION",
        "trait_id": "TRAIT_THERMAL_INSULATION",
        "severity": "CRITICAL",
        "explanation": "Outdoor installation causes condensation on non-insulated metal surfaces. Double-wall insulated housing required to maintain surface above dew point.",
    },
    {
        "stressor_id": "STRESSOR_CHLORINE",
        "trait_id": "TRAIT_CORROSION_RESISTANCE_C5",
        "severity": "CRITICAL",
        "explanation": "Chlorine environments require minimum C5 corrosion resistance (stainless steel). Lower grades corrode rapidly.",
    },
    {
        "stressor_id": "STRESSOR_SALT_SPRAY",
        "trait_id": "TRAIT_CORROSION_RESISTANCE_C5M",
        "severity": "CRITICAL",
        "explanation": "Marine/coastal environments require C5-M marine-grade corrosion resistance (acid-proof stainless).",
    },
    {
        "stressor_id": "STRESSOR_EXPLOSIVE_ATMOSPHERE",
        "trait_id": "TRAIT_ELECTROSTATIC_GROUNDING",
        "severity": "CRITICAL",
        "explanation": "Explosive atmosphere (ATEX zone) requires all components to be electrostatically grounded to prevent spark ignition.",
    },
    {
        "stressor_id": "STRESSOR_HYGIENE_REQUIREMENTS",
        "trait_id": "TRAIT_CORROSION_RESISTANCE_C5",
        "severity": "WARNING",
        "explanation": "Medical/cleanroom applications follow VDI 6022 which recommends C5 corrosion resistance (stainless steel) for hygienic surfaces.",
    },
    {
        "stressor_id": "STRESSOR_PARTICULATE_EXPOSURE",
        "trait_id": "TRAIT_MECHANICAL_FILTRATION",
        "severity": "INFO",
        "explanation": "Particle capture requires mechanical filtration (bag or panel filters). Carbon adsorption is ineffective against solid particulates.",
    },
    {
        "stressor_id": "STRESSOR_CHEMICAL_VAPORS",
        "trait_id": "TRAIT_POROUS_ADSORPTION",
        "severity": "INFO",
        "explanation": "Gas/odor/VOC removal requires activated carbon adsorption. Mechanical filters cannot capture gas-phase contaminants.",
    },
    {
        "stressor_id": "STRESSOR_GREASE_EXPOSURE",
        "trait_id": "TRAIT_MECHANICAL_FILTRATION",
        "severity": "INFO",
        "explanation": "Kitchen/grease environments need mechanical pre-filtration before any carbon stage to protect carbon from lipid contamination.",
    },
]


# =============================================================================
# FUNCTIONAL GOALS — User Intents That Map to Traits
# =============================================================================

FUNCTIONAL_GOALS = [
    {
        "id": "GOAL_ODOR_REMOVAL",
        "name": "Odor/Gas Removal",
        "description": "Remove gaseous contaminants, VOCs, odors via adsorption",
        "keywords": ["odor", "smell", "fume", "gas", "voc", "volatile", "chemical",
                      "zapach", "exhaust", "stink", "odour", "remove odor", "remove smell"],
        "required_trait_id": "TRAIT_POROUS_ADSORPTION",
    },
    {
        "id": "GOAL_PARTICLE_REMOVAL",
        "name": "Particle Removal",
        "description": "Capture solid particles, dust, mist via mechanical filtration",
        "keywords": ["dust", "particle", "smoke", "soot", "pollen", "mist",
                      "pył", "kurz", "particulate", "pm10", "pm2.5"],
        "required_trait_id": "TRAIT_MECHANICAL_FILTRATION",
    },
    {
        "id": "GOAL_THERMAL_PROTECTION",
        "name": "Thermal / Condensation Protection",
        "description": "Prevent condensation on outdoor or cold installations",
        "keywords": ["outdoor", "condensation", "insulated", "weather protection",
                      "dew point", "thermal break"],
        "required_trait_id": "TRAIT_THERMAL_INSULATION",
    },
    {
        "id": "GOAL_HEPA_FILTRATION",
        "name": "HEPA Filtration",
        "description": "High-efficiency filtration for cleanroom or sterile environments",
        "keywords": ["hepa", "cleanroom", "sterile", "h13", "h14", "ultra-clean"],
        "required_trait_id": "TRAIT_HEPA_FILTRATION",
    },
]


# =============================================================================
# LOGIC GATES — Conditional Vetoes with Data Requirements (Layer 3)
# =============================================================================

LOGIC_GATES = [
    {
        "id": "GATE_DEW_POINT",
        "name": "Dew Point Condensation Gate",
        "condition_logic": "IF min_temperature < dew_point(relative_humidity) THEN VETO ELSE PASS",
        "physics_explanation": (
            "Outdoor installations cause condensation when surface temperature drops below "
            "the dew point. Insulated (double-wall) housing maintains surface temperature "
            "above dew point, preventing water damage to filters."
        ),
        "monitors_stressor_id": "STRESSOR_OUTDOOR_CONDENSATION",
        "requires_data": [
            {"param_id": "PARAM_MIN_TEMP", "name": "Minimum Ambient Temperature",
             "property_key": "min_temperature", "priority": 1,
             "question": "What is the minimum expected ambient temperature at the installation site?",
             "unit": "celsius"},
            {"param_id": "PARAM_REL_HUMIDITY", "name": "Relative Humidity",
             "property_key": "relative_humidity", "priority": 2,
             "question": "What is the typical relative humidity at the site?",
             "unit": "percent"},
        ],
        "trigger_contexts": ["ENV_OUTDOOR"],
    },
    {
        "id": "GATE_GREASE_LOAD",
        "name": "Grease Loading Gate",
        "condition_logic": "IF grease_presence == true THEN VETO ELSE PASS",
        "physics_explanation": (
            "Lipids permanently coat activated carbon pores via irreversible adsorption. "
            "Even trace grease permanently deactivates carbon. A pre-filter stage is mandatory "
            "for any application where grease, oil, or fat is present in the airstream."
        ),
        "monitors_stressor_id": "STRESSOR_GREASE_EXPOSURE",
        "requires_data": [
            {"param_id": "PARAM_GREASE_PRESENCE", "name": "Grease/Oil Presence Confirmation",
             "property_key": "grease_presence", "priority": 1,
             "question": "Is grease, oil, or fat present in the air stream (e.g., kitchen exhaust, industrial process)?",
             "unit": "boolean"},
        ],
        "trigger_contexts": ["APP_KITCHEN"],
    },
    {
        "id": "GATE_CHLORINE_EXPOSURE",
        "name": "Chlorine Exposure Gate",
        "condition_logic": "IF chlorine_level > 0.5 THEN DEMAND_C5 ELSE WARN",
        "physics_explanation": (
            "Chlorine from disinfection or pool water aggressively attacks zinc coatings, "
            "causing through-corrosion of standard galvanized (C3) housings within months. "
            "Stainless steel (C5) or acid-proof (C5-M) is required."
        ),
        "monitors_stressor_id": "STRESSOR_CHLORINE",
        "requires_data": [
            {"param_id": "PARAM_CHLORINE_LEVEL", "name": "Chlorine Concentration",
             "property_key": "chlorine_level", "priority": 1,
             "question": "What is the approximate chlorine concentration in the environment (ppm)?",
             "unit": "ppm"},
        ],
        "trigger_contexts": ["APP_HOSPITAL", "APP_POOL"],
    },
    {
        "id": "GATE_ATEX_ZONE",
        "name": "ATEX Zone Classification Gate",
        "condition_logic": "IF atex_zone IN [0,1,2,20,21,22] THEN DEMAND_GROUNDING",
        "physics_explanation": (
            "Explosive atmospheres require all components to prevent ignition sources. "
            "Static charge on ungrounded filter housings can produce sparks exceeding "
            "the minimum ignition energy of many dust/gas mixtures."
        ),
        "monitors_stressor_id": "STRESSOR_EXPLOSIVE_ATMOSPHERE",
        "requires_data": [
            {"param_id": "PARAM_ATEX_ZONE", "name": "ATEX Zone Classification",
             "property_key": "atex_zone", "priority": 1,
             "question": "Which ATEX zone classification applies (Zone 0/1/2 for gas, Zone 20/21/22 for dust)?",
             "unit": "zone"},
        ],
        "trigger_contexts": ["ENV_ATEX", "APP_POWDER_COATING"],
    },
]


# =============================================================================
# HARD CONSTRAINTS — Physical Limits on Items (Layer 1)
# =============================================================================

HARD_CONSTRAINTS = [
    {"item_id": "FAM_GDC", "property_key": "housing_length_mm", "operator": ">=",
     "value": 750, "error_msg": "GDC requires minimum 750mm housing length for carbon cylinders. Auto-correcting to 750mm."},
    {"item_id": "FAM_GDB", "property_key": "housing_length_mm", "operator": ">=",
     "value": 550, "error_msg": "GDB requires minimum 550mm housing length for bag filters. Auto-correcting to 550mm."},
    {"item_id": "FAM_GDMI", "property_key": "housing_length_mm", "operator": ">=",
     "value": 600, "error_msg": "GDMI insulated housing requires minimum 600mm length. Auto-correcting to 600mm."},
    {"item_id": "FAM_GDC", "property_key": "housing_width_mm", "operator": ">=",
     "value": 300, "error_msg": "GDC minimum 300mm width for carbon cartridge geometry."},
]


# =============================================================================
# DEPENDENCY RULES — Graph-Driven Multi-Item Assembly (Layer 3)
# =============================================================================

DEPENDENCY_RULES = [
    {
        "id": "DEP_KITCHEN_CARBON",
        "dependency_type": "MANDATES_PROTECTION",
        "description": "Kitchen/grease environments require mechanical pre-filtration before carbon stage to prevent lipid contamination of activated carbon pores.",
        "upstream_trait_id": "TRAIT_MECHANICAL_FILTRATION",
        "downstream_trait_id": "TRAIT_POROUS_ADSORPTION",
        "triggered_by_stressor_id": "STRESSOR_GREASE_EXPOSURE",
    },
    {
        "id": "DEP_DUSTY_CARBON",
        "dependency_type": "MANDATES_PROTECTION",
        "description": "Particulate environments require mechanical pre-filtration before carbon to prevent physical pore blockage.",
        "upstream_trait_id": "TRAIT_MECHANICAL_FILTRATION",
        "downstream_trait_id": "TRAIT_POROUS_ADSORPTION",
        "triggered_by_stressor_id": "STRESSOR_PARTICULATE_EXPOSURE",
    },
    {
        "id": "DEP_PAINT_CARBON",
        "dependency_type": "MANDATES_PROTECTION",
        "description": "Paint shop environments generate both overspray mist and VOC vapors. Mechanical pre-filtration captures mist before it reaches the carbon adsorption stage.",
        "upstream_trait_id": "TRAIT_MECHANICAL_FILTRATION",
        "downstream_trait_id": "TRAIT_POROUS_ADSORPTION",
        "triggered_by_stressor_id": "STRESSOR_PARTICULATE_EXPOSURE",
    },
]


# =============================================================================
# OPTIMIZATION STRATEGIES — Sort Preferences per Item (Layer 1)
# =============================================================================

OPTIMIZATION_STRATEGIES = [
    {"item_id": "FAM_GDB", "name": "Minimize Width",
     "sort_property": "housing_width_mm", "sort_order": "ASC",
     "description": "Prefer narrower modules to minimize installation footprint."},
    {"item_id": "FAM_GDC", "name": "Minimize Width",
     "sort_property": "housing_width_mm", "sort_order": "ASC",
     "description": "Prefer narrower modules to minimize duct obstruction."},
    {"item_id": "FAM_GDP", "name": "Max Throughput",
     "sort_property": "reference_throughput", "sort_order": "DESC",
     "description": "Prefer higher-capacity modules to reduce module count."},
    {"item_id": "FAM_GDMI", "name": "Minimize Width",
     "sort_property": "housing_width_mm", "sort_order": "ASC",
     "description": "Prefer narrower modules for insulated housings."},
]


# =============================================================================
# CAPACITY RULES — Throughput/Sizing from Graph (replaces hardcoded dict)
# =============================================================================

CAPACITY_RULES = [
    {"id": "CAP_GDB_600", "item_id": "FAM_GDB", "module_descriptor": "600x600",
     "input_requirement": "airflow_m3h", "output_rating": 3400,
     "assumption": "1.5 m/s face velocity",
     "description": "GDB: 3400 m3/h per 1/1 module (592x592mm) at 1.5 m/s"},
    {"id": "CAP_GDMI_600", "item_id": "FAM_GDMI", "module_descriptor": "600x600",
     "input_requirement": "airflow_m3h", "output_rating": 3400,
     "assumption": "1.5 m/s face velocity",
     "description": "GDMI: 3400 m3/h per 1/1 module at 1.5 m/s"},
    {"id": "CAP_GDC_600", "item_id": "FAM_GDC", "module_descriptor": "600x600",
     "input_requirement": "airflow_m3h", "output_rating": 2400,
     "capacity_per_component": 150, "component_count_key": "capacity_units",
     "assumption": "150 m3/h dwell time per cartridge (standard: 16 cartridges for 600x600)",
     "description": "GDC: 2400 m3/h per 600x600 module (16 cartridges x 150)"},
    {"id": "CAP_GDC_FLEX_600", "item_id": "FAM_GDC_FLEX", "module_descriptor": "600x600",
     "input_requirement": "airflow_m3h", "output_rating": 2100,
     "capacity_per_component": 150, "component_count_key": "capacity_units",
     "assumption": "150 m3/h dwell time per cartridge (FLEX: 14 cartridges for 600x600)",
     "description": "GDC FLEX: 2100 m3/h per 600x600 module (14 cartridges x 150)"},
    {"id": "CAP_GDP_600", "item_id": "FAM_GDP", "module_descriptor": "600x600",
     "input_requirement": "airflow_m3h", "output_rating": 3500,
     "assumption": "1.6 m/s face velocity",
     "description": "GDP: 3500 m3/h per 600x600 module"},
]


# =============================================================================
# BRIDGING RELATIONSHIPS — Connect to Existing Schema
# =============================================================================

# ProductFamily -> PhysicalTrait (HAS_TRAIT)
PRODUCT_TRAITS = [
    # GDC: Carbon filter housing — primary trait is porous adsorption
    {"product_id": "FAM_GDC", "trait_id": "TRAIT_POROUS_ADSORPTION", "primary": True},
    {"product_id": "FAM_GDC", "trait_id": "TRAIT_BAYONET_MOUNT", "primary": False},
    {"product_id": "FAM_GDC", "trait_id": "TRAIT_MODULAR_ASSEMBLY", "primary": False},
    # GDC FLEX
    {"product_id": "FAM_GDC_FLEX", "trait_id": "TRAIT_POROUS_ADSORPTION", "primary": True},
    {"product_id": "FAM_GDC_FLEX", "trait_id": "TRAIT_EXTRACTABLE_RAIL", "primary": False},
    # GDB: Bag filter housing — primary trait is mechanical filtration
    {"product_id": "FAM_GDB", "trait_id": "TRAIT_MECHANICAL_FILTRATION", "primary": True},
    {"product_id": "FAM_GDB", "trait_id": "TRAIT_EXCENTRIC_LOCK", "primary": False},
    {"product_id": "FAM_GDB", "trait_id": "TRAIT_MODULAR_ASSEMBLY", "primary": False},
    # GDP: Panel filter housing
    {"product_id": "FAM_GDP", "trait_id": "TRAIT_MECHANICAL_FILTRATION", "primary": True},
    {"product_id": "FAM_GDP", "trait_id": "TRAIT_MODULAR_ASSEMBLY", "primary": False},
    # GDMI: Insulated housing — has both mechanical filtration AND thermal insulation
    {"product_id": "FAM_GDMI", "trait_id": "TRAIT_THERMAL_INSULATION", "primary": True},
    {"product_id": "FAM_GDMI", "trait_id": "TRAIT_MECHANICAL_FILTRATION", "primary": False},
    {"product_id": "FAM_GDMI", "trait_id": "TRAIT_EXCENTRIC_LOCK", "primary": False},
    {"product_id": "FAM_GDMI", "trait_id": "TRAIT_MODULAR_ASSEMBLY", "primary": False},
    # PFF: Mounting frame
    {"product_id": "FAM_PFF", "trait_id": "TRAIT_MECHANICAL_FILTRATION", "primary": True},
]

# Material -> PhysicalTrait (PROVIDES_TRAIT)
MATERIAL_TRAITS = [
    {"material_id": "MAT_RF", "trait_id": "TRAIT_CORROSION_RESISTANCE_C5"},
    {"material_id": "MAT_SF", "trait_id": "TRAIT_CORROSION_RESISTANCE_C5"},
    {"material_id": "MAT_SF", "trait_id": "TRAIT_CORROSION_RESISTANCE_C5M"},
    {"material_id": "MAT_FZ", "trait_id": "TRAIT_CORROSION_RESISTANCE_C3"},
    {"material_id": "MAT_AZ", "trait_id": "TRAIT_CORROSION_RESISTANCE_C3"},
    {"material_id": "MAT_ZM", "trait_id": "TRAIT_CORROSION_RESISTANCE_C5"},
]

# Application/Environment -> EnvironmentalStressor (EXPOSES_TO)
CONTEXT_STRESSORS = [
    # Hospital
    {"context_id": "APP_HOSPITAL", "stressor_id": "STRESSOR_CHLORINE"},
    {"context_id": "APP_HOSPITAL", "stressor_id": "STRESSOR_HYGIENE_REQUIREMENTS"},
    # Pool
    {"context_id": "APP_POOL", "stressor_id": "STRESSOR_CHLORINE"},
    {"context_id": "APP_POOL", "stressor_id": "STRESSOR_HUMIDITY"},
    # Marine
    {"context_id": "APP_MARINE", "stressor_id": "STRESSOR_SALT_SPRAY"},
    {"context_id": "APP_MARINE", "stressor_id": "STRESSOR_HUMIDITY"},
    # Kitchen (Application)
    {"context_id": "APP_KITCHEN", "stressor_id": "STRESSOR_GREASE_EXPOSURE"},
    {"context_id": "APP_KITCHEN", "stressor_id": "STRESSOR_CHEMICAL_VAPORS"},
    # Kitchen (Environment — for IS_A-aware stressor traversal)
    {"context_id": "ENV_KITCHEN", "stressor_id": "STRESSOR_GREASE_EXPOSURE"},
    {"context_id": "ENV_KITCHEN", "stressor_id": "STRESSOR_CHEMICAL_VAPORS"},
    # Paint shop
    {"context_id": "APP_PAINT", "stressor_id": "STRESSOR_CHEMICAL_VAPORS"},
    {"context_id": "APP_PAINT", "stressor_id": "STRESSOR_PARTICULATE_EXPOSURE"},
    # Powder coating
    {"context_id": "APP_POWDER_COATING", "stressor_id": "STRESSOR_EXPLOSIVE_ATMOSPHERE"},
    {"context_id": "APP_POWDER_COATING", "stressor_id": "STRESSOR_PARTICULATE_EXPOSURE"},
    {"context_id": "APP_POWDER_COATING", "stressor_id": "STRESSOR_CHEMICAL_VAPORS"},
    # Outdoor environment
    {"context_id": "ENV_OUTDOOR", "stressor_id": "STRESSOR_OUTDOOR_CONDENSATION"},
    {"context_id": "ENV_OUTDOOR", "stressor_id": "STRESSOR_HUMIDITY"},
    # ATEX environment
    {"context_id": "ENV_ATEX", "stressor_id": "STRESSOR_EXPLOSIVE_ATMOSPHERE"},
]


# =============================================================================
# SEED FUNCTIONS
# =============================================================================

def create_physical_traits(graph):
    """Create PhysicalTrait nodes."""
    print("\n📦 Creating PhysicalTrait nodes...")
    for trait in PHYSICAL_TRAITS:
        graph.query("""
            MERGE (t:PhysicalTrait {id: $id})
            SET t.name = $name,
                t.description = $description,
                t.category = $category,
                t.keywords = $keywords
        """, trait)
        print(f"   ✅ {trait['id']}: {trait['name']}")
    print(f"   Created {len(PHYSICAL_TRAITS)} PhysicalTrait nodes")


def create_environmental_stressors(graph):
    """Create EnvironmentalStressor nodes."""
    print("\n🌪️ Creating EnvironmentalStressor nodes...")
    for stressor in ENVIRONMENTAL_STRESSORS:
        graph.query("""
            MERGE (s:EnvironmentalStressor {id: $id})
            SET s.name = $name,
                s.description = $description,
                s.category = $category,
                s.keywords = $keywords
        """, stressor)
        print(f"   ✅ {stressor['id']}: {stressor['name']}")
    print(f"   Created {len(ENVIRONMENTAL_STRESSORS)} EnvironmentalStressor nodes")


def create_causal_rules(graph):
    """Create NEUTRALIZED_BY and DEMANDS_TRAIT relationships."""
    print("\n🔗 Creating CausalRule relationships...")

    # NEUTRALIZED_BY: Trait -> Stressor
    for rule in NEUTRALIZED_BY_RULES:
        graph.query("""
            MATCH (t:PhysicalTrait {id: $trait_id})
            MATCH (s:EnvironmentalStressor {id: $stressor_id})
            MERGE (t)-[r:NEUTRALIZED_BY]->(s)
            SET r.severity = $severity,
                r.explanation = $explanation
        """, rule)
        print(f"   ✅ NEUTRALIZED_BY: {rule['trait_id']} --[{rule['severity']}]--> {rule['stressor_id']}")

    # DEMANDS_TRAIT: Stressor -> Trait
    for rule in DEMANDS_TRAIT_RULES:
        graph.query("""
            MATCH (s:EnvironmentalStressor {id: $stressor_id})
            MATCH (t:PhysicalTrait {id: $trait_id})
            MERGE (s)-[r:DEMANDS_TRAIT]->(t)
            SET r.severity = $severity,
                r.explanation = $explanation
        """, rule)
        print(f"   ✅ DEMANDS_TRAIT: {rule['stressor_id']} --[{rule['severity']}]--> {rule['trait_id']}")

    total = len(NEUTRALIZED_BY_RULES) + len(DEMANDS_TRAIT_RULES)
    print(f"   Created {total} causal rules ({len(NEUTRALIZED_BY_RULES)} NEUTRALIZED_BY + {len(DEMANDS_TRAIT_RULES)} DEMANDS_TRAIT)")


def create_bridging_relationships(graph):
    """Connect traits/stressors to existing ProductFamily, Material, Application, Environment nodes."""
    print("\n🌉 Creating bridging relationships to existing schema...")

    # ProductFamily -> PhysicalTrait (HAS_TRAIT)
    print("\n   ProductFamily -> PhysicalTrait:")
    for pt in PRODUCT_TRAITS:
        result = graph.query("""
            MATCH (pf:ProductFamily {id: $product_id})
            MATCH (t:PhysicalTrait {id: $trait_id})
            MERGE (pf)-[r:HAS_TRAIT]->(t)
            SET r.primary = $primary
            RETURN pf.name AS pf_name, t.name AS t_name
        """, pt)
        record = result_single(result)
        if record:
            marker = " (PRIMARY)" if pt["primary"] else ""
            print(f"   ✅ {record['pf_name']} -> {record['t_name']}{marker}")
        else:
            print(f"   ⚠️ SKIP: {pt['product_id']} or {pt['trait_id']} not found")

    # Material -> PhysicalTrait (PROVIDES_TRAIT)
    print("\n   Material -> PhysicalTrait:")
    for mt in MATERIAL_TRAITS:
        result = graph.query("""
            MATCH (m:Material {id: $material_id})
            MATCH (t:PhysicalTrait {id: $trait_id})
            MERGE (m)-[r:PROVIDES_TRAIT]->(t)
            RETURN m.name AS m_name, t.name AS t_name
        """, mt)
        record = result_single(result)
        if record:
            print(f"   ✅ {record['m_name']} -> {record['t_name']}")
        else:
            print(f"   ⚠️ SKIP: {mt['material_id']} or {mt['trait_id']} not found")

    # Application/Environment -> EnvironmentalStressor (EXPOSES_TO)
    print("\n   Context -> EnvironmentalStressor:")
    for cs in CONTEXT_STRESSORS:
        # Try Application first, then Environment
        result = graph.query("""
            OPTIONAL MATCH (app:Application {id: $context_id})
            OPTIONAL MATCH (env:Environment {id: $context_id})
            WITH coalesce(app, env) AS ctx
            WHERE ctx IS NOT NULL
            MATCH (s:EnvironmentalStressor {id: $stressor_id})
            MERGE (ctx)-[r:EXPOSES_TO]->(s)
            RETURN labels(ctx)[0] AS ctx_type, ctx.name AS ctx_name, s.name AS s_name
        """, cs)
        record = result_single(result)
        if record:
            print(f"   ✅ {record['ctx_type']}:{record['ctx_name']} -> {record['s_name']}")
        else:
            print(f"   ⚠️ SKIP: {cs['context_id']} or {cs['stressor_id']} not found")


def create_functional_goals(graph):
    """Create FunctionalGoal nodes and REQUIRES_TRAIT relationships."""
    print("\n🎯 Creating FunctionalGoal nodes...")
    for goal in FUNCTIONAL_GOALS:
        graph.query("""
            MERGE (g:FunctionalGoal {id: $id})
            SET g.name = $name,
                g.description = $description,
                g.keywords = $keywords
        """, goal)
        # Create REQUIRES_TRAIT relationship
        graph.query("""
            MATCH (g:FunctionalGoal {id: $goal_id})
            MATCH (t:PhysicalTrait {id: $trait_id})
            MERGE (g)-[:REQUIRES_TRAIT]->(t)
        """, {"goal_id": goal["id"], "trait_id": goal["required_trait_id"]})
        print(f"   ✅ {goal['id']}: {goal['name']} → {goal['required_trait_id']}")
    print(f"   Created {len(FUNCTIONAL_GOALS)} FunctionalGoal nodes")


def create_logic_gates(graph):
    """Create LogicGate and Parameter nodes with MONITORS, REQUIRES_DATA, TRIGGERS_GATE relationships."""
    print("\n🚦 Creating LogicGate nodes...")
    for gate in LOGIC_GATES:
        # Create LogicGate node
        graph.query("""
            MERGE (g:LogicGate {id: $id})
            SET g.name = $name,
                g.condition_logic = $condition_logic,
                g.physics_explanation = $physics_explanation
        """, gate)
        print(f"   ✅ {gate['id']}: {gate['name']}")

        # MONITORS -> EnvironmentalStressor
        graph.query("""
            MATCH (g:LogicGate {id: $gate_id})
            MATCH (s:EnvironmentalStressor {id: $stressor_id})
            MERGE (g)-[:MONITORS]->(s)
        """, {"gate_id": gate["id"], "stressor_id": gate["monitors_stressor_id"]})
        print(f"      MONITORS → {gate['monitors_stressor_id']}")

        # REQUIRES_DATA -> Parameter nodes
        for param in gate["requires_data"]:
            graph.query("""
                MERGE (p:Parameter {id: $param_id})
                SET p.name = $name,
                    p.property_key = $property_key,
                    p.priority = $priority,
                    p.question = $question,
                    p.unit = $unit
            """, param)
            graph.query("""
                MATCH (g:LogicGate {id: $gate_id})
                MATCH (p:Parameter {id: $param_id})
                MERGE (g)-[:REQUIRES_DATA]->(p)
            """, {"gate_id": gate["id"], "param_id": param["param_id"]})
            print(f"      REQUIRES_DATA → {param['param_id']} ({param['property_key']})")

        # Context -[:TRIGGERS_GATE]-> LogicGate
        for ctx_id in gate["trigger_contexts"]:
            graph.query("""
                OPTIONAL MATCH (app:Application {id: $ctx_id})
                OPTIONAL MATCH (env:Environment {id: $ctx_id})
                WITH coalesce(app, env) AS ctx
                WHERE ctx IS NOT NULL
                MATCH (g:LogicGate {id: $gate_id})
                MERGE (ctx)-[:TRIGGERS_GATE]->(g)
            """, {"ctx_id": ctx_id, "gate_id": gate["id"]})
            print(f"      {ctx_id} -TRIGGERS_GATE-> {gate['id']}")

    print(f"   Created {len(LOGIC_GATES)} LogicGate nodes with parameters")


def create_hard_constraints(graph):
    """Create HardConstraint nodes linked to ProductFamily via HAS_HARD_CONSTRAINT."""
    print("\n🔒 Creating HardConstraint nodes...")
    for i, hc in enumerate(HARD_CONSTRAINTS):
        hc_id = f"HC_{hc['item_id']}_{hc['property_key']}".upper()
        graph.query("""
            MERGE (hc:HardConstraint {id: $hc_id})
            SET hc.property_key = $property_key,
                hc.operator = $operator,
                hc.value = $value,
                hc.error_msg = $error_msg
        """, {**hc, "hc_id": hc_id})
        # Link to ProductFamily
        graph.query("""
            MATCH (pf:ProductFamily {id: $item_id})
            MATCH (hc:HardConstraint {id: $hc_id})
            MERGE (pf)-[:HAS_HARD_CONSTRAINT]->(hc)
        """, {"item_id": hc["item_id"], "hc_id": hc_id})
        print(f"   ✅ {hc_id}: {hc['item_id']} {hc['property_key']} {hc['operator']} {hc['value']}")
    print(f"   Created {len(HARD_CONSTRAINTS)} HardConstraint nodes")


def create_dependency_rules(graph):
    """Create DependencyRule nodes with UPSTREAM_REQUIRES_TRAIT, DOWNSTREAM_PROVIDES_TRAIT, TRIGGERED_BY_STRESSOR."""
    print("\n🔗 Creating DependencyRule nodes...")
    for rule in DEPENDENCY_RULES:
        graph.query("""
            MERGE (dr:DependencyRule {id: $id})
            SET dr.dependency_type = $dependency_type,
                dr.description = $description
        """, rule)
        # UPSTREAM_REQUIRES_TRAIT -> PhysicalTrait
        graph.query("""
            MATCH (dr:DependencyRule {id: $rule_id})
            MATCH (t:PhysicalTrait {id: $trait_id})
            MERGE (dr)-[:UPSTREAM_REQUIRES_TRAIT]->(t)
        """, {"rule_id": rule["id"], "trait_id": rule["upstream_trait_id"]})
        # DOWNSTREAM_PROVIDES_TRAIT -> PhysicalTrait
        graph.query("""
            MATCH (dr:DependencyRule {id: $rule_id})
            MATCH (t:PhysicalTrait {id: $trait_id})
            MERGE (dr)-[:DOWNSTREAM_PROVIDES_TRAIT]->(t)
        """, {"rule_id": rule["id"], "trait_id": rule["downstream_trait_id"]})
        # TRIGGERED_BY_STRESSOR -> EnvironmentalStressor
        graph.query("""
            MATCH (dr:DependencyRule {id: $rule_id})
            MATCH (s:EnvironmentalStressor {id: $stressor_id})
            MERGE (dr)-[:TRIGGERED_BY_STRESSOR]->(s)
        """, {"rule_id": rule["id"], "stressor_id": rule["triggered_by_stressor_id"]})
        print(f"   ✅ {rule['id']}: {rule['dependency_type']} ({rule['upstream_trait_id']} → {rule['downstream_trait_id']})")
    print(f"   Created {len(DEPENDENCY_RULES)} DependencyRule nodes")


def create_optimization_strategies(graph):
    """Create Strategy nodes linked to ProductFamily via OPTIMIZATION_STRATEGY."""
    print("\n📊 Creating Strategy nodes...")
    for strat in OPTIMIZATION_STRATEGIES:
        strat_id = f"STRAT_{strat['item_id']}_{strat['sort_property']}".upper()
        graph.query("""
            MERGE (s:Strategy {id: $strat_id})
            SET s.name = $name,
                s.sort_property = $sort_property,
                s.sort_order = $sort_order,
                s.description = $description
        """, {**strat, "strat_id": strat_id})
        # Link to ProductFamily
        graph.query("""
            MATCH (pf:ProductFamily {id: $item_id})
            MATCH (s:Strategy {id: $strat_id})
            MERGE (pf)-[:OPTIMIZATION_STRATEGY]->(s)
        """, {"item_id": strat["item_id"], "strat_id": strat_id})
        print(f"   ✅ {strat_id}: {strat['name']} ({strat['sort_property']} {strat['sort_order']})")
    print(f"   Created {len(OPTIMIZATION_STRATEGIES)} Strategy nodes")


def create_capacity_rules(graph):
    """Create CapacityRule nodes linked to ProductFamily via HAS_CAPACITY."""
    print("\n📐 Creating CapacityRule nodes...")
    for cap in CAPACITY_RULES:
        params = {
            **cap,
            "capacity_per_component": cap.get("capacity_per_component"),
            "component_count_key": cap.get("component_count_key"),
        }
        graph.query("""
            MERGE (cr:CapacityRule {id: $id})
            SET cr.module_descriptor = $module_descriptor,
                cr.input_requirement = $input_requirement,
                cr.output_rating = $output_rating,
                cr.assumption = $assumption,
                cr.description = $description,
                cr.capacity_per_component = $capacity_per_component,
                cr.component_count_key = $component_count_key
        """, params)
        # Link to ProductFamily
        graph.query("""
            MATCH (pf:ProductFamily {id: $item_id})
            MATCH (cr:CapacityRule {id: $id})
            MERGE (pf)-[:HAS_CAPACITY]->(cr)
        """, cap)
        print(f"   ✅ {cap['id']}: {cap['input_requirement']} → {cap['output_rating']} per {cap['module_descriptor']}")
    print(f"   Created {len(CAPACITY_RULES)} CapacityRule nodes")


def fix_gdc_flex_capacity_units(graph):
    """Fix GDC_FLEX SizeProperty capacity_units values.

    The FLEX variant has fewer cartridges per module than standard GDC
    due to rail mounting mechanism. This corrects the auto-generated values.
    """
    print("\n🔧 Fixing GDC FLEX capacity_units (SizeProperty values)...")
    corrections = {
        "SP_DIM_300x300_GDC_FLEX_CAPACITY": 3,
        "SP_DIM_300x600_GDC_FLEX_CAPACITY": 7,
        "SP_DIM_600x300_GDC_FLEX_CAPACITY": 7,
        "SP_DIM_600x600_GDC_FLEX_CAPACITY": 14,
        "SP_DIM_600x900_GDC_FLEX_CAPACITY": 20,
        "SP_DIM_900x600_GDC_FLEX_CAPACITY": 20,
        "SP_DIM_600x1200_GDC_FLEX_CAPACITY": 28,
        "SP_DIM_1200x600_GDC_FLEX_CAPACITY": 28,
        "SP_DIM_900x900_GDC_FLEX_CAPACITY": 30,
        "SP_DIM_900x1200_GDC_FLEX_CAPACITY": 40,
        "SP_DIM_1200x900_GDC_FLEX_CAPACITY": 40,
        "SP_DIM_1200x1200_GDC_FLEX_CAPACITY": 56,
    }
    for sp_id, new_value in corrections.items():
        graph.query("""
            MATCH (sp:SizeProperty {id: $sp_id})
            SET sp.value = $new_value
        """, {"sp_id": sp_id, "new_value": new_value})
        print(f"   ✅ {sp_id} → {new_value}")
    print(f"   Fixed {len(corrections)} SizeProperty nodes")


def create_indexes(graph):
    """Create indexes for trait-based queries."""
    print("\n📇 Creating indexes...")
    indexes = [
        "CREATE INDEX trait_id IF NOT EXISTS FOR (t:PhysicalTrait) ON (t.id)",
        "CREATE INDEX trait_name IF NOT EXISTS FOR (t:PhysicalTrait) ON (t.name)",
        "CREATE INDEX stressor_id IF NOT EXISTS FOR (s:EnvironmentalStressor) ON (s.id)",
        "CREATE INDEX stressor_name IF NOT EXISTS FOR (s:EnvironmentalStressor) ON (s.name)",
        "CREATE INDEX goal_id IF NOT EXISTS FOR (g:FunctionalGoal) ON (g.id)",
        "CREATE INDEX gate_id IF NOT EXISTS FOR (g:LogicGate) ON (g.id)",
        "CREATE INDEX param_id IF NOT EXISTS FOR (p:Parameter) ON (p.id)",
        "CREATE INDEX constraint_id IF NOT EXISTS FOR (hc:HardConstraint) ON (hc.id)",
        "CREATE INDEX dependency_rule_id IF NOT EXISTS FOR (dr:DependencyRule) ON (dr.id)",
        "CREATE INDEX strategy_id IF NOT EXISTS FOR (s:Strategy) ON (s.id)",
        "CREATE INDEX capacity_rule_id IF NOT EXISTS FOR (cr:CapacityRule) ON (cr.id)",
    ]
    for idx in indexes:
        graph.query(idx)
        print(f"   ✅ {idx.split('IF NOT EXISTS')[0].strip()}")


def verify_trait_graph(graph):
    """Verify the trait graph is correctly seeded."""
    print("\n🔍 Verifying trait graph...")
    # Count nodes
    result = graph.query("""
        MATCH (t:PhysicalTrait) RETURN count(t) AS cnt
    """)
    trait_count = result_single(result)["cnt"]
    print(f"   PhysicalTrait nodes: {trait_count}")

    result = graph.query("""
        MATCH (s:EnvironmentalStressor) RETURN count(s) AS cnt
    """)
    stressor_count = result_single(result)["cnt"]
    print(f"   EnvironmentalStressor nodes: {stressor_count}")

    # Count relationships
    result = graph.query("""
        MATCH ()-[r:NEUTRALIZED_BY]->() RETURN count(r) AS cnt
    """)
    neut_count = result_single(result)["cnt"]

    result = graph.query("""
        MATCH ()-[r:DEMANDS_TRAIT]->() RETURN count(r) AS cnt
    """)
    demands_count = result_single(result)["cnt"]
    print(f"   NEUTRALIZED_BY relationships: {neut_count}")
    print(f"   DEMANDS_TRAIT relationships: {demands_count}")

    result = graph.query("""
        MATCH ()-[r:HAS_TRAIT]->() RETURN count(r) AS cnt
    """)
    has_trait_count = result_single(result)["cnt"]

    result = graph.query("""
        MATCH ()-[r:PROVIDES_TRAIT]->() RETURN count(r) AS cnt
    """)
    provides_count = result_single(result)["cnt"]

    result = graph.query("""
        MATCH ()-[r:EXPOSES_TO]->() RETURN count(r) AS cnt
    """)
    exposes_count = result_single(result)["cnt"]
    print(f"   HAS_TRAIT relationships: {has_trait_count}")
    print(f"   PROVIDES_TRAIT relationships: {provides_count}")
    print(f"   EXPOSES_TO relationships: {exposes_count}")

    # v2.0 node counts
    for label in ["LogicGate", "Parameter", "HardConstraint", "DependencyRule", "Strategy", "CapacityRule"]:
        result = graph.query(f"MATCH (n:{label}) RETURN count(n) AS cnt")
        cnt = result_single(result)["cnt"]
        print(f"   {label} nodes: {cnt}")

    # v2.0 relationship counts
    for rel_type in ["MONITORS", "REQUIRES_DATA", "TRIGGERS_GATE", "HAS_HARD_CONSTRAINT",
                     "UPSTREAM_REQUIRES_TRAIT", "DOWNSTREAM_PROVIDES_TRAIT", "TRIGGERED_BY_STRESSOR",
                     "OPTIMIZATION_STRATEGY", "HAS_CAPACITY"]:
        result = graph.query(f"MATCH ()-[r:{rel_type}]->() RETURN count(r) AS cnt")
        cnt = result_single(result)["cnt"]
        print(f"   {rel_type} relationships: {cnt}")

    # Smoke test: Outdoor + GDB should trigger veto
    print("\n   🧪 Smoke test: 'outdoor GDB' scenario")
    result = graph.query("""
        MATCH (env:Environment {id: 'ENV_OUTDOOR'})-[:EXPOSES_TO]->(s:EnvironmentalStressor)
        MATCH (s)-[r:DEMANDS_TRAIT {severity: 'CRITICAL'}]->(demanded:PhysicalTrait)
        OPTIONAL MATCH (pf:ProductFamily {id: 'FAM_GDB'})-[:HAS_TRAIT]->(demanded)
        RETURN s.name AS stressor, demanded.name AS demanded_trait,
               CASE WHEN pf IS NULL THEN 'MISSING → VETO' ELSE 'PRESENT → OK' END AS status
    """)
    for record in result_to_dicts(result):
        print(f"   {record['stressor']} demands {record['demanded_trait']}: {record['status']}")

    # Smoke test: Kitchen + GDC should trigger NEUTRALIZED_BY warning
    print("\n   🧪 Smoke test: 'kitchen GDC' scenario")
    result = graph.query("""
        MATCH (app:Application {id: 'APP_KITCHEN'})-[:EXPOSES_TO]->(s:EnvironmentalStressor)
        MATCH (t:PhysicalTrait)<-[:HAS_TRAIT {primary: true}]-(pf:ProductFamily {id: 'FAM_GDC'})
        OPTIONAL MATCH (t)-[n:NEUTRALIZED_BY]->(s)
        WHERE n IS NOT NULL
        RETURN pf.name AS product, t.name AS trait, s.name AS stressor,
               n.severity AS severity, n.explanation AS explanation
    """)
    records = list(result)
    if records:
        for record in records:
            print(f"   {record['product']}: {record['trait']} NEUTRALIZED_BY {record['stressor']} [{record['severity']}]")
    else:
        print("   No neutralization detected (check trait assignments)")


def main():
    from falkordb import FalkorDB

    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", 6379))
    password = os.getenv("FALKORDB_PASSWORD", None)
    graph_name = os.getenv("FALKORDB_GRAPH", "hvac")

    # FalkorDB connects with defaults if env vars not set

    print("=" * 60)
    print("HVAC TRAIT SEED SCRIPT v2.0 — Neuro-Symbolic Meta-Graph")
    print("=" * 60)
    print("\nSeeds PhysicalTrait, EnvironmentalStressor, CausalRule,")
    print("LogicGate, HardConstraint, DependencyRule, Strategy, CapacityRule")
    print("nodes alongside the existing Layer 2 (Physics) schema.")
    print("All operations use MERGE — safe to run multiple times.")

    print(f"\nConnecting to FalkorDB at {uri}...")
    db = FalkorDB(host=host, port=port, password=password)
    graph = db.select_graph(graph_name)

    try:
        result = graph.query("RETURN 1 AS test")
        if result_single(result)["test"] != 1:
            raise Exception("Connection test failed")
        print("Connected successfully!")

        # Phase 1: Core trait layer
        create_physical_traits(graph)
        create_environmental_stressors(graph)
        create_functional_goals(graph)
        create_causal_rules(graph)
        create_bridging_relationships(graph)

        # Phase 2: Logic gates, constraints, dependencies
        create_logic_gates(graph)
        create_hard_constraints(graph)
        create_dependency_rules(graph)
        create_optimization_strategies(graph)
        create_capacity_rules(graph)
        fix_gdc_flex_capacity_units(graph)

        create_indexes(graph)
        verify_trait_graph(graph)

        print("\n" + "=" * 60)
        print("TRAIT SEED v2.0 COMPLETE")
        print("=" * 60)
        print("\n--- Phase 1 (Trait Layer) ---")
        print("✅ PhysicalTrait nodes (product capabilities)")
        print("✅ EnvironmentalStressor nodes (attack vectors)")
        print("✅ FunctionalGoal nodes (user intents → required traits)")
        print("✅ NEUTRALIZED_BY relationships (trait defeated by stressor)")
        print("✅ DEMANDS_TRAIT relationships (stressor requires trait)")
        print("✅ REQUIRES_TRAIT relationships (goal → needed trait)")
        print("✅ HAS_TRAIT bridges (ProductFamily -> PhysicalTrait)")
        print("✅ PROVIDES_TRAIT bridges (Material -> PhysicalTrait)")
        print("✅ EXPOSES_TO bridges (Application/Environment -> Stressor)")
        print("\n--- Phase 2 (Gates, Constraints, Dependencies) ---")
        print("✅ LogicGate nodes (conditional vetoes with data requirements)")
        print("✅ Parameter nodes (gate data requirements with property_key)")
        print("✅ HardConstraint nodes (physical limits with operator/value)")
        print("✅ DependencyRule nodes (graph-driven multi-item assembly)")
        print("✅ Strategy nodes (optimization preferences per item)")
        print("✅ CapacityRule nodes (throughput/sizing from graph)")

    finally:
        pass  # FalkorDB connection auto-managed


if __name__ == "__main__":
    main()
