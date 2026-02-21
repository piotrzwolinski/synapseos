"""Shared fixtures for SynapseOS regression test suite.

Loads REAL tenant config (tenants/mann_hummel/config.yaml) — pins actual config values.
Provides mock DB fixtures for migration-safe testing.
"""

import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure backend is importable
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.logic.state import TechnicalState, TagSpecification, MaterialCode
from backend.config_loader import get_config, load_domain_config


# =============================================================================
# CONFIG FIXTURES
# =============================================================================

@pytest.fixture
def config():
    """Load real DomainConfig from tenant config (not mocked)."""
    return get_config("mann_hummel")


# =============================================================================
# TECHNICAL STATE FIXTURES
# =============================================================================

@pytest.fixture
def empty_state():
    """Fresh TechnicalState with no data."""
    return TechnicalState()


@pytest.fixture
def state_with_tag():
    """TechnicalState with one complete tag (item_1: 600x600, 3000 m³/h, GDC)."""
    state = TechnicalState()
    state.merge_tag("item_1", filter_width=600, filter_height=600, airflow_m3h=3000)
    state.detected_family = "GDC"
    return state


@pytest.fixture
def state_with_material():
    """TechnicalState with RF material locked."""
    state = TechnicalState()
    state.lock_material("RF")
    state.merge_tag("item_1", filter_width=600, filter_height=600, airflow_m3h=3000)
    state.detected_family = "GDB"
    return state


@pytest.fixture
def state_with_assembly():
    """TechnicalState with a two-stage assembly (PROTECTOR + TARGET)."""
    state = TechnicalState()
    state.merge_tag("item_1", filter_width=600, filter_height=600, airflow_m3h=3000)
    state.detected_family = "GDC"

    # Simulate assembly creation manually (avoiding engine dependency)
    state.assembly_group = {
        "group_id": "assembly_item_1",
        "rationale": "Kitchen environment requires grease pre-filter",
        "stages": [
            {"role": "PROTECTOR", "product_family": "GDP", "tag_id": "item_1_stage_1",
             "provides_trait": "Grease Pre-Filtration", "reason": "Neutralizes grease stressor"},
            {"role": "TARGET", "product_family": "GDC", "tag_id": "item_1_stage_2",
             "provides_trait": "Carbon Adsorption", "reason": "Primary odor removal"},
        ],
    }
    # Create stage tags
    del state.tags["item_1"]
    state.merge_tag("item_1_stage_1", filter_width=600, filter_height=600,
                     airflow_m3h=3000, product_family="GDP")
    state.tags["item_1_stage_1"].assembly_role = "PROTECTOR"
    state.tags["item_1_stage_1"].assembly_group_id = "assembly_item_1"

    state.merge_tag("item_1_stage_2", filter_width=600, filter_height=600,
                     airflow_m3h=3000, product_family="GDC")
    state.tags["item_1_stage_2"].assembly_role = "TARGET"
    state.tags["item_1_stage_2"].assembly_group_id = "assembly_item_1"

    return state


@pytest.fixture
def state_fully_populated():
    """Fully populated state with project, material, resolved params, and complete tag."""
    state = TechnicalState()
    state.project_name = "TestProject"
    state.lock_material("RF")
    state.detected_family = "GDB"
    state.resolved_params = {"connection_type": "PG", "door_side": "R"}
    state.merge_tag("item_1", filter_width=610, filter_height=305,
                     filter_depth=292, airflow_m3h=3000, product_family="GDB")
    state.tags["item_1"].product_code = "GDB-300x600-550-R-PG-RF"
    state.tags["item_1"].weight_kg = 45.0
    return state


# =============================================================================
# MOCK DB FIXTURES — for migration-safe testing
# =============================================================================

def _make_mock_db():
    """Create a comprehensive mock of GraphConnection with realistic return shapes.

    This mock defines the CONTRACT that the DB backend (FalkorDB) must satisfy.
    Each method returns data in the exact shape the engine/retriever/session_graph expects.
    """
    db = MagicMock()

    # --- Graph stats ---
    db.get_node_count.return_value = 150
    db.get_relationship_count.return_value = 300
    db.verify_connection.return_value = True

    # --- Stressor detection ---
    db.get_stressors_by_keywords.return_value = [
        {
            "id": "STR_GREASE", "name": "Grease Aerosol",
            "description": "Airborne grease particles from cooking",
            "category": "Contamination",
            "matched_keywords": ["kitchen", "grease"],
            "match_count": 2,
        },
    ]
    db.get_stressors_for_application.return_value = [
        {
            "id": "STR_GREASE", "name": "Grease Aerosol",
            "description": "Airborne grease particles", "category": "Contamination",
        },
    ]

    # --- Causal rules ---
    db.get_causal_rules_for_stressors.return_value = [
        {
            "rule_type": "NEUTRALIZED_BY", "stressor_id": "STR_GREASE",
            "stressor_name": "Grease Aerosol", "trait_id": "TRAIT_GREASE_PRE",
            "trait_name": "Grease Pre-Filtration", "severity": "CRITICAL",
            "explanation": "Grease clogs carbon filters; pre-filtration required",
        },
    ]

    # --- Product families with traits ---
    db.get_all_product_families_with_traits.return_value = [
        {
            "product_id": "FAM_GDB", "product_name": "GDB",
            "product_type": "particle_filter", "selection_priority": 10,
            "direct_trait_ids": ["TRAIT_PARTICLE"], "material_trait_ids": [],
            "all_trait_ids": ["TRAIT_PARTICLE"],
        },
        {
            "product_id": "FAM_GDC", "product_name": "GDC",
            "product_type": "carbon_filter", "selection_priority": 20,
            "direct_trait_ids": ["TRAIT_CARBON"], "material_trait_ids": [],
            "all_trait_ids": ["TRAIT_CARBON"],
        },
        {
            "product_id": "FAM_GDP", "product_name": "GDP",
            "product_type": "pre_filter", "selection_priority": 30,
            "direct_trait_ids": ["TRAIT_GREASE_PRE"], "material_trait_ids": [],
            "all_trait_ids": ["TRAIT_GREASE_PRE"],
        },
    ]
    db.get_product_traits.return_value = [
        {"id": "TRAIT_PARTICLE", "name": "Particle Filtration", "source": "direct", "is_primary": True},
    ]

    # --- Goals ---
    db.get_goals_by_keywords.return_value = []

    # --- Logic gates ---
    db.get_logic_gates_for_stressors.return_value = []
    db.get_gates_triggered_by_context.return_value = []

    # --- Constraints ---
    db.get_hard_constraints.return_value = []
    db.get_installation_constraints.return_value = []

    # --- Capacity / Sizing ---
    db.get_capacity_rules.return_value = [
        {
            "item_id": "FAM_GDB", "input_property": "airflow_m3h",
            "output_property": "rated_airflow_m3h", "rule_type": "lookup",
        },
    ]
    db.get_available_dimension_modules.return_value = [
        {
            "variant_id": "GDB-600x600", "width_mm": 600, "height_mm": 600,
            "rated_airflow": 3400, "name": "GDB 600x600",
        },
        {
            "variant_id": "GDB-300x600", "width_mm": 300, "height_mm": 600,
            "rated_airflow": 1700, "name": "GDB 300x600",
        },
    ]
    db.validate_spatial_feasibility.return_value = [
        {"product_family_id": "FAM_GDB", "feasible": True},
    ]

    # --- Materials ---
    db.get_available_materials.return_value = ["FZ", "RF", "ZM"]
    db.get_material_specifications.return_value = [
        {"code": "FZ", "name": "Galvanised Steel", "corrosion_class": "C2"},
        {"code": "RF", "name": "Stainless Steel", "corrosion_class": "C5"},
    ]
    db.get_material_property.return_value = None

    # --- Applications ---
    db.get_all_applications.return_value = [
        {"id": "APP_KITCHEN", "name": "Commercial Kitchen",
         "keywords": ["kitchen", "restaurant", "cooking"]},
        {"id": "APP_INDUSTRIAL", "name": "Industrial Process",
         "keywords": ["factory", "industrial", "manufacturing"]},
    ]
    db.match_application_by_keywords.return_value = None

    # --- Environment ---
    db.get_environment_keywords.return_value = {
        "ENV_INDOOR": ["indoor", "inside"],
        "ENV_OUTDOOR": ["outdoor", "outside", "rooftop"],
    }
    db.detect_environment_from_keywords.return_value = None
    db.resolve_environment_hierarchy.return_value = []

    # --- Alternatives ---
    db.find_alternatives_for_space_constraint.return_value = []
    db.find_alternatives_for_environment_constraint.return_value = []
    db.find_material_alternatives_for_threshold.return_value = []
    db.find_other_products_for_material_threshold.return_value = []
    db.find_products_with_higher_capacity.return_value = []

    # --- Clarifications ---
    db.get_clarification_params.return_value = []
    db.get_required_parameters.return_value = []
    db.get_contextual_clarifications.return_value = []

    # --- Optimization ---
    db.get_optimization_strategy.return_value = None

    # --- Accessories ---
    db.get_accessory_compatibility.return_value = {"is_compatible": True, "status": "ALLOWED"}
    db.get_all_accessory_codes.return_value = []

    # --- Product detail ---
    db.get_product_family_code_format.return_value = {
        "pattern": "{Family}-{Width}x{Height}-{Length}-{Door}-{Connection}-{Material}",
    }
    db.get_default_length_variant.return_value = 550
    db.get_variant_weight.return_value = 45.0
    db.get_dimension_module_weight.return_value = 45.0
    db.get_connection_length_offset.return_value = 0
    db.get_reference_airflow_for_dimensions.return_value = {"rated_airflow": 3400}

    # --- Vector search ---
    db.vector_search_concepts.return_value = [
        {"concept": "Kitchen ventilation", "description": "Cooking exhaust systems", "score": 0.92},
    ]
    db.hybrid_retrieval.return_value = []
    db.check_safety_risks.return_value = []
    db.get_similar_cases.return_value = []

    # --- Fulltext search ---
    db.search_product_variants.return_value = []
    db.find_alias_matches.return_value = []

    # --- Semantic rules ---
    db.get_semantic_rules.return_value = []

    # --- Dependency rules ---
    db.get_dependency_rules_for_stressors.return_value = []

    # --- Size-determined properties ---
    db.get_size_determined_properties.return_value = {}

    # --- Session graph manager ---
    db.get_session_graph_manager.return_value = MagicMock()

    return db


@pytest.fixture
def mock_db():
    """Mock GraphConnection with realistic return shapes.

    This is the DB contract fixture. The real FalkorDB-backed DB
    must produce data matching these shapes.
    """
    return _make_mock_db()


@pytest.fixture
def mock_session_manager():
    """Mock SessionGraphManager for Layer 4 tests."""
    mgr = MagicMock()
    mgr.ensure_session.return_value = None
    mgr.clear_session.return_value = None
    mgr.set_project.return_value = None
    mgr.lock_material.return_value = None
    mgr.set_detected_family.return_value = None
    mgr.set_pending_clarification.return_value = None
    mgr.set_accessories.return_value = None
    mgr.set_assembly_group.return_value = None
    mgr.set_resolved_params.return_value = None
    mgr.set_vetoed_families.return_value = None
    mgr.store_turn.return_value = None
    mgr.get_recent_turns.return_value = []
    mgr.get_tag_count.return_value = 0
    mgr.get_project_state.return_value = {
        "session_id": "test_session",
        "project": None,
        "tags": [],
        "tag_count": 0,
    }
    mgr.get_project_state_for_prompt.return_value = ""
    mgr.upsert_tag.return_value = {
        "tag_id": "item_1", "filter_width": 600, "filter_height": 600,
        "housing_width": 600, "housing_height": 600, "airflow_m3h": 3000,
        "is_complete": True,
    }
    return mgr


# =============================================================================
# ENGINE VERDICT FIXTURE
# =============================================================================

@pytest.fixture
def sample_verdict():
    """A realistic EngineVerdict for adapter/pipeline tests."""
    from backend.logic.universal_engine import (
        EngineVerdict, DetectedStressor, CausalRule, TraitMatch,
        AssemblyStage, GateEvaluation,
    )
    verdict = EngineVerdict()
    verdict.detected_stressors = [
        DetectedStressor(
            id="STR_GREASE", name="Grease Aerosol",
            description="Airborne grease from cooking",
            detection_method="keyword", confidence=0.95,
            matched_keywords=["kitchen"],
        ),
    ]
    verdict.active_causal_rules = [
        CausalRule(
            rule_type="NEUTRALIZED_BY", stressor_id="STR_GREASE",
            stressor_name="Grease Aerosol", trait_id="TRAIT_GREASE_PRE",
            trait_name="Grease Pre-Filtration", severity="CRITICAL",
            explanation="Grease clogs carbon filters",
        ),
    ]
    verdict.ranked_products = [
        TraitMatch(
            product_family_id="FAM_GDB", product_family_name="GDB",
            traits_present=["TRAIT_PARTICLE"], traits_missing=[],
            coverage_score=1.0, selection_priority=10,
        ),
    ]
    verdict.recommended_product = verdict.ranked_products[0]
    return verdict
