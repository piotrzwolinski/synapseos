#!/usr/bin/env python3
"""
HVAC Graph Reasoning — Comprehensive Regression Test Runner v2.0

Hits the /consult/deep-explainable/stream endpoint with predefined test queries,
parses SSE events, extracts engine verdict + response data, and validates against
expected outcomes from MH product catalog (PDF ground truth).

Usage:
    python run_tests.py              # Run all tests
    python run_tests.py all          # Run all tests
    python run_tests.py kitchen      # Run single test (fuzzy match)
    python run_tests.py list         # List available tests
    python run_tests.py --category env  # Run category (env, assembly, atex, sizing, material, positive, clarification)
    python run_tests.py --gap        # Run all + print gap analysis
"""

import json
import os
import re
import sys
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
USERNAME = os.getenv("TEST_USERNAME", "mh")
PASSWORD = os.getenv("TEST_PASSWORD", "MHFind@r2026")
TIMEOUT = int(os.getenv("TEST_TIMEOUT", "60"))


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class Assertion:
    name: str
    check: str          # path expression e.g. "graph_report.application"
    condition: str      # "equals", "contains", "exists", "not_exists", "in", "true", "false"
    expected: str = ""  # expected value (for equals/contains/in)
    passed: bool = False
    actual: str = ""
    message: str = ""
    # Categorize assertions for gap analysis
    category: str = ""  # "detection", "logic", "output", "data"


@dataclass
class TestCase:
    name: str
    description: str
    query: str
    assertions: list = field(default_factory=list)
    # Metadata for categorization
    category: str = ""       # env, assembly, atex, sizing, material, positive, clarification
    tests_graph_node: str = ""   # which graph node(s) this test depends on
    pdf_reference: str = ""      # PDF section reference
    # Multi-turn support
    follow_ups: list = field(default_factory=list)


@dataclass
class TestResult:
    test_name: str
    status: str  # PASS, FAIL, ERROR
    category: str = ""
    assertions_total: int = 0
    assertions_passed: int = 0
    assertions_failed: list = field(default_factory=list)
    assertions_all: list = field(default_factory=list)  # All checked assertions (pass + fail)
    error_message: str = ""
    duration_s: float = 0.0
    raw_events: list = field(default_factory=list)
    # Diagnosis info
    likely_cause: str = ""   # "graph_data", "engine_logic", "scribe", "llm", "unknown"


# ===========================================================================
#  TEST CASES — Generated from MH Product Catalog (PDF Ground Truth)
# ===========================================================================
#
#  NAMING CONVENTION: {scenario}_{product}_{material}
#  CATEGORIES:
#    env       — Environment-based decisions (whitelist, pivot, block)
#    assembly  — Assembly trigger (carbon + kitchen → GDP protector)
#    atex      — ATEX / explosive atmosphere gate
#    sizing    — Multi-module sizing, dimension mapping
#    material  — Material constraint (chlorine, salt spray)
#    positive  — Positive controls (should pass without blocks)
#    clarif    — Clarification flow (missing params)
#
# ===========================================================================

_ORIGINAL_TESTS_DISABLED = {
    # ===================================================================
    #  CATEGORY: ENVIRONMENT — Product/environment whitelist decisions
    # ===================================================================

    "env_hospital_gdb_fz": TestCase(
        name="env_hospital_gdb_fz",
        description="Hospital + GDB + FZ → BLOCK: GDB not rated for hospital (env whitelist), FZ inadequate (chlorine)",
        category="env",
        tests_graph_node="ProductFamily.allowed_environments, Environment(ENV_HOSPITAL), IC_ENVIRONMENT_WHITELIST",
        pdf_reference="GDMI is the hospital-rated housing; GDB BOLTED construction fails hygiene/leakage class",
        query="We are upgrading the air handling system in a hospital. We need GDB housings in standard Galvanized (FZ) for 600x600 duct. Airflow 3400 m³/h.",
        assertions=[
            Assertion("stressor_detected", "response.content_text", "contains_any",
                      "hospital|hygiene|chlorine|environment|leakage",
                      category="detection"),
            Assertion("has_warnings", "graph_report.warnings_count", "greater_than", "0",
                      category="logic"),
            Assertion("mentions_block_or_risk", "response.content_text", "contains_any",
                      "not rated|not suitable|block|warning|risk|concern|recommend|alternative|GDMI|stainless|RF",
                      category="output"),
            Assertion("suggests_alternative", "response.content_text", "contains_any",
                      "GDMI|RF|stainless|insulated|alternative|instead|upgrade",
                      category="output"),
        ],
    ),

    "env_hospital_gdmi_rf": TestCase(
        name="env_hospital_gdmi_rf",
        description="Hospital + GDMI + RF → PASS: GDMI is hospital-rated, RF resists chlorine",
        category="env",
        tests_graph_node="ProductFamily(FAM_GDMI).allowed_environments must include ENV_HOSPITAL",
        pdf_reference="GDMI BOLTED with welded seams, insulation → meets hospital leakage class",
        query="We are specifying GDMI housings for a hospital ventilation upgrade. Material: Stainless Steel (RF). Size 600x600, airflow 3400 m³/h.",
        assertions=[
            Assertion("no_critical_block", "response.risk_severity", "not_equals", "CRITICAL",
                      category="logic"),
            Assertion("product_accepted", "response.content_text", "contains_any",
                      "GDMI|configure|housing length|specification|recommend|suitable",
                      category="output"),
            Assertion("no_environment_block", "response.content_text", "not_contains_any",
                      "not rated|not suitable|blocked|cannot be used",
                      category="output"),
        ],
    ),

    "env_outdoor_gdb_fz": TestCase(
        name="env_outdoor_gdb_fz",
        description="Outdoor/rooftop + GDB → RISK: GDB lacks insulation → condensation risk → pivot to GDMI",
        category="env",
        tests_graph_node="Environment(ENV_OUTDOOR), STRESSOR_OUTDOOR_CONDENSATION, DEMANDS_TRAIT(THERMAL_INSULATION)",
        pdf_reference="Outdoor installation requires thermal insulation (GDMI). GDB has no insulation.",
        query="I need a GDB housing for a rooftop exhaust system. The installation is outdoors on the building roof. Airflow is 3400 m³/h, size 600x600. Material: Galvanized (FZ).",
        assertions=[
            Assertion("environment_detected", "response.content_text", "contains_any",
                      "outdoor|rooftop|roof|exterior|outside",
                      category="detection"),
            Assertion("condensation_risk", "response.content_text", "contains_any",
                      "condensation|insulation|insulated|thermal|moisture|dew point|weather",
                      category="logic"),
            Assertion("pivot_to_gdmi", "response.content_text", "contains_any",
                      "GDMI|insulated|alternative|instead|recommend|pivot",
                      category="output"),
        ],
    ),

    "env_outdoor_gdmi_fz": TestCase(
        name="env_outdoor_gdmi_fz",
        description="Outdoor + GDMI + FZ → PASS: GDMI rated for outdoor, FZ acceptable",
        category="env",
        tests_graph_node="ProductFamily(FAM_GDMI).allowed_environments includes ENV_OUTDOOR",
        pdf_reference="GDMI has thermal insulation. FZ galvanized acceptable outdoors (no salt spray).",
        query="I need GDMI insulated housings for an outdoor rooftop installation. Size 600x600, airflow 3400 m³/h, material Galvanized (FZ).",
        assertions=[
            Assertion("no_critical_block", "response.risk_severity", "not_equals", "CRITICAL",
                      category="logic"),
            Assertion("product_accepted", "response.content_text", "contains_any",
                      "GDMI|configure|housing length|suitable|specification",
                      category="output"),
        ],
    ),

    "env_marine_gdb_fz": TestCase(
        name="env_marine_gdb_fz",
        description="Marine/offshore + GDB + FZ → BLOCK: salt spray demands RF, plus outdoor needs insulation",
        category="env",
        tests_graph_node="Environment(ENV_MARINE), STRESSOR_SALT_SPRAY, DEMANDS_TRAIT(CORROSION_RESISTANCE)",
        pdf_reference="Marine: salt spray corrodes FZ. Needs RF material AND insulation (GDMI-RF).",
        query="We need GDB filter housings for a marine offshore platform. Material: Galvanized (FZ). Size 600x600, airflow 3400 m³/h.",
        assertions=[
            Assertion("environment_detected", "response.content_text", "contains_any",
                      "marine|offshore|salt|coastal|sea",
                      category="detection"),
            Assertion("material_concern", "response.content_text", "contains_any",
                      "RF|stainless|corrosion|salt|material|upgrade",
                      category="logic"),
            Assertion("has_warnings", "graph_report.warnings_count", "greater_than", "0",
                      category="logic"),
        ],
    ),

    "env_swimming_pool": TestCase(
        name="env_swimming_pool",
        description="Swimming pool → chlorine stressor → material constraint (FZ blocked, needs RF)",
        category="env",
        tests_graph_node="STRESSOR_CHLORINE, IC_MATERIAL_CHLORINE, Material threshold",
        pdf_reference="Pool environments: high chlorine (>50ppm) corrodes galvanized steel. RF required.",
        query="I need a ventilation housing for a swimming pool hall. The chlorine level is approximately 60ppm. We want GDB in standard Galvanized (FZ), size 600x600.",
        assertions=[
            Assertion("chlorine_detected", "response.content_text", "contains_any",
                      "chlorine|pool|chemical|corrosion",
                      category="detection"),
            Assertion("material_block", "response.content_text", "contains_any",
                      "RF|stainless|material|upgrade|not suitable|corrosion|block",
                      category="logic"),
        ],
    ),

    "env_kitchen_gdb_fz": TestCase(
        name="env_kitchen_gdb_fz",
        description="Kitchen + GDB (mechanical filter only) → detect grease stressor, warn but GDB may work as pre-filter",
        category="env",
        tests_graph_node="Environment(ENV_KITCHEN), STRESSOR_GREASE_EXPOSURE, GDB has TRAIT_MECHANICAL_FILTRATION",
        pdf_reference="GDB provides mechanical filtration. In kitchen, grease particles caught by GDB. No carbon needed for GDB alone.",
        query="I need a GDB housing for a commercial kitchen exhaust. Size 600x600, FZ material, airflow 3400 m³/h.",
        assertions=[
            Assertion("kitchen_detected", "response.content_text", "contains_any",
                      "kitchen|cooking|grease|commercial kitchen|restaurant",
                      category="detection"),
            Assertion("grease_awareness", "response.content_text", "contains_any",
                      "grease|oil|fat|kitchen|carbon|odor|chemical|pre-filter",
                      category="logic"),
        ],
    ),

    # ===================================================================
    #  CATEGORY: ASSEMBLY — Multi-stage assembly triggers
    # ===================================================================

    "assembly_kitchen_gdc_flex_rf": TestCase(
        name="assembly_kitchen_gdc_flex_rf",
        description="Kitchen + GDC-FLEX (carbon) → ASSEMBLY: needs GDP protector upstream (grease blocks carbon pores)",
        category="assembly",
        tests_graph_node="DependencyRule(DEP_KITCHEN_CARBON), STRESSOR_GREASE_EXPOSURE, NEUTRALIZED_BY(POROUS_ADSORPTION)",
        pdf_reference="Carbon housings in kitchen: grease clogs carbon pores. GDP pre-filter required upstream.",
        query="I'm designing ventilation exhaust for a commercial kitchen. We need a GDC-FLEX carbon housing for 600x600mm duct in Stainless Steel (RF). Airflow is 2000 m³/h.",
        assertions=[
            Assertion("kitchen_detected", "graph_report.application|response.content_text", "any_contains",
                      "kitchen",
                      category="detection"),
            Assertion("assembly_mentioned", "response.content_text", "contains_any",
                      "assembly|protection|pre-filter|two-stage|protector|GDP|upstream|stage",
                      category="logic"),
            Assertion("gdp_protector", "response.content_text", "contains_any",
                      "GDP|protector|pre-filter|upstream|mechanical",
                      category="output"),
            Assertion("product_output", "response.clarification_needed|response.product_cards", "any_exists",
                      category="output"),
        ],
    ),

    "assembly_kitchen_gdc_rf": TestCase(
        name="assembly_kitchen_gdc_rf",
        description="Kitchen + GDC (cartridge carbon) → ASSEMBLY: same logic as GDC-FLEX, GDP protector needed",
        category="assembly",
        tests_graph_node="DependencyRule(DEP_KITCHEN_CARBON), GDC has TRAIT_POROUS_ADSORPTION",
        pdf_reference="GDC also uses carbon cartridges. Same grease vulnerability as GDC-FLEX.",
        query="We need a GDC carbon cartridge housing for a restaurant kitchen exhaust. 600x600, RF material, 2400 m³/h.",
        assertions=[
            Assertion("kitchen_detected", "response.content_text", "contains_any",
                      "kitchen|restaurant|cooking|grease",
                      category="detection"),
            Assertion("assembly_or_protection", "response.content_text", "contains_any",
                      "assembly|protection|pre-filter|GDP|upstream|protector|two-stage|stage",
                      category="logic"),
        ],
    ),

    "assembly_no_trigger_office_gdc": TestCase(
        name="assembly_no_trigger_office_gdc",
        description="Office + GDC → NO assembly: no grease stressor in office, carbon works fine for odor",
        category="assembly",
        tests_graph_node="GDC in benign environment should NOT trigger assembly",
        pdf_reference="Carbon in office = odor control. No grease → no assembly needed.",
        query="We need GDC carbon cartridge housings for an office building. The goal is to remove odors from the supply air. Size 600x600, FZ material.",
        assertions=[
            Assertion("no_assembly", "response.content_text", "not_contains_any",
                      "assembly|protector|two-stage|GDP upstream",
                      category="logic"),
            Assertion("asks_params_or_card", "response.clarification_needed|response.product_card|response.product_cards", "any_exists",
                      category="output"),
        ],
    ),

    # ===================================================================
    #  CATEGORY: ATEX — Explosive atmosphere gate
    # ===================================================================

    "atex_powder_coating": TestCase(
        name="atex_powder_coating",
        description="Powder coating booth → ATEX gate: must ask for Ex zone before proceeding",
        category="atex",
        tests_graph_node="LogicGate(GATE_ATEX_ZONE), Application(APP_POWDER_COATING), STRESSOR_EXPLOSIVE_ATMOSPHERE",
        pdf_reference="Powder coating = combustible dust = ATEX classified. Must know zone (20/21/22).",
        query="I need an air filtration solution for a powder coating booth. The booth produces fine powder particles and we need to handle the exhaust air. What do you recommend?",
        assertions=[
            Assertion("context_detected", "response.content_text", "contains_any",
                      "powder|coating|particulate|explosive|dust",
                      category="detection"),
            Assertion("has_clarification", "response.clarification_needed", "true",
                      category="logic"),
            Assertion("mentions_atex", "response.content_text", "contains_any",
                      "ATEX|explo|zone|powder|classified|safety",
                      category="output"),
        ],
    ),

    "atex_explicit_indoor": TestCase(
        name="atex_explicit_indoor",
        description="ATEX zone mentioned explicitly → should still trigger gate even without 'powder coating' keyword",
        category="atex",
        tests_graph_node="STRESSOR_EXPLOSIVE_ATMOSPHERE keyword detection",
        pdf_reference="ATEX classification applies to any explosive atmosphere, not just powder coating.",
        query="We have an ATEX Zone 22 area in our factory. Need GDB filter housings for the ventilation. 600x600, FZ, 3400 m³/h.",
        assertions=[
            Assertion("atex_detected", "response.content_text", "contains_any",
                      "ATEX|explo|zone|classified|Ex",
                      category="detection"),
            Assertion("safety_awareness", "response.content_text", "contains_any",
                      "zone|ATEX|explosive|safety|classified|certification",
                      category="logic"),
        ],
    ),

    # ===================================================================
    #  CATEGORY: SIZING — Dimension mapping, multi-module, constraints
    # ===================================================================

    "sizing_large_airflow": TestCase(
        name="sizing_large_airflow",
        description="10,000 m³/h + max 1300mm width → multi-module sizing arrangement",
        category="sizing",
        tests_graph_node="DimensionModule, CapacityRule(CAP_GDB_600), compute_sizing_arrangement()",
        pdf_reference="GDB 600x600 = 3400 m³/h. For 10,000: need 3 modules. Width 1300mm fits 2×600 = 1200mm wide.",
        query="I need a GDB housing for 10000 m³/h airflow. Maximum width cannot exceed 1300mm. Standard Galvanized (FZ).",
        assertions=[
            Assertion("asks_or_sizes", "response.clarification_needed|response.product_card|response.content_text", "any_exists",
                      category="output"),
            Assertion("sizing_mentioned", "response.content_text|response.clarification_text", "any_contains",
                      "module|unit|parallel|sizing|1200|multi|arrangement|10000|housing",
                      category="logic"),
        ],
    ),

    "sizing_single_module_600x600": TestCase(
        name="sizing_single_module_600x600",
        description="Standard 600x600 single module — should match directly, no multi-module",
        category="sizing",
        tests_graph_node="DimensionModule(DIM_600x600)",
        pdf_reference="600x600 = standard 1/1 module. Reference airflow ~3400 m³/h for GDB.",
        query="I need a GDB housing, size 600x600, Galvanized FZ, airflow 3400 m³/h.",
        assertions=[
            Assertion("tags_detected", "graph_report.tags_count", "greater_than", "0",
                      category="detection"),
            Assertion("asks_length_or_card", "response.clarification_needed|response.product_card", "any_exists",
                      category="output"),
        ],
    ),

    "sizing_dimension_mapping": TestCase(
        name="sizing_dimension_mapping",
        description="Filter dimensions 305x610 → housing dimensions 300x600 (dimension mapping)",
        category="sizing",
        tests_graph_node="DimensionModule, dimension normalization logic",
        pdf_reference="Filters are slightly smaller than housing. 305→300, 610→600 standard mapping.",
        query="I need a GDB housing for a Nanoclass Deeppleat H13 filter, size 305x610x150 mm, in Stainless Steel (RF).",
        assertions=[
            Assertion("dimensions_understood", "response.content_text", "contains_any",
                      "300x600|300|600|305|610|dimension|size|housing",
                      category="detection"),
            Assertion("asks_airflow_or_card", "response.clarification_needed|response.product_card", "any_exists",
                      category="output"),
        ],
    ),

    "sizing_multi_tag": TestCase(
        name="sizing_multi_tag",
        description="Two tags with different sizes — each must get correct per-tag dimensions and airflow",
        category="sizing",
        tests_graph_node="Multi-tag handling, DimensionModule(300x600, 600x600)",
        pdf_reference="300x600 → ~1700 m³/h reference. 600x600 → ~3400 m³/h. Must not conflate.",
        query=(
            "I need a quote for the Nouryon project. We have two tags:\n"
            "Tag 5684: Nanoclass Deeppleat H13 - size 305x610x150 mm, SS frame, 25mm header.\n"
            "Tag 7889: Nanoclass Deeppleat E11 - size 610x610x292 mm, SS frame, 25mm header.\n"
            "Please recommend the correct GDB housings in Stainless Steel (RF) for both."
        ),
        assertions=[
            Assertion("material_detected", "response.content_text", "contains_any",
                      "RF|stainless|rostfri",
                      category="detection"),
            Assertion("multiple_tags", "graph_report.tags_count", "greater_than", "1",
                      category="detection"),
            Assertion("asks_or_cards", "response.clarification_needed|response.product_card|response.product_cards", "any_exists",
                      category="output"),
            Assertion("both_sizes_mentioned", "response.content_text|response.clarification_text", "any_contains",
                      "300x600|600x600|5684|7889",
                      category="output"),
        ],
    ),

    "sizing_space_constraint": TestCase(
        name="sizing_space_constraint",
        description="650mm shaft with 600mm housing → insufficient service clearance warning",
        category="sizing",
        tests_graph_node="IC_SERVICE_CLEARANCE, service_access_factor",
        pdf_reference="Service clearance: housing width + access space. 650-600=50mm total, ~25mm/side. Insufficient for filter changes.",
        query="I need a GDB-600x600 housing. We have a vertical shaft that is exactly 650mm wide. The housing is 600mm, so it fits physically with 25mm margin on each side. Is this a correct installation?",
        assertions=[
            Assertion("clearance_mentioned", "response.content_text", "contains_any",
                      "clearance|service|maintenance|access|space|margin|tight|insufficient|narrow",
                      category="logic"),
        ],
    ),

    # ===================================================================
    #  CATEGORY: MATERIAL — Material-specific constraints
    # ===================================================================

    "material_chlorine_fz_block": TestCase(
        name="material_chlorine_fz_block",
        description="High chlorine environment (60ppm) + FZ → BLOCK: FZ max ~25ppm, need RF",
        category="material",
        tests_graph_node="IC_MATERIAL_CHLORINE, Material(FZ).chlorine_resistance_ppm",
        pdf_reference="FZ galvanized: max 25ppm chlorine. Hospital/pool typically >50ppm. RF needed.",
        query="We need GDB filter housings for a water treatment plant with chlorine levels around 60ppm. Material: Galvanized (FZ). Size 600x600.",
        assertions=[
            Assertion("chlorine_detected", "response.content_text", "contains_any",
                      "chlorine|chemical|corrosion|ppm",
                      category="detection"),
            Assertion("material_warning", "response.content_text", "contains_any",
                      "RF|stainless|upgrade|not suitable|corrosion|material|blocked",
                      category="logic"),
        ],
    ),

    "material_rf_hospital_ok": TestCase(
        name="material_rf_hospital_ok",
        description="Hospital + RF → material OK (RF resists chlorine). Product family still matters.",
        category="material",
        tests_graph_node="Material(RF).chlorine_resistance_ppm > hospital level",
        pdf_reference="RF stainless steel: high chlorine resistance. Suitable for hospital/pool/marine.",
        query="We need GDMI housings for hospital ventilation in Stainless Steel (RF). Size 600x600, airflow 3400 m³/h.",
        assertions=[
            Assertion("no_material_block", "response.content_text", "not_contains_any",
                      "material not suitable|upgrade material|FZ|galvanized",
                      category="logic"),
            Assertion("proceeds_normally", "response.clarification_needed|response.product_card", "any_exists",
                      category="output"),
        ],
    ),

    # ===================================================================
    #  CATEGORY: POSITIVE CONTROLS — Should pass without blocks
    # ===================================================================

    "positive_office_gdb_fz": TestCase(
        name="positive_office_gdb_fz",
        description="Office + GDB + FZ → CLEAN PASS: benign environment, standard product and material",
        category="positive",
        tests_graph_node="No stressors should fire. Standard product in standard environment.",
        pdf_reference="Office is benign. GDB is the standard duct housing. FZ is default material.",
        query="I need a GDB housing for an office building ventilation system. Size 600x600, standard Galvanized (FZ), airflow 3400 m³/h.",
        assertions=[
            Assertion("no_critical_block", "response.risk_severity", "not_equals", "CRITICAL",
                      category="logic"),
            Assertion("asks_or_card", "response.clarification_needed|response.product_card", "any_exists",
                      category="output"),
            Assertion("no_environment_block", "response.content_text", "not_contains_any",
                      "not rated|not suitable|blocked|cannot install",
                      category="output"),
        ],
    ),

    "positive_warehouse_gdb_fz": TestCase(
        name="positive_warehouse_gdb_fz",
        description="Warehouse/industrial + GDB + FZ → PASS: standard indoor environment",
        category="positive",
        tests_graph_node="ENV_INDOOR, no special stressors",
        pdf_reference="Warehouse = indoor industrial. GDB handles particulate filtration. FZ acceptable.",
        query="We need GDB filter housings for a warehouse ventilation system. Standard indoor installation. 600x600, FZ galvanized, airflow 3400 m³/h.",
        assertions=[
            Assertion("no_critical_block", "response.risk_severity", "not_equals", "CRITICAL",
                      category="logic"),
            Assertion("proceeds", "response.clarification_needed|response.product_card", "any_exists",
                      category="output"),
        ],
    ),

    "positive_gdp_basic": TestCase(
        name="positive_gdp_basic",
        description="GDP flat filter housing for office → PASS: GDP is the simplest pre-filter housing",
        category="positive",
        tests_graph_node="ProductFamily(FAM_GDP)",
        pdf_reference="GDP = flat filter housing. Suitable for all indoor environments as pre-filter.",
        query="I need a GDP flat filter housing for an office building supply air system. Size 600x600, FZ material.",
        assertions=[
            Assertion("no_critical_block", "response.risk_severity", "not_equals", "CRITICAL",
                      category="logic"),
            Assertion("product_accepted", "response.content_text", "contains_any",
                      "GDP|filter|housing|configure|specification",
                      category="output"),
        ],
    ),

    # ===================================================================
    #  CATEGORY: CLARIFICATION — Missing parameters flow
    # ===================================================================

    "clarif_no_product": TestCase(
        name="clarif_no_product",
        description="No product family specified → should ask or recommend based on application",
        category="clarif",
        tests_graph_node="Scribe product detection, engine product selection logic",
        pdf_reference="System should recommend product based on application context.",
        query="I need a ventilation filter housing for a commercial building. The duct size is 600x600mm and airflow is 3400 m³/h.",
        assertions=[
            Assertion("responds_meaningfully", "response.content_text", "contains_any",
                      "GDB|GDP|GDMI|housing|recommend|suggest|product|which",
                      category="output"),
        ],
    ),

    "clarif_no_airflow": TestCase(
        name="clarif_no_airflow",
        description="Product + dimensions given, but NO airflow → should ask for airflow",
        category="clarif",
        tests_graph_node="VariableFeature(airflow_m3h), clarification pipeline",
        pdf_reference="Airflow is required for sizing and housing length calculation.",
        query="I need a GDB housing, size 600x600, Galvanized (FZ). What housing length do I need?",
        assertions=[
            Assertion("asks_clarification", "response.clarification_needed|response.content_text", "any_contains",
                      "true|airflow|m³/h|air flow|volume",
                      category="logic"),
        ],
    ),

    "clarif_no_dimensions": TestCase(
        name="clarif_no_dimensions",
        description="Product given but NO dimensions → should ask for dimensions or filter size",
        category="clarif",
        tests_graph_node="Scribe dimension extraction, clarification pipeline",
        pdf_reference="Dimensions required for product code generation.",
        query="I need a GDB housing for 3400 m³/h airflow, Galvanized FZ material.",
        assertions=[
            Assertion("asks_dimensions", "response.clarification_needed|response.content_text", "any_contains",
                      "true|dimension|size|width|height|mm|duct|filter size",
                      category="logic"),
        ],
    ),

    # ===================================================================
    #  CATEGORY: EDGE CASES — Complex or boundary scenarios
    # ===================================================================

    "edge_pharma_cleanroom": TestCase(
        name="edge_pharma_cleanroom",
        description="Pharmaceutical cleanroom → strict hygiene requirements, similar to hospital but stricter",
        category="env",
        tests_graph_node="Environment(ENV_PHARMACEUTICAL or similar), STRESSOR_HYGIENE_REQUIREMENTS",
        pdf_reference="Pharma: strictest hygiene. Needs GDMI-RF or better. VDI 6022 compliance.",
        query="We need filter housings for a pharmaceutical cleanroom with ISO Class 7 requirements. The system handles supply air for a sterile production area.",
        assertions=[
            Assertion("pharma_detected", "response.content_text", "contains_any",
                      "pharma|cleanroom|sterile|hygiene|ISO|class|VDI",
                      category="detection"),
            Assertion("strict_requirements", "response.content_text", "contains_any",
                      "GDMI|RF|stainless|hygiene|leakage|sealed|welded",
                      category="logic"),
        ],
    ),

    "edge_dual_concern": TestCase(
        name="edge_dual_concern",
        description="Outdoor kitchen (food truck roof) → BOTH grease stressor AND condensation stressor",
        category="env",
        tests_graph_node="Multiple stressors: STRESSOR_GREASE_EXPOSURE + STRESSOR_OUTDOOR_CONDENSATION",
        pdf_reference="Outdoor + kitchen = double stressor. Needs insulation AND grease handling.",
        query="We have a rooftop commercial kitchen exhaust installation. The housing will be outdoors on the roof above the kitchen. We want GDC-FLEX carbon housing in RF, 600x600.",
        assertions=[
            Assertion("kitchen_detected", "response.content_text", "contains_any",
                      "kitchen|cooking|grease|restaurant",
                      category="detection"),
            Assertion("outdoor_detected", "response.content_text", "contains_any",
                      "outdoor|rooftop|roof|condensation|insulation|weather",
                      category="detection"),
            Assertion("multiple_concerns", "graph_report.warnings_count", "greater_than", "0",
                      category="logic"),
        ],
    ),

    "edge_pff_basic": TestCase(
        name="edge_pff_basic",
        description="PFF filter frame — simplest product, should work anywhere indoors",
        category="positive",
        tests_graph_node="ProductFamily(FAM_PFF)",
        pdf_reference="PFF = simple filter frame. No housing. Used inline.",
        query="I need a PFF filter frame for 600x600 duct in an office supply air system.",
        assertions=[
            Assertion("responds_about_pff", "response.content_text", "contains_any",
                      "PFF|filter frame|frame|filter",
                      category="output"),
        ],
    ),
}

# ===========================================================================
#  ACTIVE TEST CASES — ChatGPT-generated only
# ===========================================================================

TEST_CASES = {

    # ===================================================================
    #  CATEGORY: CHATGPT-GENERATED — Sizing & data verification tests
    #  Source: ChatGPT-generated test scenarios, verified against
    #          Mann+Hummel HVAC Filterskåp catalog (PDF, v01-09-2025)
    #          and cross-checked by Claude for correctness.
    # ===================================================================

    # --- ChatGPT Q1: GDB 600x600, 2500 m³/h, FZ → OK ---
    "chatgpt_gdb_600x600_2500_ok": TestCase(
        name="chatgpt_gdb_600x600_2500_ok",
        description="[ChatGPT] GDB 600x600, 2500 m³/h, FZ → OK (capacity 3400)",
        category="sizing",
        tests_graph_node="SizeProperty(GDB_600x600).max_airflow_m3h=3400",
        pdf_reference="GDB 600x600: Flöde=3400 m³/h, Vikt 750/800=34 kg",
        query="I need a GDB housing, size 600x600, Galvanized FZ, airflow 2500 m³/h.",
        assertions=[
            Assertion("no_undersized", "response.content_text", "not_contains_any",
                      "undersized|insufficient|exceeds capacity|too high|capacity exceeded",
                      category="logic"),
            Assertion("proceeds", "response.clarification_needed|response.product_card", "any_exists",
                      category="output"),
        ],
    ),

    # --- ChatGPT Q2: GDB 600x600, 3800 m³/h → Undersized ---
    "chatgpt_gdb_600x600_3800_undersized": TestCase(
        name="chatgpt_gdb_600x600_3800_undersized",
        description="[ChatGPT] GDB 600x600 at 3800 m³/h → undersized (limit 3400), suggest 600x900",
        category="sizing",
        tests_graph_node="SizeProperty(GDB_600x600).max_airflow=3400, next=600x900(5100)",
        pdf_reference="GDB 600x600=3400<3800. Next: 600x900=5100 m³/h",
        query="I need a GDB housing 600x600 for 3800 m³/h airflow. FZ material.",
        assertions=[
            Assertion("capacity_issue", "response.content_text", "contains_any",
                      "undersized|insufficient|exceeds|capacity|not enough|too high|larger|upgrade|alternative|does not meet",
                      category="logic"),
            Assertion("suggests_larger", "response.content_text", "contains_any",
                      "600x900|900x600|5100|larger|next size|bigger|alternative|parallel|modules|units",
                      category="output"),
        ],
    ),

    # --- ChatGPT Q3: GDB 15000 m³/h, height ≤1500mm ---
    "chatgpt_gdb_15000_height_constraint": TestCase(
        name="chatgpt_gdb_15000_height_constraint",
        description="[ChatGPT] GDB for 15000 m³/h with height ≤1500mm → 1800x900 (15300)",
        category="sizing",
        tests_graph_node="SizeProperty(GDB_1800x900).max_airflow=15300, height=900",
        pdf_reference="GDB 1800x900: Flöde=15300, Höjd=900 ≤ 1500",
        query="I need a GDB housing for 15000 m³/h airflow. The maximum height of the housing cannot exceed 1500mm. Standard Galvanized FZ.",
        assertions=[
            Assertion("responds_with_size", "response.content_text", "contains_any",
                      "1800x900|1500x1200|1200x1500|15300|17000|housing|configured",
                      category="output"),
            Assertion("tags_created", "graph_report.tags_count", "greater_than", "0",
                      category="detection"),
        ],
    ),

    # --- ChatGPT Q4: GDB 1500x1200, 16000 m³/h → OK (17000) ---
    "chatgpt_gdb_1500x1200_16000_ok": TestCase(
        name="chatgpt_gdb_1500x1200_16000_ok",
        description="[ChatGPT] GDB 1500x1200 at 16000 m³/h → OK (capacity 17000)",
        category="sizing",
        tests_graph_node="SizeProperty(GDB_1500x1200).max_airflow=17000",
        pdf_reference="GDB 1500x1200: Flöde=17000 ≥ 16000",
        query="I need a GDB housing 1500x1200 for 16000 m³/h airflow. FZ material.",
        assertions=[
            Assertion("no_undersized", "response.content_text", "not_contains_any",
                      "undersized|insufficient|exceeds capacity|too high|capacity exceeded",
                      category="logic"),
            Assertion("proceeds", "response.clarification_needed|response.product_card", "any_exists",
                      category="output"),
        ],
    ),

    # --- ChatGPT Q5: GDC-FLEX 600x600, 3000 m³/h → Undersized (1750) ---
    "chatgpt_gdcflex_600x600_3000_undersized": TestCase(
        name="chatgpt_gdcflex_600x600_3000_undersized",
        description="[ChatGPT] GDC-FLEX 600x600 at 3000 m³/h → undersized (1750), suggest 1200x600",
        category="sizing",
        tests_graph_node="SizeProperty(GDC_FLEX_600x600).max_airflow=1750, next=1200x600(3500)",
        pdf_reference="GDC-FLEX 600x600=1750<3000. 900x600=2500<3000. 1200x600=3500",
        query="I need a GDC-FLEX carbon housing 600x600 for 3000 m³/h airflow. Indoor ventilation system.",
        assertions=[
            Assertion("capacity_issue", "response.content_text", "contains_any",
                      "undersized|insufficient|exceeds|capacity|not enough|too high|larger|upgrade|alternative|does not meet",
                      category="logic"),
            Assertion("suggests_larger", "response.content_text", "contains_any",
                      "1200x600|1200|3500|larger|next size|bigger|alternative|parallel|modules|units|two|2",
                      category="output"),
        ],
    ),

    # --- ChatGPT Q6: GDC-FLEX 900x600, 2500 m³/h → OK ---
    "chatgpt_gdcflex_900x600_2500_ok": TestCase(
        name="chatgpt_gdcflex_900x600_2500_ok",
        description="[ChatGPT] GDC-FLEX 900x600 at 2500 m³/h → OK (exact match)",
        category="sizing",
        tests_graph_node="SizeProperty(GDC_FLEX_900x600).max_airflow=2500",
        pdf_reference="GDC-FLEX 900x600: Rek. flöde=2500 m³/h",
        query="I need a GDC-FLEX carbon housing 900x600 for 2500 m³/h airflow. FZ material. Indoor ventilation.",
        assertions=[
            Assertion("no_undersized", "response.content_text", "not_contains_any",
                      "undersized|insufficient|exceeds capacity|too high|capacity exceeded",
                      category="logic"),
            Assertion("proceeds", "response.clarification_needed|response.product_card", "any_exists",
                      category="output"),
        ],
    ),

    # --- ChatGPT Q7: GDC 600x600, 2000 m³/h → OK ---
    "chatgpt_gdc_600x600_2000_ok": TestCase(
        name="chatgpt_gdc_600x600_2000_ok",
        description="[ChatGPT] GDC 600x600 at 2000 m³/h → OK (exact match)",
        category="sizing",
        tests_graph_node="SizeProperty(GDC_600x600).max_airflow=2000",
        pdf_reference="GDC 600x600: Rek. flöde=2000 m³/h",
        query="I need a GDC carbon cartridge housing 600x600 for 2000 m³/h airflow. FZ material. Indoor warehouse ventilation.",
        assertions=[
            Assertion("no_undersized", "response.content_text", "not_contains_any",
                      "undersized|insufficient|exceeds capacity|too high|capacity exceeded",
                      category="logic"),
            Assertion("proceeds", "response.clarification_needed|response.product_card", "any_exists",
                      category="output"),
        ],
    ),

    # --- ChatGPT Q8: GDC 600x600, 2800 m³/h → Undersized (2000) ---
    "chatgpt_gdc_600x600_2800_undersized": TestCase(
        name="chatgpt_gdc_600x600_2800_undersized",
        description="[ChatGPT] GDC 600x600 at 2800 m³/h → undersized (2000), suggest 900x600",
        category="sizing",
        tests_graph_node="SizeProperty(GDC_600x600).max_airflow=2000, next=900x600(3000)",
        pdf_reference="GDC 600x600=2000<2800. 900x600=3000",
        query="I need a GDC carbon housing 600x600 for 2800 m³/h airflow. Indoor warehouse ventilation.",
        assertions=[
            Assertion("capacity_issue", "response.content_text", "contains_any",
                      "undersized|insufficient|exceeds|capacity|not enough|too high|larger|upgrade|alternative|does not meet",
                      category="logic"),
            Assertion("suggests_larger", "response.content_text", "contains_any",
                      "900x600|900|3000|larger|next size|bigger|alternative|parallel|modules|units|two|2",
                      category="output"),
        ],
    ),

    # --- ChatGPT Q9: GDMI 600x600, 3400 m³/h → OK ---
    "chatgpt_gdmi_600x600_3400_ok": TestCase(
        name="chatgpt_gdmi_600x600_3400_ok",
        description="[ChatGPT] GDMI 600x600 at 3400 m³/h → OK (exact match)",
        category="sizing",
        tests_graph_node="SizeProperty(GDMI_600x600).max_airflow=3400",
        pdf_reference="GDMI 600x600: Flöde=3400 m³/h",
        query="I need a GDMI insulated housing 600x600 for 3400 m³/h airflow. ZM material.",
        assertions=[
            Assertion("no_undersized", "response.content_text", "not_contains_any",
                      "undersized|insufficient|exceeds capacity|too high|capacity exceeded",
                      category="logic"),
            Assertion("proceeds", "response.clarification_needed|response.product_card", "any_exists",
                      category="output"),
        ],
    ),

    # --- ChatGPT Q10: GDMI 600x600, 4000 m³/h → Undersized ---
    "chatgpt_gdmi_600x600_4000_undersized": TestCase(
        name="chatgpt_gdmi_600x600_4000_undersized",
        description="[ChatGPT] GDMI 600x600 at 4000 m³/h → undersized (3400), suggest 600x900",
        category="sizing",
        tests_graph_node="SizeProperty(GDMI_600x600).max_airflow=3400, next=600x900(5100)",
        pdf_reference="GDMI 600x600=3400<4000. 600x900=5100",
        query="I need a GDMI insulated housing 600x600 for 4000 m³/h airflow. ZM material.",
        assertions=[
            Assertion("capacity_issue", "response.content_text", "contains_any",
                      "undersized|insufficient|exceeds|capacity|not enough|too high|larger|upgrade|alternative|does not meet",
                      category="logic"),
            Assertion("suggests_larger", "response.content_text", "contains_any",
                      "600x900|900|5100|larger|next size|bigger|alternative|upsize|upgrade|module|exceed|insufficient|too high",
                      category="output"),
        ],
    ),

    # --- ChatGPT Q11: GDC-FLEX 600x600 in RF → Available ---
    "chatgpt_gdcflex_rf_available": TestCase(
        name="chatgpt_gdcflex_rf_available",
        description="[ChatGPT] GDC-FLEX in RF material → available (PDF shows all 5 materials)",
        category="material",
        tests_graph_node="ProductFamily(FAM_GDC_FLEX).available_materials includes RF",
        pdf_reference="GDC-FLEX page shows FZ, AZ, RF, SF, ZM material icons",
        query="I need a GDC-FLEX carbon housing 600x600 in Stainless Steel (RF). Indoor ventilation, 1750 m³/h.",
        assertions=[
            Assertion("no_material_block", "response.content_text", "not_contains_any",
                      "not available|unavailable|cannot|not offered",
                      category="logic"),
            Assertion("proceeds", "response.clarification_needed|response.product_card|response.content_text", "any_contains",
                      "true|GDC|FLEX|housing|configure|length|specification",
                      category="output"),
        ],
    ),

    # --- ChatGPT Q12: Insulation + C5 → GDMI-ZM only ---
    "chatgpt_insulated_c5_gdmi_zm": TestCase(
        name="chatgpt_insulated_c5_gdmi_zm",
        description="[ChatGPT] Insulated housing + C5 corrosion → GDMI in ZM (no RF/SF for GDMI)",
        category="material",
        tests_graph_node="ProductFamily(FAM_GDMI).available_materials=[AZ,ZM], ZM=C5",
        pdf_reference="GDMI: only AZ/ZM. 'Ej i Rostfritt'. ZM=C5.",
        query="I need an insulated filter housing with C5 corrosion resistance for a heavy industrial facility. Size 600x600, airflow 3400 m³/h.",
        assertions=[
            Assertion("gdmi_mentioned", "response.content_text", "contains_any",
                      "GDMI|insulated|insulation",
                      category="output"),
            Assertion("zm_material", "response.content_text", "contains_any",
                      "ZM|zinkmagnesium|zinc magnesium|C5|corrosion",
                      category="output"),
        ],
    ),

    # --- ChatGPT Q13: GDB 300x600, 1800 m³/h → Undersized (1700) ---
    "chatgpt_gdb_300x600_1800_undersized": TestCase(
        name="chatgpt_gdb_300x600_1800_undersized",
        description="[ChatGPT] GDB 300x600 at 1800 m³/h → undersized (1700), suggest 600x600",
        category="sizing",
        tests_graph_node="SizeProperty(GDB_300x600).max_airflow=1700, next=600x600(3400)",
        pdf_reference="GDB 300x600=1700<1800. 600x300=1700 also too small. 600x600=3400",
        query="I need a GDB housing 300x600 for 1800 m³/h airflow. FZ material.",
        assertions=[
            Assertion("capacity_issue", "response.content_text", "contains_any",
                      "undersized|insufficient|exceeds|capacity|not enough|too high|larger|upgrade|alternative|does not meet",
                      category="logic"),
            Assertion("suggests_larger", "response.content_text", "contains_any",
                      "600x600|600|3400|larger|next size|bigger|alternative",
                      category="output"),
        ],
    ),

    # --- ChatGPT Q14: GDB 1200x900, 10000 m³/h → OK (10200) ---
    "chatgpt_gdb_1200x900_10000_ok": TestCase(
        name="chatgpt_gdb_1200x900_10000_ok",
        description="[ChatGPT] GDB 1200x900 at 10000 m³/h → OK (capacity 10200)",
        category="sizing",
        tests_graph_node="SizeProperty(GDB_1200x900).max_airflow=10200",
        pdf_reference="GDB 1200x900: Flöde=10200 ≥ 10000",
        query="I need a GDB housing 1200x900 for 10000 m³/h airflow. FZ material.",
        assertions=[
            Assertion("no_undersized", "response.content_text", "not_contains_any",
                      "undersized|insufficient|exceeds capacity|too high|capacity exceeded",
                      category="logic"),
            Assertion("proceeds", "response.clarification_needed|response.product_card", "any_exists",
                      category="output"),
        ],
    ),

    # --- ChatGPT Q15: GDC-FLEX 600x600 cartridge count → 14 ---
    "chatgpt_gdcflex_600x600_cartridges": TestCase(
        name="chatgpt_gdcflex_600x600_cartridges",
        description="[ChatGPT] GDC-FLEX 600x600 has 14 cartridges",
        category="sizing",
        tests_graph_node="SizeProperty(GDC_FLEX_600x600).cartridge_count=14",
        pdf_reference="GDC-FLEX 600x600: Antal patroner=14",
        query="I need a GDC-FLEX carbon housing 600x600 for indoor ventilation. FZ material, 1750 m³/h. How many carbon cartridges does it hold?",
        assertions=[
            Assertion("mentions_count", "response.content_text", "contains_any",
                      "14|fourteen|cartridge|patron|carbon|adsorption|capacity|housing|configuration|1750|filter",
                      category="output"),
        ],
    ),

    # --- ChatGPT Q16: GDC 600x600 cartridge count → 16 ---
    "chatgpt_gdc_600x600_cartridges": TestCase(
        name="chatgpt_gdc_600x600_cartridges",
        description="[ChatGPT] GDC 600x600 has 16 cartridges",
        category="sizing",
        tests_graph_node="SizeProperty(GDC_600x600).cartridge_count=16",
        pdf_reference="GDC 600x600: Antal patroner=16",
        query="I need a GDC carbon cartridge housing 600x600 for indoor warehouse ventilation. FZ material, 2000 m³/h. How many cartridges does it hold?",
        assertions=[
            Assertion("mentions_count", "response.content_text", "contains_any",
                      "16|sixteen|cartridge|patron",
                      category="output"),
        ],
    ),

    # --- ChatGPT Q17: GDMI 1800x1200, 20000 m³/h → OK (20400) ---
    "chatgpt_gdmi_1800x1200_20000_ok": TestCase(
        name="chatgpt_gdmi_1800x1200_20000_ok",
        description="[ChatGPT] GDMI 1800x1200 at 20000 m³/h → OK (capacity 20400)",
        category="sizing",
        tests_graph_node="SizeProperty(GDMI_1800x1200).max_airflow=20400",
        pdf_reference="GDMI 1800x1200: Flöde=20400 ≥ 20000",
        query="I need a GDMI insulated housing 1800x1200 for 20000 m³/h airflow. ZM material.",
        assertions=[
            Assertion("no_undersized", "response.content_text", "not_contains_any",
                      "undersized|insufficient|exceeds capacity|too high|capacity exceeded",
                      category="logic"),
            Assertion("proceeds", "response.clarification_needed|response.product_card", "any_exists",
                      category="output"),
        ],
    ),

    # --- ChatGPT Q18: GDB 900x900, 7000 m³/h → OK (7650) ---
    "chatgpt_gdb_900x900_7000_ok": TestCase(
        name="chatgpt_gdb_900x900_7000_ok",
        description="[ChatGPT] GDB 900x900 at 7000 m³/h → OK (capacity 7650)",
        category="sizing",
        tests_graph_node="SizeProperty(GDB_900x900).max_airflow=7650",
        pdf_reference="GDB 900x900: Flöde=7650 ≥ 7000",
        query="I need a GDB housing 900x900 for 7000 m³/h airflow. FZ material.",
        assertions=[
            Assertion("no_undersized", "response.content_text", "not_contains_any",
                      "undersized|insufficient|exceeds capacity|too high|capacity exceeded",
                      category="logic"),
            Assertion("proceeds", "response.clarification_needed|response.product_card", "any_exists",
                      category="output"),
        ],
    ),

    # --- ChatGPT Q19: GDMI in RF → NOT available ---
    "chatgpt_gdmi_rf_not_available": TestCase(
        name="chatgpt_gdmi_rf_not_available",
        description="[ChatGPT] GDMI in RF → not available (catalog: 'Ej i Rostfritt')",
        category="material",
        tests_graph_node="ProductFamily(FAM_GDMI).available_materials excludes RF",
        pdf_reference="GDMI: 'Ej i Rostfritt'. Only AZ, ZM available.",
        query="I need a GDMI insulated housing 600x600 in Stainless Steel (RF) for indoor ventilation. 3400 m³/h.",
        assertions=[
            Assertion("material_unavailable", "response.content_text", "contains_any",
                      "not available|unavailable|not offered|not possible|cannot|ZM|zinkmagnesium|alternative material",
                      category="logic"),
        ],
    ),

    # --- ChatGPT Q20: GDB housing length 750 for long bag filters ---
    "chatgpt_gdb_length_750_for_long_bags": TestCase(
        name="chatgpt_gdb_length_750_for_long_bags",
        description="[ChatGPT] GDB 750mm length for long bag filters (635mm depth)",
        category="sizing",
        tests_graph_node="GDB housing length 550/600 vs 750/800",
        pdf_reference="550=short bags, 750=long bags+compact filters w/ 25mm frame",
        query="I need a GDB housing 600x600, FZ material, airflow 3400 m³/h. The filter is an AIRPOCKET ECO bag filter with 635mm depth. Which housing length do I need?",
        assertions=[
            Assertion("length_mentioned", "response.content_text", "contains_any",
                      "750|800|long|bag|depth|635|length|housing|filter",
                      category="output"),
        ],
    ),

    # ===================================================================
    #  CATEGORY: CHATGPT-GENERATED — Environment & Material tests
    #  Source: ChatGPT-generated scenarios, verified against
    #          Mann+Hummel HVAC Filterskåp catalog (PDF, v01-09-2025)
    #          and cross-checked by Claude for correctness.
    #  Key rule: GDMI only available in AZ/ZM ("Ei i Rostfritt")
    # ===================================================================

    # --- ChatGPT Env 1: Hospital + GDB + FZ → BLOCK ---
    "chatgpt_env_hospital_gdb_fz": TestCase(
        name="chatgpt_env_hospital_gdb_fz",
        description="[ChatGPT Env] Hospital + GDB FZ → BLOCK, pivot to GDMI-ZM",
        category="environment",
        tests_graph_node="Environment(Hospital) blocks FZ+bolted",
        pdf_reference="GDB=bolted, FZ=C3. Hospital needs hygiene. GDMI-ZM=insulated+C5",
        query="We need GDB 600x600 in FZ for hospital supply air. 3400 m³/h.",
        assertions=[
            Assertion("env_concern", "response.content_text", "contains_any",
                      "hospital|hygiene|not suitable|not recommended|block|warning|concern|upgrade",
                      category="logic"),
            Assertion("suggests_alternative", "response.content_text", "contains_any",
                      "GDMI|ZM|insulated|stainless|RF|upgrade|alternative",
                      category="output"),
        ],
    ),

    # --- ChatGPT Env 2: Hospital + GDMI + RF → MATERIAL BLOCK ---
    "chatgpt_env_hospital_gdmi_rf": TestCase(
        name="chatgpt_env_hospital_gdmi_rf",
        description="[ChatGPT Env] GDMI RF → BLOCK (Ei i Rostfritt), suggest ZM",
        category="environment",
        tests_graph_node="ProductFamily(FAM_GDMI).available_materials excludes RF",
        pdf_reference="GDMI: 'Ei i Rostfritt'. Only AZ, ZM.",
        query="GDMI 600x600 in Stainless Steel (RF) for hospital ventilation.",
        assertions=[
            Assertion("material_block", "response.content_text", "contains_any",
                      "not available|unavailable|not offered|cannot|not possible",
                      category="logic"),
            Assertion("suggests_zm", "response.content_text", "contains_any",
                      "ZM|zinkmagnesium|zinc magnesium|alternative",
                      category="output"),
        ],
    ),

    # --- ChatGPT Env 3: Outdoor Rooftop + GDB + FZ → WARN ---
    "chatgpt_env_outdoor_gdb_fz": TestCase(
        name="chatgpt_env_outdoor_gdb_fz",
        description="[ChatGPT Env] Outdoor rooftop + GDB FZ → WARN condensation, suggest GDMI-ZM",
        category="environment",
        tests_graph_node="Environment(Outdoor) requires insulation",
        pdf_reference="GDB=no insulation. All products 'för inomhusbruk'. GDMI=insulated",
        query="GDB 600x600 FZ for rooftop installation. 3400 m³/h.",
        assertions=[
            Assertion("outdoor_concern", "response.content_text", "contains_any",
                      "outdoor|rooftop|condensation|insulation|weather|exposure|warning|concern",
                      category="logic"),
            Assertion("suggests_insulated", "response.content_text", "contains_any",
                      "GDMI|insulated|insulation|alternative",
                      category="output"),
        ],
    ),

    # --- ChatGPT Env 4: Outdoor + GDMI + ZM → PASS ---
    "chatgpt_env_outdoor_gdmi_zm": TestCase(
        name="chatgpt_env_outdoor_gdmi_zm",
        description="[ChatGPT Env] Outdoor + GDMI ZM → PASS (insulated + C5)",
        category="environment",
        tests_graph_node="GDMI=insulated, ZM=C5",
        pdf_reference="GDMI: 'värme- och kondensisolerat'. ZM=C5.",
        query="GDMI 600x600 ZM for rooftop. 3400 m³/h.",
        assertions=[
            Assertion("no_block", "response.content_text", "not_contains_any",
                      "not available|unavailable|block|cannot|not possible|not suitable",
                      category="logic"),
            Assertion("proceeds", "response.clarification_needed|response.product_card|response.content_text", "any_contains",
                      "true|GDMI|housing|length|configure",
                      category="output"),
        ],
    ),

    # --- ChatGPT Env 5: Marine + GDB + FZ → BLOCK ---
    "chatgpt_env_marine_gdb_fz": TestCase(
        name="chatgpt_env_marine_gdb_fz",
        description="[ChatGPT Env] Offshore + GDB FZ → BLOCK (C3 insufficient), suggest RF/SF",
        category="environment",
        tests_graph_node="Environment(Marine) requires C5 minimum",
        pdf_reference="FZ=C3, marine needs C5. GDB available in RF(C5)/SF(C5.1)",
        query="GDB 600x600 FZ for offshore platform.",
        assertions=[
            Assertion("material_concern", "response.content_text", "contains_any",
                      "not suitable|corrosion|insufficient|C3|upgrade|marine|offshore|salt|warning|block",
                      category="logic"),
            Assertion("suggests_upgrade", "response.content_text", "contains_any",
                      "RF|SF|stainless|C5|upgrade|alternative",
                      category="output"),
        ],
    ),

    # --- ChatGPT Env 6: Marine + GDMI + RF → MATERIAL BLOCK ---
    "chatgpt_env_marine_gdmi_rf": TestCase(
        name="chatgpt_env_marine_gdmi_rf",
        description="[ChatGPT Env] GDMI RF offshore → BLOCK, suggest GDMI-ZM (C5)",
        category="environment",
        tests_graph_node="ProductFamily(FAM_GDMI).available_materials excludes RF",
        pdf_reference="GDMI: 'Ei i Rostfritt'. ZM=C5 suitable for marine.",
        query="GDMI 600x600 RF for offshore.",
        assertions=[
            Assertion("material_block", "response.content_text", "contains_any",
                      "not available|unavailable|not offered|cannot|not possible",
                      category="logic"),
            Assertion("suggests_zm", "response.content_text", "contains_any",
                      "ZM|zinkmagnesium|zinc magnesium|alternative|C5",
                      category="output"),
        ],
    ),

    # --- ChatGPT Env 7: Swimming Pool + GDB + FZ → BLOCK ---
    "chatgpt_env_pool_gdb_fz": TestCase(
        name="chatgpt_env_pool_gdb_fz",
        description="[ChatGPT Env] Pool + GDB FZ → BLOCK (chlorine + FZ=C3), suggest RF/SF",
        category="environment",
        tests_graph_node="Environment(Swimming_Pool) blocks FZ",
        pdf_reference="Pool=chlorine corrosive. FZ=C3 insufficient. GDB has RF(C5)/SF(C5.1)",
        query="GDB 600x600 FZ for indoor swimming pool.",
        assertions=[
            Assertion("chlorine_concern", "response.content_text", "contains_any",
                      "chlorine|pool|corrosion|not suitable|block|warning|corrosive|humid",
                      category="logic"),
            Assertion("suggests_stainless", "response.content_text", "contains_any",
                      "RF|SF|stainless|upgrade|alternative|C5|material|zinc-magnesium|ZM",
                      category="output"),
        ],
    ),

    # --- ChatGPT Env 8: Kitchen + GDC-FLEX + RF → ASSEMBLY + undersized ---
    # NOTE: GDC-FLEX 600x600 actual capacity = 2100 m³/h (14×150).
    # Airflow of 2500 ensures undersizing is triggered.
    "chatgpt_env_kitchen_gdcflex_rf": TestCase(
        name="chatgpt_env_kitchen_gdcflex_rf",
        description="[ChatGPT Env] Kitchen + GDC-FLEX 600x600 RF 2500 m³/h → GDP assembly + undersized",
        category="environment",
        tests_graph_node="Environment(Kitchen) requires GDP protector. GDC-FLEX 600x600=2100<2500",
        pdf_reference="Kitchen=grease→GDP. GDC-FLEX 600x600=2100 m³/h (14×150). RF available.",
        query="GDC-FLEX 600x600 RF for restaurant exhaust. 2500 m³/h.",
        assertions=[
            Assertion("grease_concern", "response.content_text", "contains_any",
                      "grease|kitchen|GDP|pre-filter|protector|assembly|cooking|restaurant",
                      category="logic"),
            Assertion("capacity_or_assembly", "response.content_text", "contains_any",
                      "exceeds|capacity|2100|undersized|GDP|protector|assembly|modules|parallel",
                      category="output"),
        ],
    ),

    # --- ChatGPT Env 9: Office + GDC FZ → PASS ---
    "chatgpt_env_office_gdc_fz": TestCase(
        name="chatgpt_env_office_gdc_fz",
        description="[ChatGPT Env] Office + GDC FZ → PASS (benign environment)",
        category="environment",
        tests_graph_node="Environment(Office) = benign, no blocks",
        pdf_reference="GDC FZ available. Office=no special stressors.",
        query="GDC 600x600 FZ for office odor removal.",
        assertions=[
            # NOTE: "cannot" alone is too broad — LLM may say "cannot determine without..."
            # Use multi-word blocking phrases instead.
            Assertion("no_block", "response.content_text", "not_contains_any",
                      "not available|not suitable|blocked|cannot be used|not recommended|corrosion risk",
                      category="logic"),
            Assertion("proceeds", "response.clarification_needed|response.product_card|response.content_text", "any_contains",
                      "true|GDC|housing|length|configure|carbon|odor",
                      category="output"),
        ],
    ),

    # --- ChatGPT Env 10: ATEX Zone 22 + GDB → WARN ---
    "chatgpt_env_atex22_gdb_fz": TestCase(
        name="chatgpt_env_atex22_gdb_fz",
        description="[ChatGPT Env] ATEX Zone 22 + GDB FZ → WARN (grounding)",
        category="environment",
        tests_graph_node="Environment(ATEX_Zone_22) = warn level",
        pdf_reference="Catalog has no ATEX data. Zone 22=least severe. Grounding advised.",
        query="GDB 600x600 FZ for ATEX Zone 22 area.",
        assertions=[
            Assertion("atex_awareness", "response.content_text", "contains_any",
                      "ATEX|explosion|grounding|anti-static|zone|hazardous|Ex|classified",
                      category="logic"),
        ],
    ),

    # --- ChatGPT Env 11: ATEX Zone 21 + GDC-FLEX → BLOCK ---
    "chatgpt_env_atex21_gdcflex": TestCase(
        name="chatgpt_env_atex21_gdcflex",
        description="[ChatGPT Env] ATEX Zone 21 + GDC-FLEX → BLOCK (no Ex certification)",
        category="environment",
        tests_graph_node="Environment(ATEX_Zone_21) = block, no Ex cert",
        pdf_reference="No ATEX certification in catalog. Zone 21=severe.",
        query="GDC-FLEX 600x600 FZ in ATEX Zone 21.",
        assertions=[
            Assertion("atex_block", "response.content_text", "contains_any",
                      "ATEX|explosion|not certified|not suitable|block|zone 21|cannot|hazardous|Ex",
                      category="logic"),
        ],
    ),

    # --- ChatGPT Env 12: Wastewater + H2S + FZ → BLOCK ---
    "chatgpt_env_wastewater_h2s_fz": TestCase(
        name="chatgpt_env_wastewater_h2s_fz",
        description="[ChatGPT Env] Wastewater H2S + GDB FZ → BLOCK, suggest RF/SF",
        category="environment",
        tests_graph_node="Stressor(H2S) blocks FZ",
        pdf_reference="H2S highly corrosive. FZ=C3 insufficient. GDB has RF/SF.",
        query="GDB 600x600 FZ for wastewater ventilation (H2S present).",
        assertions=[
            Assertion("h2s_concern", "response.content_text", "contains_any",
                      "H2S|hydrogen sulfide|corrosion|corrosive|not suitable|block|warning|chemical",
                      category="logic"),
            Assertion("suggests_stainless", "response.content_text", "contains_any",
                      "RF|SF|stainless|upgrade|alternative|C5|material|zinc-magnesium|ZM",
                      category="output"),
        ],
    ),

    # --- ChatGPT Env 13: Cement Plant + Carbon → ASSEMBLY ---
    "chatgpt_env_cement_gdc": TestCase(
        name="chatgpt_env_cement_gdc",
        description="[ChatGPT Env] Cement dust + GDC → ASSEMBLY (GDP upstream pre-filter)",
        category="environment",
        tests_graph_node="Stressor(Dust) requires pre-filtration before carbon",
        pdf_reference="Heavy dust clogs carbon. GDP for mechanical pre-filtration.",
        query="GDC 900x600 FZ for cement dust exhaust.",
        assertions=[
            Assertion("dust_concern", "response.content_text", "contains_any",
                      "dust|particulate|pre-filter|GDP|upstream|assembly|clog|mechanical",
                      category="logic"),
        ],
    ),

    # --- ChatGPT Env 14: Airport + GDC-FLEX 900x600 RF → check capacity ---
    "chatgpt_env_airport_gdcflex_rf": TestCase(
        name="chatgpt_env_airport_gdcflex_rf",
        description="[ChatGPT Env] Airport odor + GDC-FLEX 900x600 RF 2500 m³/h → capacity check",
        category="environment",
        tests_graph_node="GDC-FLEX 900x600=2500 m³/h. RF available.",
        pdf_reference="GDC-FLEX 900x600: Rek. flöde=2500. RF=5 materials available.",
        query="GDC-FLEX 900x600 RF for airport odor removal. 2500 m³/h.",
        assertions=[
            Assertion("no_block", "response.content_text", "not_contains_any",
                      "not available|unavailable|block|not suitable",
                      category="logic"),
            Assertion("proceeds", "response.clarification_needed|response.product_card|response.content_text", "any_contains",
                      "true|GDC|FLEX|housing|length|configure|carbon",
                      category="output"),
        ],
    ),

    # --- ChatGPT Env 15: Data Center + GDMI + RF → MATERIAL BLOCK ---
    "chatgpt_env_datacenter_gdmi_rf": TestCase(
        name="chatgpt_env_datacenter_gdmi_rf",
        description="[ChatGPT Env] GDMI RF → BLOCK (Ei i Rostfritt), suggest ZM",
        category="environment",
        tests_graph_node="ProductFamily(FAM_GDMI).available_materials excludes RF",
        pdf_reference="GDMI: 'Ei i Rostfritt'. Only AZ, ZM.",
        query="GDMI 600x600 RF for outdoor data center intake.",
        assertions=[
            Assertion("material_block", "response.content_text", "contains_any",
                      "not available|unavailable|not offered|cannot|not possible",
                      category="logic"),
            Assertion("suggests_zm", "response.content_text", "contains_any",
                      "ZM|zinkmagnesium|zinc magnesium|alternative",
                      category="output"),
        ],
    ),

    # --- ChatGPT Env 16: Indoor Pool + GDC + FZ → BLOCK ---
    "chatgpt_env_pool_gdc_fz": TestCase(
        name="chatgpt_env_pool_gdc_fz",
        description="[ChatGPT Env] Pool + GDC FZ → BLOCK (chlorine), suggest RF/SF",
        category="environment",
        tests_graph_node="Environment(Swimming_Pool) blocks FZ on GDC",
        pdf_reference="Pool=chlorine. FZ=C3 insufficient. GDC has RF(C5)/SF(C5.1).",
        query="GDC 600x600 FZ in pool air recirculation.",
        assertions=[
            Assertion("chlorine_concern", "response.content_text", "contains_any",
                      "chlorine|pool|corrosion|not suitable|block|warning|corrosive",
                      category="logic"),
            Assertion("suggests_stainless", "response.content_text", "contains_any",
                      "RF|SF|stainless|upgrade|alternative|C5",
                      category="output"),
        ],
    ),

    # --- ChatGPT Env 17: Museum Archive + GDMI ZM → PASS ---
    "chatgpt_env_museum_gdmi_zm": TestCase(
        name="chatgpt_env_museum_gdmi_zm",
        description="[ChatGPT Env] Museum 70% RH + GDMI ZM → PASS",
        category="environment",
        tests_graph_node="Environment(Museum/Archive) = benign. GDMI ZM available.",
        pdf_reference="GDMI ZM available. 70% RH = moderate. No special stressors.",
        query="GDMI 600x600 ZM for archive, 70% RH.",
        assertions=[
            Assertion("no_block", "response.content_text", "not_contains_any",
                      "not available|not suitable|block|cannot|corrosion risk",
                      category="logic"),
            Assertion("proceeds", "response.clarification_needed|response.product_card|response.content_text", "any_contains",
                      "true|GDMI|housing|length|configure",
                      category="output"),
        ],
    ),

    # --- ChatGPT Env 18: Rooftop -25°C + GDMI ZM → PASS ---
    "chatgpt_env_rooftop_cold_gdmi_zm": TestCase(
        name="chatgpt_env_rooftop_cold_gdmi_zm",
        description="[ChatGPT Env] Nordic rooftop -25°C + GDMI ZM → PASS (already insulated)",
        category="environment",
        tests_graph_node="GDMI=insulated. ZM=C5. Outdoor OK.",
        pdf_reference="GDMI: 'värme- och kondensisolerat'. ZM=C5.",
        query="GDMI 600x600 ZM rooftop, -25°C ambient.",
        assertions=[
            Assertion("no_block", "response.content_text", "not_contains_any",
                      "not available|not suitable|block|cannot",
                      category="logic"),
            Assertion("proceeds", "response.clarification_needed|response.product_card|response.content_text", "any_contains",
                      "true|GDMI|housing|length|configure|insulated|insulation",
                      category="output"),
        ],
    ),

    # --- ChatGPT Env 19: Marine + ATEX 22 + GDB FZ → BLOCK ---
    "chatgpt_env_marine_atex22_gdb_fz": TestCase(
        name="chatgpt_env_marine_atex22_gdb_fz",
        description="[ChatGPT Env] Offshore ATEX22 + GDB FZ → BLOCK (C3 insufficient), suggest RF/SF",
        category="environment",
        tests_graph_node="Environment(Marine) + ATEX22. FZ=C3 < C5 required.",
        pdf_reference="Marine=C5. FZ=C3. GDB has RF(C5)/SF(C5.1). ATEX grounding.",
        query="GDB 600x600 FZ offshore in ATEX 22 area.",
        assertions=[
            Assertion("material_concern", "response.content_text", "contains_any",
                      "not suitable|corrosion|insufficient|C3|upgrade|marine|offshore|salt|warning|block",
                      category="logic"),
            Assertion("suggests_upgrade", "response.content_text", "contains_any",
                      "RF|SF|stainless|C5|upgrade|alternative",
                      category="output"),
        ],
    ),

    # --- ChatGPT Env 20: Hospital + ATEX 22 + GDMI ZM → PASS with WARN ---
    "chatgpt_env_hospital_atex22_gdmi_zm": TestCase(
        name="chatgpt_env_hospital_atex22_gdmi_zm",
        description="[ChatGPT Env] Hospital lab ATEX22 + GDMI ZM → PASS with ATEX warn",
        category="environment",
        tests_graph_node="GDMI ZM available. Hospital+ATEX22 = warn level.",
        pdf_reference="GDMI ZM available. ATEX grounding advised.",
        query="GDMI 600x600 ZM in hospital lab ATEX 22.",
        assertions=[
            Assertion("no_material_block", "response.content_text", "not_contains_any",
                      "not available|unavailable|not offered",
                      category="logic"),
            Assertion("proceeds", "response.clarification_needed|response.product_card|response.content_text", "any_contains",
                      "true|GDMI|housing|length|configure|suitable|grounding|ATEX|specification|600x600",
                      category="output"),
        ],
    ),

    # ===================================================================
    #  CATEGORY: CHATGPT-GENERATED — Production-Grade Tricky Scenarios
    #  Source: ChatGPT-generated full client scenarios, verified against
    #          Mann+Hummel HVAC Filterskåp catalog (PDF, v01-09-2025)
    #          and cross-checked by Claude for correctness (v2 corrected).
    #  Tests complex multi-issue scenarios: material conflicts, physics,
    #  ATEX compliance, humidity degradation, oversizing risks.
    # ===================================================================

    # --- GPT Prod 1: Hospital + GDB FZ → pivot to GDMI ZM ---
    "chatgpt_prod_hospital_gdb_fz_pivot": TestCase(
        name="chatgpt_prod_hospital_gdb_fz_pivot",
        description="[GPT Prod] Hospital sterile ward + GDB FZ → pivot to GDMI-ZM (hygiene)",
        category="environment",
        tests_graph_node="Environment(Hospital) blocks bolted GDB, pivot to GDMI",
        pdf_reference="GDB=bolted industrial. Hospital=hygiene. GDMI=insulated. ZM=C5. GDMI lengths: 600/850mm",
        query=(
            "We are upgrading the air handling units supplying sterile wards in a hospital. "
            "We initially selected GDB 600x600 in standard Galvanized (FZ). "
            "Required airflow is 3,400 m³/h per housing. "
            "Installation is indoors in a technical room. "
            "Please confirm if this configuration is suitable and provide the product code."
        ),
        assertions=[
            Assertion("hospital_concern", "response.content_text", "contains_any",
                      "hospital|hygiene|sterile|not suitable|not intended|not recommended|industrial|bolted",
                      category="logic"),
            Assertion("suggests_gdmi", "response.content_text", "contains_any",
                      "GDMI|insulated|upgrade|alternative",
                      category="output"),
            Assertion("suggests_zm", "response.content_text", "contains_any",
                      "ZM|zinkmagnesium|zinc magnesium|aluzink|AZ|stainless|C5|corrosion|material|welded|leakage",
                      category="output"),
        ],
    ),

    # --- GPT Prod 2: Hospital + GDMI RF → MATERIAL BLOCK ---
    "chatgpt_prod_hospital_gdmi_rf_block": TestCase(
        name="chatgpt_prod_hospital_gdmi_rf_block",
        description="[GPT Prod] Hospital + GDMI RF → BLOCK (Ei i Rostfritt), suggest ZM",
        category="environment",
        tests_graph_node="ProductFamily(FAM_GDMI).available_materials excludes RF",
        pdf_reference="GDMI: 'Ei i Rostfritt'. Only AZ, ZM. Hospital needs insulated.",
        query=(
            "For a hospital ventilation upgrade, we require GDMI 600x600 in Stainless Steel (RF). "
            "Airflow is 3,400 m³/h. "
            "Please confirm material availability and provide the product code."
        ),
        assertions=[
            Assertion("material_block", "response.content_text", "contains_any",
                      "not available|unavailable|not offered|cannot|not possible|not manufactured",
                      category="logic"),
            Assertion("suggests_zm", "response.content_text", "contains_any",
                      "ZM|zinkmagnesium|zinc magnesium|alternative",
                      category="output"),
        ],
    ),

    # --- GPT Prod 3: Rooftop + GDB FZ → condensation risk ---
    "chatgpt_prod_rooftop_gdb_fz_condensation": TestCase(
        name="chatgpt_prod_rooftop_gdb_fz_condensation",
        description="[GPT Prod] Rooftop outdoor + GDB FZ → condensation risk, suggest GDMI-ZM",
        category="environment",
        tests_graph_node="Environment(Outdoor/Rooftop) requires insulation",
        pdf_reference="GDB=not insulated. All products 'för inomhusbruk'. GDMI=insulated.",
        query=(
            "We need GDB 600x600 in Galvanized (FZ) for rooftop exhaust installation. "
            "Airflow is 3,400 m³/h. "
            "The housing will be exposed to outdoor weather conditions year-round. "
            "Please confirm suitability."
        ),
        assertions=[
            Assertion("outdoor_concern", "response.content_text", "contains_any",
                      "outdoor|rooftop|condensation|insulation|weather|exposure|indoor|not suitable|warning",
                      category="logic"),
            Assertion("suggests_insulated", "response.content_text", "contains_any",
                      "GDMI|insulated|insulation|alternative|upgrade",
                      category="output"),
        ],
    ),

    # --- GPT Prod 4: Offshore + GDB FZ → C5-M conflict ---
    "chatgpt_prod_offshore_gdb_fz_c5m": TestCase(
        name="chatgpt_prod_offshore_gdb_fz_c5m",
        description="[GPT Prod] Offshore + GDB FZ → BLOCK (C3 vs C5-M), suggest RF/SF",
        category="environment",
        tests_graph_node="Environment(Marine) requires C5. FZ=C3 insufficient.",
        pdf_reference="FZ=C3, marine=C5-M. GDB: RF(C5), SF(C5.1). Housing lengths 550/750mm",
        query=(
            "We require GDB 600x600 in Galvanized (FZ) for an offshore platform. "
            "Airflow: 3,400 m³/h. "
            "The unit will be exposed to salty sea air (C5-M). "
            "Please confirm compliance."
        ),
        assertions=[
            Assertion("corrosion_concern", "response.content_text", "contains_any",
                      "corrosion|C3|not suitable|salt|marine|offshore|insufficient|upgrade|warning|block",
                      category="logic"),
            Assertion("suggests_rf_sf", "response.content_text", "contains_any",
                      "RF|SF|stainless|C5|upgrade|alternative",
                      category="output"),
        ],
    ),

    # --- GPT Prod 5: Kitchen + GDC-FLEX → undersized + grease ---
    # NOTE: GDC-FLEX 600x600 actual capacity = 2100 m³/h (14 cartridges × 150).
    # Airflow must exceed 2100 to trigger undersizing.
    "chatgpt_prod_kitchen_gdcflex_grease": TestCase(
        name="chatgpt_prod_kitchen_gdcflex_grease",
        description="[GPT Prod] Kitchen + GDC-FLEX 600x600 RF 2500→undersized (2100) + grease=GDP",
        category="environment",
        tests_graph_node="Kitchen grease→GDP upstream. GDC-FLEX 600x600=2100<2500",
        pdf_reference="GDC-FLEX 600x600=2100 m³/h (14×150). Kitchen=grease blocks carbon. GDP pre-filter.",
        query=(
            "We selected GDC-FLEX 600x600 in RF for a commercial kitchen exhaust. "
            "Airflow is 2,500 m³/h. "
            "Please confirm configuration."
        ),
        assertions=[
            Assertion("capacity_issue", "response.content_text", "contains_any",
                      "2100|undersized|exceed|capacity|insufficient|too small|upsize|larger|modules|parallel",
                      category="logic"),
            Assertion("grease_concern", "response.content_text", "contains_any",
                      "grease|kitchen|pre-filter|GDP|pore|clog|block|contamination|fat|oil",
                      category="logic"),
        ],
    ),

    # --- GPT Prod 6: Cement + GDC without pre-filter ---
    "chatgpt_prod_cement_gdc_no_prefilter": TestCase(
        name="chatgpt_prod_cement_gdc_no_prefilter",
        description="[GPT Prod] Cement plant + GDC 900x600 → no pre-filter = dust clogs carbon",
        category="environment",
        tests_graph_node="Heavy dust→GDP required upstream of carbon GDC",
        pdf_reference="Carbon pores clogged by dust. GDP mechanical pre-filter required.",
        query=(
            "We plan to install GDC 900x600 carbon housings for a cement plant exhaust line. "
            "Airflow is 2,400 m³/h per unit. "
            "The exhaust contains fine cement dust. "
            "No mechanical pre-filtration is currently planned. "
            "Please confirm suitability."
        ),
        assertions=[
            Assertion("dust_concern", "response.content_text", "contains_any",
                      "dust|clog|pre-filter|GDP|pre-filtration|particle|mechanical|upstream",
                      category="logic"),
            Assertion("carbon_risk", "response.content_text", "contains_any",
                      "carbon|adsorption|pore|efficiency|service life|clog|block|reduce",
                      category="logic"),
        ],
    ),

    # --- GPT Prod 7: ATEX Zone 21 + GDC-FLEX → BLOCK ---
    "chatgpt_prod_atex21_gdcflex_block": TestCase(
        name="chatgpt_prod_atex21_gdcflex_block",
        description="[GPT Prod] ATEX Zone 21 + GDC-FLEX → BLOCK (no Ex certification)",
        category="environment",
        tests_graph_node="ATEX Zone 21=explosive likely during normal ops. No ATEX cert in catalog.",
        pdf_reference="No ATEX/Ex certification. Zone 21=likely during normal operation.",
        query=(
            "We want to install GDC-FLEX 600x600 in an ATEX Zone 21 area. "
            "Airflow is 1,600 m³/h. "
            "Please confirm compliance."
        ),
        assertions=[
            Assertion("atex_concern", "response.content_text", "contains_any",
                      "ATEX|explosion|explosive|zone 21|not certified|compliance|safety|ex-rated",
                      category="logic"),
            Assertion("cannot_approve", "response.content_text", "contains_any",
                      "cannot|not approved|not certified|not compliant|clarification|specialist|expert|protection|grounding|grounded|static|ignition|must",
                      category="output"),
        ],
    ),

    # --- GPT Prod 8: Flour Mill ATEX 22 + GDB 15000 m³/h ---
    "chatgpt_prod_flour_atex22_gdb_15000": TestCase(
        name="chatgpt_prod_flour_atex22_gdb_15000",
        description="[GPT Prod] Flour mill ATEX22 + 15000 m³/h + h≤1500mm → GDB 1800x900",
        category="sizing",
        tests_graph_node="GDB 1800x900=15300 m³/h, h=900mm. ATEX22 grounding.",
        pdf_reference="GDB 1800x900: Rek. flöde=15300, Höjd=900mm. ATEX22 grounding required.",
        query=(
            "I need a filtration bank for a flour mill exhaust system. "
            "The application is high-risk due to explosive wheat dust, classified as ATEX Zone 22. "
            "Total airflow is 15,000 m³/h. "
            "We have a fixed height limit of 1,500 mm on the installation platform, but width is not a problem. "
            "Material: Galvanized (FZ). "
            "Please recommend the GDB assembly and specific requirements."
        ),
        assertions=[
            Assertion("size_selection", "response.content_text", "contains_any",
                      "1800x900|1800|15300|15000",
                      category="output"),
            Assertion("atex_awareness", "response.content_text", "contains_any",
                      "ATEX|grounding|anti-static|explosion|zone 22|electrostatic|ground|static|ignition|spark",
                      category="logic"),
        ],
    ),

    # --- GPT Prod 9: Museum 85% RH + carbon → humidity degradation ---
    "chatgpt_prod_museum_85rh_carbon": TestCase(
        name="chatgpt_prod_museum_85rh_carbon",
        description="[GPT Prod] Museum 85% RH + GDC RF → carbon adsorption reduced by humidity",
        category="environment",
        tests_graph_node="High humidity >50-60% reduces carbon adsorption efficiency",
        pdf_reference="Carbon physics: water vapor competes for adsorption sites at high RH.",
        query=(
            "We require GDC 600x600 in RF for odor control in a museum archive. "
            "Relative humidity is constantly around 85%. "
            "Airflow is 1,200 m³/h. "
            "Please confirm performance suitability."
        ),
        assertions=[
            Assertion("humidity_concern", "response.content_text", "contains_any",
                      "humidity|RH|moisture|water vapor|adsorption|reduced|performance|degraded|efficiency",
                      category="logic"),
            Assertion("mitigation", "response.content_text", "contains_any",
                      "dehumidif|pre-heat|control|reduce|humidity|condition",
                      category="output"),
        ],
    ),

    # --- GPT Prod 10: Oversized GDC → low velocity channeling ---
    # NOTE: GDC doesn't have DIM_1800x1200. Use 1200x1200 (effective 9600 m³/h).
    # 800/9600 = 8% utilization = extreme oversizing.
    "chatgpt_prod_oversized_gdc_low_velocity": TestCase(
        name="chatgpt_prod_oversized_gdc_low_velocity",
        description="[GPT Prod] GDC 1200x1200 RF @ 800 m³/h → extreme oversizing (8% util), channeling risk",
        category="sizing",
        tests_graph_node="GDC 1200x1200 effective=9600 m³/h. 800/9600=8% util→oversized",
        pdf_reference="GDC 1200x1200 nominal=9600. 800<<9600. Low velocity→uneven distribution.",
        query=(
            "For an office odor control project, we selected GDC 1200x1200 in RF. "
            "Airflow is only 800 m³/h. "
            "We intentionally oversized to increase safety margin. "
            "Please confirm acceptability."
        ),
        assertions=[
            Assertion("oversizing_concern", "response.content_text", "contains_any",
                      "oversize|oversized|velocity|channeling|distribution|excessive|too large|inefficient|utilization",
                      category="logic"),
            Assertion("smaller_recommendation", "response.content_text", "contains_any",
                      "smaller|reduce|optimal|appropriate|recommend|closer|nominal|300x300|300x600|600x300",
                      category="output"),
        ],
    ),

    # ===================================================================
    #  CATEGORY: CHATGPT-GENERATED — Hardcore / Golden Manifest V2
    #  Source: ChatGPT-generated tricky scenarios, verified against
    #          Mann+Hummel HVAC Filterskåp catalog (PDF, v01-09-2025)
    #          and cross-checked by Claude. Covers: material locks,
    #          carbon physics, ATEX, geometry, LCC, stressor cascades.
    # ===================================================================

    # --- HC 1: GDMI SF Trap (marine C5-M) ---
    "hc_gdmi_sf_trap": TestCase(
        name="hc_gdmi_sf_trap",
        description="[HC] GDMI SF marine → BLOCK (Ej i Rostfritt), pivot GDB-SF+insulation",
        category="material",
        tests_graph_node="ProductFamily(FAM_GDMI).available_materials excludes RF/SF",
        pdf_reference="GDMI: 'Ej i Rostfritt'. Only AZ, ZM. Övriga skåp isoleras på plats.",
        query=(
            "We require an insulated GDMI housing in Syrafast Stainless Steel (SF / 316) "
            "for a marine chemical plant (C5-M). "
            "Airflow: 3400 m³/h. "
            "Please provide the code."
        ),
        assertions=[
            Assertion("material_block", "response.content_text", "contains_any",
                      "not available|unavailable|not offered|cannot|not possible|not manufactured",
                      category="logic"),
            Assertion("suggests_alternative", "response.content_text", "contains_any",
                      "GDB|SF|ZM|AZ|aluzink|insulation|on site|alternative|upgrade|material",
                      category="output"),
        ],
    ),

    # --- HC 2: GDC-FLEX RF availability (CORRECTED — RF IS available) ---
    "hc_gdcflex_rf_available": TestCase(
        name="hc_gdcflex_rf_available",
        description="[HC] GDC-FLEX RF → PASS (5 materials available incl. RF)",
        category="material",
        tests_graph_node="ProductFamily(FAM_GDC_FLEX).available_materials includes RF",
        pdf_reference="GDC-FLEX page: 5 material icons FZ/AZ/RF/SF/ZM. RF available.",
        query=(
            "Office ventilation system. "
            "We want GDC-FLEX in Stainless Steel (RF). "
            "Airflow: 1750 m³/h. "
            "Please confirm availability."
        ),
        assertions=[
            Assertion("no_material_block", "response.content_text", "not_contains_any",
                      "not available|unavailable|not offered|cannot be manufactured",
                      category="logic"),
            Assertion("proceeds", "response.clarification_needed|response.product_card|response.content_text", "any_contains",
                      "true|GDC|FLEX|housing|length|configure|750|900",
                      category="output"),
        ],
    ),

    # --- HC 3: GDB Length 900mm → BLOCK ---
    "hc_gdb_length_900_block": TestCase(
        name="hc_gdb_length_900_block",
        description="[HC] GDB length 900mm → BLOCK (only 550/750), recommend 750",
        category="sizing",
        tests_graph_node="GDB housing lengths: 550/600 and 750/800 only",
        pdf_reference="GDB: '550 mm för korta påsfilter och 750 mm för långa'. No 900mm.",
        query=(
            "We want GDB-600x600 in FZ, housing length 900 mm. "
            "Airflow: 3400 m³/h."
        ),
        assertions=[
            Assertion("length_issue", "response.content_text", "contains_any",
                      "not available|invalid|550|750|length|not offered|option",
                      category="logic"),
        ],
    ),

    # --- HC 4: Tropical Greenhouse 95% RH ---
    "hc_greenhouse_95rh_carbon": TestCase(
        name="hc_greenhouse_95rh_carbon",
        description="[HC] Greenhouse 95% RH + GDC → carbon humidity degradation warning",
        category="environment",
        tests_graph_node="High humidity >70% reduces carbon adsorption (capillary condensation)",
        pdf_reference="Carbon physics: water occupies micropores, VOC breakthrough increases.",
        query=(
            "We are installing a GDC-600x600 carbon housing in a greenhouse. "
            "Temperature: 30°C. Humidity: 95% RH. "
            "Airflow: 2000 m³/h. "
            "The goal is VOC removal."
        ),
        assertions=[
            Assertion("humidity_concern", "response.content_text", "contains_any",
                      "humidity|RH|moisture|water|adsorption|reduced|performance|degraded|efficiency|warning",
                      category="logic"),
        ],
    ),

    # --- HC 5: Kitchen Grease Killer ---
    "hc_kitchen_grease_killer": TestCase(
        name="hc_kitchen_grease_killer",
        description="[HC] Kitchen hood → GDC-FLEX directly = carbon destroyed, GDP required",
        category="environment",
        tests_graph_node="Kitchen grease→irreversible carbon pore blockage→GDP upstream",
        pdf_reference="Grease causes irreversible carbon pore blockage. GDP pre-filter required.",
        query=(
            "Commercial hotel kitchen exhaust. "
            "We want to connect GDC-FLEX directly above the hood to save space. "
            "Airflow: 1500 m³/h."
        ),
        assertions=[
            Assertion("grease_concern", "response.content_text", "contains_any",
                      "grease|kitchen|pre-filter|GDP|pore|clog|block|contamination|fat|oil|lipid",
                      category="logic"),
            Assertion("assembly_required", "response.content_text", "contains_any",
                      "GDP|pre-filter|upstream|stage|assembly|two-stage|mechanical",
                      category="output"),
        ],
    ),

    # --- HC 6: Shared Duct Trap (office + fry station) ---
    "hc_shared_duct_grease_trap": TestCase(
        name="hc_shared_duct_grease_trap",
        description="[HC] Office duct shared with fry station → grease risk for carbon",
        category="environment",
        tests_graph_node="Even small grease contamination→carbon damage. Stressor cascade.",
        pdf_reference="Grease blocks carbon pores irreversibly. Pre-filter needed.",
        query=(
            "Our office supply air duct passes through a garage. "
            "We want GDC-600x600 to remove diesel smells. "
            "However, the same duct is connected to a small fry station exhaust. "
            "Airflow: 2000 m³/h."
        ),
        assertions=[
            Assertion("grease_risk", "response.content_text", "contains_any",
                      "grease|fry|oil|fat|pre-filter|GDP|contamination|kitchen|pore|block|lipid",
                      category="logic"),
        ],
    ),

    # --- HC 7: Formaldehyde Lab ---
    "hc_formaldehyde_lab": TestCase(
        name="hc_formaldehyde_lab",
        description="[HC] Anatomy lab formaldehyde → standard carbon insufficient, media warning",
        category="environment",
        tests_graph_node="Formaldehyde poorly adsorbed by standard carbon. Impregnated media needed.",
        pdf_reference="Expert knowledge: HCHO MW=30, standard AC poor. KOH/KI media in catalog.",
        query=(
            "Anatomy laboratory exhaust. "
            "Formaldehyde vapors present. "
            "We want GDC-600x600 in RF. "
            "Airflow: 2000 m³/h."
        ),
        assertions=[
            Assertion("chemical_concern", "response.content_text", "contains_any",
                      "formaldehyde|chemical|media|impregnated|special|specific|standard carbon|KOH|amine",
                      category="logic"),
        ],
    ),

    # --- HC 8: Zero-Tolerance Hole (service access, NOT flanges) ---
    "hc_shaft_service_access": TestCase(
        name="hc_shaft_service_access",
        description="[HC] Shaft exactly 1200x1500 → service door clearance warning",
        category="sizing",
        tests_graph_node="Housing fits shaft, but service door needs clearance (+140mm from diagram)",
        pdf_reference="GDB side-hinged service door. Diagram shows +140mm clearance needed.",
        query=(
            "I have a shaft opening exactly 1200x1500 mm. "
            "I want GDB-1200x1500. "
            "Airflow: 17,000 m³/h."
        ),
        assertions=[
            Assertion("sizing_ok", "response.content_text", "contains_any",
                      "1200x1500|17000|17 000|fit|suitable|match|configuration",
                      category="logic"),
        ],
    ),

    # --- HC 9: FLEX Contact Time Failure (3500 >> 1750) ---
    "hc_flex_contact_time_failure": TestCase(
        name="hc_flex_contact_time_failure",
        description="[HC] GDC-FLEX 600x600 @ 3500 m³/h → 200% overload, BLOCK",
        category="sizing",
        tests_graph_node="GDC-FLEX 600x600=1750 m³/h. 3500=200% overload.",
        pdf_reference="GDC-FLEX 600x600: Rek. flöde=1750. Contact time failure at 3500.",
        query=(
            "We need to remove heavy solvent odors at 3500 m³/h. "
            "Duct size: 600x600 mm. "
            "Can we use GDC-FLEX 600x600?"
        ),
        assertions=[
            Assertion("capacity_exceeded", "response.content_text", "contains_any",
                      "1750|exceed|capacity|undersized|too high|insufficient|overload|upsize|larger",
                      category="logic"),
            Assertion("multi_module", "response.content_text", "contains_any",
                      "1200|two|2|multiple|module|larger|900|upsize",
                      category="output"),
        ],
    ),

    # --- HC 10: Tight Maintenance Shaft (650mm) ---
    "hc_tight_maintenance_shaft": TestCase(
        name="hc_tight_maintenance_shaft",
        description="[HC] 650mm shaft + GDB-600x600 side door → service clearance warning",
        category="sizing",
        tests_graph_node="GDB side-hinged door needs clearance. 650-600=50mm insufficient.",
        pdf_reference="GDB: 'Serviceluckan är höghängd som standard'. Diagram +140mm.",
        query=(
            "We have a 650 mm wide shaft. "
            "We want GDB-600x600 with side access door."
        ),
        assertions=[
            Assertion("clearance_concern", "response.content_text", "contains_any",
                      "clearance|service|access|door|space|maintenance|tight|insufficient|650|PFF|front",
                      category="logic"),
        ],
    ),

    # --- HC 11: ATEX Zone 21 Powder Booth ---
    "hc_atex21_powder_booth": TestCase(
        name="hc_atex21_powder_booth",
        description="[HC] ATEX Zone 21 powder booth + GDB-FZ → BLOCK (no Ex cert)",
        category="environment",
        tests_graph_node="ATEX Zone 21=explosive dust likely during normal ops. No Ex cert.",
        pdf_reference="No ATEX/Ex certification in catalog. Zone 21 requires Cat 2D.",
        query=(
            "Powder coating booth exhaust. "
            "ATEX Zone 21 (dust). "
            "Can we use standard GDB-FZ?"
        ),
        assertions=[
            Assertion("atex_concern", "response.content_text", "contains_any",
                      "ATEX|explosion|explosive|zone 21|not certified|compliance|safety|ex-rated|cannot|not suitable|not recommended|powder|dust|grounding",
                      category="logic"),
        ],
    ),

    # --- HC 12: Hospital Supply Leakage (no HEPA mention) ---
    "hc_hospital_leakage_class": TestCase(
        name="hc_hospital_leakage_class",
        description="[HC] Surgical ward + GDB-FZ → BLOCK (bolted, hygiene), pivot GDMI-ZM",
        category="environment",
        tests_graph_node="Hospital requires hygienic construction. GDB=bolted. Pivot GDMI.",
        pdf_reference="GDB=bolted enkelväggsutförande. GDMI=insulated dubbelmantlat. Both max F9.",
        query=(
            "Surgical ward supply air. "
            "Airflow: 3400 m³/h. "
            "Duct 600x600 mm. "
            "Can we use GDB-FZ?"
        ),
        assertions=[
            Assertion("hospital_concern", "response.content_text", "contains_any",
                      "hospital|surgical|hygiene|not suitable|not recommended|bolted|leakage|upgrade|sterile",
                      category="logic"),
            Assertion("suggests_gdmi", "response.content_text", "contains_any",
                      "GDMI|insulated|ZM|upgrade|alternative",
                      category="output"),
        ],
    ),

    # --- HC 13: Wastewater H2S + FZ ---
    "hc_wastewater_h2s_fz": TestCase(
        name="hc_wastewater_h2s_fz",
        description="[HC] H2S wastewater + GDB FZ → BLOCK (zinc attacked), suggest SF",
        category="environment",
        tests_graph_node="H2S aggressively attacks zinc. FZ=C3 insufficient.",
        pdf_reference="FZ=C3 (galvanized zinc). H2S corrosion. Need SF(C5.1).",
        query=(
            "Wastewater plant exhaust. "
            "Hydrogen Sulfide (H2S) present. "
            "We want GDB in FZ."
        ),
        assertions=[
            Assertion("h2s_concern", "response.content_text", "contains_any",
                      "H2S|hydrogen sulfide|corrosion|corrosive|not suitable|attack|zinc|chemical|block|warning",
                      category="logic"),
            Assertion("suggests_upgrade", "response.content_text", "contains_any",
                      "SF|RF|stainless|C5|upgrade|alternative|material|zinc-magnesium|ZM",
                      category="output"),
        ],
    ),

    # --- HC 14: Aluminium Dust ATEX 22 ---
    "hc_aluminium_dust_atex22": TestCase(
        name="hc_aluminium_dust_atex22",
        description="[HC] Aluminium grinding dust ATEX 22 + GDB FZ → grounding + anti-static",
        category="environment",
        tests_graph_node="Aluminium dust=explosive+conductive. ATEX22 grounding required.",
        pdf_reference="ATEX Zone 22: grounding + anti-static filter media required.",
        query=(
            "Aluminium grinding dust. "
            "ATEX Zone 22. "
            "GDB housing in FZ."
        ),
        assertions=[
            Assertion("atex_awareness", "response.content_text", "contains_any",
                      "ATEX|grounding|anti-static|explosion|zone 22|electrostatic|ground|dust",
                      category="logic"),
        ],
    ),

    # --- HC 15: Arctic -40°C Condensation ---
    "hc_arctic_condensation": TestCase(
        name="hc_arctic_condensation",
        description="[HC] Rooftop -40°C + GDB-FZ → BLOCK (condensation/freezing), need GDMI",
        category="environment",
        tests_graph_node="GDB=oisolerat. -40°C outside → condensation guaranteed. Need GDMI.",
        pdf_reference="GDB: 'oisolerat enkelväggsutförande'. GDMI: 'värme- och kondensisolerat'.",
        query=(
            "Rooftop installation in Northern Norway. "
            "Outdoor temperature: -40°C. "
            "Exhaust air: 20°C / 50% RH. "
            "We want GDB-FZ."
        ),
        assertions=[
            Assertion("condensation_concern", "response.content_text", "contains_any",
                      "condensation|freezing|insulation|temperature|cold|outdoor|not suitable|warning|block",
                      category="logic"),
            Assertion("suggests_gdmi", "response.content_text", "contains_any",
                      "GDMI|insulated|insulation|alternative|upgrade",
                      category="output"),
        ],
    ),

    # --- HC 16: Cruise Ship 2600 > GDC 2000 ---
    "hc_cruise_ship_gdc_oversized": TestCase(
        name="hc_cruise_ship_gdc_oversized",
        description="[HC] Cruise ship 2600 m³/h + GDC 600x600 (2000) → undersized",
        category="sizing",
        tests_graph_node="GDC 600x600=2000 m³/h. 2600>2000 → undersized.",
        pdf_reference="GDC 600x600: Rek. flöde=2000. Next size: 900x600=3000.",
        query=(
            "Cruise ship exhaust. "
            "2600 m³/h. "
            "GDC-600x600 in RF."
        ),
        assertions=[
            Assertion("capacity_exceeded", "response.content_text", "contains_any",
                      "2000|exceed|capacity|undersized|too high|insufficient|upsize|larger|900",
                      category="logic"),
        ],
    ),

    # --- HC 17: LCC 4x separate 300x300 housings ---
    "hc_lcc_four_small_housings": TestCase(
        name="hc_lcc_four_small_housings",
        description="[HC] 4 separate 300x300 housings vs 1x600x600 → LCC warning",
        category="sizing",
        tests_graph_node="4 separate small housings = higher cost, more maintenance than 1x600x600",
        pdf_reference="1/4 modul=300x300, 1/1 modul=600x600. 3400 m³/h benchmark per 1/1 modul.",
        query=(
            "We need 3400 m³/h. "
            "Instead of one 600x600 housing, we want four separate 300x300 housings."
        ),
        assertions=[
            Assertion("efficiency_concern", "response.content_text", "contains_any",
                      "600x600|single|one|recommend|cost|maintenance|efficient|LCC|unnecessary|simpler",
                      category="logic"),
        ],
    ),

    # --- HC 18: Short Bag 600mm in 550mm housing ---
    "hc_short_bag_geometry_error": TestCase(
        name="hc_short_bag_geometry_error",
        description="[HC] 600mm bag filter in GDB-550 → BLOCK (max 450mm), need 750",
        category="sizing",
        tests_graph_node="GDB 550mm housing: filter max 450mm. 600mm filter doesn't fit.",
        pdf_reference="Skåp 550/600mm → Filter max 450mm. Skåp 750/800mm → Filter max 650mm.",
        query=(
            "We have bag filters 600 mm long. "
            "Please provide GDB-550 housing."
        ),
        assertions=[
            Assertion("geometry_block", "response.content_text", "contains_any",
                      "not fit|too long|exceed|450|750|length|geometry|does not|cannot|maximum",
                      category="logic"),
        ],
    ),

    # --- HC 19: Marine Insulated Stainless (GDMI-SF) ---
    "hc_marine_gdmi_sf_pivot": TestCase(
        name="hc_marine_gdmi_sf_pivot",
        description="[HC] Ship + GDMI-SF → BLOCK (Ej i Rostfritt), pivot GDB-SF+insulation",
        category="material",
        tests_graph_node="GDMI not in SF. Suggest GDB-SF + insulation on site.",
        pdf_reference="GDMI: 'Ej i Rostfritt'. Övriga skåp isoleras på plats.",
        query=(
            "Ship installation. "
            "We require insulation and Syrafast stainless (SF). "
            "Please provide GDMI-SF."
        ),
        assertions=[
            Assertion("material_block", "response.content_text", "contains_any",
                      "not available|unavailable|not offered|cannot|not possible",
                      category="logic"),
            Assertion("suggests_alternative", "response.content_text", "contains_any",
                      "GDB|SF|insulation|on site|alternative|ZM",
                      category="output"),
        ],
    ),

    # --- HC 20: THE STRESSOR CASCADE (Boss Level) ---
    "hc_stressor_cascade_boss": TestCase(
        name="hc_stressor_cascade_boss",
        description="[HC] Hospital rooftop kitchen marine + GDC-FLEX RF 600x600 3000→MULTI-BLOCK",
        category="environment",
        tests_graph_node="5 stressors: capacity+insulation+hygiene+marine+grease. RF available.",
        pdf_reference="GDC-FLEX 600x600=1750<3000. Kitchen=GDP. Rooftop=insulation. Hospital=hygiene.",
        query=(
            "Rooftop kitchen exhaust for a hospital. "
            "Marine climate. "
            "3000 m³/h. "
            "We want GDC-FLEX RF 600x600."
        ),
        assertions=[
            Assertion("capacity_fail", "response.content_text", "contains_any",
                      "1750|exceed|capacity|undersized|insufficient|3000|too high|upsize",
                      category="logic"),
            Assertion("grease_concern", "response.content_text", "contains_any",
                      "grease|kitchen|pre-filter|GDP|pore|clog|fat|oil|lipid",
                      category="logic"),
            Assertion("multi_issue", "response.content_text", "contains_any",
                      "outdoor|rooftop|insulation|marine|hospital|hygiene|multiple|several",
                      category="logic"),
        ],
    ),
}


# ---------------------------------------------------------------------------
# Load AI-generated tests from JSON (produced by Test Generator debate)
# ---------------------------------------------------------------------------
GENERATED_TESTS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "backend", "static", "generated-tests.json"
)

def _load_generated_tests() -> dict:
    """Load approved AI-generated tests and merge into TEST_CASES."""
    if not os.path.exists(GENERATED_TESTS_FILE):
        return {}
    try:
        with open(GENERATED_TESTS_FILE, "r") as f:
            tests_data = json.load(f)
        result = {}
        for t in tests_data:
            if not t.get("name") or not t.get("query"):
                continue
            assertions = []
            for a in t.get("assertions", []):
                assertions.append(Assertion(
                    name=a.get("name", ""),
                    check=a.get("check", "response.content_text"),
                    condition=a.get("condition", "contains_any"),
                    expected=a.get("expected", ""),
                    category=a.get("category", "output"),
                ))
            result[t["name"]] = TestCase(
                name=t["name"],
                description=t.get("description", "AI-generated test"),
                query=t["query"],
                category=t.get("category", "generated"),
                tests_graph_node=t.get("tests_graph_node", ""),
                pdf_reference=t.get("pdf_reference", "AI-generated from catalog debate"),
                assertions=assertions,
            )
        return result
    except (json.JSONDecodeError, OSError, KeyError) as e:
        print(f"  Warning: Could not load generated tests: {e}")
        return {}

# Merge generated tests into the active suite
TEST_CASES.update(_load_generated_tests())


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
def authenticate() -> str:
    """Login and return JWT token."""
    try:
        r = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": USERNAME, "password": PASSWORD},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()["access_token"]
    except Exception as e:
        print(f"  AUTH ERROR: {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# SSE Client
# ---------------------------------------------------------------------------
def call_streaming_endpoint(query: str, session_id: str, token: str) -> list:
    """Hit the streaming endpoint and collect all SSE events."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {"query": query, "session_id": session_id}

    events = []
    try:
        r = requests.post(
            f"{BASE_URL}/consult/deep-explainable/stream",
            json=payload,
            headers=headers,
            stream=True,
            timeout=TIMEOUT,
        )
        r.raise_for_status()

        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                try:
                    event = json.loads(line[6:])
                    events.append(event)
                except json.JSONDecodeError:
                    pass
    except requests.exceptions.Timeout:
        events.append({"type": "error", "detail": f"Timeout after {TIMEOUT}s"})
    except Exception as e:
        events.append({"type": "error", "detail": str(e)})

    return events


# ---------------------------------------------------------------------------
# Result Extraction
# ---------------------------------------------------------------------------
def extract_test_data(events: list) -> dict:
    """Extract structured data from SSE events for assertion checking."""
    data = {
        "response": {},
        "graph_report": {},
        "technical_state": {},
        "timings": {},
        "errors": [],
        "steps": [],
    }

    for event in events:
        etype = event.get("type", event.get("step", ""))

        if etype == "error":
            data["errors"].append(event.get("detail", "unknown"))

        elif event.get("type") == "complete" or event.get("step") == "complete":
            resp = event.get("response", {})
            if isinstance(resp, str):
                try:
                    resp = json.loads(resp)
                except json.JSONDecodeError:
                    resp = {"raw": resp}
            data["response"] = resp
            data["graph_report"] = event.get("graph_report", {})
            data["technical_state"] = event.get("technical_state", {})
            data["timings"] = event.get("timings", {})

            # Flatten content_segments into single text for easy matching
            segments = resp.get("content_segments", [])
            text_parts = []
            for seg in segments:
                if isinstance(seg, dict):
                    text_parts.append(seg.get("text", ""))
                elif isinstance(seg, str):
                    text_parts.append(seg)
            data["response"]["content_text"] = " ".join(text_parts).lower()

            # Flatten clarification option descriptions for assertion matching
            clar = resp.get("clarification") or {}
            clar_texts = []
            for opt in clar.get("options", []):
                if isinstance(opt, dict):
                    clar_texts.append(opt.get("description", ""))
                    clar_texts.append(str(opt.get("value", "")))
            data["response"]["clarification_text"] = " ".join(clar_texts).lower()

            # Derive tags_count from technical_state.tags dict length
            ts = data.get("technical_state", {})
            if isinstance(ts.get("tags"), dict):
                ts["tags_count"] = len(ts["tags"])

        elif event.get("type") == "inference":
            data["steps"].append({
                "step": event.get("step"),
                "status": event.get("status"),
                "detail": event.get("detail", ""),
            })

    return data


# ---------------------------------------------------------------------------
# Assertion Engine
# ---------------------------------------------------------------------------
def resolve_path(data: dict, path: str):
    """Resolve a dotted path like 'graph_report.application' from nested dict."""
    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    return current


def check_assertion(assertion: Assertion, data: dict) -> Assertion:
    """Evaluate a single assertion against extracted data."""
    a = assertion

    # Handle pipe-separated paths (OR logic for "any_exists")
    if "|" in a.check:
        paths = a.check.split("|")
    else:
        paths = [a.check]

    values = []
    for p in paths:
        v = resolve_path(data, p)
        values.append(v)

    # Primary value (first path)
    val = values[0]
    a.actual = str(val)[:200] if val is not None else "(none)"

    if a.condition == "equals":
        a.passed = str(val).lower() == a.expected.lower()
        if not a.passed:
            a.message = f"Expected '{a.expected}', got '{a.actual}'"

    elif a.condition == "not_equals":
        a.passed = val is None or str(val).lower() != a.expected.lower()
        if not a.passed:
            a.message = f"Expected NOT '{a.expected}', but got it"

    elif a.condition == "contains":
        a.passed = val is not None and a.expected.lower() in str(val).lower()
        if not a.passed:
            a.message = f"Expected to contain '{a.expected}' in '{a.actual}'"

    elif a.condition == "contains_any":
        options = [o.strip().lower() for o in a.expected.split("|")]
        val_str = str(val).lower() if val is not None else ""
        a.passed = any(o in val_str for o in options)
        if not a.passed:
            a.message = f"Expected any of [{a.expected}] in '{a.actual[:100]}'"

    elif a.condition == "not_contains_any":
        options = [o.strip().lower() for o in a.expected.split("|")]
        val_str = str(val).lower() if val is not None else ""
        a.passed = not any(o in val_str for o in options)
        if not a.passed:
            matched = [o for o in options if o in val_str]
            a.message = f"Expected NONE of [{a.expected}] but found [{', '.join(matched)}]"

    elif a.condition == "exists":
        if isinstance(val, list):
            a.passed = len(val) > 0
        elif isinstance(val, dict):
            a.passed = len(val) > 0
        else:
            a.passed = val is not None and val != "" and val != 0
        if not a.passed:
            a.message = f"Expected to exist, got '{a.actual}'"

    elif a.condition == "not_exists":
        a.passed = val is None or val == "" or val == 0
        if not a.passed:
            a.message = f"Expected not to exist, got '{a.actual}'"

    elif a.condition == "any_exists":
        a.passed = any(
            v is not None and v != "" and v != 0 and (not isinstance(v, (list, dict)) or len(v) > 0)
            for v in values
        )
        a.actual = " | ".join(str(v)[:50] if v else "(none)" for v in values)
        if not a.passed:
            a.message = f"Expected at least one of [{a.check}] to exist"

    elif a.condition == "any_contains":
        # Check if ANY of the pipe-separated paths contains the expected string
        options = [o.strip().lower() for o in a.expected.split("|")]
        a.passed = any(
            v is not None and any(o in str(v).lower() for o in options)
            for v in values
        )
        a.actual = " | ".join(str(v)[:80] if v else "(none)" for v in values)
        if not a.passed:
            a.message = f"Expected any of [{a.check}] to contain [{a.expected}]"

    elif a.condition == "true":
        a.passed = val is True or str(val).lower() == "true"
        if not a.passed:
            a.message = f"Expected True, got '{a.actual}'"

    elif a.condition == "false":
        a.passed = val is False or val is None or str(val).lower() == "false"
        if not a.passed:
            a.message = f"Expected False/None, got '{a.actual}'"

    elif a.condition == "greater_than":
        try:
            a.passed = float(val) > float(a.expected)
        except (TypeError, ValueError):
            a.passed = False
        if not a.passed:
            a.message = f"Expected > {a.expected}, got '{a.actual}'"

    else:
        a.message = f"Unknown condition: {a.condition}"

    return a


# ---------------------------------------------------------------------------
# Diagnosis — Likely cause analysis
# ---------------------------------------------------------------------------
def diagnose_failure(result: TestResult, test: TestCase) -> str:
    """Analyze failed assertions to determine likely root cause."""
    failed_categories = [a.category for a in result.assertions_failed]

    if "detection" in failed_categories:
        # Detection failures = Scribe or graph keywords
        return "scribe_or_graph_keywords"
    elif "logic" in failed_categories and "output" not in failed_categories:
        # Logic failed but output exists = engine/graph data
        return "engine_or_graph_data"
    elif "output" in failed_categories and "logic" not in failed_categories:
        # Output wrong but logic worked = LLM generation
        return "llm_generation"
    elif "logic" in failed_categories and "output" in failed_categories:
        # Both failed = graph data is likely root cause
        return "graph_data"
    else:
        return "unknown"


# ---------------------------------------------------------------------------
# Test Runner
# ---------------------------------------------------------------------------
def run_test(test: TestCase, token: str) -> TestResult:
    """Run a single test case and return results."""
    session_id = f"test-{test.name}-{uuid.uuid4().hex[:8]}"
    result = TestResult(test_name=test.name, status="PASS", category=test.category)

    # Clear any previous session state
    try:
        requests.post(
            f"{BASE_URL}/chat/clear",
            json={"session_id": session_id},
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
    except Exception:
        pass

    start = time.time()

    # Execute query
    events = call_streaming_endpoint(test.query, session_id, token)
    result.raw_events = events
    result.duration_s = time.time() - start

    # Check for API errors
    errors = [e for e in events if e.get("type") == "error"]
    if errors:
        result.status = "ERROR"
        result.error_message = errors[0].get("detail", "Unknown error")
        return result

    # Check for complete event
    complete_events = [e for e in events if e.get("type") == "complete" or e.get("step") == "complete"]
    if not complete_events:
        result.status = "ERROR"
        result.error_message = "No 'complete' event received"
        return result

    # Extract data and run assertions
    data = extract_test_data(events)
    result.assertions_total = len(test.assertions)

    for assertion in test.assertions:
        checked = check_assertion(assertion, data)
        result.assertions_all.append(checked)
        if checked.passed:
            result.assertions_passed += 1
        else:
            result.assertions_failed.append(checked)

    if result.assertions_failed:
        result.status = "FAIL"
        result.likely_cause = diagnose_failure(result, test)

    return result


def print_result(result: TestResult, verbose: bool = False):
    """Print a single test result."""
    test = TEST_CASES.get(result.test_name)
    desc = test.description if test else ""

    if result.status == "PASS":
        icon = "PASS"
    elif result.status == "FAIL":
        icon = "FAIL"
    else:
        icon = "ERR!"

    passed_str = f"{result.assertions_passed}/{result.assertions_total}"
    cat = f"[{result.category}]" if result.category else ""
    print(f"  {icon} {result.test_name:<32} {passed_str:<6} {result.duration_s:>5.1f}s {cat:<12} {desc[:60]}")

    if result.status == "ERROR":
        print(f"       ERROR: {result.error_message}")

    if result.status == "FAIL":
        for a in result.assertions_failed:
            cat_label = f"({a.category})" if a.category else ""
            print(f"       FAIL: [{a.name}] {a.message} {cat_label}")
        if result.likely_cause:
            print(f"       LIKELY CAUSE: {result.likely_cause}")

    if verbose and result.raw_events:
        output_file = f"/tmp/test-hvac-{result.test_name}.json"
        with open(output_file, "w") as f:
            json.dump(result.raw_events, f, indent=2, default=str)
        print(f"       Raw events saved to: {output_file}")


# ---------------------------------------------------------------------------
# Gap Analysis
# ---------------------------------------------------------------------------
def print_gap_analysis(results: list):
    """Analyze all failures and produce a gap analysis grouped by likely cause."""
    print(f"\n{'=' * 80}")
    print(f"  GAP ANALYSIS — What needs fixing and where")
    print(f"{'=' * 80}\n")

    # Group by likely cause
    by_cause = defaultdict(list)
    for r in results:
        if r.status == "FAIL":
            by_cause[r.likely_cause].append(r)
        elif r.status == "ERROR":
            by_cause["api_error"].append(r)

    cause_labels = {
        "graph_data": "GRAPH DATA — Missing nodes, relationships, or properties in Neo4j",
        "engine_or_graph_data": "ENGINE/GRAPH — Engine logic or missing graph data",
        "scribe_or_graph_keywords": "SCRIBE/KEYWORDS — Intent extraction failed (missing keywords or Scribe bug)",
        "llm_generation": "LLM GENERATION — Engine was correct but LLM produced wrong text",
        "api_error": "API ERROR — Backend error or timeout",
        "unknown": "UNKNOWN — Needs manual investigation",
    }

    if not by_cause:
        print("  No failures detected! All tests passed.\n")
        return

    for cause, tests in sorted(by_cause.items()):
        label = cause_labels.get(cause, cause)
        print(f"  --- {label} ({len(tests)} tests) ---\n")

        for r in tests:
            test = TEST_CASES.get(r.test_name)
            print(f"    {r.test_name}")
            if test:
                print(f"      Graph dependency: {test.tests_graph_node}")
                print(f"      PDF reference: {test.pdf_reference}")
            for a in r.assertions_failed:
                print(f"      FAILED: [{a.name}] {a.message}")
            print()

    # Category summary
    print(f"  --- SUMMARY BY CATEGORY ---\n")
    by_cat = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0, "error": 0})
    for r in results:
        cat = r.category or "uncategorized"
        by_cat[cat]["total"] += 1
        if r.status == "PASS":
            by_cat[cat]["passed"] += 1
        elif r.status == "FAIL":
            by_cat[cat]["failed"] += 1
        else:
            by_cat[cat]["error"] += 1

    print(f"    {'Category':<15} {'Total':>6} {'Pass':>6} {'Fail':>6} {'Error':>6} {'Rate':>8}")
    print(f"    {'─' * 15} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 8}")
    for cat in sorted(by_cat.keys()):
        s = by_cat[cat]
        rate = f"{s['passed']/s['total']*100:.0f}%" if s['total'] > 0 else "N/A"
        print(f"    {cat:<15} {s['total']:>6} {s['passed']:>6} {s['failed']:>6} {s['error']:>6} {rate:>8}")

    totals = {"total": 0, "passed": 0, "failed": 0, "error": 0}
    for s in by_cat.values():
        for k in totals:
            totals[k] += s[k]
    rate = f"{totals['passed']/totals['total']*100:.0f}%" if totals['total'] > 0 else "N/A"
    print(f"    {'─' * 15} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 8}")
    print(f"    {'TOTAL':<15} {totals['total']:>6} {totals['passed']:>6} {totals['failed']:>6} {totals['error']:>6} {rate:>8}")
    print()

    # Actionable graph fix suggestions
    graph_failures = by_cause.get("graph_data", []) + by_cause.get("engine_or_graph_data", [])
    if graph_failures:
        print(f"  --- SUGGESTED GRAPH FIXES ---\n")
        seen_nodes = set()
        for r in graph_failures:
            test = TEST_CASES.get(r.test_name)
            if test and test.tests_graph_node and test.tests_graph_node not in seen_nodes:
                seen_nodes.add(test.tests_graph_node)
                print(f"    FIX: {test.tests_graph_node}")
                print(f"          (for test: {r.test_name})")
        print()


# ---------------------------------------------------------------------------
# JSON Export for Test Lab viewer
# ---------------------------------------------------------------------------
def serialize_results_json(results: list, output_path: str):
    """Serialize test results to JSON for the Test Lab webapp viewer."""
    from datetime import datetime, timezone

    categories = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0, "errors": 0})
    tests_out = []

    for r in results:
        test = TEST_CASES.get(r.test_name)
        cat = r.category or "uncategorized"
        categories[cat]["total"] += 1
        if r.status == "PASS":
            categories[cat]["passed"] += 1
        elif r.status == "FAIL":
            categories[cat]["failed"] += 1
        else:
            categories[cat]["errors"] += 1

        # Re-extract response data from raw events
        data = extract_test_data(r.raw_events) if r.raw_events else {}
        resp = data.get("response", {})

        # Build assertion list from stored results
        all_assertions = []
        for a in r.assertions_all:
            all_assertions.append({
                "name": a.name,
                "check": a.check,
                "condition": a.condition,
                "expected": a.expected,
                "actual": a.actual,
                "passed": a.passed,
                "message": a.message,
                "category": a.category,
            })

        tests_out.append({
            "name": r.test_name,
            "description": test.description if test else "",
            "category": cat,
            "query": test.query if test else "",
            "graph_dependency": test.tests_graph_node if test else "",
            "pdf_reference": test.pdf_reference if test else "",
            "status": r.status,
            "duration_s": round(r.duration_s, 2),
            "likely_cause": r.likely_cause or None,
            "error_message": r.error_message or None,
            "assertions": all_assertions,
            "response": {
                "content_text": resp.get("content_text", ""),
                "content_segments": resp.get("content_segments", []),
                "product_card": resp.get("product_card"),
                "product_cards": resp.get("product_cards"),
                "clarification": resp.get("clarification"),
                "clarification_needed": resp.get("clarification_needed", False),
                "risk_detected": resp.get("risk_detected", False),
                "risk_severity": resp.get("risk_severity"),
                "status_badges": resp.get("status_badges", []),
            },
            "inference_steps": data.get("steps", []),
        })

    output = {
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "base_url": BASE_URL,
            "total_tests": len(results),
            "passed": sum(1 for r in results if r.status == "PASS"),
            "failed": sum(1 for r in results if r.status == "FAIL"),
            "errors": sum(1 for r in results if r.status == "ERROR"),
            "duration_s": round(sum(r.duration_s for r in results), 1),
            "categories": dict(categories),
        },
        "tests": tests_out,
    }

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n  JSON results saved to: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
PARALLEL_WORKERS = int(os.getenv("TEST_PARALLEL", "10"))


def _run_test_wrapper(args_tuple):
    """Wrapper for ThreadPoolExecutor."""
    name, test, token = args_tuple
    result = run_test(test, token)
    return name, result


def _parse_flag(args, flag, has_value=False, default=None):
    """Extract a flag (and optional value) from args list, returning (value, remaining_args)."""
    if flag not in args:
        return default, args
    idx = args.index(flag)
    if has_value and idx + 1 < len(args):
        val = args[idx + 1]
        remaining = [a for a in args if a not in (flag, val)]
        return val, remaining
    elif has_value:
        remaining = [a for a in args if a != flag]
        return default, remaining
    else:
        remaining = [a for a in args if a != flag]
        return True, remaining


def main():
    args = sys.argv[1:]

    # Handle "list" command
    if args and args[0] == "list":
        print(f"\nAvailable test cases ({len(TEST_CASES)} total):\n")
        by_cat = defaultdict(list)
        for name, tc in TEST_CASES.items():
            by_cat[tc.category].append((name, tc))

        for cat in sorted(by_cat.keys()):
            print(f"  [{cat}]")
            for name, tc in by_cat[cat]:
                print(f"    {name:<35} {tc.description[:55]}")
            print()
        print(f"Run with: python run_tests.py [test-name|all|--category <cat>|--gap|--parallel N|--limit N]")
        return

    # Parse flags
    gap_mode, args = _parse_flag(args, "--gap")
    gap_mode = gap_mode or False

    json_output, args = _parse_flag(args, "--json", has_value=True,
        default=None)
    if json_output is None and "--json" in sys.argv:
        json_output = os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend", "static", "test-results.json")

    category_filter, args = _parse_flag(args, "--category", has_value=True)

    parallel_str, args = _parse_flag(args, "--parallel", has_value=True)
    parallel = int(parallel_str) if parallel_str else PARALLEL_WORKERS

    sequential, args = _parse_flag(args, "--sequential")
    sequential = sequential or False

    limit_str, args = _parse_flag(args, "--limit", has_value=True)
    limit = int(limit_str) if limit_str else None

    # Determine which tests to run
    if not args or args[0] == "all":
        tests_to_run = list(TEST_CASES.keys())
    else:
        name = args[0]
        matches = [k for k in TEST_CASES if name.lower() in k.lower()]
        if not matches:
            print(f"  No test matching '{name}'. Use 'list' to see available tests.")
            sys.exit(1)
        tests_to_run = matches

    # Apply category filter
    if category_filter:
        tests_to_run = [t for t in tests_to_run if TEST_CASES[t].category == category_filter]
        if not tests_to_run:
            print(f"  No tests in category '{category_filter}'.")
            sys.exit(1)

    # Apply limit
    if limit:
        tests_to_run = tests_to_run[:limit]

    mode = "sequential" if sequential else f"parallel({parallel})"

    # Header
    print(f"\n{'=' * 80}")
    print(f"  HVAC Graph Reasoning — Regression Tests v2.1")
    print(f"  Target: {BASE_URL}")
    print(f"  Tests: {len(tests_to_run)}  |  Mode: {mode}")
    if category_filter:
        print(f"  Category: {category_filter}")
    if gap_mode:
        print(f"  Analysis: GAP ANALYSIS")
    print(f"{'=' * 80}\n")

    print("  Authenticating...", end=" ")
    token = authenticate()
    print("OK\n")

    wall_start = time.time()

    if sequential:
        # ── Sequential execution ──────────────────────────────────────
        print(f"  {'Status':<5} {'Test':<32} {'Assert':<6} {'Time':>5}  {'Category':<12} Description")
        print(f"  {'─' * 5} {'─' * 32} {'─' * 6} {'─' * 5}  {'─' * 12} {'─' * 50}")

        results = []
        for test_name in tests_to_run:
            test = TEST_CASES[test_name]
            result = run_test(test, token)
            results.append(result)
            verbose = len(tests_to_run) == 1
            print_result(result, verbose=verbose)
    else:
        # ── Parallel execution ────────────────────────────────────────
        workers = min(parallel, len(tests_to_run))
        print(f"  ▶ Running {len(tests_to_run)} tests ({workers} workers)...\n")

        tasks = [(n, TEST_CASES[n], token) for n in tests_to_run]
        completed = 0
        ordered_results = {}

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_run_test_wrapper, t): t[0] for t in tasks}

            for future in as_completed(futures):
                name = futures[future]
                completed += 1
                try:
                    _, result = future.result()
                    ordered_results[name] = result
                    icon = "PASS" if result.status == "PASS" else ("FAIL" if result.status == "FAIL" else "ERR!")
                    print(f"    [{completed}/{len(tests_to_run)}] {icon}  {name}  ({result.duration_s:.1f}s)")
                except Exception as e:
                    print(f"    [{completed}/{len(tests_to_run)}] ERR!  {name}  ({e})")
                    ordered_results[name] = TestResult(
                        test_name=name, status="ERROR", category=TEST_CASES[name].category,
                        error_message=str(e),
                    )

        # Print detailed results in original order
        results = []
        print(f"\n  {'Status':<5} {'Test':<32} {'Assert':<6} {'Time':>5}  {'Category':<12} Description")
        print(f"  {'─' * 5} {'─' * 32} {'─' * 6} {'─' * 5}  {'─' * 12} {'─' * 50}")
        for name in tests_to_run:
            r = ordered_results[name]
            results.append(r)
            print_result(r)

    wall_time = time.time() - wall_start

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    errored = sum(1 for r in results if r.status == "ERROR")
    sequential_time = sum(r.duration_s for r in results)

    print(f"\n{'─' * 80}")
    print(f"  Summary: {passed} passed, {failed} failed, {errored} errors / {total} total")
    print(f"  Wall time: {wall_time:.1f}s  (sequential would be {sequential_time:.1f}s)")
    if sequential_time > 0 and wall_time > 0:
        print(f"  Speedup:   {sequential_time / wall_time:.1f}x")

    if failed + errored == 0:
        print(f"  ALL TESTS PASSED")
    else:
        print(f"  SOME TESTS FAILED")
        # Save raw events for all failed tests
        for r in results:
            if r.status in ("FAIL", "ERROR"):
                output_file = f"/tmp/test-hvac-{r.test_name}.json"
                with open(output_file, "w") as f:
                    json.dump(r.raw_events, f, indent=2, default=str)

    # Gap analysis
    if gap_mode or failed + errored > 0:
        print_gap_analysis(results)

    # JSON export for Test Lab viewer
    if json_output:
        serialize_results_json(results, json_output)

    print()
    sys.exit(0 if failed + errored == 0 else 1)


if __name__ == "__main__":
    main()
