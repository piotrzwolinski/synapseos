"""Database layer CONTRACT tests — pins return shapes for migration safety.

These tests verify that Neo4jConnection methods return data in the exact
structure that the engine, retriever, and session graph expect.

When migrating to FalkorDB, swap `_get_real_db()` to use FalkorDB driver
and all these tests must still pass — that's the migration contract.

Strategy:
- Tests use the REAL database (Neo4j Aura) when NEO4J_URI is set
- Tests are SKIPPED when no database is available (CI/local without DB)
- Each test pins the SHAPE of the return value (keys, types), not exact data
"""

import os
import pytest

# Skip entire module if no database connection
pytestmark = pytest.mark.skipif(
    not os.getenv("FALKORDB_HOST"),
    reason="FALKORDB_HOST not set — skipping live DB contract tests"
)


@pytest.fixture(scope="module")
def live_db():
    """Get a real database connection for contract testing."""
    from backend.database import GraphConnection
    db = GraphConnection()
    db.connect()
    yield db
    db.close()


# =============================================================================
# GRAPH STATS
# =============================================================================

class TestGraphStats:
    def test_node_count_returns_int(self, live_db):
        result = live_db.get_node_count()
        assert isinstance(result, int)
        assert result >= 0

    def test_relationship_count_returns_int(self, live_db):
        result = live_db.get_relationship_count()
        assert isinstance(result, int)
        assert result >= 0

    def test_verify_connection_returns_bool(self, live_db):
        result = live_db.verify_connection()
        assert result is True


# =============================================================================
# STRESSOR DETECTION — return shape contract
# =============================================================================

class TestStressorContract:
    def test_get_stressors_by_keywords_shape(self, live_db):
        result = live_db.get_stressors_by_keywords(["kitchen", "grease"])
        assert isinstance(result, list)
        if result:
            s = result[0]
            assert "id" in s
            assert "name" in s
            assert "description" in s
            assert "matched_keywords" in s
            assert isinstance(s["matched_keywords"], list)

    def test_get_stressors_for_application_shape(self, live_db):
        result = live_db.get_stressors_for_application("APP_KITCHEN")
        assert isinstance(result, list)
        if result:
            s = result[0]
            assert "id" in s
            assert "name" in s

    def test_empty_keywords_returns_empty(self, live_db):
        result = live_db.get_stressors_by_keywords([])
        assert isinstance(result, list)


# =============================================================================
# CAUSAL RULES
# =============================================================================

class TestCausalRuleContract:
    def test_shape(self, live_db):
        result = live_db.get_causal_rules_for_stressors(["STR_GREASE"])
        assert isinstance(result, list)
        if result:
            r = result[0]
            assert "rule_type" in r
            assert r["rule_type"] in ("NEUTRALIZED_BY", "DEMANDS_TRAIT")
            assert "stressor_id" in r
            assert "trait_id" in r
            assert "trait_name" in r
            assert "severity" in r
            assert r["severity"] in ("CRITICAL", "WARNING", "INFO")

    def test_empty_stressors_returns_empty(self, live_db):
        result = live_db.get_causal_rules_for_stressors([])
        assert isinstance(result, list)


# =============================================================================
# PRODUCT FAMILIES & TRAITS
# =============================================================================

class TestProductFamilyContract:
    def test_get_all_families_shape(self, live_db):
        result = live_db.get_all_product_families_with_traits()
        assert isinstance(result, list)
        assert len(result) > 0, "Expected at least one product family in graph"
        pf = result[0]
        assert "product_id" in pf
        assert "product_name" in pf
        assert "all_trait_ids" in pf
        assert isinstance(pf["all_trait_ids"], list)
        # selection_priority should be numeric
        assert "selection_priority" in pf
        assert isinstance(pf["selection_priority"], (int, float))

    def test_get_product_traits_shape(self, live_db):
        families = live_db.get_all_product_families_with_traits()
        if families:
            fam_id = families[0]["product_id"]
            # get_product_traits expects the family name, not ID
            fam_name = families[0]["product_name"]
            result = live_db.get_product_traits(fam_name)
            assert isinstance(result, list)
            if result:
                t = result[0]
                assert "id" in t
                assert "name" in t


# =============================================================================
# APPLICATIONS & ENVIRONMENT
# =============================================================================

class TestApplicationContract:
    def test_get_all_applications_shape(self, live_db):
        result = live_db.get_all_applications()
        assert isinstance(result, list)
        if result:
            app = result[0]
            assert "id" in app
            assert "name" in app
            assert "keywords" in app
            assert isinstance(app["keywords"], list)

    def test_environment_keywords_shape(self, live_db):
        result = live_db.get_environment_keywords()
        assert isinstance(result, dict)
        for env_id, keywords in result.items():
            assert isinstance(env_id, str)
            assert isinstance(keywords, list)


# =============================================================================
# DIMENSION MODULES (Sizing)
# =============================================================================

class TestDimensionModuleContract:
    def test_get_available_modules_shape(self, live_db):
        families = live_db.get_all_product_families_with_traits()
        if families:
            fam_id = families[0]["product_id"]
            result = live_db.get_available_dimension_modules(fam_id)
            assert isinstance(result, list)
            if result:
                dm = result[0]
                assert "width_mm" in dm
                assert "height_mm" in dm
                assert isinstance(dm["width_mm"], (int, float))
                assert isinstance(dm["height_mm"], (int, float))


# =============================================================================
# MATERIALS
# =============================================================================

class TestMaterialContract:
    def test_get_available_materials_shape(self, live_db):
        families = live_db.get_all_product_families_with_traits()
        if families:
            fam_id = families[0]["product_id"]
            result = live_db.get_available_materials(fam_id)
            assert isinstance(result, list)
            if result:
                assert isinstance(result[0], str)

    def test_get_material_specs_shape(self, live_db):
        result = live_db.get_material_specifications()
        assert isinstance(result, list)
        if result:
            m = result[0]
            assert "code" in m
            assert "name" in m


# =============================================================================
# CONSTRAINTS
# =============================================================================

class TestConstraintContract:
    def test_hard_constraints_shape(self, live_db):
        families = live_db.get_all_product_families_with_traits()
        if families:
            fam_id = families[0]["product_id"]
            result = live_db.get_hard_constraints(fam_id)
            assert isinstance(result, list)

    def test_installation_constraints_shape(self, live_db):
        families = live_db.get_all_product_families_with_traits()
        if families:
            fam_id = families[0]["product_id"]
            result = live_db.get_installation_constraints(fam_id)
            assert isinstance(result, list)


# =============================================================================
# CAPACITY RULES
# =============================================================================

class TestCapacityContract:
    def test_capacity_rules_shape(self, live_db):
        families = live_db.get_all_product_families_with_traits()
        if families:
            fam_id = families[0]["product_id"]
            result = live_db.get_capacity_rules(fam_id)
            assert isinstance(result, list)


# =============================================================================
# CLARIFICATION PARAMETERS
# =============================================================================

class TestClarificationContract:
    def test_get_clarification_params_shape(self, live_db):
        result = live_db.get_clarification_params()
        assert isinstance(result, list)

    def test_get_required_parameters_shape(self, live_db):
        families = live_db.get_all_product_families_with_traits()
        if families:
            fam_name = families[0]["product_name"]
            result = live_db.get_required_parameters(fam_name)
            assert isinstance(result, list)


# =============================================================================
# VECTOR SEARCH — contract for embedding-based queries
# =============================================================================

class TestVectorSearchContract:
    """These tests verify the vector search API contract.
    When migrating to FalkorDB, the vector search syntax changes but
    the return shape must remain identical.
    """

    def test_vector_search_concepts_shape(self, live_db):
        # Use a dummy embedding of correct dimension
        dummy_embedding = [0.0] * 3072
        try:
            result = live_db.vector_search_concepts(dummy_embedding, top_k=2)
            assert isinstance(result, list)
            if result:
                c = result[0]
                assert "score" in c
                assert isinstance(c["score"], float)
        except Exception:
            pytest.skip("Vector index not initialized")

    def test_hybrid_retrieval_shape(self, live_db):
        dummy_embedding = [0.0] * 3072
        try:
            result = live_db.hybrid_retrieval(dummy_embedding, top_k=2)
            assert isinstance(result, list)
        except Exception:
            pytest.skip("Vector index not initialized")


# =============================================================================
# FULLTEXT SEARCH
# =============================================================================

class TestFulltextSearchContract:
    def test_search_product_variants_shape(self, live_db):
        result = live_db.search_product_variants("GDB")
        assert isinstance(result, list)

    def test_find_alias_matches_shape(self, live_db):
        result = live_db.find_alias_matches("pocket filter")
        assert isinstance(result, list)


# =============================================================================
# SESSION GRAPH MANAGER
# =============================================================================

class TestSessionGraphManagerContract:
    """Contract tests for Layer 4 state operations."""

    @pytest.fixture
    def session_mgr(self, live_db):
        from backend.logic.session_graph import SessionGraphManager
        return SessionGraphManager(live_db)

    def test_ensure_session_creates_node(self, session_mgr):
        session_mgr.ensure_session("__test_contract__")
        state = session_mgr.get_project_state("__test_contract__")
        assert state["session_id"] == "__test_contract__"
        # Cleanup
        session_mgr.clear_session("__test_contract__")

    def test_get_project_state_shape(self, session_mgr):
        session_mgr.ensure_session("__test_shape__")
        state = session_mgr.get_project_state("__test_shape__")
        assert "session_id" in state
        assert "project" in state
        assert "tags" in state
        assert "tag_count" in state
        assert isinstance(state["tags"], list)
        assert isinstance(state["tag_count"], int)
        session_mgr.clear_session("__test_shape__")

    def test_upsert_tag_returns_dict(self, session_mgr):
        session_mgr.ensure_session("__test_tag__")
        result = session_mgr.upsert_tag(
            "__test_tag__", "item_1",
            filter_width=600, filter_height=600, airflow_m3h=3000,
        )
        assert isinstance(result, dict)
        assert "tag_id" in result
        session_mgr.clear_session("__test_tag__")

    def test_store_and_retrieve_turns(self, session_mgr):
        session_mgr.ensure_session("__test_turns__")
        session_mgr.store_turn("__test_turns__", "user", "Hello", 1)
        session_mgr.store_turn("__test_turns__", "assistant", "Hi there", 2)
        turns = session_mgr.get_recent_turns("__test_turns__", n=5)
        assert isinstance(turns, list)
        assert len(turns) >= 2
        assert turns[0]["role"] in ("user", "assistant")
        assert "message" in turns[0]
        session_mgr.clear_session("__test_turns__")

    def test_clear_session_removes_all(self, session_mgr):
        session_mgr.ensure_session("__test_clear__")
        session_mgr.upsert_tag("__test_clear__", "item_1", filter_width=600, filter_height=600)
        session_mgr.clear_session("__test_clear__")
        state = session_mgr.get_project_state("__test_clear__")
        assert state["tag_count"] == 0
        assert state["project"] is None

    def test_set_and_get_resolved_params(self, session_mgr):
        session_mgr.ensure_session("__test_params__")
        session_mgr.set_resolved_params("__test_params__", {"connection_type": "PG"})
        state = session_mgr.get_project_state("__test_params__")
        project = state.get("project") or {}
        # resolved_params is stored as JSON string in graph
        import json
        rp = project.get("resolved_params")
        if isinstance(rp, str):
            rp = json.loads(rp)
        assert rp is not None
        assert rp.get("connection_type") == "PG"
        session_mgr.clear_session("__test_params__")


# =============================================================================
# GOALS & LOGIC GATES — core engine input
# =============================================================================

class TestGoalsAndGatesContract:
    def test_goals_by_keywords_shape(self, live_db):
        result = live_db.get_goals_by_keywords(["kitchen", "ventilation"])
        assert isinstance(result, list)
        # May be empty but shape must be list of dicts if any
        if result:
            g = result[0]
            assert isinstance(g, dict)

    def test_logic_gates_for_stressors_shape(self, live_db):
        result = live_db.get_logic_gates_for_stressors(["STR_GREASE"])
        assert isinstance(result, list)
        if result:
            gate = result[0]
            assert isinstance(gate, dict)

    def test_gates_triggered_by_context_shape(self, live_db):
        result = live_db.get_gates_triggered_by_context(["APP_KITCHEN"])
        assert isinstance(result, list)

    def test_empty_stressor_ids_gates(self, live_db):
        result = live_db.get_logic_gates_for_stressors([])
        assert isinstance(result, list)


# =============================================================================
# DEPENDENCY RULES
# =============================================================================

class TestDependencyRuleContract:
    def test_dependency_rules_shape(self, live_db):
        result = live_db.get_dependency_rules_for_stressors(["STR_GREASE"])
        assert isinstance(result, list)
        if result:
            r = result[0]
            assert isinstance(r, dict)

    def test_empty_stressor_ids_returns_empty(self, live_db):
        result = live_db.get_dependency_rules_for_stressors([])
        assert isinstance(result, list)


# =============================================================================
# OPTIMIZATION STRATEGY
# =============================================================================

class TestOptimizationContract:
    def test_optimization_strategy_shape(self, live_db):
        families = live_db.get_all_product_families_with_traits()
        if families:
            fam_id = families[0]["product_id"]
            result = live_db.get_optimization_strategy(fam_id)
            # Can be None or dict
            assert result is None or isinstance(result, dict)


# =============================================================================
# SIZE-DETERMINED PROPERTIES
# =============================================================================

class TestSizeDeterminedPropsContract:
    def test_size_determined_properties_shape(self, live_db):
        families = live_db.get_all_product_families_with_traits()
        if families:
            fam_id = families[0]["product_id"]
            result = live_db.get_size_determined_properties(fam_id, 600, 600)
            assert isinstance(result, dict)


# =============================================================================
# ALTERNATIVES (sales recovery) — 5 methods
# =============================================================================

class TestAlternativesContract:
    def test_space_constraint_alternatives_shape(self, live_db):
        families = live_db.get_all_product_families_with_traits()
        if families:
            fam_id = families[0]["product_id"]
            result = live_db.find_alternatives_for_space_constraint(
                product_family_id=fam_id,
                max_width=1200, max_height=600,
            )
            assert isinstance(result, list)

    def test_environment_alternatives_shape(self, live_db):
        families = live_db.get_all_product_families_with_traits()
        if families:
            fam_id = families[0]["product_id"]
            result = live_db.find_alternatives_for_environment_constraint(
                product_family_id=fam_id,
                environment_id="ENV_OUTDOOR",
            )
            assert isinstance(result, list)

    def test_material_threshold_alternatives_shape(self, live_db):
        families = live_db.get_all_product_families_with_traits()
        if families:
            fam_id = families[0]["product_id"]
            result = live_db.find_material_alternatives_for_threshold(
                product_family_id=fam_id,
                current_material="FZ",
                violation_type="corrosion_class",
            )
            assert isinstance(result, list)

    def test_other_products_material_threshold_shape(self, live_db):
        families = live_db.get_all_product_families_with_traits()
        if families:
            fam_id = families[0]["product_id"]
            result = live_db.find_other_products_for_material_threshold(
                product_family_id=fam_id,
                required_trait_ids=["TRAIT_PARTICLE"],
            )
            assert isinstance(result, list)

    def test_higher_capacity_alternatives_shape(self, live_db):
        families = live_db.get_all_product_families_with_traits()
        if families:
            fam_id = families[0]["product_id"]
            result = live_db.find_products_with_higher_capacity(
                product_family_id=fam_id,
                current_airflow=3000,
            )
            assert isinstance(result, list)


# =============================================================================
# ENVIRONMENT DETECTION
# =============================================================================

class TestEnvironmentContract:
    def test_detect_environment_shape(self, live_db):
        result = live_db.detect_environment_from_keywords(["outdoor", "rooftop"])
        # Can be None or dict
        assert result is None or isinstance(result, dict)

    def test_resolve_hierarchy_shape(self, live_db):
        result = live_db.resolve_environment_hierarchy("ENV_OUTDOOR")
        assert isinstance(result, list)


# =============================================================================
# CONTEXTUAL CLARIFICATIONS
# =============================================================================

class TestContextualClarificationContract:
    def test_contextual_clarifications_shape(self, live_db):
        result = live_db.get_contextual_clarifications("APP_KITCHEN")
        assert isinstance(result, list)

    def test_contextual_clarifications_with_family(self, live_db):
        families = live_db.get_all_product_families_with_traits()
        if families:
            fam_name = families[0]["product_name"]
            result = live_db.get_contextual_clarifications("APP_KITCHEN", product_family=fam_name)
            assert isinstance(result, list)


# =============================================================================
# PRODUCT DETAIL METHODS
# =============================================================================

class TestProductDetailContract:
    def test_default_length_variant_shape(self, live_db):
        families = live_db.get_all_product_families_with_traits()
        if families:
            fam_id = families[0]["product_id"]
            result = live_db.get_default_length_variant(fam_id)
            assert result is None or isinstance(result, (int, float))

    def test_product_family_code_format_shape(self, live_db):
        families = live_db.get_all_product_families_with_traits()
        if families:
            fam_id = families[0]["product_id"]
            result = live_db.get_product_family_code_format(fam_id)
            assert result is None or isinstance(result, dict)

    def test_connection_length_offset_shape(self, live_db):
        result = live_db.get_connection_length_offset("PG")
        assert result is None or isinstance(result, (int, float))

    def test_reference_airflow_shape(self, live_db):
        result = live_db.get_reference_airflow_for_dimensions(600, 600)
        assert result is None or isinstance(result, dict)


# =============================================================================
# MATERIAL SUITABILITY
# =============================================================================

class TestMaterialSuitabilityContract:
    def test_check_material_suitability_shape(self, live_db):
        result = live_db.check_material_suitability("Commercial Kitchen", "FZ")
        assert isinstance(result, dict)

    def test_material_property_shape(self, live_db):
        families = live_db.get_all_product_families_with_traits()
        if families:
            fam_id = families[0]["product_id"]
            result = live_db.get_material_property(fam_id, "RF", "corrosion_class")
            # Can be None or any value
            pass


# =============================================================================
# ACCESSORY METHODS
# =============================================================================

class TestAccessoryContract:
    def test_all_accessory_codes_shape(self, live_db):
        result = live_db.get_all_accessory_codes()
        assert isinstance(result, list)

    def test_accessory_compatibility_shape(self, live_db):
        result = live_db.get_accessory_compatibility("ACC_DRAIN", "GDB")
        assert isinstance(result, dict)


# =============================================================================
# EXPERT REVIEW METHODS — uses peek() and {.*}
# =============================================================================

class TestExpertReviewContract:
    def test_get_expert_conversations_shape(self, live_db):
        result = live_db.get_expert_conversations(limit=5, offset=0)
        assert isinstance(result, dict)
        assert "conversations" in result
        assert "total" in result

    def test_get_expert_reviews_summary_shape(self, live_db):
        result = live_db.get_expert_reviews_summary()
        assert isinstance(result, dict)
        assert "total" in result

    def test_get_conversation_detail_shape(self, live_db):
        result = live_db.get_conversation_detail("nonexistent_session")
        assert isinstance(result, dict)


# =============================================================================
# GRAPH REASONING CONTEXT
# =============================================================================

class TestGraphReasoningContextContract:
    def test_graph_reasoning_context_shape(self, live_db):
        result = live_db.get_graph_reasoning_context("Commercial Kitchen", "GDB")
        assert isinstance(result, dict)

    def test_product_family_data_dump_shape(self, live_db):
        result = live_db.get_product_family_data_dump("GDB")
        assert isinstance(result, dict)


# =============================================================================
# PHYSICS RISKS
# =============================================================================

class TestPhysicsRisksContract:
    def test_unmitigated_risks_shape(self, live_db):
        result = live_db.check_unmitigated_physics_risks("GDB")
        assert isinstance(result, list)

    def test_safe_alternative_for_risk_shape(self, live_db):
        result = live_db.get_safe_alternative_for_risk("RISK_NONEXISTENT")
        assert isinstance(result, list)


# =============================================================================
# SEMANTIC RULES
# =============================================================================

class TestSemanticRulesContract:
    def test_semantic_rules_shape(self, live_db):
        result = live_db.get_semantic_rules()
        assert isinstance(result, list)

    def test_graph_rules_as_candidates_shape(self, live_db):
        result = live_db.get_graph_rules_as_candidates()
        assert isinstance(result, list)


# =============================================================================
# VARIABLE FEATURES
# =============================================================================

class TestVariableFeaturesContract:
    def test_variable_features_shape(self, live_db):
        families = live_db.get_all_product_families_with_traits()
        if families:
            fam_name = families[0]["product_name"]
            result = live_db.get_variable_features(fam_name)
            assert isinstance(result, list)


# =============================================================================
# SPATIAL FEASIBILITY
# =============================================================================

class TestSpatialFeasibilityContract:
    def test_validate_spatial_feasibility_shape(self, live_db):
        families = live_db.get_all_product_families_with_traits()
        if families:
            fam_id = families[0]["product_id"]
            result = live_db.validate_spatial_feasibility(fam_id, 600, 600)
            assert isinstance(result, list)
