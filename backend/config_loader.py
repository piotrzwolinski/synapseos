"""Configuration Loader for Domain-Agnostic Reasoning Engine.

This module provides a type-safe, validated configuration system.
All domain-specific logic is externalized to YAML configuration files.
"""

import re
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, field

import yaml
from pydantic import BaseModel, Field


# =============================================================================
# PYDANTIC MODELS FOR CONFIGURATION VALIDATION
# =============================================================================

class EntityPattern(BaseModel):
    """A regex pattern for extracting domain entities."""
    pattern: str
    description: str = ""
    flags: str = ""
    examples: list[str] = Field(default_factory=list)

    def compile(self) -> re.Pattern:
        """Compile the regex pattern with appropriate flags."""
        flags = 0
        if "IGNORECASE" in self.flags.upper():
            flags |= re.IGNORECASE
        if "MULTILINE" in self.flags.upper():
            flags |= re.MULTILINE
        return re.compile(self.pattern, flags)


class EntityPatternGroup(BaseModel):
    """A group of entity patterns (e.g., product codes)."""
    values: list[str] = Field(default_factory=list)
    description: str = ""


class NormalizationConfig(BaseModel):
    """Configuration for normalizing extracted entities."""
    replace_space_with: str = "-"
    uppercase: bool = True


class DisplayField(BaseModel):
    """Configuration for displaying a single field."""
    key: str
    label: str = ""
    format: str = "{value}"
    required: bool = False
    is_array: bool = False
    array_join: str = ", "
    display_only_if_true: bool = False
    fallback_keys: list[str] = Field(default_factory=list)
    default: str = ""
    hidden_if_combined: bool = False
    combine_with: str = ""
    combined_format: str = ""
    append_to_combined: bool = False
    append_format: str = ""


class OptionsDisplayConfig(BaseModel):
    """Configuration for displaying option codes."""
    header: str = "  **Options:**"
    json_key: str = "options_json"
    fallback_key: str = "available_options"
    format: str = '    • Code "{code}": {description}'
    category_format: str = " [{category}]"


class PrimaryEntityDisplay(BaseModel):
    """Configuration for primary entity display (products)."""
    header_template: str = "### {icon} {title}"
    icon: str = "📦"
    title: str = "CONFIGURATION DATA"
    fields: list[DisplayField] = Field(default_factory=list)
    options_display: OptionsDisplayConfig = Field(default_factory=OptionsDisplayConfig)


class SecondaryEntityDisplay(BaseModel):
    """Configuration for secondary entity display."""
    header: str
    fields: list[DisplayField] = Field(default_factory=list)
    item_prefix: str = "  • "
    show_options: bool = False


class PolicyTrigger(BaseModel):
    """Triggers that activate a reasoning policy."""
    keywords: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)


class PolicyValidation(BaseModel):
    """Validation rules for a policy."""
    check_attribute: str
    required_values: list[str] = Field(default_factory=list)
    warning_values: list[str] = Field(default_factory=list)
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    compare_to_query: bool = False
    match_extracted_value: bool = False
    fail_message: str = ""
    recommendation: str = ""


class ReasoningPolicy(BaseModel):
    """A Guardian reasoning policy."""
    id: str
    name: str
    description: str = ""
    triggers: PolicyTrigger
    validation: PolicyValidation
    priority: str = "medium"  # critical, high, medium, low


class SearchTriggers(BaseModel):
    """Keywords that trigger different types of searches."""
    option_keywords: list[str] = Field(default_factory=list)
    material_keywords: list[str] = Field(default_factory=list)
    technical_keywords: list[str] = Field(default_factory=list)


class Prompts(BaseModel):
    """LLM prompt templates."""
    system: str = ""
    synthesis: str = ""
    no_context: str = ""


class OutputSchemaProperty(BaseModel):
    """A property in the output schema."""
    type: str
    description: str = ""
    enum: list[str] = Field(default_factory=list)
    items: Optional[dict] = None


class OutputSchema(BaseModel):
    """Schema for structured LLM output."""
    type: str = "object"
    properties: dict[str, Any] = Field(default_factory=dict)


class ProjectSearch(BaseModel):
    """Configuration for project name extraction."""
    patterns: list[str] = Field(default_factory=list)
    known_identifiers: list[str] = Field(default_factory=list)
    stopwords: list[str] = Field(default_factory=list)


# =============================================================================
# GUARDIAN RULES MODELS
# =============================================================================

class MaterialSpec(BaseModel):
    """Material specification with corrosion class."""
    code: str
    full_name: str
    corrosion_class: str
    description: str = ""
    suitable_for: list[str] = Field(default_factory=list)


class DemandingEnvironment(BaseModel):
    """Environment that requires specific material grades."""
    name: str
    aliases: list[str] = Field(default_factory=list)
    min_corrosion_class: str
    required_materials: list[str] = Field(default_factory=list)
    concern: str = ""


class ProductWarning(BaseModel):
    """Warning for specific product applications."""
    trigger: list[str] = Field(default_factory=list)
    message: str
    alternative: str = ""


class ProductCapability(BaseModel):
    """Product family capabilities and limitations."""
    family: str
    full_name: str
    filters: list[str] = Field(default_factory=list)
    does_NOT_filter: list[str] = Field(default_factory=list)
    type: str = ""
    special_feature: str = ""
    recommended_for: list[str] = Field(default_factory=list)
    warning_applications: list[ProductWarning] = Field(default_factory=list)


class InstallationWarning(BaseModel):
    """Warning for installation conditions."""
    trigger: list[str] = Field(default_factory=list)
    condition: str = ""
    products_affected: list[str] = Field(default_factory=list)
    message: str
    alternative: str = ""


class GeometricOption(BaseModel):
    """Option that requires minimum dimensions."""
    option: str
    aliases: list[str] = Field(default_factory=list)
    min_length_mm: int = 0
    additional_length_mm: int = 0
    message: str = ""


class AccessoryCompat(BaseModel):
    """Accessory compatibility rules."""
    accessory: str
    full_name: str
    compatible_with: list[str] = Field(default_factory=list)
    NOT_compatible_with: list[str] = Field(default_factory=list)
    reason: str = ""


class HazardDomain(BaseModel):
    """Safety hazard domain configuration."""
    keywords: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    severity: str = "warning"
    action: str = ""


class ClarificationParam(BaseModel):
    """Parameter that requires clarification."""
    name: str
    aliases: list[str] = Field(default_factory=list)
    units: list[str] = Field(default_factory=list)
    applies_to: list[str] = Field(default_factory=list)
    prompt: str = ""


# =============================================================================
# MAIN CONFIGURATION CONTAINER
# =============================================================================

@dataclass
class DomainConfig:
    """Complete domain configuration container."""

    # Domain metadata
    domain_id: str = ""
    domain_name: str = ""
    company: str = ""
    description: str = ""
    version: str = "1.0"

    # Entity patterns
    product_code_patterns: list[EntityPattern] = field(default_factory=list)
    product_families: list[str] = field(default_factory=list)
    material_codes: list[str] = field(default_factory=list)
    option_codes: list[str] = field(default_factory=list)
    normalization: NormalizationConfig = field(default_factory=NormalizationConfig)

    # Display configuration
    primary_entity_display: PrimaryEntityDisplay = field(default_factory=PrimaryEntityDisplay)
    secondary_entities: dict[str, SecondaryEntityDisplay] = field(default_factory=dict)

    # Reasoning policies
    policies: list[ReasoningPolicy] = field(default_factory=list)

    # Search triggers
    search_triggers: SearchTriggers = field(default_factory=SearchTriggers)

    # Prompts
    prompts: Prompts = field(default_factory=Prompts)

    # Output schema
    output_schema: OutputSchema = field(default_factory=OutputSchema)

    # Project search
    project_search: ProjectSearch = field(default_factory=ProjectSearch)

    # Guardian rules (loaded from YAML)
    material_hierarchy: list[MaterialSpec] = field(default_factory=list)
    demanding_environments: list[DemandingEnvironment] = field(default_factory=list)
    product_capabilities: list[ProductCapability] = field(default_factory=list)
    installation_warnings: list[InstallationWarning] = field(default_factory=list)
    geometric_options: list[GeometricOption] = field(default_factory=list)
    installation_tolerance_mm: int = 10
    accessory_compatibility: list[AccessoryCompat] = field(default_factory=list)
    hazard_domains: dict[str, HazardDomain] = field(default_factory=dict)
    clarification_params: list[ClarificationParam] = field(default_factory=list)
    prompt_templates: dict[str, str] = field(default_factory=dict)
    sample_questions: dict[str, dict] = field(default_factory=dict)

    def get_all_search_keywords(self) -> list[str]:
        """Get all keywords that should trigger configuration searches."""
        keywords = []
        keywords.extend(self.search_triggers.option_keywords)
        keywords.extend(self.search_triggers.material_keywords)
        keywords.extend(self.search_triggers.technical_keywords)
        keywords.extend(self.material_codes)
        keywords.extend(self.option_codes)
        return list(set(keywords))

    def get_active_policies_for_query(self, query: str) -> list[ReasoningPolicy]:
        """Get policies that are triggered by the query."""
        query_lower = query.lower()
        active = []

        for policy in self.policies:
            triggered = False

            # Check keyword triggers
            for keyword in policy.triggers.keywords:
                if keyword.lower() in query_lower:
                    triggered = True
                    break

            # Check pattern triggers
            if not triggered:
                for pattern in policy.triggers.patterns:
                    if re.search(pattern, query, re.IGNORECASE):
                        triggered = True
                        break

            if triggered:
                active.append(policy)

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        active.sort(key=lambda p: priority_order.get(p.priority, 99))

        return active

    def format_policies_for_prompt(self, policies: list[ReasoningPolicy]) -> str:
        """Format active policies for injection into LLM prompt."""
        if not policies:
            return "No special policies are active for this query."

        lines = ["The following policies are ACTIVE for this query:\n"]
        for policy in policies:
            lines.append(f"**[{policy.id}] {policy.name}** (Priority: {policy.priority})")
            lines.append(f"  - Description: {policy.description}")
            lines.append(f"  - Check: Verify '{policy.validation.check_attribute}' attribute")
            if policy.validation.required_values:
                lines.append(f"  - Required values: {', '.join(policy.validation.required_values)}")
            if policy.validation.min_value is not None:
                lines.append(f"  - Minimum value: {policy.validation.min_value}")
            lines.append(f"  - If validation fails: {policy.validation.fail_message}")
            lines.append(f"  - Recommendation: {policy.validation.recommendation}")
            lines.append("")

        return "\n".join(lines)

    def get_material_rules_prompt(self) -> str:
        """Generate material-environment rules section for prompts."""
        if not self.material_hierarchy:
            return ""

        lines = ["**Material corrosion class hierarchy:**"]
        for mat in self.material_hierarchy:
            lines.append(f"- {mat.code} ({mat.full_name}) = {mat.corrosion_class}: {mat.description}")

        lines.append("\n**Demanding environments requiring upgraded materials:**")
        for env in self.demanding_environments:
            materials = ", ".join(env.required_materials)
            aliases = ", ".join(env.aliases[:3]) if env.aliases else ""
            lines.append(f"- {env.name} (aliases: {aliases}): requires {env.min_corrosion_class} ({materials}) - {env.concern}")

        return "\n".join(lines)

    def get_product_rules_prompt(self) -> str:
        """Generate product-application rules section for prompts."""
        if not self.product_capabilities:
            return ""

        lines = ["**Product capabilities and limitations:**"]
        for prod in self.product_capabilities:
            filters_str = ", ".join(prod.filters) if prod.filters else "N/A"
            not_filters_str = ", ".join(prod.does_NOT_filter) if prod.does_NOT_filter else "N/A"
            lines.append(f"- {prod.family} ({prod.full_name}): Filters [{filters_str}], Does NOT filter [{not_filters_str}]")

            for warning in prod.warning_applications:
                triggers = ", ".join(warning.trigger[:3])
                lines.append(f"  ⚠️ Triggers: [{triggers}] → {warning.message}")

        if self.installation_warnings:
            lines.append("\n**Installation environment warnings:**")
            for warn in self.installation_warnings:
                triggers = ", ".join(warn.trigger)
                products = ", ".join(warn.products_affected)
                lines.append(f"- [{triggers}] + [{warn.condition}] for [{products}]: {warn.message}")

        return "\n".join(lines)

    def get_geometric_rules_prompt(self) -> str:
        """Generate geometric constraint rules for prompts."""
        if not self.geometric_options:
            return ""

        lines = ["**Geometric constraints:**"]
        for opt in self.geometric_options:
            if opt.min_length_mm:
                lines.append(f"- Option '{opt.option}': requires minimum {opt.min_length_mm}mm length")
            if opt.additional_length_mm:
                lines.append(f"- Option '{opt.option}': adds {opt.additional_length_mm}mm to total length")

        lines.append(f"\n**Installation tolerance:** Minimum {self.installation_tolerance_mm}mm margin recommended. Zero-tolerance fits are risky.")

        return "\n".join(lines)

    def get_accessory_rules_prompt(self) -> str:
        """Generate accessory compatibility rules for prompts."""
        if not self.accessory_compatibility:
            return ""

        lines = ["**Accessory compatibility:**"]
        for acc in self.accessory_compatibility:
            compat = ", ".join(acc.compatible_with)
            incompat = ", ".join(acc.NOT_compatible_with)
            lines.append(f"- {acc.accessory} ({acc.full_name}): Compatible with [{compat}]")
            if acc.NOT_compatible_with:
                lines.append(f"  ⚠️ NOT compatible with [{incompat}]: {acc.reason}")

        return "\n".join(lines)

    def get_all_guardian_rules_prompt(self) -> str:
        """Get all Guardian rules combined for prompt injection."""
        sections = []

        material_rules = self.get_material_rules_prompt()
        if material_rules:
            sections.append("## MATERIAL-ENVIRONMENT RULES\n" + material_rules)

        product_rules = self.get_product_rules_prompt()
        if product_rules:
            sections.append("## PRODUCT-APPLICATION RULES\n" + product_rules)

        geometric_rules = self.get_geometric_rules_prompt()
        if geometric_rules:
            sections.append("## GEOMETRIC CONSTRAINTS\n" + geometric_rules)

        accessory_rules = self.get_accessory_rules_prompt()
        if accessory_rules:
            sections.append("## ACCESSORY COMPATIBILITY\n" + accessory_rules)

        return "\n\n".join(sections)

    def check_material_environment_mismatch(self, query: str) -> Optional[dict]:
        """Check if query has a material-environment mismatch."""
        query_lower = query.lower()

        # Find requested material
        requested_material = None
        for mat in self.material_hierarchy:
            if mat.code.lower() in query_lower or mat.full_name.lower() in query_lower:
                requested_material = mat
                break

        if not requested_material:
            return None

        # Find mentioned environment
        detected_environment = None
        for env in self.demanding_environments:
            all_names = [env.name.lower()] + [a.lower() for a in env.aliases]
            for name in all_names:
                if name in query_lower:
                    detected_environment = env
                    break
            if detected_environment:
                break

        if not detected_environment:
            return None

        # Check if material is suitable
        if requested_material.code not in detected_environment.required_materials:
            return {
                "material": requested_material.code,
                "material_class": requested_material.corrosion_class,
                "environment": detected_environment.name,
                "required_class": detected_environment.min_corrosion_class,
                "recommended": ", ".join(detected_environment.required_materials),
                "concern": detected_environment.concern
            }

        return None

    def check_product_application_mismatch(self, query: str) -> Optional[dict]:
        """Check if query has a product-application mismatch."""
        query_lower = query.lower()

        for prod in self.product_capabilities:
            if prod.family.lower() not in query_lower:
                continue

            for warning in prod.warning_applications:
                for trigger in warning.trigger:
                    if trigger.lower() in query_lower:
                        return {
                            "product": prod.family,
                            "trigger": trigger,
                            "message": warning.message,
                            "alternative": warning.alternative
                        }

        # Check installation warnings
        for warn in self.installation_warnings:
            trigger_found = any(t.lower() in query_lower for t in warn.trigger)
            condition_met = warn.condition.lower() in query_lower or "no insulation" in query_lower or "bez izolacji" in query_lower

            if trigger_found and condition_met:
                for prod in warn.products_affected:
                    if prod.lower() in query_lower:
                        return {
                            "product": prod,
                            "trigger": ", ".join(warn.trigger),
                            "message": warn.message,
                            "alternative": warn.alternative
                        }

        return None

    def check_accessory_compatibility(self, query: str) -> Optional[dict]:
        """Check if query has an accessory compatibility issue."""
        query_lower = query.lower()

        for acc in self.accessory_compatibility:
            if acc.accessory.lower() not in query_lower:
                continue

            for incompat in acc.NOT_compatible_with:
                if incompat.lower() in query_lower:
                    return {
                        "accessory": acc.accessory,
                        "product": incompat,
                        "reason": acc.reason
                    }

        return None


# =============================================================================
# CONFIGURATION LOADER
# =============================================================================

import os

# Available domain configurations
DOMAIN_CONFIGS = {
    "mann_hummel": "domain_config.yaml",
    "wacker": "domain_config_wacker.yaml",
}

# Default domain from environment variable or fallback
DEFAULT_DOMAIN = os.environ.get("DOMAIN_ID", "mann_hummel")


def get_available_domains() -> list[dict]:
    """Get list of available domain configurations."""
    domains = []
    config_dir = Path(__file__).parent

    for domain_id, filename in DOMAIN_CONFIGS.items():
        config_path = config_dir / filename
        if config_path.exists():
            # Quick load to get domain metadata
            with open(config_path, 'r', encoding='utf-8') as f:
                raw = yaml.safe_load(f)
            domain_meta = raw.get("domain", {})
            domains.append({
                "id": domain_id,
                "name": domain_meta.get("name", domain_id),
                "company": domain_meta.get("company", "Unknown"),
                "description": domain_meta.get("description", ""),
                "version": domain_meta.get("version", "1.0"),
                "config_file": filename
            })

    return domains


def load_domain_config(config_path: Optional[str] = None, domain_id: Optional[str] = None) -> DomainConfig:
    """Load and validate domain configuration from YAML file.

    Args:
        config_path: Path to config file. If None, uses domain_id to find config.
        domain_id: Domain identifier. If None, uses DEFAULT_DOMAIN.

    Returns:
        Validated DomainConfig object
    """
    if config_path is None:
        if domain_id is None:
            domain_id = DEFAULT_DOMAIN

        filename = DOMAIN_CONFIGS.get(domain_id, "domain_config.yaml")
        config_path = Path(__file__).parent / filename

    with open(config_path, 'r', encoding='utf-8') as f:
        raw = yaml.safe_load(f)

    config = DomainConfig()

    # Load domain metadata
    domain = raw.get("domain", {})
    config.domain_id = domain.get("id", "")
    config.domain_name = domain.get("name", "")
    config.company = domain.get("company", "")
    config.description = domain.get("description", "")
    config.version = domain.get("version", "1.0")

    # Load entity patterns
    entity_patterns = raw.get("entity_patterns", {})

    # Product code patterns
    for p in entity_patterns.get("product_codes", []):
        config.product_code_patterns.append(EntityPattern(**p))

    # Product families
    families = entity_patterns.get("product_families", {})
    config.product_families = families.get("values", [])

    # Material codes
    materials = entity_patterns.get("material_codes", {})
    config.material_codes = materials.get("values", [])

    # Option codes
    options = entity_patterns.get("option_codes", {})
    config.option_codes = options.get("values", [])

    # Normalization
    norm = entity_patterns.get("normalization", {})
    config.normalization = NormalizationConfig(**norm)

    # Load display schema
    display = raw.get("display_schema", {})

    # Primary entity display
    primary = display.get("primary_entity", {})
    if primary:
        fields = [DisplayField(**f) for f in primary.get("fields", [])]
        options_display = OptionsDisplayConfig(**primary.get("options_display", {}))
        config.primary_entity_display = PrimaryEntityDisplay(
            header_template=primary.get("header_template", "### {icon} {title}"),
            icon=primary.get("icon", "📦"),
            title=primary.get("title", "DATA"),
            fields=fields,
            options_display=options_display
        )

    # Secondary entities
    for name, entity_config in display.get("secondary_entities", {}).items():
        fields = [DisplayField(**f) for f in entity_config.get("fields", [])]
        config.secondary_entities[name] = SecondaryEntityDisplay(
            header=entity_config.get("header", f"### {name.upper()}"),
            fields=fields,
            item_prefix=entity_config.get("item_prefix", "  • "),
            show_options=entity_config.get("show_options", False)
        )

    # Load reasoning policies
    for policy_data in raw.get("reasoning_policies", []):
        trigger_data = policy_data.get("triggers", {})
        validation_data = policy_data.get("validation", {})

        policy = ReasoningPolicy(
            id=policy_data.get("id", ""),
            name=policy_data.get("name", ""),
            description=policy_data.get("description", ""),
            triggers=PolicyTrigger(**trigger_data),
            validation=PolicyValidation(**validation_data),
            priority=policy_data.get("priority", "medium")
        )
        config.policies.append(policy)

    # Load search triggers
    triggers = raw.get("search_triggers", {})
    config.search_triggers = SearchTriggers(
        option_keywords=triggers.get("option_keywords", []),
        material_keywords=triggers.get("material_keywords", []),
        technical_keywords=triggers.get("technical_keywords", [])
    )

    # Load prompts
    prompts = raw.get("prompts", {})
    config.prompts = Prompts(
        system=prompts.get("system", ""),
        synthesis=prompts.get("synthesis", ""),
        no_context=prompts.get("no_context", "")
    )

    # Load output schema
    schema = raw.get("output_schema", {})
    if schema:
        config.output_schema = OutputSchema(
            type=schema.get("type", "object"),
            properties=schema.get("properties", {})
        )

    # Load project search config
    proj = raw.get("project_search", {})
    config.project_search = ProjectSearch(
        patterns=proj.get("patterns", []),
        known_identifiers=proj.get("known_identifiers", []),
        stopwords=proj.get("stopwords", [])
    )

    # Load Guardian rules
    mat_env_rules = raw.get("material_environment_rules", {})

    # Material hierarchy
    for mat in mat_env_rules.get("material_hierarchy", []):
        config.material_hierarchy.append(MaterialSpec(**mat))

    # Demanding environments
    for env in mat_env_rules.get("demanding_environments", []):
        config.demanding_environments.append(DemandingEnvironment(**env))

    # Product application rules
    prod_rules = raw.get("product_application_rules", {})

    # Product capabilities
    for prod in prod_rules.get("product_capabilities", []):
        warnings = []
        for w in prod.get("warning_applications", []):
            warnings.append(ProductWarning(**w))
        cap = ProductCapability(
            family=prod.get("family", ""),
            full_name=prod.get("full_name", ""),
            filters=prod.get("filters", []),
            does_NOT_filter=prod.get("does_NOT_filter", []),
            type=prod.get("type", ""),
            special_feature=prod.get("special_feature", ""),
            recommended_for=prod.get("recommended_for", []),
            warning_applications=warnings
        )
        config.product_capabilities.append(cap)

    # Installation warnings
    for warn in prod_rules.get("installation_warnings", []):
        config.installation_warnings.append(InstallationWarning(**warn))

    # Geometric constraints
    geo = raw.get("geometric_constraints", {})
    for opt in geo.get("options_requiring_length", []):
        config.geometric_options.append(GeometricOption(**opt))

    tolerance = geo.get("installation_tolerance", {})
    config.installation_tolerance_mm = tolerance.get("minimum_margin_mm", 10)

    # Accessory compatibility
    for acc in raw.get("accessory_compatibility", []):
        config.accessory_compatibility.append(AccessoryCompat(**acc))

    # Safety detection
    safety = raw.get("safety_detection", {})
    for domain_name, domain_data in safety.get("hazard_domains", {}).items():
        config.hazard_domains[domain_name] = HazardDomain(**domain_data)

    # Clarification rules
    clarif = raw.get("clarification_rules", {})
    for param in clarif.get("required_parameters", []):
        config.clarification_params.append(ClarificationParam(**param))

    # Prompt templates
    config.prompt_templates = raw.get("prompt_templates", {})

    # Sample questions
    config.sample_questions = raw.get("sample_questions", {})

    return config


# =============================================================================
# GLOBAL CONFIG SINGLETON
# =============================================================================

# Multi-tenant config storage
_configs: dict[str, DomainConfig] = {}
_current_domain: str = DEFAULT_DOMAIN


def get_config(domain_id: Optional[str] = None) -> DomainConfig:
    """Get the loaded domain configuration.

    Args:
        domain_id: Optional domain to load. If None, uses current domain.

    Returns:
        DomainConfig for the specified or current domain.
    """
    global _configs, _current_domain

    if domain_id is None:
        domain_id = _current_domain

    if domain_id not in _configs:
        _configs[domain_id] = load_domain_config(domain_id=domain_id)

    return _configs[domain_id]


def get_current_domain() -> str:
    """Get the current active domain ID."""
    return _current_domain


def set_current_domain(domain_id: str) -> DomainConfig:
    """Switch to a different domain configuration.

    Args:
        domain_id: The domain to switch to.

    Returns:
        The newly active DomainConfig.

    Raises:
        ValueError: If domain_id is not in DOMAIN_CONFIGS.
    """
    global _current_domain

    if domain_id not in DOMAIN_CONFIGS:
        available = list(DOMAIN_CONFIGS.keys())
        raise ValueError(f"Unknown domain '{domain_id}'. Available: {available}")

    _current_domain = domain_id
    return get_config(domain_id)


def reload_config(config_path: Optional[str] = None, domain_id: Optional[str] = None) -> DomainConfig:
    """Force reload of configuration.

    Args:
        config_path: Optional specific path to load from.
        domain_id: Optional domain to reload. If None, reloads current domain.
    """
    global _configs, _current_domain

    if domain_id is None:
        domain_id = _current_domain

    _configs[domain_id] = load_domain_config(config_path, domain_id)
    return _configs[domain_id]


def get_domain_config_summary() -> dict:
    """Get a summary of the current domain configuration for the Settings UI."""
    config = get_config()
    return {
        "domain": {
            "id": config.domain_id,
            "name": config.domain_name,
            "company": config.company,
            "description": config.description,
            "version": config.version,
        },
        "guardian_rules": {
            "material_count": len(config.material_hierarchy),
            "environment_count": len(config.demanding_environments),
            "product_rules_count": len(config.product_capabilities),
            "accessory_rules_count": len(config.accessory_compatibility),
        },
        "materials": [
            {"code": m.code, "name": m.full_name, "class": m.corrosion_class}
            for m in config.material_hierarchy
        ],
        "demanding_environments": [
            {"name": e.name, "required_materials": e.required_materials, "concern": e.concern}
            for e in config.demanding_environments
        ],
        "product_capabilities": [
            {"family": p.family, "name": p.full_name, "filters": p.filters, "warnings_count": len(p.warning_applications)}
            for p in config.product_capabilities
        ],
        "sample_questions": config.sample_questions,
        "clarification_params": [
            {"name": p.name, "units": p.units, "prompt": p.prompt}
            for p in config.clarification_params
        ],
        "prompts": {
            "system": config.prompts.system,
            "synthesis": config.prompts.synthesis,
            "no_context": config.prompts.no_context,
        },
        "prompt_templates": config.prompt_templates,
    }


# =============================================================================
# UI CONFIGURATION MODELS (for Graph Visualization)
# =============================================================================

class NodeStyle(BaseModel):
    """Style configuration for a node type."""
    color: str = "#94a3b8"
    size: int = 8
    icon: str = "circle"
    display_name: str = ""


class RelationshipStyle(BaseModel):
    """Style configuration for a relationship type."""
    color: str = "#64748b"
    width: float = 1.5
    dashed: bool = False


class GraphLayoutConfig(BaseModel):
    """Force-directed layout configuration."""
    charge_strength: float = -100
    link_distance: float = 50
    center_strength: float = 0.05


class GraphVisualizationConfig(BaseModel):
    """Complete graph visualization configuration."""
    default: NodeStyle = Field(default_factory=NodeStyle)
    node_styles: dict[str, NodeStyle] = Field(default_factory=dict)
    relationship_styles: dict[str, RelationshipStyle] = Field(default_factory=dict)
    layout: GraphLayoutConfig = Field(default_factory=GraphLayoutConfig)


class EntityCardConfig(BaseModel):
    """Configuration for entity detail cards."""
    title_field: str = "name"
    fallback_title_fields: list[str] = Field(default_factory=lambda: ["id", "title"])
    priority_fields: list[str] = Field(default_factory=list)


class UIConfig(BaseModel):
    """Complete UI configuration container."""
    graph_visualization: GraphVisualizationConfig = Field(default_factory=GraphVisualizationConfig)
    entity_card: EntityCardConfig = Field(default_factory=EntityCardConfig)


# =============================================================================
# UI CONFIGURATION LOADER
# =============================================================================

def load_ui_config(config_path: Optional[str] = None) -> UIConfig:
    """Load and validate UI configuration from YAML file.

    Args:
        config_path: Path to config file. Defaults to ui_config.yaml.

    Returns:
        Validated UIConfig object
    """
    if config_path is None:
        config_path = Path(__file__).parent / "ui_config.yaml"

    if not Path(config_path).exists():
        # Return default config if file doesn't exist
        return UIConfig()

    with open(config_path, 'r', encoding='utf-8') as f:
        raw = yaml.safe_load(f)

    if not raw:
        return UIConfig()

    # Parse graph visualization config
    graph_viz = raw.get("graph_visualization", {})
    default_style = NodeStyle(**graph_viz.get("default", {}))

    node_styles = {}
    for name, style_data in graph_viz.get("node_styles", {}).items():
        node_styles[name] = NodeStyle(**style_data)

    rel_styles = {}
    for name, style_data in graph_viz.get("relationship_styles", {}).items():
        rel_styles[name] = RelationshipStyle(**style_data)

    layout = GraphLayoutConfig(**graph_viz.get("layout", {}))

    graph_config = GraphVisualizationConfig(
        default=default_style,
        node_styles=node_styles,
        relationship_styles=rel_styles,
        layout=layout
    )

    # Parse entity card config
    entity_card_data = raw.get("entity_card", {})
    entity_card = EntityCardConfig(
        title_field=entity_card_data.get("title_field", "name"),
        fallback_title_fields=entity_card_data.get("fallback_title_fields", ["id", "title"]),
        priority_fields=entity_card_data.get("priority_fields", [])
    )

    return UIConfig(
        graph_visualization=graph_config,
        entity_card=entity_card
    )


# =============================================================================
# UI CONFIG SINGLETON
# =============================================================================

_ui_config: Optional[UIConfig] = None


def get_ui_config() -> UIConfig:
    """Get the loaded UI configuration (singleton)."""
    global _ui_config
    if _ui_config is None:
        _ui_config = load_ui_config()
    return _ui_config


def reload_ui_config(config_path: Optional[str] = None) -> UIConfig:
    """Force reload of UI configuration."""
    global _ui_config
    _ui_config = load_ui_config(config_path)
    return _ui_config
