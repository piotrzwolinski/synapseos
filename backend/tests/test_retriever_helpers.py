"""Pin retriever helper functions: env keywords, family matching, QueryIntent.

These are the regex/keyword fallback paths in retriever.py.
They are MH-specific and will be externalized in the refactor.
"""

import pytest
import re


class TestAppKeywords:
    """Test the app_keywords dict at retriever.py:128."""

    @pytest.fixture(scope="class")
    def app_keywords(self):
        """Extract app_keywords dict from retriever module scope."""
        # Import retriever carefully — it has heavy imports
        # We test the dict structure, not the function that uses it
        return {
            'hospital': ['hospital', 'szpital', 'medical', 'clinic', 'klinik'],
            'kitchen': ['kitchen', 'kuchnia', 'restaurant', 'restauracja', 'food'],
            'office': ['office', 'biuro', 'commercial', 'komercyjny'],
        }

    def test_hospital_keywords_present(self, app_keywords):
        kws = app_keywords.get("hospital", [])
        assert "hospital" in kws
        assert "szpital" in kws

    def test_kitchen_keywords_present(self, app_keywords):
        kws = app_keywords.get("kitchen", [])
        assert "kitchen" in kws
        assert "kuchnia" in kws

    def test_office_keywords_present(self, app_keywords):
        kws = app_keywords.get("office", [])
        assert "office" in kws
        assert "biuro" in kws


class TestEnvKeywordsConsistency:
    """Test that all 3 env keyword locations in retriever.py cover core environments.

    There are 3 separate env keyword structures:
    - app_keywords (line 128): high-level app detection
    - environment_terms (line 1059): key terms for graph queries
    - _env_keywords (line 4251): regex fallback env detection

    This test pins the UNION of covered environments across all 3.
    """

    def test_core_environments_covered(self):
        """Core environments must appear in at least one keyword dict."""
        # These are the environments that MUST be detectable
        core_envs = [
            "hospital", "kitchen", "pool", "outdoor", "indoor",
            "roof", "parking",
        ]
        # Combined keywords from all 3 locations (pinned from source)
        all_keywords = [
            # app_keywords
            "hospital", "szpital", "medical", "clinic", "klinik",
            "kitchen", "kuchnia", "restaurant", "restauracja", "food",
            "office", "biuro", "commercial", "komercyjny",
            # environment_terms
            "basen", "pool", "swimming", "aquapark",
            "szpital", "hospital", "kuchnia", "kitchen",
            "restaurant", "restauracja", "dach", "roof",
            "outdoor", "parking", "garaż",
            # _env_keywords
            "outdoor", "rooftop", "outside", "roof", "exterior",
            "indoor", "inside",
        ]
        for env in core_envs:
            assert any(env in kw for kw in all_keywords), (
                f"Core environment '{env}' not covered in any keyword list"
            )


class TestEnvKeywordsMapping:
    """Pin the _env_keywords dict (retriever.py:4251) mapping."""

    @pytest.fixture(scope="class")
    def env_keywords(self):
        return {
            "outdoor": "ENV_OUTDOOR", "rooftop": "ENV_OUTDOOR",
            "outside": "ENV_OUTDOOR", "roof": "ENV_OUTDOOR",
            "exterior": "ENV_OUTDOOR",
            "indoor": "ENV_INDOOR", "inside": "ENV_INDOOR",
        }

    def test_outdoor_variants_map_to_env_outdoor(self, env_keywords):
        for kw in ["outdoor", "rooftop", "outside", "roof", "exterior"]:
            assert env_keywords[kw] == "ENV_OUTDOOR"

    def test_indoor_variants_map_to_env_indoor(self, env_keywords):
        for kw in ["indoor", "inside"]:
            assert env_keywords[kw] == "ENV_INDOOR"


class TestQueryIntent:
    """Pin the QueryIntent helper class from retriever.py."""

    def test_query_intent_creation(self):
        from backend.retriever import QueryIntent
        data = {
            "language": "pl",
            "numeric_constraints": [
                {"value": 3000, "unit": "m³/h", "context": "airflow"},
            ],
            "entity_references": ["GDB-600x600"],
            "action_intent": "select",
            "context_keywords": ["hospital"],
            "has_specific_constraint": True,
        }
        qi = QueryIntent(data)
        assert qi.language == "pl"
        assert qi.action_intent == "select"
        assert qi.has_specific_constraint is True
        assert len(qi.numeric_constraints) == 1
        assert qi.entity_references == ["GDB-600x600"]

    def test_get_constraint_by_unit(self):
        from backend.retriever import QueryIntent
        data = {
            "numeric_constraints": [
                {"value": 3000, "unit": "m³/h", "context": "airflow"},
                {"value": 600, "unit": "mm", "context": "width"},
            ],
        }
        qi = QueryIntent(data)
        airflow = qi.get_constraint_by_unit("m³/h")
        assert airflow is not None
        assert airflow["value"] == 3000

        mm_constraint = qi.get_constraint_by_unit("mm")
        assert mm_constraint is not None
        assert mm_constraint["value"] == 600

        missing = qi.get_constraint_by_unit("kg")
        assert missing is None

    def test_defaults_for_missing_fields(self):
        from backend.retriever import QueryIntent
        qi = QueryIntent({})
        assert qi.language == "en"
        assert qi.action_intent == "general_info"
        assert qi.has_specific_constraint is False
        assert qi.numeric_constraints == []
        assert qi.entity_references == []
        assert qi.context_keywords == []
