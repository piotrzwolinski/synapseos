"""Pin DomainConfig loading and helper behavior."""

import pytest
from backend.config_loader import get_config, get_available_domains, DomainConfig


class TestConfigLoading:
    def test_load_config_returns_domain_config(self, config):
        assert isinstance(config, DomainConfig)

    def test_config_has_product_families(self, config):
        assert config.product_families == [
            "GDC-FLEX", "GDC", "GDP", "GDR", "GDF", "GDMI", "GDB", "PFF", "BFF"
        ]

    def test_config_has_material_codes(self, config):
        assert config.material_codes == ["FZ", "ZM", "RF", "SS", "ALU", "AZ"]

    def test_config_has_material_hierarchy(self, config):
        assert len(config.material_hierarchy) >= 4
        codes = {m.code for m in config.material_hierarchy}
        assert "RF" in codes
        assert "FZ" in codes

    def test_config_has_assembly_shared_properties(self, config):
        assert "filter_width" in config.assembly_shared_properties
        assert "filter_height" in config.assembly_shared_properties
        assert "airflow_m3h" in config.assembly_shared_properties

    def test_config_domain_metadata(self, config):
        assert config.company == "Mann+Hummel"
        assert config.domain_id == "hvac_filtration"

    def test_config_has_demanding_environments(self, config):
        env_names = {e.name.lower() for e in config.demanding_environments}
        assert any("hospital" in n or "medical" in n for n in env_names)
        assert any("pool" in n or "swim" in n for n in env_names)

    def test_config_has_product_capabilities(self, config):
        families = {p.family for p in config.product_capabilities}
        assert "GDB" in families or "GDC" in families


class TestTenantDiscovery:
    def test_tenant_directory_discovered(self):
        domains = get_available_domains()
        domain_ids = [d["id"] for d in domains]
        assert "mann_hummel" in domain_ids

    def test_tenant_has_metadata(self):
        domains = get_available_domains()
        mh = next(d for d in domains if d["id"] == "mann_hummel")
        assert mh["company"] == "Mann+Hummel"


class TestDimensionMaterialTables:
    """Phase 2: Verify dimension/material tables loaded from tenant config."""

    def test_dimension_mapping_loaded(self, config):
        assert len(config.dimension_mapping) >= 10
        assert config.dimension_mapping[287] == 300
        assert config.dimension_mapping[592] == 600
        assert config.dimension_mapping[900] == 900

    def test_corrosion_class_map_loaded(self, config):
        assert config.corrosion_class_map["FZ"] == "C3"
        assert config.corrosion_class_map["RF"] == "C5"
        assert config.corrosion_class_map["SF"] == "C5.1"

    def test_housing_length_derivation_loaded(self, config):
        rules = config.housing_length_derivation
        assert "GDB" in rules
        assert "GDMI" in rules
        assert "GDC" in rules
        # GDB has 3 breakpoints
        assert len(rules["GDB"]) == 3
        assert rules["GDB"][0]["max_depth"] == 292
        assert rules["GDB"][0]["length"] == 550

    def test_orientation_threshold_loaded(self, config):
        assert config.orientation_threshold == 600

    def test_material_codes_extended_loaded(self, config):
        assert len(config.material_codes_extended) >= 4
        codes = {m.code for m in config.material_codes_extended}
        assert "RF" in codes
        assert "FZ" in codes
        # Check aliases
        rf = next(m for m in config.material_codes_extended if m.code == "RF")
        assert "STAINLESS" in rf.aliases

    def test_default_material_loaded(self, config):
        assert config.default_material == "FZ"


class TestFallbackKeywords:
    """Phase 4: Verify fallback keywords loaded from tenant config."""

    def test_application_keywords_loaded(self, config):
        assert len(config.fallback_application_keywords) >= 5
        assert "hospital" in config.fallback_application_keywords
        assert "hospital" in config.fallback_application_keywords["hospital"]

    def test_environment_terms_loaded(self, config):
        assert len(config.fallback_environment_terms) >= 10
        assert "pool" in config.fallback_environment_terms
        assert "hospital" in config.fallback_environment_terms

    def test_environment_mapping_loaded(self, config):
        mapping = config.fallback_environment_mapping
        assert mapping["outdoor"] == "ENV_OUTDOOR"
        assert mapping["hospital"] == "ENV_HOSPITAL"
        assert mapping["pool"] == "ENV_POOL"
        assert mapping["atex"] == "ENV_ATEX"
        assert mapping["marine"] == "ENV_MARINE"

    def test_env_to_app_inference_loaded(self, config):
        assert config.fallback_env_to_app_inference["ENV_HOSPITAL"] == "APP_HOSPITAL"
        assert config.fallback_env_to_app_inference["ENV_POOL"] == "APP_POOL"

    def test_chat_app_keywords_loaded(self, config):
        kw = config.fallback_chat_app_keywords
        assert kw["hospital"] == "Hospital"
        assert kw["kitchen"] == "Commercial Kitchen"
        assert kw["pool"] == "Swimming Pool"

    def test_default_product_family_loaded(self, config):
        assert config.default_product_family == "GDB"


class TestScribeHints:
    """Phase 5a: Verify scribe hints loaded from tenant config."""

    def test_product_inference_loaded(self, config):
        assert len(config.scribe_product_inference) >= 4
        families = {h["product_family"] for h in config.scribe_product_inference}
        assert "GDMI" in families
        assert "GDC" in families
        assert "GDP" in families
        assert "GDB" in families

    def test_connection_types_loaded(self, config):
        assert "PG" in config.scribe_connection_types
        assert "F" in config.scribe_connection_types
        assert "flange" in config.scribe_connection_types["F"]

    def test_material_hints_loaded(self, config):
        assert "RF" in config.scribe_material_hints
        assert "stainless" in config.scribe_material_hints["RF"]

    def test_accessory_hints_loaded(self, config):
        assert len(config.scribe_accessory_hints) >= 3
        codes = {h["code"] for h in config.scribe_accessory_hints}
        assert "EXL" in codes


class TestJudgePrompts:
    """Phase 5b: Verify judge prompts loaded from tenant files."""

    def test_judge_system_prompt_loaded(self):
        from backend.judge_prompts import JUDGE_SYSTEM_PROMPT
        assert len(JUDGE_SYSTEM_PROMPT) > 1000
        assert "HVAC" in JUDGE_SYSTEM_PROMPT or "engineer" in JUDGE_SYSTEM_PROMPT

    def test_judge_user_prompt_has_placeholders(self):
        from backend.judge_prompts import JUDGE_USER_PROMPT_TEMPLATE
        assert "{conversation}" in JUDGE_USER_PROMPT_TEMPLATE
        assert "{product_card}" in JUDGE_USER_PROMPT_TEMPLATE

    def test_question_generation_prompt_has_placeholder(self):
        from backend.judge_prompts import QUESTION_GENERATION_PROMPT
        assert "{target_count}" in QUESTION_GENERATION_PROMPT


class TestGuardianRules:
    def test_check_material_environment_mismatch_hospital_fz(self, config):
        result = config.check_material_environment_mismatch("hospital with FZ material")
        assert result is not None
        assert result["material"] == "FZ"

    def test_check_material_environment_no_mismatch_rf_hospital(self, config):
        result = config.check_material_environment_mismatch("hospital with RF material")
        # RF should be acceptable for hospital (C5 class)
        assert result is None

    def test_get_material_rules_prompt_nonempty(self, config):
        prompt = config.get_material_rules_prompt()
        assert len(prompt) > 100
        assert "corrosion" in prompt.lower()

    def test_get_all_guardian_rules_prompt_has_sections(self, config):
        prompt = config.get_all_guardian_rules_prompt()
        assert "MATERIAL" in prompt
        assert "PRODUCT" in prompt
