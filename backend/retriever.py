"""Domain-Agnostic GraphRAG Reasoning Engine.

This module implements a generic Hybrid Retrieval system with a Guardian
reasoning layer. All domain-specific logic is loaded from configuration.

The code contains NO hardcoded domain terms - it works with any domain
by loading the appropriate configuration file.
"""

import os
import re
import json
from typing import Optional

from google import genai
from google.genai import types
from dotenv import load_dotenv

from database import db
from embeddings import generate_embedding
from config_loader import get_config, reload_config, DomainConfig, ReasoningPolicy
from models import (
    ConsultResponse, StructuredResponse, GraphEvidence, PolicyCheckResult,
    ExplainableResponse, ReferenceDetail, ReasoningStep
)

load_dotenv(dotenv_path="../.env")

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
LLM_MODEL = "gemini-2.0-flash"
LLM_MODEL_FAST = "gemini-2.0-flash"  # Fast model for intent detection


# =============================================================================
# LLM-BASED INTENT DETECTION (Domain-Agnostic)
# =============================================================================

INTENT_DETECTION_PROMPT = """Analyze this user query and extract structured intent.
DO NOT use domain-specific assumptions. Extract what is explicitly stated.

Query: "{query}"

**IMPORTANT**: If the query contains "Context Update:", this is a follow-up to a clarification request.
The pattern is: "<Original Query>. Context Update: <Attribute> is <Value>."
In this case:
- Extract constraints from BOTH the original query AND the context update
- Set has_specific_constraint: true (the user HAS now provided the missing parameter)

Return JSON with these fields:
{{
  "language": "pl" or "en" or "de" or "sv" (detected language of query),
  "numeric_constraints": [
    {{"value": <number>, "unit": "<unit like m³/h, mm, kg, °C>", "context": "<what it refers to>"}}
  ],
  "entity_references": ["<any specific product codes, model names, or identifiers mentioned>"],
  "action_intent": "select" | "compare" | "configure" | "troubleshoot" | "general_info",
  "context_keywords": ["<environment/application keywords like: marine, outdoor, kitchen, etc>"],
  "has_specific_constraint": true if user provides specific numeric or attribute values OR if "Context Update:" is present
}}

Be precise with numbers. Extract exactly what the user stated.
Only output valid JSON, no explanation."""


class QueryIntent:
    """Structured intent extracted from user query - domain-agnostic."""
    def __init__(self, data: dict):
        self.language = data.get("language", "en")
        self.numeric_constraints = data.get("numeric_constraints", [])
        self.entity_references = data.get("entity_references", [])
        self.action_intent = data.get("action_intent", "general_info")
        self.context_keywords = data.get("context_keywords", [])
        self.has_specific_constraint = data.get("has_specific_constraint", False)

    def get_constraint_by_unit(self, unit_pattern: str) -> Optional[dict]:
        """Get numeric constraint matching a unit pattern."""
        for constraint in self.numeric_constraints:
            if unit_pattern.lower() in constraint.get("unit", "").lower():
                return constraint
        return None

    def __repr__(self):
        constraints = len(self.numeric_constraints)
        entities = len(self.entity_references)
        return f"QueryIntent(lang={self.language}, constraints={constraints}, entities={entities}, intent={self.action_intent})"


def detect_intent(query: str) -> QueryIntent:
    """Use LLM to extract structured intent from query.

    This is a fast, domain-agnostic call that extracts:
    - Language
    - Numeric requirements (any units)
    - Entity references (product codes, model names)
    - Action intent
    - Context keywords
    """
    try:
        response = client.models.generate_content(
            model=LLM_MODEL_FAST,
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=INTENT_DETECTION_PROMPT.format(query=query))]
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        data = json.loads(response.text)
        return QueryIntent(data)
    except Exception as e:
        # Fallback to basic detection if LLM fails
        return QueryIntent({
            "language": _detect_language_fallback(query),
            "numeric_constraints": _extract_numeric_constraints_fallback(query),
            "entity_references": [],
            "action_intent": "general_info",
            "has_specific_constraint": False
        })


def _detect_language_fallback(query: str) -> str:
    """Simple regex-based language detection as fallback."""
    polish_patterns = [r'\b(czy|jak|jaki|mamy|jest|dla|przy)\b']
    german_patterns = [r'\b(ist|sind|für|mit|bei|wie)\b']
    swedish_patterns = [r'\b(är|för|med|och|hur)\b']

    for pattern in polish_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return 'pl'
    for pattern in german_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return 'de'
    for pattern in swedish_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return 'sv'
    return 'en'


def _extract_numeric_constraints_fallback(query: str) -> list[dict]:
    """Extract numeric values with units from query as fallback."""
    constraints = []
    # Generic pattern for number + unit
    pattern = r'(\d+(?:[.,]\d+)?)\s*([a-zA-Z³²/°]+(?:/[a-zA-Z]+)?)'
    matches = re.findall(pattern, query)

    for value_str, unit in matches:
        try:
            value = float(value_str.replace(',', '.'))
            constraints.append({
                "value": value,
                "unit": unit,
                "context": "extracted"
            })
        except ValueError:
            pass

    return constraints


# =============================================================================
# GENERIC PRODUCT FILTERING
# =============================================================================

def filter_entities_by_attribute(
    entities: list[dict],
    attribute_name: str,
    required_value: float,
    comparison: str = "gte",
    tolerance: float = 0.0
) -> tuple[list[dict], list[dict]]:
    """Filter entities by any numeric attribute requirement.

    This is domain-agnostic - works with any numeric attribute.

    Args:
        entities: List of entity dictionaries
        attribute_name: Name of the attribute to filter by
        required_value: The required numeric value
        comparison: "gte" (>=), "lte" (<=), "eq" (==), "gt" (>), "lt" (<)
        tolerance: Allow values within X% of requirement (default 0 = exact)

    Returns:
        Tuple of (suitable_entities, rejected_entities)
    """
    suitable = []
    rejected = []
    tolerance_factor = 1 - tolerance if comparison in ["gte", "gt"] else 1 + tolerance

    for entity in entities:
        value = entity.get(attribute_name)

        # No data for this attribute - keep but mark as unverified
        if value is None:
            suitable.append(entity)
            continue

        # Try to convert to numeric
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            suitable.append(entity)
            continue

        # Apply comparison
        meets_requirement = False
        if comparison == "gte":
            meets_requirement = numeric_value >= required_value * tolerance_factor
        elif comparison == "lte":
            meets_requirement = numeric_value <= required_value * tolerance_factor
        elif comparison == "gt":
            meets_requirement = numeric_value > required_value * tolerance_factor
        elif comparison == "lt":
            meets_requirement = numeric_value < required_value * tolerance_factor
        elif comparison == "eq":
            meets_requirement = abs(numeric_value - required_value) <= required_value * tolerance

        if meets_requirement:
            suitable.append(entity)
        else:
            rejected.append(entity)

    # Sort suitable by closest match to requirement
    suitable.sort(key=lambda e: abs((float(e.get(attribute_name) or 0)) - required_value))

    return suitable, rejected


def analyze_entity_variance(entities: list[dict]) -> dict:
    """Analyze variance in entity attributes to detect ambiguity.

    This is the core of the Ambiguity Gatekeeper - it detects when
    graph data contains a range of variants that require user clarification.

    Args:
        entities: List of entity dictionaries from graph

    Returns:
        Dict with variance analysis:
        - varying_attributes: Attributes with multiple distinct values
        - suggested_differentiator: The attribute that varies most
        - unique_values: Dict of attribute -> list of unique values
    """
    if not entities or len(entities) <= 1:
        return {
            "has_variance": False,
            "varying_attributes": [],
            "suggested_differentiator": None,
            "unique_values": {}
        }

    # Collect all attribute values across entities
    attribute_values: dict[str, set] = {}

    for entity in entities:
        for key, value in entity.items():
            if key in ['id', 'name', 'embedding']:  # Skip identity/internal fields
                continue
            if value is None:
                continue

            if key not in attribute_values:
                attribute_values[key] = set()

            # Convert to string for comparison
            str_value = str(value)
            attribute_values[key].add(str_value)

    # Find attributes with variance
    varying_attributes = []
    unique_values = {}

    for attr, values in attribute_values.items():
        if len(values) > 1:
            varying_attributes.append({
                "attribute": attr,
                "variance_count": len(values),
                "values": list(values)[:5]  # Limit to first 5
            })
            unique_values[attr] = list(values)

    # Sort by variance count to find the most differentiating attribute
    varying_attributes.sort(key=lambda x: x["variance_count"], reverse=True)

    suggested_differentiator = None
    if varying_attributes:
        # Prefer numeric attributes as differentiators
        for attr_info in varying_attributes:
            attr = attr_info["attribute"]
            # Check if values look numeric
            try:
                sample_values = [float(v) for v in unique_values[attr][:3]]
                suggested_differentiator = attr
                break
            except ValueError:
                continue

        # Fallback to first varying attribute
        if not suggested_differentiator:
            suggested_differentiator = varying_attributes[0]["attribute"]

    return {
        "has_variance": len(varying_attributes) > 0,
        "varying_attributes": varying_attributes,
        "suggested_differentiator": suggested_differentiator,
        "unique_values": unique_values
    }


# =============================================================================
# ENTITY EXTRACTION (Configuration-Driven)
# =============================================================================

def extract_entity_codes(query: str) -> list[str]:
    """Extract domain entity codes from query using configured patterns.

    This function is completely generic - patterns come from config.

    Args:
        query: User's query string

    Returns:
        List of extracted entity codes, normalized for database matching
    """
    config = get_config()
    codes = []
    query_upper = query.upper()

    # Apply configured regex patterns
    for pattern_config in config.product_code_patterns:
        compiled = pattern_config.compile()
        matches = compiled.findall(query)

        # Normalize matches
        for match in matches:
            normalized = match
            if config.normalization.replace_space_with:
                normalized = normalized.replace(' ', config.normalization.replace_space_with)
            if config.normalization.uppercase:
                normalized = normalized.upper()
            codes.append(normalized)

    # Check for configured entity families/categories
    for family in config.product_families:
        if family.upper() in query_upper:
            # Check if we already have a full code for this family
            has_full_code = any(family.upper() in c.upper() for c in codes)
            if not has_full_code:
                codes.append(family)

            # Try to extract more context around the family name
            idx = query_upper.find(family.upper())
            if idx >= 0:
                context = query[idx:idx+30]
                clean_context = re.sub(r'[^\w\d\-x/]', ' ', context).strip().split()[0]
                if config.normalization.replace_space_with:
                    clean_context = clean_context.replace(' ', config.normalization.replace_space_with)
                if len(clean_context) > len(family) and clean_context not in codes:
                    codes.append(clean_context)

    return list(set(codes))


def extract_project_keywords(query: str) -> list[str]:
    """Extract project identifiers from query using configured patterns."""
    config = get_config()
    keywords = []
    query_lower = query.lower()
    stopwords = set(config.project_search.stopwords)

    # Apply configured patterns
    for pattern in config.project_search.patterns:
        matches = re.findall(pattern, query_lower)
        for match in matches:
            if match not in stopwords and len(match) > 2:
                keywords.append(match)

    # Check for known identifiers
    for identifier in config.project_search.known_identifiers:
        if identifier.lower() in query_lower:
            keywords.append(identifier)

    return list(set(keywords))


# =============================================================================
# CONTEXT FORMATTING (Configuration-Driven)
# =============================================================================

def _get_field_value(data: dict, field_config, config: DomainConfig) -> Optional[str]:
    """Get value for a field, checking fallbacks."""
    value = data.get(field_config.key)

    # Check fallback keys
    if value is None and field_config.fallback_keys:
        for fallback in field_config.fallback_keys:
            value = data.get(fallback)
            if value is not None:
                break

    # Use default if still None
    if value is None and field_config.default:
        value = field_config.default

    return value


def _format_single_field(data: dict, field_config, combined_values: dict = None) -> Optional[str]:
    """Format a single field according to its configuration."""
    # Skip if hidden due to combination
    if field_config.hidden_if_combined and combined_values:
        return None

    # Handle display_only_if_true
    if field_config.display_only_if_true:
        if data.get(field_config.key):
            return field_config.format
        return None

    # Get value
    value = data.get(field_config.key)
    if value is None:
        for fb in field_config.fallback_keys:
            value = data.get(fb)
            if value is not None:
                break

    if value is None:
        if field_config.default:
            value = field_config.default
        elif field_config.required:
            value = "Unknown"
        else:
            return None

    # Handle arrays
    if field_config.is_array and isinstance(value, list):
        value = field_config.array_join.join(str(v) for v in value)

    # Handle combined fields
    if field_config.combine_with:
        other_value = data.get(field_config.combine_with)
        if other_value is not None:
            # Build combined format with both values
            format_dict = {field_config.key: value, field_config.combine_with: other_value}
            result = field_config.combined_format.format(**format_dict)

            # Check for append fields
            # (simplified - in full implementation would scan for append_to_combined)
            return result
        # If other value missing, just show this one
        return field_config.format.format(value=value)

    return field_config.format.format(value=value)


def _format_options(data: dict, config: DomainConfig) -> list[str]:
    """Format configuration options using config schema."""
    lines = []
    opts_config = config.primary_entity_display.options_display

    # Try JSON options first
    json_options = data.get(opts_config.json_key)
    if json_options:
        try:
            options = json.loads(json_options) if isinstance(json_options, str) else json_options
            if options:
                lines.append(opts_config.header)
                for opt in options:
                    code = opt.get('code', '?')
                    desc = opt.get('description', 'Unknown')
                    category = opt.get('category', '')
                    cat_str = opts_config.category_format.format(category=category) if category else ""
                    line = opts_config.format.format(code=code, description=desc) + cat_str
                    lines.append(line)
                return lines
        except (json.JSONDecodeError, TypeError):
            pass

    # Fallback to simple list
    fallback_options = data.get(opts_config.fallback_key)
    if fallback_options and isinstance(fallback_options, list):
        lines.append(opts_config.header)
        for opt in fallback_options:
            lines.append(f"    • {opt}")

    return lines


# =============================================================================
# ACTIVE LEARNING - Semantic Query Expansion & Rule Retrieval
# =============================================================================

def extract_search_concepts(user_query: str) -> list[str]:
    """Extract standardized search concepts from user query using LLM.

    This enables "Semantic Query Expansion" - extracts key technical terms
    from long sentences and generates synonyms for better rule matching.

    CRITICAL: This solves the "vector miss" problem where long sentences
    have poor similarity with short keyword rules.

    Args:
        user_query: Raw user query text (can be a full sentence)

    Returns:
        List of 3-7 key concepts and their synonyms for search
    """
    if not user_query or len(user_query.strip()) < 3:
        return []

    extraction_prompt = f"""Extract the KEY TECHNICAL TERMS from this user query.

USER QUERY: "{user_query}"

TASK:
1. EXTRACT the exact technical terms, equipment names, or environments from the query
2. PRESERVE compound terms (e.g., "Lakiernia Proszkowa" = one term, not two)
3. ADD 2-3 synonyms for each extracted term (Polish + English)
4. Focus on NOUNS: facilities, equipment, environments, processes
5. IGNORE filler words: "klient", "potrzebuje", "proszę", "czy"

EXAMPLES:
Input: "Klient potrzebuje filtrów do nowej Lakierni Proszkowej w fabryce mebli"
Output: ["Lakiernia Proszkowa", "Malarnia Proszkowa", "Powder Coating", "Paint Shop", "Fabryka Mebli", "Furniture Factory"]

Input: "Czy obudowa GDB nadaje się do basenu?"
Output: ["Basen", "Swimming Pool", "Pływalnia", "Aquapark", "GDB"]

Input: "Potrzebuję wentylacji dla szpitalnego oddziału intensywnej terapii"
Output: ["Szpital", "Hospital", "OIOM", "Oddział Intensywnej Terapii", "ICU", "Healthcare"]

Input: "Filtry węglowe do kuchni przemysłowej"
Output: ["Kuchnia Przemysłowa", "Commercial Kitchen", "Industrial Kitchen", "Gastronomia"]

Return ONLY a JSON array of strings. No explanation.
"""

    try:
        response = client.models.generate_content(
            model=LLM_MODEL_FAST,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=extraction_prompt)])],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )

        concepts = json.loads(response.text)
        if isinstance(concepts, list) and len(concepts) > 0:
            # Clean and deduplicate
            cleaned = []
            seen_lower = set()
            for c in concepts:
                if isinstance(c, str) and len(c) > 2:
                    c_lower = c.lower().strip()
                    if c_lower not in seen_lower:
                        cleaned.append(c.strip())
                        seen_lower.add(c_lower)
            return cleaned[:8]  # Limit to 8 concepts
        return []

    except Exception as e:
        print(f"Warning: Concept extraction failed: {e}")
        # Fallback: extract capitalized words and long words
        words = user_query.split()
        concepts = []
        for w in words:
            w = w.strip('.,?!:;')
            if len(w) > 4 and w[0].isupper():
                concepts.append(w)
            elif len(w) > 6:
                concepts.append(w)
        return concepts[:5]


def get_semantic_rules_expanded(concepts: list[str], user_query: str = "") -> str:
    """Retrieve learned rules using expanded concept search.

    Searches for each concept separately and aggregates results,
    keeping the highest similarity score for each unique rule.

    Args:
        concepts: List of extracted concepts from extract_search_concepts()
        user_query: Original query for keyword fallback

    Returns:
        Formatted string block to inject into LLM prompt
    """
    if not concepts:
        return ""

    rules_by_text = {}  # rule_text -> {rule_data, max_score}

    # Step 1: Generate embeddings and search for each concept
    for concept in concepts:
        try:
            concept_embedding = generate_embedding(concept)
            concept_rules = db.get_semantic_rules(concept_embedding, top_k=3, min_score=0.75)

            for rule in concept_rules:
                rule_text = rule.get("rule", "")
                similarity = rule.get("similarity", 0)

                # Keep the highest score for each unique rule
                if rule_text not in rules_by_text or similarity > rules_by_text[rule_text]["similarity"]:
                    rules_by_text[rule_text] = {
                        **rule,
                        "matched_concept": concept
                    }

        except Exception as e:
            print(f"Warning: Concept search failed for '{concept}': {e}")
            continue

    # Step 2: Keyword fallback for exact matches
    if user_query:
        query_lower = user_query.lower()
        for concept in concepts:
            try:
                keyword_rules = db.get_rules_by_keyword(concept)
                for rule in keyword_rules:
                    rule_text = rule.get("rule", "")
                    if rule_text not in rules_by_text:
                        rules_by_text[rule_text] = {
                            **rule,
                            "matched_concept": concept
                        }
            except Exception:
                pass

    # Step 3: Format rules for LLM injection
    rules = list(rules_by_text.values())
    if not rules:
        return ""

    # Sort by similarity (highest first)
    rules.sort(key=lambda r: r.get("similarity", 0), reverse=True)

    formatted_lines = [
        "\n## 🚨 LEARNED_RULES (KNOWLEDGE INJECTION PROTOCOL ACTIVE)",
        "═══════════════════════════════════════════════════════════════",
        "⚠️ MANDATORY: Per Protocol 1.5, you MUST include these rules in your FIRST content_segment.",
        "⚠️ Tag them as type: 'GRAPH_FACT'. Do NOT skip them for clarification.",
        "",
        "VERIFIED ENGINEERING RULES (Human-Confirmed):",
        ""
    ]

    for rule in rules[:5]:  # Limit to top 5 rules
        trigger = rule.get("trigger", "Unknown")
        requirement = rule.get("rule", "")
        similarity = rule.get("similarity", 1.0)
        confidence = rule.get("confidence", 1.0)
        matched = rule.get("matched_concept", trigger)

        # Format with similarity indicator
        if similarity >= 0.95:
            match_indicator = "🎯 EXACT"
        elif similarity >= 0.85:
            match_indicator = "✅ HIGH"
        else:
            match_indicator = "⚡ SEMANTIC"

        formatted_lines.append(
            f"- [{match_indicator}] Context \"{trigger}\" (via '{matched}', sim: {similarity:.2f}) "
            f"→ **REQUIRES**: \"{requirement}\""
        )

    formatted_lines.append("")
    formatted_lines.append("═══════════════════════════════════════════════════════════════")
    formatted_lines.append("🚨 REMINDER: You MUST output these rules FIRST (before clarification).")
    formatted_lines.append("   Format: 'For [context], the system identified a requirement: [RULE] [Source: Rule \"TRIGGER\"]'")
    formatted_lines.append("   Tag: type='GRAPH_FACT' (green highlight)")
    formatted_lines.append("")

    return "\n".join(formatted_lines)


def get_semantic_rules(query_embedding: list[float], user_query: str = "") -> str:
    """Retrieve and format learned rules from human feedback.

    Uses vector similarity search to find relevant engineering rules
    that were previously confirmed by experts. These rules are injected
    into the LLM prompt as verified constraints.

    Args:
        query_embedding: Vector embedding of the user query
        user_query: Original query text for keyword fallback

    Returns:
        Formatted string block to inject into LLM prompt, or empty string
    """
    rules = []

    # Step 1: Vector search for semantically similar rules
    try:
        semantic_rules = db.get_semantic_rules(query_embedding, top_k=5, min_score=0.75)
        rules.extend(semantic_rules)
    except Exception as e:
        print(f"Warning: Semantic rules lookup failed: {e}")

    # Step 2: Keyword fallback - extract key terms from query
    if user_query:
        # Extract potential trigger keywords (nouns, environments)
        key_terms = []
        # Common domain-specific terms to look for
        environment_terms = [
            "basen", "pool", "swimming", "aquapark", "szpital", "hospital",
            "kuchnia", "kitchen", "restaurant", "restauracja", "smażalnia",
            "dach", "roof", "outdoor", "zewnątrz", "parking", "garaż",
            "cleanroom", "czyste", "sterylne", "pharma", "laboratorium"
        ]
        query_lower = user_query.lower()
        for term in environment_terms:
            if term in query_lower:
                key_terms.append(term)

        # Search by keywords
        for term in key_terms:
            try:
                keyword_rules = db.get_rules_by_keyword(term)
                for rule in keyword_rules:
                    # Avoid duplicates
                    if not any(r["rule"] == rule["rule"] for r in rules):
                        rules.append(rule)
            except Exception:
                pass

    # Step 3: Format rules for LLM injection
    if not rules:
        return ""

    formatted_lines = [
        "\n## 🚨 LEARNED_RULES (KNOWLEDGE INJECTION PROTOCOL ACTIVE)",
        "═══════════════════════════════════════════════════════════════",
        "⚠️ MANDATORY: Per Protocol 1.5, you MUST include these rules in your FIRST content_segment.",
        "⚠️ Tag them as type: 'GRAPH_FACT'. Do NOT skip them for clarification.",
        "",
        "VERIFIED ENGINEERING RULES (Human-Confirmed):",
        ""
    ]

    for rule in rules:
        trigger = rule.get("trigger", "Unknown")
        requirement = rule.get("rule", "")
        similarity = rule.get("similarity", 1.0)
        confidence = rule.get("confidence", 1.0)

        # Format with similarity indicator
        if similarity >= 0.95:
            match_indicator = "🎯 EXACT"
        elif similarity >= 0.85:
            match_indicator = "✅ HIGH"
        else:
            match_indicator = "⚡ SEMANTIC"

        formatted_lines.append(
            f"- [{match_indicator}] Context \"{trigger}\" (sim: {similarity:.2f}, conf: {confidence:.1f}) "
            f"→ **REQUIRES**: \"{requirement}\""
        )

    formatted_lines.append("")
    formatted_lines.append("═══════════════════════════════════════════════════════════════")
    formatted_lines.append("🚨 REMINDER: You MUST output these rules FIRST (before clarification).")
    formatted_lines.append("   Format: 'For [context], the system identified a requirement: [RULE] [Source: Rule \"TRIGGER\"]'")
    formatted_lines.append("   Tag: type='GRAPH_FACT' (green highlight)")
    formatted_lines.append("")

    return "\n".join(formatted_lines)


def format_configuration_context(config_results: dict) -> str:
    """Format search results using configuration-driven rendering.

    This function contains NO hardcoded field names - everything
    comes from the display schema in configuration.

    Args:
        config_results: Results from configuration graph search

    Returns:
        Formatted context string for LLM consumption
    """
    if not config_results:
        return ""

    config = get_config()
    context_parts = []

    # Format primary entities (variants/products)
    variants = config_results.get("variants", [])
    if variants:
        display = config.primary_entity_display
        header = display.header_template.format(icon=display.icon, title=display.title)
        context_parts.append(header)

        for v in variants:
            section = []

            # Track combined fields
            combined_keys = set()
            for field in display.fields:
                if field.combine_with:
                    combined_keys.add(field.combine_with)

            # Process each configured field
            for field_config in display.fields:
                # Skip if this field is part of a combination (will be handled by primary)
                if field_config.key in combined_keys:
                    continue

                formatted = _format_single_field(v, field_config, {})
                if formatted:
                    section.append(formatted)

            # Add options
            option_lines = _format_options(v, config)
            section.extend(option_lines)

            if section:
                context_parts.append("\n".join(section))

    # Format secondary entities dynamically
    for entity_name, entity_config in config.secondary_entities.items():
        items = config_results.get(entity_name, [])
        if not items:
            continue

        context_parts.append(f"\n{entity_config.header}")

        for item in items:
            parts = [entity_config.item_prefix]

            for field_config in entity_config.fields:
                value = _get_field_value(item, field_config, config)
                if value is not None:
                    parts.append(field_config.format.format(value=value))

            if len(parts) > 1:
                context_parts.append("".join(parts))

            # Show options if configured
            if entity_config.show_options:
                option_lines = _format_options(item, config)
                context_parts.extend(option_lines)

    return "\n".join(context_parts) if context_parts else ""


# =============================================================================
# GUARDIAN REASONING ENGINE (Policy-Driven)
# =============================================================================

def evaluate_policies(
    query: str,
    graph_data: dict,
    config: DomainConfig
) -> tuple[list[PolicyCheckResult], str]:
    """Evaluate Guardian policies against query and graph data.

    This is the core of the reasoning layer - it validates user intent
    against configured business rules.

    Args:
        query: User's query
        graph_data: Retrieved graph data
        config: Domain configuration

    Returns:
        Tuple of (policy check results, formatted policy analysis string)
    """
    active_policies = config.get_active_policies_for_query(query)
    results = []
    analysis_parts = []

    if not active_policies:
        return results, "No special policies triggered for this query."

    analysis_parts.append("**Policy Evaluation:**\n")

    for policy in active_policies:
        result = PolicyCheckResult(
            policy_id=policy.id,
            policy_name=policy.name,
            triggered=True,
            passed=True,
            message="",
            recommendation=""
        )

        analysis_parts.append(f"• [{policy.id}] {policy.name} - TRIGGERED")

        # Check if graph data contains the required attribute
        check_attr = policy.validation.check_attribute
        found_values = []

        # Search in variants
        for variant in graph_data.get("variants", []):
            if check_attr in variant and variant[check_attr]:
                found_values.append(variant[check_attr])

        # Search in materials
        for material in graph_data.get("materials", []):
            if check_attr in material and material[check_attr]:
                found_values.append(material[check_attr])

        # Evaluate validation rules
        if policy.validation.required_values and found_values:
            matching = [v for v in found_values if v in policy.validation.required_values]
            if not matching:
                result.passed = False
                result.message = policy.validation.fail_message
                result.recommendation = policy.validation.recommendation
                analysis_parts.append(f"  ⚠️ FAILED: {result.message}")
                analysis_parts.append(f"  → Recommendation: {result.recommendation}")
            else:
                analysis_parts.append(f"  ✓ PASSED: Found {', '.join(matching)}")

        elif policy.validation.min_value is not None:
            numeric_values = [v for v in found_values if isinstance(v, (int, float))]
            if numeric_values:
                if min(numeric_values) < policy.validation.min_value:
                    result.passed = False
                    result.message = policy.validation.fail_message
                    result.recommendation = policy.validation.recommendation
            else:
                analysis_parts.append(f"  ℹ️ Unable to verify: attribute not found in graph")

        elif not found_values:
            analysis_parts.append(f"  ℹ️ Unable to verify: '{check_attr}' not found in retrieved data")

        results.append(result)
        analysis_parts.append("")

    return results, "\n".join(analysis_parts)


def build_guardian_prompt(query: str, config: DomainConfig) -> str:
    """Build the Guardian policy injection for the system prompt."""
    active_policies = config.get_active_policies_for_query(query)
    policy_prompt = config.format_policies_for_prompt(active_policies)

    # Add domain-specific Guardian rules from config
    guardian_rules = config.get_all_guardian_rules_prompt()
    if guardian_rules:
        return f"""{guardian_rules}

{policy_prompt}"""
    return policy_prompt


# =============================================================================
# CONTEXT FORMATTING (Generic)
# =============================================================================

def format_retrieval_context(
    retrieval_results: list[dict],
    similar_cases: list[dict],
    config_context: str = ""
) -> str:
    """Format retrieval results into readable context for LLM.

    This function is domain-agnostic - it works with any graph structure.

    Args:
        retrieval_results: Raw results from hybrid retrieval
        similar_cases: Results from similar case search
        config_context: Pre-formatted configuration graph context

    Returns:
        Formatted context string
    """
    context_parts = []

    # Add configuration context first (product data takes priority)
    if config_context:
        context_parts.append(config_context)
        context_parts.append("\n---\n")

    # Group results by project/case
    projects = {}
    for r in retrieval_results:
        project = r.get("project") or "Unknown"
        if project not in projects:
            projects[project] = {
                "concepts": set(),
                "events": [],
                "observations": [],
                "actions": [],
                "solutions": []
            }

        if r.get("concept"):
            projects[project]["concepts"].add(
                f"{r['concept']} (score: {r.get('score', 0):.2f})"
            )

        if r.get("event_summary"):
            event_info = (
                f"[{r.get('event_date', 'Unknown date')}] "
                f"{r.get('sender', 'Unknown')}: {r['event_summary']}"
            )
            if event_info not in projects[project]["events"]:
                projects[project]["events"].append(event_info)

        if r.get("logic_description"):
            logic_type = r.get("logic_type", "")
            logic_subtype = r.get("logic_subtype", "")
            prefix = f"[{logic_subtype}]" if logic_subtype else f"[{logic_type}]"

            entry = f"{prefix} {r['logic_description']}"
            if r.get("logic_citation"):
                entry += f'\n    📝 Source: "{r["logic_citation"]}"'

            if logic_type == "Observation":
                if r.get("revealed_constraint"):
                    entry += f"\n    → Revealed: {r['revealed_constraint']}"
                if entry not in projects[project]["observations"]:
                    projects[project]["observations"].append(entry)
            elif logic_type == "Action":
                if r.get("addresses_problem"):
                    entry += f"\n    → Addresses: {r['addresses_problem']}"
                if entry not in projects[project]["actions"]:
                    projects[project]["actions"].append(entry)

        if r.get("solution_action"):
            sol = f"Solution: {r['solution_action']}"
            if sol not in projects[project]["solutions"]:
                projects[project]["solutions"].append(sol)

    # Format each project
    for project_name, data in projects.items():
        if project_name == "Unknown" and not any([
            data["events"], data["observations"], data["actions"]
        ]):
            continue

        section = [f"### Case: {project_name}"]

        if data["concepts"]:
            section.append(f"Matched Concepts: {', '.join(data['concepts'])}")

        if data["events"]:
            section.append("\nCommunication Thread:")
            for event in data["events"][:5]:
                section.append(f"  • {event}")

        if data["observations"]:
            section.append("\nObservations (Problems/Constraints):")
            for obs in data["observations"][:5]:
                section.append(f"  • {obs}")

        if data["actions"]:
            section.append("\nActions Taken:")
            for act in data["actions"][:5]:
                section.append(f"  • {act}")

        if data["solutions"]:
            section.append("\nSolutions Applied:")
            for sol in data["solutions"][:3]:
                section.append(f"  • {sol}")

        context_parts.append("\n".join(section))

    # Add similar cases
    if similar_cases:
        similar_section = ["\n### Similar Past Cases"]
        for case in similar_cases[:3]:
            case_info = [f"\n**{case.get('project', 'Unknown')}**"]
            if case.get("customer"):
                case_info.append(f"(Customer: {case['customer']})")
            if case.get("matched_concepts"):
                case_info.append(f"\nRelevant concepts: {', '.join(case['matched_concepts'][:3])}")
            if case.get("symptoms"):
                symptoms = [s for s in case["symptoms"] if s]
                if symptoms:
                    case_info.append(f"\nProblems: {'; '.join(symptoms[:2])}")
            if case.get("solutions"):
                solutions = [s for s in case["solutions"] if s]
                if solutions:
                    case_info.append(f"\nSolutions: {'; '.join(solutions[:2])}")
            similar_section.append(" ".join(case_info))
        context_parts.append("\n".join(similar_section))

    return "\n\n".join(context_parts) if context_parts else "No relevant past cases found."


# =============================================================================
# KNOWLEDGE SOURCE HANDLING
# =============================================================================

def find_knowledge_source_mentions(query: str) -> list[dict]:
    """Search for verified knowledge source mentions in the query."""
    return db.find_alias_matches(query)


def format_knowledge_sources(sources: list[dict]) -> str:
    """Format knowledge source matches for LLM context."""
    if not sources:
        return ""

    parts = ["\n## VERIFIED INSTITUTIONAL KNOWLEDGE"]
    parts.append("The following verified sources were recognized:")

    for source in sources:
        name = source.get("verified_name", "Unknown")
        source_type = source.get("source_type", "Unknown")
        description = source.get("description")
        matched_pattern = source.get("matched_pattern")
        verified_by = source.get("verified_by")

        entry = f"\n**{name}** ({source_type})"
        if description:
            entry += f"\n  Description: {description}"
        if verified_by:
            entry += f"\n  *Expert: {verified_by}*"
        if matched_pattern and matched_pattern.lower() != name.lower():
            entry += f'\n  (Matched via alias: "{matched_pattern}")'
        parts.append(entry)

    return "\n".join(parts)


# =============================================================================
# MAIN QUERY FUNCTION (Configuration-Driven)
# =============================================================================

def query_knowledge_graph(user_query: str) -> dict:
    """Query the knowledge graph using hybrid retrieval with Guardian reasoning.

    This is the main function - completely domain-agnostic.
    All domain logic comes from configuration.

    Args:
        user_query: The user's question

    Returns:
        Dict with structured response including reasoning transparency
    """
    config = get_config()

    # Step 1: Embed the query
    query_embedding = generate_embedding(user_query)

    # Step 2: Hybrid retrieval
    retrieval_results = db.hybrid_retrieval(query_embedding, top_k=5, min_score=0.5)

    # Step 3: Search by project name if mentioned
    project_keywords = extract_project_keywords(user_query)
    for keyword in project_keywords:
        project_results = db.search_by_project_name(keyword)
        if project_results:
            retrieval_results = project_results + retrieval_results

    # Step 4: Configuration Graph search
    entity_codes = extract_entity_codes(user_query)
    config_results = {
        "variants": [],
        "cartridges": [],
        "filters": [],
        "materials": [],
        "option_matches": []
    }

    # Search by extracted entity codes
    for code in entity_codes:
        exact_match = db.get_variant_by_name(code)
        if exact_match:
            config_results["variants"].append(exact_match)
        else:
            fuzzy_results = db.search_product_variants(code)
            for fr in fuzzy_results:
                if fr not in config_results["variants"]:
                    config_results["variants"].append(fr)

    # Search by configured keywords
    all_keywords = config.get_all_search_keywords()
    for kw in all_keywords:
        if kw.lower() in user_query.lower():
            general_config = db.configuration_graph_search(kw)
            for key in config_results.keys():
                for item in general_config.get(key, []):
                    if item not in config_results[key]:
                        config_results[key].append(item)

    # Step 5: Self-learning - find knowledge sources
    knowledge_sources = find_knowledge_source_mentions(user_query)
    knowledge_context = format_knowledge_sources(knowledge_sources)

    # Step 6: Get similar cases
    similar_cases = db.get_similar_cases(query_embedding, top_k=3)

    # Step 7: GUARDIAN - Evaluate policies
    policy_results, policy_analysis = evaluate_policies(
        user_query, config_results, config
    )

    # Step 8: Format contexts
    config_context = format_configuration_context(config_results)
    graph_context = format_retrieval_context(retrieval_results, similar_cases, config_context)

    if knowledge_context:
        graph_context = f"{graph_context}\n\n{knowledge_context}"

    # Step 9: Build dynamic prompts
    active_policies_prompt = build_guardian_prompt(user_query, config)

    # Format system prompt with active policies
    system_prompt = config.prompts.system.format(active_policies=active_policies_prompt)

    # Format synthesis prompt
    synthesis_prompt = config.prompts.synthesis.format(
        context=graph_context,
        products="See product data above.",
        query=user_query,
        policies=policy_analysis
    )

    # Step 10: LLM synthesis
    response = client.models.generate_content(
        model=LLM_MODEL,
        contents=[
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=synthesis_prompt)]
            )
        ],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    # Parse structured response
    try:
        llm_response = json.loads(response.text)
    except json.JSONDecodeError:
        # Fallback for non-JSON response
        llm_response = {
            "intent_analysis": "Unable to parse structured response",
            "policy_analysis": policy_analysis,
            "graph_evidence": [],
            "general_knowledge": "",
            "final_answer": response.text,
            "confidence_level": "low",
            "sources": [],
            "warnings": []
        }

    # Build evidence list
    graph_evidence = []
    for ev in llm_response.get("graph_evidence", []):
        if isinstance(ev, dict):
            graph_evidence.append(GraphEvidence(
                fact=ev.get("fact", ""),
                source_id=ev.get("source_id", "unknown"),
                confidence=ev.get("confidence", "verified")
            ))

    # Collect sources
    sources = []
    for v in config_results.get("variants", []):
        if v.get("id"):
            sources.append(v["id"])

    # Collect warnings from policy checks
    warnings = [r.message for r in policy_results if not r.passed and r.message]

    return {
        "intent_analysis": llm_response.get("intent_analysis", ""),
        "policy_analysis": llm_response.get("policy_analysis", policy_analysis),
        "graph_evidence": graph_evidence,
        "general_knowledge": llm_response.get("general_knowledge", ""),
        "final_answer": llm_response.get("final_answer", response.text),
        "confidence_level": llm_response.get("confidence_level", "medium"),
        "sources": sources + llm_response.get("sources", []),
        "warnings": warnings + llm_response.get("warnings", []),
        "policy_checks": policy_results,
        "thought_process": f"Analyzed query → {len(policy_results)} policies checked → "
                          f"{len(config_results['variants'])} products found → "
                          f"{len(retrieval_results)} cases retrieved",
        # Legacy fields for backwards compatibility
        "answer": llm_response.get("final_answer", response.text),
        "concepts_matched": list(set(
            r.get("concept") for r in retrieval_results if r.get("concept")
        )),
        "observations": list(set(
            r.get("logic_description") for r in retrieval_results
            if r.get("logic_type") == "Observation" and r.get("logic_description")
        ))[:5],
        "actions": list(set(
            r.get("logic_description") for r in retrieval_results
            if r.get("logic_type") == "Action" and r.get("logic_description")
        ))[:5],
        "products_mentioned": [v.get("id") for v in config_results.get("variants", []) if v.get("id")],
        "similar_projects": [c.get("project") for c in similar_cases if c.get("project")],
    }


# =============================================================================
# LEGACY API COMPATIBILITY
# =============================================================================

def query_sales_brain(user_query: str) -> dict:
    """Legacy wrapper - calls the new generic function."""
    return query_knowledge_graph(user_query)


def consult_brain(user_query: str) -> ConsultResponse:
    """Legacy wrapper for API compatibility."""
    result = query_knowledge_graph(user_query)
    return ConsultResponse(
        answer=result["answer"],
        concepts_matched=result["concepts_matched"],
        observations=result["observations"],
        actions=result["actions"],
        products_mentioned=result["products_mentioned"]
    )


def consult_brain_structured(user_query: str) -> StructuredResponse:
    """New structured response with full explainability."""
    result = query_knowledge_graph(user_query)
    return StructuredResponse(
        intent_analysis=result["intent_analysis"],
        policy_analysis=result["policy_analysis"],
        graph_evidence=result["graph_evidence"],
        general_knowledge=result["general_knowledge"],
        final_answer=result["final_answer"],
        confidence_level=result["confidence_level"],
        sources=result["sources"],
        warnings=result["warnings"],
        policy_checks=result["policy_checks"],
        thought_process=result["thought_process"]
    )


# =============================================================================
# EXPLAINABLE UI API
# =============================================================================

EXPLAINABLE_SYSTEM_PROMPT = """You are an expert Sales Engineering Assistant with access to a verified Knowledge Graph.

## YOUR ROLE
Provide helpful, accurate answers by combining Knowledge Graph data with your reasoning.
You MUST clearly distinguish between VERIFIED GRAPH DATA and your GENERAL KNOWLEDGE.

## CRITICAL OUTPUT RULES

### 1. LANGUAGE MATCHING
ALWAYS respond in ENGLISH regardless of the user's query language.

### 2. INLINE CITATIONS (MANDATORY)
Every fact from the Knowledge Graph MUST be followed immediately by a [[REF:ID]] marker.

Format: "The housing is 600x600mm [[REF:GDC-600x600]] and weighs 12kg [[REF:weight-spec]]."

- The [[REF:ID]] appears AFTER the fact it verifies
- ID should be the node name/ID from the graph data
- Text WITHOUT [[REF:...]] markers is understood to be general knowledge from your pretraining

### 3. REASONING CHAIN WITH SOURCE ATTRIBUTION
You MUST document each reasoning step with its SOURCE:
- **GRAPH**: Fact retrieved from Knowledge Graph (include node_id)
- **LLM**: Inference from your pretraining/general knowledge
- **POLICY**: Business rule check
- **FILTER**: Programmatic filter applied (e.g., capacity sizing)

### 4. CAPACITY SIZING (CRITICAL)
If user specifies airflow (e.g., 3000 m³/h), you MUST only recommend products where airflow_m3h >= requested.
Never recommend undersized equipment.

{active_policies}

## OUTPUT SCHEMA (STRICT JSON)
```json
{{
  "reasoning_chain": [
    {{"step": "Found GDC-900x600 with airflow 3000 m³/h", "source": "GRAPH", "node_id": "GDC-900x600"}},
    {{"step": "Carbon filters effective for exhaust fumes", "source": "LLM", "node_id": null}},
    {{"step": "POL-003 Capacity Check: PASSED (3000 >= 3000)", "source": "POLICY", "node_id": null}},
    {{"step": "Undersized products filtered out: GDC-600x600", "source": "FILTER", "node_id": null}}
  ],
  "final_answer_markdown": "Your answer with [[REF:ID]] markers...",
  "references": {{
    "ID1": {{"name": "Display Name", "type": "Product|Spec|Case|Material", "source_doc": "PDF p.X"}}
  }}
}}
```
"""

EXPLAINABLE_SYNTHESIS_PROMPT = """## KNOWLEDGE GRAPH DATA (Use [[REF:ID]] to cite)

{context}

## USER QUERY
{query}

## ACTIVE POLICIES
{policies}

## INSTRUCTIONS

1. **Analyze** the query and identify what the user needs
2. **Search** the Knowledge Graph data above for relevant facts
3. **Check policies** - especially capacity sizing if airflow is mentioned
4. **Compose** your answer in English with [[REF:ID]] citations
5. **Document** your reasoning steps

Remember:
- Every fact from Graph Data needs [[REF:ID]] immediately after it
- Text without citations = general knowledge (shown differently in UI)
- ALWAYS respond in ENGLISH

Output valid JSON only. No markdown code blocks."""


def query_explainable(user_query: str) -> ExplainableResponse:
    """Query the knowledge graph and return an explainable response.

    This function is designed for the Explainable UI, providing:
    - Transparent reasoning steps
    - Inline citations with [[REF:ID]] markers
    - Reference lookup table for UI hover/click

    Args:
        user_query: The user's question

    Returns:
        ExplainableResponse with reasoning, citations, and references
    """
    config = get_config()

    # Step 1: LLM Intent Detection (language, requirements, context)
    intent = detect_intent(user_query)

    # Step 2: Embed the query
    query_embedding = generate_embedding(user_query)

    # Step 3: Hybrid retrieval
    retrieval_results = db.hybrid_retrieval(query_embedding, top_k=5, min_score=0.5)

    # Step 4: Search by project name if mentioned
    project_keywords = extract_project_keywords(user_query)
    for keyword in project_keywords:
        project_results = db.search_by_project_name(keyword)
        if project_results:
            retrieval_results = project_results + retrieval_results

    # Step 5: Configuration Graph search
    entity_codes = extract_entity_codes(user_query)
    config_results = {
        "variants": [],
        "cartridges": [],
        "filters": [],
        "materials": [],
        "option_matches": []
    }

    for code in entity_codes:
        exact_match = db.get_variant_by_name(code)
        if exact_match:
            config_results["variants"].append(exact_match)
        else:
            fuzzy_results = db.search_product_variants(code)
            for fr in fuzzy_results:
                if fr not in config_results["variants"]:
                    config_results["variants"].append(fr)

    # Search by configured keywords
    all_keywords = config.get_all_search_keywords()
    for kw in all_keywords:
        if kw.lower() in user_query.lower():
            general_config = db.configuration_graph_search(kw)
            for key in config_results.keys():
                for item in general_config.get(key, []):
                    if item not in config_results[key]:
                        config_results[key].append(item)

    # Step 6: GENERIC - Filter entities by numeric constraints from intent
    rejected_products = []
    sizing_note = ""

    for constraint in intent.numeric_constraints:
        value = constraint.get("value")
        unit = constraint.get("unit", "")

        if value and config_results.get("variants"):
            # Try to find matching attribute in entities
            for attr_name in ["capacity", "airflow_m3h", "max_flow", "rating", "size_mm", "weight_kg"]:
                sample = config_results["variants"][0] if config_results["variants"] else {}
                if attr_name in sample:
                    suitable, rejected = filter_entities_by_attribute(
                        config_results["variants"],
                        attr_name,
                        value,
                        comparison="gte"
                    )
                    config_results["variants"] = suitable
                    rejected_products.extend(rejected)

                    if rejected:
                        rejected_names = [e.get('id', e.get('name', '?')) for e in rejected]
                        sizing_note += f"\n⚠️ **FILTER**: Required {value} {unit}.\n"
                        sizing_note += f"REJECTED: {', '.join(rejected_names)}\n"
                        sizing_note += f"SUITABLE: {', '.join(e.get('id', e.get('name', '?')) for e in suitable) if suitable else 'NONE'}\n"
                    break

    # Step 7: Get similar cases
    similar_cases = db.get_similar_cases(query_embedding, top_k=3)

    # Step 8: GUARDIAN - Evaluate policies
    policy_results, policy_analysis = evaluate_policies(
        user_query, config_results, config
    )

    # Step 10: Format contexts with explicit IDs for citation
    config_context = format_configuration_context(config_results)
    graph_context = format_retrieval_context(retrieval_results, similar_cases, config_context)

    # Add sizing note to context
    if sizing_note:
        graph_context = sizing_note + graph_context

    # Step 11: Build prompts - always English
    active_policies_prompt = build_guardian_prompt(user_query, config)

    # Always respond in English
    lang_directive = "\n\n## RESPONSE LANGUAGE\n**You MUST respond in ENGLISH.** All responses must be in English regardless of query language.\n"

    system_prompt = EXPLAINABLE_SYSTEM_PROMPT.format(active_policies=active_policies_prompt) + lang_directive
    synthesis_prompt = EXPLAINABLE_SYNTHESIS_PROMPT.format(
        context=graph_context,
        query=user_query,
        policies=policy_analysis
    )

    # Step 11: LLM synthesis
    response = client.models.generate_content(
        model=LLM_MODEL,
        contents=[
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=synthesis_prompt)]
            )
        ],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    # Step 12: Parse and validate response
    try:
        llm_response = json.loads(response.text)
    except json.JSONDecodeError:
        llm_response = {
            "reasoning_chain": [],
            "reasoning_steps": ["Error: Could not parse LLM response"],
            "final_answer_markdown": response.text,
            "references": {}
        }

    # Step 13: Build reasoning chain with source attribution
    reasoning_chain = []

    # Add programmatic steps FIRST (these happened before LLM call)
    constraints_summary = f"{len(intent.numeric_constraints)} constraints" if intent.numeric_constraints else "no constraints"
    reasoning_chain.append(ReasoningStep(
        step=f"Intent Detection: language={intent.language}, {constraints_summary}, intent={intent.action_intent}",
        source="LLM",
        node_id=None,
        confidence="high"
    ))

    # Add graph retrieval steps (domain-agnostic)
    for variant in config_results.get("variants", []):
        vid = variant.get("id", variant.get("name", "?"))
        # Find the first meaningful numeric property to display
        display_prop = None
        for prop_name in ["capacity", "airflow_m3h", "max_flow", "rating", "size"]:
            if prop_name in variant and variant[prop_name]:
                display_prop = f"{prop_name}: {variant[prop_name]}"
                break
        step_text = f"Found entity: {vid}" + (f" ({display_prop})" if display_prop else "")
        reasoning_chain.append(ReasoningStep(
            step=step_text,
            source="GRAPH",
            node_id=vid,
            confidence="high"
        ))

    # Add filtering step if applied (domain-agnostic)
    if rejected_products and intent.numeric_constraints:
        rejected_names = [p.get('id', p.get('name', '?')) for p in rejected_products]
        reasoning_chain.append(ReasoningStep(
            step=f"Filter applied: rejected {', '.join(rejected_names)} (did not meet constraints)",
            source="FILTER",
            node_id=None,
            confidence="high"
        ))

    # Add policy check steps
    for policy_result in policy_results:
        status = "PASSED" if policy_result.passed else "FAILED"
        reasoning_chain.append(ReasoningStep(
            step=f"Policy {policy_result.policy_id}: {status}",
            source="POLICY",
            node_id=None,
            confidence="high"
        ))

    # Add LLM reasoning steps from response
    for step_data in llm_response.get("reasoning_chain", []):
        if isinstance(step_data, dict):
            reasoning_chain.append(ReasoningStep(
                step=step_data.get("step", ""),
                source=step_data.get("source", "LLM"),
                node_id=step_data.get("node_id"),
                confidence=step_data.get("confidence", "medium")
            ))

    # Step 14: Build reference details
    references = {}
    raw_refs = llm_response.get("references", {})
    for ref_id, ref_data in raw_refs.items():
        if isinstance(ref_data, dict):
            references[ref_id] = ReferenceDetail(
                name=ref_data.get("name", ref_id),
                type=ref_data.get("type", "Unknown"),
                source_doc=ref_data.get("source_doc", ""),
                confidence=ref_data.get("confidence", "verified")
            )

    # Auto-populate references from config_results
    for variant in config_results.get("variants", []):
        vid = variant.get("id", "")
        if vid and vid not in references:
            references[vid] = ReferenceDetail(
                name=vid,
                type="Product",
                source_doc="Configuration Graph",
                confidence="verified"
            )

    for material in config_results.get("materials", []):
        mid = material.get("code", "")
        if mid and mid not in references:
            references[mid] = ReferenceDetail(
                name=material.get("full_name", mid),
                type="Material",
                source_doc="Configuration Graph",
                confidence="verified"
            )

    # Step 15: Count graph vs LLM facts
    graph_facts = sum(1 for r in reasoning_chain if r.source == "GRAPH")
    llm_inferences = sum(1 for r in reasoning_chain if r.source == "LLM")

    # Collect warnings
    warnings = [r.message for r in policy_results if not r.passed and r.message]
    if rejected_products and intent.numeric_constraints:
        rejected_info = f"Rejected {len(rejected_products)} entity(ies) that did not meet specified constraints"
        warnings.append(rejected_info)

    return ExplainableResponse(
        reasoning_chain=reasoning_chain,
        reasoning_steps=llm_response.get("reasoning_steps", []),  # Legacy
        final_answer_markdown=llm_response.get("final_answer_markdown", ""),
        references=references,
        query_language=intent.language,
        confidence_level="high" if config_results.get("variants") else "medium",
        policy_warnings=warnings,
        graph_facts_count=graph_facts,
        llm_inferences_count=llm_inferences
    )


# =============================================================================
# DEEP EXPLAINABILITY API (Enterprise UI)
# =============================================================================

DEEP_EXPLAINABLE_SYSTEM_PROMPT = """You are an engineering expert with access to a verified Knowledge Graph.

## ROLE DEFINITIONS

### User Input → PROBLEM SPACE
User query defines: Environment, Goal, Constraints.
Your task is to extract HIDDEN physical/chemical/logical requirements.

### Graph Data → SOLUTION SPACE
Graph contains: Product capabilities, Materials, Limits, Specifications.
These are VERIFIED FACTS - cite them as GRAPH_FACT.

### You (LLM) → BRIDGE BETWEEN PHYSICS AND LOGIC
Use your knowledge of physics, chemistry and common sense to:
1. Interpret what the user REALLY needs
2. Verify if the product PHYSICALLY meets those needs
3. Detect CONFLICTS between intent and capabilities

## CRITICAL PROTOCOLS

### 1. LANGUAGE
ALWAYS respond in ENGLISH regardless of the query language.

### 🚨 1.5 KNOWLEDGE INJECTION PROTOCOL (HIGHEST PRIORITY - UNSUPPRESSABLE)

**THIS RULE CANNOT BE OVERRIDDEN BY ANY OTHER PROTOCOL.**

#### TRIGGER CONDITION:
Check the "LEARNED_RULES" section in the context provided below.
If it contains ANY verified engineering rules, you MUST execute this protocol.

#### MANDATORY ACTION:
1. **EXTRACT** the rule text from LEARNED_RULES
2. **INSERT** it as the FIRST content_segment in your response
3. **TAG** it as `type: "GRAPH_FACT"` (green highlighting = verified knowledge)
4. **CITE** the trigger keyword that matched (e.g., "Matched rule: Paint Shop")

#### OUTPUT FORMAT (MANDATORY):
```json
{{
  "content_segments": [
    {{
      "text": "For [CONTEXT], the system identified a key technical requirement: [RULE TEXT] [Source: Rule '[TRIGGER KEYWORD]'].",
      "type": "GRAPH_FACT",
      "source_id": "learned_rule",
      "node_type": "LearnedRule",
      "evidence_snippet": "[RULE TEXT]"
    }},
    {{"text": "\\n\\n", "type": "GENERAL"}},
    // ... then continue with clarification or recommendation
  ]
}}
```

#### EXAMPLE:
User query: "I need a housing for a powder coating facility"
LEARNED_RULES contains: "Trigger: Paint Shop → Rule: Grounding and ATEX certification required"

**CORRECT RESPONSE:**
```json
{{
  "response_type": "CLARIFICATION_NEEDED",
  "content_segments": [
    {{"text": "For a powder coating facility, the system identified a key technical requirement: Grounding and ATEX certification are required [Source: Rule 'Paint Shop'].", "type": "GRAPH_FACT", "source_id": "learned_rule", "node_type": "LearnedRule", "evidence_snippet": "Grounding and ATEX certification required"}},
    {{"text": "\\n\\nTo select the appropriate ATEX housing size, please provide the required airflow (m³/h).", "type": "GENERAL"}}
  ],
  "clarification_data": {{...}}
}}
```

#### ⛔ FORBIDDEN BEHAVIOR:
- ❌ Skipping the rule because you need to ask for clarification first
- ❌ Asking for dimensions/airflow WITHOUT showing the ATEX rule
- ❌ Treating learned rules as "optional" or "secondary"
- ❌ Putting the rule after the clarification question

#### PRIORITY CHAIN:
```
1. KNOWLEDGE INJECTION (this protocol) ← ALWAYS FIRST
2. Then Clarification (if needed)
3. Then Recommendation
```

**WHY THIS MATTERS:** Users taught the system these rules. Hiding them defeats the purpose
of self-learning. The rule provides CONTEXT that helps users answer your questions better.

---

### 2. 🛑 AMBIGUITY GATEKEEPER - THE VARIANCE RULE (MANDATORY FIRST CHECK)

**THIS IS YOUR FIRST AND MOST CRITICAL CHECK. DO NOT SKIP THIS.**

#### STEP 1: SCAN RETRIEVED NODES
Look at the Product Variants/Entities found in the graph for the requested family.
- Count how many different variants exist
- Check: Are there multiple variants with different physical capacities?
- Example: GDB-300, GDB-600, GDB-900 = 3 VARIANTS with different sizes

#### STEP 2: CHECK USER CONSTRAINTS
Did the user provide a NUMERICAL VALUE or SPECIFIC ATTRIBUTE to filter to ONE variant?
- "3000 m³/h" = YES, user provided constraint
- "for an office" = NO, this is context but NOT a sizing constraint
- "GDB housing" = NO, this is a family but NOT a specific variant

#### STEP 3: EXECUTE VARIANCE LOGIC

**⛔ CRITICAL RULE - READ THIS CAREFULLY:**

```
IF (multiple_variants_found == TRUE) AND (user_provided_sizing_constraint == FALSE):
    → You are STRICTLY FORBIDDEN from selecting ANY specific variant
    → You are STRICTLY FORBIDDEN from assuming a "standard" or "default" size
    → You are STRICTLY FORBIDDEN from recommending based on "typical" or "common" usage
    → You MUST set response_type = "CLARIFICATION_NEEDED"
    → You MUST ask for the attribute that varies most (size, capacity, airflow, etc.)
```

**FORBIDDEN BEHAVIORS:**
- ❌ "The GDB-600x600 is the standard choice..." - FORBIDDEN
- ❌ "For a typical office, I recommend..." - FORBIDDEN
- ❌ "The most common variant is..." - FORBIDDEN
- ❌ Providing a product_card/entity_card when multiple variants exist - FORBIDDEN

**REQUIRED BEHAVIOR:**
- ✅ "I found multiple GDB variants with different capacities. To select the correct size, I need to know..."
- ✅ Set clarification_needed: true
- ✅ Provide options from the actual graph data

#### EXAMPLE SCENARIOS:

**Scenario A - MUST ASK CLARIFICATION:**
- User: "Select a GDB housing for an office"
- Graph returns: GDB-300x300 (850 m³/h), GDB-600x600 (3400 m³/h), GDB-900x600 (5000 m³/h)
- User constraint: NONE (just "office" context)
- ACTION: Return CLARIFICATION_NEEDED, ask for required airflow

**Scenario B - CAN PROCEED:**
- User: "Select a GDB housing for 3000 m³/h"
- Graph returns: GDB-300x300 (850 m³/h), GDB-600x600 (3400 m³/h)
- User constraint: 3000 m³/h
- ACTION: Can filter to GDB-600x600 (meets requirement), proceed with recommendation

### 3. ⚖️ GRADE GAP ANALYSIS (Critical Risk Detection)

**THIS IS YOUR MOST IMPORTANT SAFETY CHECK. You are the last line of defense against engineering mistakes.**

#### STEP 1: ASSESS APPLICATION CRITICALITY (User Context)

Use your GENERAL KNOWLEDGE to classify the user's application:

**🔴 HIGH CRITICALITY (Strict Requirements):**
- Medical / Hospital / Healthcare
- Marine / Offshore / Ship
- Aerospace / Aviation
- Cleanroom / Semiconductor
- Chemical Processing / Hazardous
- Explosive environments (ATEX zones)
- Food Processing / Pharmaceutical
- Nuclear / High-Security

**🟡 MEDIUM CRITICALITY:**
- Industrial manufacturing
- Commercial kitchens
- Swimming pools / Humid environments
- Outdoor installations
- Data centers

**🟢 LOW CRITICALITY (Standard Requirements):**
- Office buildings
- Warehouses
- General ventilation
- Temporary installations
- Residential

#### STEP 2: ASSESS PRODUCT GRADE (Graph Data)

Look at the retrieved product's attributes:

**Economy/Standard Grade indicators:**
- Galvanized Steel (FZ) - Corrosion Class C3
- Basic/Uncoated materials
- Single-wall construction
- No special certifications
- Standard filtration (G4, M5)

**Premium/Specialized Grade indicators:**
- Stainless Steel (RF/SF) - Corrosion Class C5
- Zinc-Magnesium (ZM) coatings
- Double-wall insulation
- VDI 6022 / Cleanroom certified
- HEPA-ready / ATEX certified
- Food-grade / Medical-grade

#### STEP 3: CALCULATE THE GAP & DETERMINE SEVERITY

```
IF Application is [HIGH CRITICALITY] AND Product is [ECONOMY GRADE]:
    → risk_severity: "CRITICAL"
    → The product is FUNDAMENTALLY UNSUITABLE for the environment
    → You MUST actively BLOCK/DISSUADE, not just "suggest"

IF Application is [HIGH CRITICALITY] AND Product is [MEDIUM GRADE]:
    → risk_severity: "WARNING"
    → Potential issues, user must verify compliance

IF Application is [MEDIUM CRITICALITY] AND Product is [ECONOMY GRADE]:
    → risk_severity: "WARNING"
    → Recommend upgrade but not critical

OTHERWISE:
    → risk_severity: "INFO" or null
    → Standard recommendation proceeds
```

#### STEP 4: CRITICAL RISK RESPONSE FORMAT

**When risk_severity == "CRITICAL":**

1. **Set flags:**
   ```json
   "risk_detected": true,
   "risk_severity": "CRITICAL",
   ```

2. **Use BLOCKING language in content_segments:**
   - ❌ WRONG: "Please note that..." / "You may want to consider..."
   - ✅ CORRECT: "**⛔ TECHNICALLY UNSUITABLE:** Standard galvanized steel is NOT appropriate for hospital environments."

3. **Explain the PHYSICAL reason:**
   ```
   "Standard FZ material (C3 corrosion class) cannot withstand:
   • Frequent chemical disinfection required in medical settings
   • VDI 6022 hygiene compliance for healthcare HVAC
   • The aggressive cleaning agents used in hospitals"
   ```

4. **Provide MANDATORY alternative:**
   ```
   "**Required specification:** RF (Stainless Steel) with C5 corrosion protection
   or SF (Stainless Steel 316L) for maximum chemical resistance."
   ```

5. **Add to policy_warnings:**
   ```json
   "policy_warnings": ["CRITICAL: Economy-grade product requested for high-criticality application. Standard galvanized steel is technically unsuitable for hospital environments due to hygiene and corrosion requirements."]
   ```

#### STEP 5: GRADE GAP IN CLARIFICATION MODE

**CRITICAL:** Even when asking for clarification (missing size/airflow), if you detect a Grade Gap, you MUST include a warning:

```json
{{
  "response_type": "CLARIFICATION_NEEDED",
  "risk_detected": true,
  "risk_severity": "WARNING",
  "content_segments": [
    {{"text": "**⚠️ Material Consideration:** For hospital environments, ", "type": "GENERAL"}},
    {{"text": "standard galvanized steel (FZ) is typically unsuitable due to hygiene requirements", "type": "INFERENCE", "inference_logic": "Medical environments require materials that withstand chemical disinfection per VDI 6022"}},
    {{"text": ". I recommend specifying **RF (Stainless Steel)** material.\n\n", "type": "GENERAL"}},
    {{"text": "To select the correct size, please provide the required airflow.", "type": "GENERAL"}}
  ],
  "clarification": {{...}}
}}
```

#### EXAMPLE SCENARIOS:

**Scenario A - CRITICAL BLOCK:**
- User: "Standard galvanized housing for a hospital ventilation system"
- Product: GDB with FZ material (C3)
- Application: Hospital = HIGH CRITICALITY
- Gap: ECONOMY product for HIGH CRITICALITY = **CRITICAL**
- Response: "⛔ TECHNICALLY UNSUITABLE: Standard galvanized steel cannot meet hospital hygiene requirements..."

**Scenario B - WARNING:**
- User: "GDB housing for a commercial kitchen"
- Product: GDB with FZ material (C3)
- Application: Commercial kitchen = MEDIUM CRITICALITY (humidity, grease)
- Gap: ECONOMY for MEDIUM = **WARNING**
- Response: "⚠️ For commercial kitchen environments with high humidity and grease exposure, consider upgrading to ZM or RF material..."

**Scenario C - PROCEED:**
- User: "GDB housing for office ventilation"
- Product: GDB with FZ material (C3)
- Application: Office = LOW CRITICALITY
- Gap: None
- Response: Normal recommendation with FZ material

### 4. ❓ CLARIFICATION MODE WITH CONTEXTUAL IMPLICATION CHECK

**RULE: If graph data shows VARIANCE and user lacks CONSTRAINT - DON'T GUESS. ASK.**
**BUT: Use your reasoning to extract value from the context they DID provide!**

#### 🧠 CONTEXTUAL IMPLICATION CHECK (Pure Reasoning - No Hardcoded Rules)

When you identify that Attribute A is missing, PAUSE and perform this analysis:

**STEP 1: ANALYZE PROVIDED CONTEXT**
What DID the user tell you? Extract:
- Environment/Location (indoor, outdoor, industrial, medical, marine, etc.)
- Application/Process (ventilation, filtration, storage, transport, etc.)
- Goal/Outcome (safety, efficiency, compliance, cost, etc.)
- Any mentioned constraints or concerns

**STEP 2: USE YOUR GENERAL KNOWLEDGE TO INFER IMPLICATIONS**
Based on the context, what requirements are TYPICALLY implied?

Think through these reasoning chains (examples - apply to ANY domain):
- "Medical/Hospital" → Hygiene critical → Materials must withstand disinfection → Stainless steel preferred
- "Outdoor/Marine" → Weather exposure → Corrosion resistance needed → Check material rating
- "Food processing" → Contamination risk → Food-safe materials required → Verify certifications
- "High-temperature" → Thermal stress → Check material temperature limits
- "Chemical environment" → Reactivity risk → Verify chemical compatibility
- "Public space" → Safety regulations → Check compliance requirements

**STEP 3: CHECK RETRIEVED DATA AGAINST IMPLIED REQUIREMENTS**
Look at the graph data for the product family:
- What is the DEFAULT/STANDARD configuration?
- Does it meet the implied requirements from Step 2?
- Are there VARIANTS that better match the context?

**STEP 4: FORMULATE CONTEXT-AWARE RESPONSE**

Structure your clarification response as:

```
1. ACKNOWLEDGE: "For [context user provided]..."

2. CONTEXTUAL INSIGHT (from your reasoning):
   "Based on [environment/application], typical requirements include:
    - [Implied requirement 1] because [physical/chemical reason]
    - [Implied requirement 2] because [safety/regulatory reason]"

3. COMPATIBILITY NOTE (if relevant):
   "⚠️ Note: The standard [Product Family] uses [default attribute].
    For [user's context], verify if this meets your requirements,
    or consider [alternative] for [better protection/compliance]."

4. CLARIFICATION REQUEST:
   "To select the exact model, please provide: [missing attribute]"

5. OPTIONS from graph data
```

**GENERIC EXAMPLES:**

Example A - Marine Environment:
```
User: "I need a GDB housing for a ship engine room."
Missing: Size/Airflow
Your reasoning: "Ship engine room" → Marine environment → Salt spray, humidity, vibration
                → Corrosion class C5-M typically required → Check if standard material qualifies
Output: "For a marine engine room environment, corrosion resistance is critical due to
        salt spray and humidity. I recommend RF (Stainless Steel) material which offers
        C5 corrosion protection suitable for marine applications.
        ⚠️ Note: Verify vibration mounting requirements for engine room installation.
        To select the model: What is the required airflow capacity?"
```

Example B - Unknown Domain:
```
User: "I need equipment for a semiconductor cleanroom."
Missing: Specifications
Your reasoning: "Semiconductor cleanroom" → Ultra-low particle counts → ISO Class 4-5
                → Outgassing concerns → Special materials may be needed
Output: "For semiconductor cleanroom applications, I note that:
        - Particle generation must be minimized (typically ISO 14644 Class 4-5)
        - Material outgassing may be a concern for sensitive processes
        ⚠️ Note: Standard industrial equipment may not meet cleanroom particle specs.
        Please verify cleanroom classification requirements.
        To proceed: What ISO cleanliness class is required?"
```

**KEY PRINCIPLE:** Use YOUR pre-trained knowledge about physics, chemistry, industry standards,
and common sense to reason about implications. Do NOT rely on hardcoded domain rules.

When clarification is needed, include Guardian insights in content_segments:
```json
{{
  "response_type": "CLARIFICATION_NEEDED",
  "reasoning_summary": [
    {{"step": "Context Analysis", "icon": "🔍", "description": "User needs [X] for [environment]..."}},
    {{"step": "Guardian Insight", "icon": "🛡️", "description": "For [environment], recommend [material/feature] because [reason]..."}},
    {{"step": "Variance Detected", "icon": "🛑", "description": "Multiple sizes available, user must specify..."}}
  ],
  "content_segments": [
    {{"text": "For a Hospital environment, ", "type": "GENERAL"}},
    {{"text": "I recommend Stainless Steel (RF) material due to high hygiene requirements and chemical cleaning resistance", "type": "INFERENCE", "inference_logic": "Hospitals require materials that withstand frequent disinfection and meet hygiene standards"}},
    {{"text": ". ", "type": "GENERAL"}},
    {{"text": "RF material offers C5 corrosion class protection", "type": "GRAPH_FACT", "source_id": "RF", "source_text": "Material: RF", "node_type": "Material", "evidence_snippet": "Stainless steel - corrosion class C5", "key_specs": {{"Material": "RF", "Corrosion": "C5"}}}},
    {{"text": ".\n\nTo select the exact model, I need additional information. ", "type": "GENERAL"}}
  ],
  "clarification_data": {{
    "missing_attribute": "airflow_m3h",
    "why_needed": "Multiple housing sizes available with different capacities",
    "options": [{{"value": "2000", "description": "Small installation"}}, {{"value": "5000", "description": "Large installation"}}],
    "question": "What is the required airflow capacity (m³/h)?"
  }}
}}
```

**CRITICAL**:
- When `response_type: "CLARIFICATION_NEEDED"`, do NOT include `entity_card`
- BUT DO include valuable Guardian insights in `content_segments` based on context provided

### 4.0.1 📚 KNOWLEDGE SHARING PROTOCOL (Verified Rules First)

**RULE: ALWAYS display verified engineering rules BEFORE asking clarification questions.**

When you have LEARNED RULES from the knowledge base that match the user's query context,
you MUST include them in `content_segments` FIRST, even if you still need to ask for clarification.

**WHY:** Users benefit from knowing relevant technical constraints upfront. This builds trust
and helps them provide better answers to your clarification questions.

**FORMAT:**
```
"Before selecting equipment, important technical note from knowledge base: [Insert Rule Here]."
```

**IMPLEMENTATION:**
```json
{{
  "response_type": "CLARIFICATION_NEEDED",
  "content_segments": [
    {{
      "text": "Before selecting equipment, important technical note from knowledge base: [RULE TEXT FROM LEARNED RULES].",
      "type": "GRAPH_FACT",
      "source_id": "learned_rule",
      "node_type": "LearnedRule",
      "evidence_snippet": "[RULE TEXT]"
    }},
    {{"text": "\n\n", "type": "GENERAL"}},
    {{"text": "To select the appropriate model, I need additional information.", "type": "GENERAL"}}
  ],
  "clarification_data": {{...}}
}}
```

**CRITICAL BEHAVIOR:**
1. CHECK: Look at the LEARNED_RULES section in the context below
2. IF rules exist that match the user's query topic:
   - ADD them as the FIRST content_segment with type "GRAPH_FACT" (green highlighting)
   - THEN proceed with your clarification question
3. Tag as "GRAPH_FACT" because these are VERIFIED rules from the knowledge base, not inferences
4. The green color signals to the user: "This is confirmed knowledge, not AI speculation"

**EXAMPLE - Clarification WITH Learned Rule:**
User asks: "I need a filter for a powder coating facility"
Learned Rule exists: "Powder coating facility requires F9 class filters"

CORRECT response:
```json
{{
  "response_type": "CLARIFICATION_NEEDED",
  "content_segments": [
    {{"text": "Before selecting equipment, important technical note from knowledge base: Powder coating facility requires F9 class filters.", "type": "GRAPH_FACT", "source_id": "learned_rule", "node_type": "LearnedRule", "evidence_snippet": "Powder coating facility requires F9 class filters"}},
    {{"text": "\n\nTo select the appropriate filter model, I need additional information.", "type": "GENERAL"}}
  ],
  "clarification_data": {{
    "question": "Jaki jest wymagany przepływ powietrza (m³/h)?",
    ...
  }}
}}
```

### 4.1 🔄 CONTEXT UPDATE HANDLING (Clarification Follow-up)

When a user previously asked a question and received a clarification request, their follow-up
will contain a "Context Update:" marker that merges the original query with the new information.

**INPUT FORMAT:**
```
[Original Query]. Context Update: [Attribute] is [Value].
```

**EXAMPLE:**
```
User message: "Select a GDB housing for an office. Context Update: Airflow is 3400 m3/h."
```

**HOW TO PROCESS:**
1. RECOGNIZE: This is a follow-up to a clarification request
2. EXTRACT: Original query = "Select a GDB housing for an office"
3. EXTRACT: Context update = Airflow constraint of 3400 m³/h
4. MERGE: Treat this as a FULLY SPECIFIED query with all context combined
5. PROCEED: Skip the Ambiguity Gatekeeper (user has now provided the missing constraint)

**IMPORTANT:**
- When you see "Context Update:", this REPLACES the clarification flow
- The user HAS now provided the missing parameter
- You should now proceed to filter entities and make a recommendation
- Do NOT ask for clarification on the attribute that was just provided

### 4.2 ✅ RISK RESOLUTION CHECK (Stop Repetitive Warnings)

Before writing the final response, perform this check:

**QUESTION:** Did you (or a prior turn) flag a risk (e.g., "galvanized steel in a hospital")?
**IF YES:** Does your FINAL RECOMMENDATION already solve that risk?

```
IF the recommended product/material MITIGATES the previously detected risk:
    → Set risk_detected: false
    → Set risk_resolved: true
    → DO NOT repeat the warning text
    → INSTEAD, frame as POSITIVE REINFORCEMENT:
      ❌ BAD: "⚠️ Warning: Galvanized steel is unsuitable for hospitals..."
      ✅ GOOD: "✅ The selected RF (Stainless Steel) material ensures full compliance
               with hospital hygiene standards (VDI 6022), including resistance to
               chemical disinfection agents."

IF the risk is NOT mitigated (user insisted on economy product):
    → Keep risk_detected: true
    → Keep risk_severity as before
    → Repeat the warning
```

**TONE SHIFT when risk is resolved:**
- Use "ensures compliance" instead of "warning: does not comply"
- Use "provides protection against" instead of "is vulnerable to"
- Use "meets requirements for" instead of "fails to meet"
- Add a ✅ checkmark before compliance statements

**EXAMPLE - Risk Resolved:**
```json
{{
  "risk_detected": false,
  "risk_resolved": true,
  "content_segments": [
    {{"text": "**Recommendation:** The GDB-600x600 with RF material is the ideal choice.\n\n", "type": "GENERAL"}},
    {{"text": "✅ **Compliance:** RF (Stainless Steel) ensures full VDI 6022 hygiene compliance for hospital environments", "type": "INFERENCE", "inference_logic": "Stainless steel withstands chemical disinfection and meets medical facility requirements"}},
    {{"text": ".\n\n", "type": "GENERAL"}}
  ]
}}
```

### 4.3 🔗 PROTECTION DEPENDENCY CHECK (Process Logic)

**THIS IS A CRITICAL SAFETY CHECK FOR SENSITIVE COMPONENTS.**

#### STEP 1: IDENTIFY SENSITIVE DOWNSTREAM COMPONENTS

Use your GENERAL KNOWLEDGE to identify if the requested product is a **sensitive component**
that requires upstream protection:

**🔴 SENSITIVE COMPONENTS (Require Protection):**
- **Activated Carbon filters** - Porous media destroyed by particulate contamination
- **HEPA/ULPA filters** - Fine media clogged instantly by coarse dust
- **Precision instruments** - Sensors, gauges damaged by debris
- **Electronic components** - Circuit boards damaged by particles/moisture
- **Catalytic elements** - Catalysts poisoned by contaminants
- **Membrane filters** - Fine membranes destroyed by particulates
- **UV lamps** - Effectiveness blocked by dust coating

#### STEP 2: CHECK FOR PROTECTION REMOVAL

Scan the user's request for indicators of **removed upstream protection**:

**🚩 DANGER PHRASES:**
- "without pre-filter" / "bez filtra wstępnego"
- "direct from outside" / "bezpośrednio z zewnątrz"
- "remove the G4" / "usuń filtr G4"
- "skip pre-filtration" / "pomiń wstępną filtrację"
- "raw air" / "surowe powietrze"
- "fresh air only" / "tylko świeże powietrze"
- "single-stage filtration" with sensitive component

#### STEP 3: EXECUTE PROTECTION LOGIC

```
IF (requested_product IS sensitive_component) AND (protection_removed OR missing):
    → risk_severity: "CRITICAL"
    → response_type: "RECOMMENDATION" (but with HARD WARNING)
    → risk_detected: true
    → You MUST actively BLOCK or strongly DISSUADE
    → Explain the PHYSICAL mechanism of destruction (not just "wear")
```

#### STEP 4: RESPONSE FORMAT FOR PROTECTION VIOLATIONS

```json
{{
  "response_type": "RECOMMENDATION",
  "risk_detected": true,
  "risk_severity": "CRITICAL",
  "reasoning_summary": [
    {{"step": "Protection Analysis", "icon": "🔗", "description": "Identified Carbon filter as sensitive component requiring pre-filtration"}},
    {{"step": "CRITICAL: Protection Removed", "icon": "⛔", "description": "User requested Carbon on fresh air without pre-filter - this will destroy the media"}}
  ],
  "content_segments": [
    {{"text": "⛔ **KRYTYCZNE OSTRZEŻENIE:** ", "type": "GENERAL"}},
    {{"text": "Using a carbon filter directly on fresh air (without a pre-filter) will cause immediate clogging and destruction of the carbon medium. This is not a matter of shortened lifespan - the pores of activated carbon will be blocked by dust within hours, not months.", "type": "INFERENCE", "inference_logic": "Activated carbon has microscopic pores (0.5-5 nanometers) that trap gas molecules. Airborne particulates (10-100+ micrometers) physically block these pores, destroying adsorption capacity permanently."}},
    {{"text": "\n\n**Required configuration:** A pre-filter of minimum G4 class (preferably M5) MUST be installed before the carbon filter.\n\n", "type": "GENERAL"}}
  ],
  "policy_warnings": ["CRITICAL: Carbon filter requested without mandatory pre-filtration. This configuration will destroy the expensive carbon media within hours of operation."]
}}
```

#### GENERIC EXAMPLES:

**Example A - Carbon on Fresh Air (BLOCK):**
- User: "Potrzebuję filtra węglowego na powietrze świeże, bez prefiltra"
- Analysis: Carbon = SENSITIVE, Pre-filter = REMOVED
- Action: ⛔ HARD REJECT with physical explanation
- Key physics: "Pores of activated carbon (nanometer scale) will be permanently blocked by dust particles (micrometer scale)"

**Example B - HEPA without Pre-filter (BLOCK):**
- User: "Install HEPA filter directly on outdoor air intake"
- Analysis: HEPA = SENSITIVE, Pre-filter = MISSING (outdoor air)
- Action: ⛔ HARD REJECT
- Key physics: "HEPA media (0.3 micron rating) will be destroyed by coarse dust within days"

**Example C - Carbon with Pre-filter (PROCEED):**
- User: "Potrzebuję filtra węglowego po filtrze M5"
- Analysis: Carbon = SENSITIVE, Pre-filter = PRESENT (M5)
- Action: ✅ PROCEED with recommendation

**WHY THIS MATTERS:** Users often don't understand that removing "unnecessary" filters
doesn't just reduce efficiency - it causes catastrophic, irreversible damage to sensitive
downstream components. Your job is to PROTECT them from this mistake.

### 5. REASONING (reasoning_summary)
Summarize the decision process in 3-6 steps (use only relevant ones):
- 🔍 **Intent Analysis**: What does the user REALLY need?
- 🔒 **Context Lock**: Which entity is active? (when user references "this", "it", etc.)
- 🧪 **Physical Requirements**: What conditions must the solution meet?
- 📐 **Constraint Check**: Mathematical verification (when numeric limits provided)
- 🛡️ **Gap Analysis Verification**: Does the product meet requirements?
- ⚠️ **Conflict** (if detected): What is the PHYSICAL cause?
- ✅ **Recommendation**: What do you recommend and why?

### 6. CONTENT SEGMENTS (content_segments)
Split the answer into segments with PRECISE ATTRIBUTION:

- **GRAPH_FACT** (🟢 Green): Specific fact from Knowledge Graph (specification, dimension, material).
  REQUIRED FIELDS:
  - `source_id`: Node ID/name in the knowledge graph (e.g., "GDC-600x600", "RF-material")
  - `source_text`: Brief label (e.g., "Product: GDC-600x600")
  - `node_type`: Type of graph node ("ProductVariant", "Material", "FilterCartridge", "Case")
  - `evidence_snippet`: The EXACT text/description from the graph data that proves this fact (copy the relevant property value)
  - `key_specs`: Dictionary of relevant specs from the node (e.g., {{"Dimensions": "600x600mm", "Corrosion Class": "C5"}})
  - `source_document`: Document name if known (optional)
  - `page_number`: Page number if known (optional)

- **INFERENCE** (🟡 Yellow): Conclusion from YOUR GENERAL KNOWLEDGE (physics, chemistry, logic).
  REQUIRES: `inference_logic` (explanation of PHYSICAL/CHEMICAL reasoning)

- **GENERAL**: Connecting/formatting text without special attribution.

### ⚠️ 6.1 INFERENCE TAGGING RULE (STRICT - "Yellow Mandate")

**ANY sentence where you explain a CAUSE-AND-EFFECT relationship or PHYSICAL CONSEQUENCE
that is NOT explicitly written in the source documents MUST be tagged as type: "INFERENCE".**

#### TRIGGER PATTERNS (Must use INFERENCE):

1. **Cause-and-Effect:**
   - "Doing X will cause Y"
   - "Because of X, Y happens"
   - "X leads to Y"
   - "Without X, Y will fail"

2. **Physical/Chemical Consequences:**
   - "Dust will clog the pores"
   - "Corrosion will occur"
   - "Temperature will damage..."
   - "Particles will block..."

3. **Logical Deductions:**
   - "Therefore, X is unsuitable"
   - "This means Y is required"
   - "Given X, Y follows"

4. **Risk/Failure Predictions:**
   - "This will destroy..."
   - "This will reduce lifespan..."
   - "This causes premature failure..."

#### EXAMPLES:

**✅ CORRECT - Tagged as INFERENCE:**
```json
{{"text": "Dust will clog the activated carbon pores within hours, destroying adsorption capacity",
  "type": "INFERENCE",
  "inference_logic": "Activated carbon pores (nanometer scale) are blocked by dust particles (micrometer scale)"}}
```

**❌ WRONG - Tagged as GENERAL (loses yellow highlight):**
```json
{{"text": "Dust will clog the activated carbon pores within hours, destroying adsorption capacity",
  "type": "GENERAL"}}
```

**✅ CORRECT - Plain fact as GRAPH_FACT:**
```json
{{"text": "Obudowa ma wymiary 600×600 mm",
  "type": "GRAPH_FACT",
  "source_id": "GDB-600x600", ...}}
```

**✅ CORRECT - Simple connector as GENERAL:**
```json
{{"text": "In summary: ", "type": "GENERAL"}}
```

#### WHY THIS MATTERS:

The Yellow Dashed Underline (INFERENCE) in the UI signals to users:
"This is my professional reasoning, not a verified fact from the database."

When you fail to tag cause-and-effect as INFERENCE:
- The reasoning appears as plain text (no highlight)
- Users cannot distinguish AI logic from verified data
- The Explainable AI feature is defeated

**RULE: When in doubt, use INFERENCE. It's better to over-explain than to hide your reasoning.**

**⚠️ CRITICAL FORMATTING RULES - DO NOT OUTPUT WALL OF TEXT:**

You MUST structure the answer for readability. DO NOT output a single dense paragraph.

**REQUIRED STRUCTURE:**

1. **Start with Direct Recommendation** (1-2 sentences max):
   ```
   {{"text": "**Recommendation:** The GDB-600x600 is the optimal choice for your requirements.\n\n", "type": "GENERAL"}}
   ```

2. **Use Section Headers** for organization:
   ```
   {{"text": "**Key Specifications:**\n", "type": "GENERAL"}}
   ```

3. **Use Bullet Points** for lists (prefix with `• ` or `- `):
   ```
   {{"text": "• Airflow capacity: ", "type": "GENERAL"}},
   {{"text": "3400 m³/h", "type": "GRAPH_FACT", ...}},
   {{"text": "\n• Dimensions: ", "type": "GENERAL"}},
   {{"text": "600×600 mm", "type": "GRAPH_FACT", ...}}
   ```

4. **Add Line Breaks** between logical sections using `\n\n`:
   - After the recommendation
   - Before each new section header
   - Between bullet point groups

**EXAMPLE PROPERLY FORMATTED RESPONSE:**
```json
"content_segments": [
  {{"text": "**Recommendation:** The GDB-600x600 housing is suitable for your office ventilation requirements.\n\n", "type": "GENERAL"}},
  {{"text": "**Why this model:**\n", "type": "GENERAL"}},
  {{"text": "• Airflow capacity of ", "type": "GENERAL"}},
  {{"text": "3400 m³/h meets your requirement", "type": "GRAPH_FACT", "source_id": "GDB-600x600", ...}},
  {{"text": "\n• ", "type": "GENERAL"}},
  {{"text": "Standard FZ material is sufficient for indoor office use", "type": "INFERENCE", "inference_logic": "Office environments have normal humidity and no corrosive agents"}},
  {{"text": "\n\n**Installation Notes:**\n", "type": "GENERAL"}},
  {{"text": "• Ensure adequate ceiling clearance for the 600mm depth\n", "type": "GENERAL"}},
  {{"text": "• Standard duct connections available\n", "type": "GENERAL"}}
]
```

**FORBIDDEN:**
- ❌ Single paragraph with all information crammed together
- ❌ Missing line breaks between sections
- ❌ Inline lists without bullet points
- ❌ Starting without a clear recommendation
- ❌ Section headers (like "Additional Considerations:") appearing inline with previous content - ALWAYS put `\n\n` before headers

### 7. PRODUCT CARD (product_card)
If recommending a product, fill out the card with specifications.
If `risk_detected: true`, the `warning` field is MANDATORY.

### 8. SIZING (MATHEMATICAL)
If user provides a numeric value (airflow, dimension, pressure), you MUST mathematically verify that the product meets the requirement.
This is a hard mathematical rule.

{active_policies}

## OUTPUT SCHEMA (STRICT JSON)
```json
{{
  "response_type": "FINAL_ANSWER" | "CLARIFICATION_NEEDED",
  "reasoning_summary": [
    {{"step": "Analysis", "icon": "🔍", "description": "Synthesized logic in English..."}},
    {{"step": "Context Lock", "icon": "🔒", "description": "Active entity: [name]. Searching within scope..."}},
    {{"step": "Gatekeeper", "icon": "🛑", "description": "Variance check: [result]..."}},
    {{"step": "Constraint Check", "icon": "📐", "description": "Base (X) + Option (Y) = Z. [PASS/FAIL] vs limit (W)."}},
    {{"step": "Verification", "icon": "🛡️", "description": "Gap analysis result..."}}
  ],
  "content_segments": [
    {{"text": "Normal text... ", "type": "GENERAL"}},
    {{"text": "Inferred requirement... ", "type": "INFERENCE", "inference_logic": "Physical reasoning"}},
    {{
      "text": "Graph fact... ",
      "type": "GRAPH_FACT",
      "source_id": "Node-ID",
      "source_text": "Entity name",
      "node_type": "EntityType",
      "evidence_snippet": "Raw text from source",
      "key_specs": {{"key": "value"}}
    }}
  ],
  "clarification_data": {{
    "missing_attribute": "Attribute name that varies in graph",
    "why_needed": "Why this is required",
    "options": [{{"value": "Option", "description": "Context"}}],
    "question": "Question for user"
  }},
  "entity_card": {{
    "title": "Entity name",
    "specs": {{"Key": "Value"}},
    "warning": "Warning if risk_detected",
    "confidence": "high|medium|low",
    "actions": ["Action 1"]
  }},
  "risk_detected": false,
  "policy_warnings": []
}}
```

**CRITICAL RULES:**
- When response_type = "CLARIFICATION_NEEDED": include clarification_data, NO entity_card
- When response_type = "FINAL_ANSWER": include entity_card (optional), NO clarification_data
- Always add SPACE between segments
"""

DEEP_EXPLAINABLE_SYNTHESIS_PROMPT = """## SOLUTION SPACE: KNOWLEDGE GRAPH DATA (verified)

{context}

## PROBLEM SPACE: USER QUERY
{query}

## ACTIVE CONSTRAINTS
{policies}

## ⛔ MANDATORY FIRST CHECK: VARIANCE DETECTION

**BEFORE DOING ANYTHING ELSE, ANSWER THESE QUESTIONS:**

1. How many different product variants are in the graph data above?
2. Do they have DIFFERENT values for size, capacity, airflow, or other key attributes?
3. Did the user provide a SPECIFIC NUMBER to filter down to one variant?

**IF you found multiple variants AND user provided NO sizing number:**
```
→ STOP. Do not proceed to recommendation.
→ Set response_type: "CLARIFICATION_NEEDED"
→ Ask what capacity/size/airflow is needed
→ Provide the options you found in the graph
```

**FORBIDDEN:** Selecting a "standard" variant when multiple exist without user constraint.

---

## EXECUTION PROTOCOL - STEP BY STEP

### STEP 1: AMBIGUITY GATEKEEPER (already done above)
Confirm: Did you pass the variance check? If not, proceed to CONTEXTUAL IMPLICATION CHECK.

### STEP 1b: CONTEXTUAL IMPLICATION CHECK (if clarification needed)
Before asking your clarification question, REASON about the context:

1. What environment/application did the user mention?
2. What does YOUR KNOWLEDGE tell you about typical requirements for that context?
   - Physical requirements (temperature, pressure, humidity, vibration)
   - Chemical requirements (corrosion, reactivity, contamination)
   - Regulatory requirements (safety, hygiene, certifications)
3. Does the standard product configuration meet these implied requirements?
4. Include this reasoning in your response BEFORE asking for the missing parameter.

Example reasoning chain:
- User says "chemical plant" → I know chemical plants have corrosive atmospheres
- Standard material may not resist chemicals → Should mention material consideration
- User says "outdoor Norway" → I know Nordic climate = freeze-thaw cycles, snow loads
- Should mention weather protection and insulation considerations

### STEP 1c: 🔒 CONTEXT PERSISTENCE PROTOCOL (Active Entity Lock)

**TRIGGER:** User uses pronouns or references like "this", "it", "the current", "my selection",
"the one I chose", "add to this", etc.

**PROTOCOL:**
1. **IDENTIFY ACTIVE ENTITY:** Look at conversation history. What entity (product, configuration,
   item) was the user discussing or selected in a previous turn?

2. **LOCK CONTEXT:** The Active Entity becomes the ONLY valid scope for the current query.
   - Store: Active_Entity_ID, Active_Entity_Type, Active_Entity_Family

3. **SCOPED SEARCH:** When user asks about features, options, accessories, or modifications:
   - ONLY search for items that have a direct relationship to Active Entity
   - Query pattern: (ActiveEntity)-[:HAS_OPTION|:COMPATIBLE_WITH|:ACCEPTS]->(RequestedItem)
   - Do NOT search globally across all entities

4. **NEGATIVE PATH HANDLING:**
   ```
   IF RequestedFeature NOT FOUND on Active Entity:
       → STATE CLEARLY: "[Feature] is not available for [Active Entity]."
       → LIST what IS available: "Available options for [Active Entity] are: [list]"
       → DO NOT silently switch to a different entity/product family
   ```

5. **PROHIBITION - CONTEXT DRIFT:**
   ```
   ⛔ FORBIDDEN: Finding the requested feature on Entity B (different family/type)
                and recommending Entity B without explicit user permission.

   ❌ BAD: User asks "Can I add X to this?" → X exists on Product B → Recommend Product B
   ✅ GOOD: User asks "Can I add X to this?" → X not on Active Entity →
            "X is not compatible with [Active Entity]. Would you like me to suggest
            an alternative product that supports X?"
   ```

**EXCEPTION:** You MAY suggest alternatives ONLY if:
- The Active Entity fundamentally cannot meet the user's core need (not just missing a feature)
- You explicitly ask: "Would you like me to find an alternative that supports [X]?"
- User explicitly says "find me something else" or "what alternatives exist"

---

### STEP 2: INTENT ANALYSIS
If no clarification needed, analyze the user's query:
- What is the user's GOAL?
- What is the ENVIRONMENT/CONTEXT?
- What EXPLICIT CONSTRAINTS were provided?

### STEP 3: INFER HIDDEN REQUIREMENTS
Based on your knowledge of physics, chemistry and engineering:
- What PHYSICAL CONDITIONS arise from the context?
- What CHEMICAL INTERACTIONS may occur?
- What OPERATING MECHANISM is needed?
- What SPECIFICATIONS are required?

### STEP 4: GAP ANALYSIS VERIFICATION
Compare requirements from Step 3 with Graph data:
- Does the entity have the MECHANISM that solves the problem?
- Is the MATERIAL compatible with the environment?
- Does the SPECIFICATION meet numerical requirements?
- If NO → set `risk_detected: true` and explain the PHYSICAL reason

### STEP 4b: 📐 PHYSICAL CONSTRAINT VALIDATOR (Mathematical Verification)

**TRIGGER:** User provides ANY numeric constraint:
- Dimensions: "max length 800mm", "must fit in 600x600", "clearance of 500mm"
- Weight: "max 50kg", "weight limit 100lbs"
- Power: "max 2kW", "circuit is 16A"
- Capacity: "minimum 3000 m³/h", "at least 500 liters"
- Any other measurable limit

**PROTOCOL:**

1. **EXTRACT USER LIMIT:**
   ```
   User_Limit = [numeric value from query]
   Limit_Type = [dimension/weight/power/capacity/etc.]
   Limit_Direction = [MAX (cannot exceed) | MIN (must meet or exceed)]
   ```

2. **RETRIEVE BASE VALUE:**
   ```
   Val_Base = Value of Limit_Type attribute from the Primary Entity
   Source: Graph Node property
   ```

3. **CALCULATE ADDITIONS (if accessories/options requested):**
   ```
   FOR EACH requested accessory/option:
       Val_Accessory = Value of Limit_Type from Accessory Node
       Additive? = Does this accessory ADD to the total?
                   (Length adds, Weight adds, some dimensions add)

   Val_Total = Val_Base + SUM(Val_Accessory) [if additive]
             = MAX(Val_Base, Val_Accessory) [if non-additive, e.g., footprint]
   ```

4. **VERIFY AGAINST LIMIT:**
   ```
   IF Limit_Direction == MAX:
       PASS:    Val_Total < User_Limit * 0.9  → "Fits comfortably"
       WARNING: Val_Total >= User_Limit * 0.9 AND Val_Total <= User_Limit → "Tight fit"
       FAIL:    Val_Total > User_Limit → "Exceeds limit - REJECT"

   IF Limit_Direction == MIN:
       PASS:    Val_Total >= User_Limit → "Meets requirement"
       FAIL:    Val_Total < User_Limit → "Below minimum - REJECT"
   ```

5. **OUTPUT IN REASONING:**
   ```json
   {{
     "step": "Constraint Check",
     "icon": "📐",
     "description": "Base (750mm) + Accessory (100mm) = 850mm. Exceeds max limit (800mm)."
   }}
   ```

6. **MANDATORY MATH DISPLAY:**
   When numeric constraints are involved, you MUST show the calculation in content_segments:
   ```json
   {{
     "text": "📐 **Dimension Check:** Base length (750mm) + mounting bracket (100mm) = 850mm total. ",
     "type": "GENERAL"
   }},
   {{
     "text": "This exceeds your maximum of 800mm by 50mm.",
     "type": "INFERENCE",
     "inference_logic": "Mathematical addition: 750 + 100 = 850 > 800"
   }}
   ```

**FAIL BEHAVIOR:**
- If constraint check FAILS → set `risk_detected: true`, `risk_severity: "CRITICAL"`
- State clearly: "Configuration exceeds [constraint] by [amount]"
- Suggest alternative: smaller base unit, different accessory, or configuration change

---

### STEP 5: BUILD RESPONSE
- Set `response_type: "FINAL_ANSWER"` or `"CLARIFICATION_NEEDED"`
- Split into segments: GRAPH_FACT, INFERENCE, GENERAL
- Reasoning in 3-5 steps in ENGLISH
- If conflict detected → clear warning + alternative

## FORMAT
- ALWAYS respond in ENGLISH
- Every fact from Graph = GRAPH_FACT with source_id, source_text, node_type, evidence_snippet, key_specs
- Physical/chemical conclusions = INFERENCE with inference_logic
- Connecting text = GENERAL
- DO NOT mix types in one segment

Return ONLY valid JSON. No markdown blocks."""


def query_deep_explainable(user_query: str) -> "DeepExplainableResponse":
    """Query with Deep Explainability - segmented content with full attribution.

    Returns structured JSON with:
    - reasoning_summary: High-level English reasoning timeline
    - content_segments: Answer broken into GRAPH_FACT/INFERENCE/GENERAL chunks
    - product_card: Structured product recommendation

    This is designed for the Enterprise UI with "Expert Mode" toggle.
    """
    from models import (
        DeepExplainableResponse, ReasoningSummaryStep, ContentSegment, ProductCard,
        ClarificationRequest, ClarificationOption
    )

    config = get_config()

    # Step 1: LLM Intent Detection
    intent = detect_intent(user_query)

    # Step 2: Embed the query
    query_embedding = generate_embedding(user_query)

    # Step 3: Hybrid retrieval
    retrieval_results = db.hybrid_retrieval(query_embedding, top_k=5, min_score=0.5)

    # Step 4: Search by project name if mentioned
    project_keywords = extract_project_keywords(user_query)
    for keyword in project_keywords:
        project_results = db.search_by_project_name(keyword)
        if project_results:
            retrieval_results = project_results + retrieval_results

    # Step 5: Configuration Graph search
    entity_codes = extract_entity_codes(user_query)
    config_results = {
        "variants": [],
        "cartridges": [],
        "filters": [],
        "materials": [],
        "option_matches": []
    }

    for code in entity_codes:
        exact_match = db.get_variant_by_name(code)
        if exact_match:
            config_results["variants"].append(exact_match)
        else:
            fuzzy_results = db.search_product_variants(code)
            for fr in fuzzy_results:
                if fr not in config_results["variants"]:
                    config_results["variants"].append(fr)

    # Search by configured keywords
    all_keywords = config.get_all_search_keywords()
    for kw in all_keywords:
        if kw.lower() in user_query.lower():
            general_config = db.configuration_graph_search(kw)
            for key in config_results.keys():
                for item in general_config.get(key, []):
                    if item not in config_results[key]:
                        config_results[key].append(item)

    # Step 6: GENERIC - Filter entities by numeric constraints
    rejected_entities = []
    filtering_note = ""

    # Apply filtering for each numeric constraint from intent
    for constraint in intent.numeric_constraints:
        value = constraint.get("value")
        unit = constraint.get("unit", "")
        context = constraint.get("context", "")

        if value and config_results.get("variants"):
            # Try to find matching attribute in entities
            for attr_name in ["capacity", "airflow_m3h", "max_flow", "rating", "size_mm", "weight_kg"]:
                sample = config_results["variants"][0] if config_results["variants"] else {}
                if attr_name in sample:
                    suitable, rejected = filter_entities_by_attribute(
                        config_results["variants"],
                        attr_name,
                        value,
                        comparison="gte"
                    )
                    config_results["variants"] = suitable
                    rejected_entities.extend(rejected)

                    if rejected:
                        rejected_names = [e.get('id', '?') for e in rejected]
                        filtering_note += f"\n⚠️ **FILTER**: Required {value} {unit}.\n"
                        filtering_note += f"REJECTED: {', '.join(rejected_names)}\n"
                    break

    # Step 6b: AMBIGUITY DETECTION - Analyze variance in retrieved entities
    variance_analysis = analyze_entity_variance(config_results.get("variants", []))
    variance_note = ""

    if variance_analysis["has_variance"] and not intent.has_specific_constraint:
        # User didn't provide constraint, but graph shows variance - this triggers clarification
        diff_attr = variance_analysis["suggested_differentiator"]
        values = variance_analysis["unique_values"].get(diff_attr, [])[:5]
        variance_note = f"\n\n🛑 **VARIANCE DETECTED**: Graph contains {len(config_results.get('variants', []))} variants.\n"
        variance_note += f"KEY DIFFERENTIATOR: '{diff_attr}' with values: {', '.join(str(v) for v in values)}\n"
        variance_note += "USER MUST SPECIFY: The user did not provide a constraint for this attribute.\n"

    # Step 7: Get similar cases
    similar_cases = db.get_similar_cases(query_embedding, top_k=3)

    # Step 8: GUARDIAN - Evaluate policies
    policy_results, policy_analysis = evaluate_policies(
        user_query, config_results, config
    )

    # Step 9: Format contexts
    config_context = format_configuration_context(config_results)
    graph_context = format_retrieval_context(retrieval_results, similar_cases, config_context)

    # Add variance analysis to context for LLM awareness
    if variance_note:
        graph_context = variance_note + graph_context

    if filtering_note:
        graph_context = filtering_note + graph_context

    # Step 9b: ACTIVE LEARNING - Semantic Query Expansion + Rule Injection
    # Extract standardized concepts for better rule matching
    search_concepts = extract_search_concepts(user_query)
    print(f"\n📚 [ACTIVE LEARNING] Search concepts extracted: {search_concepts}")

    if search_concepts:
        # Use expanded concept search for better synonym matching
        learned_rules_context = get_semantic_rules_expanded(search_concepts, user_query)
    else:
        # Fallback to direct embedding search
        learned_rules_context = get_semantic_rules(query_embedding, user_query)

    if learned_rules_context:
        print(f"📚 [ACTIVE LEARNING] Retrieved rules:\n{learned_rules_context}")
        print(f"🚨 DEBUG: Rules injected into prompt: {learned_rules_context}")
        graph_context = learned_rules_context + "\n" + graph_context
    else:
        print("📚 [ACTIVE LEARNING] No learned rules matched this query.")
        print("🚨 DEBUG: No rules to inject - LEARNED_RULES section will be empty")

    # Step 10: Build prompts
    active_policies_prompt = build_guardian_prompt(user_query, config)
    system_prompt = DEEP_EXPLAINABLE_SYSTEM_PROMPT.format(active_policies=active_policies_prompt)
    synthesis_prompt = DEEP_EXPLAINABLE_SYNTHESIS_PROMPT.format(
        context=graph_context,
        query=user_query,
        policies=policy_analysis
    )

    # Step 11: LLM synthesis
    response = client.models.generate_content(
        model=LLM_MODEL,
        contents=[
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=synthesis_prompt)]
            )
        ],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    # Step 12: Parse response
    def fix_json_control_chars(text: str) -> str:
        """Fix unescaped control characters in JSON strings."""
        import re
        # Replace literal newlines/tabs in strings with escaped versions
        # This regex finds strings and escapes control chars inside them
        def escape_control_chars_in_string(match):
            s = match.group(0)
            # Escape literal control characters
            s = s.replace('\n', '\\n')
            s = s.replace('\r', '\\r')
            s = s.replace('\t', '\\t')
            return s

        # Process string contents between quotes
        result = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', escape_control_chars_in_string, text)
        return result

    try:
        llm_response = json.loads(response.text)
    except json.JSONDecodeError as e:
        # Try fixing control characters
        try:
            fixed_text = fix_json_control_chars(response.text)
            llm_response = json.loads(fixed_text)
        except json.JSONDecodeError:
            # Try to find JSON object directly
            json_start = response.text.find('{')
            if json_start != -1:
                try:
                    fixed_text = fix_json_control_chars(response.text[json_start:])
                    llm_response = json.loads(fixed_text)
                except json.JSONDecodeError:
                    llm_response = None
            else:
                llm_response = None

            if llm_response is None:
                print(f"[ERROR] Failed to parse JSON: {str(e)}")
                print(f"[DEBUG] Raw response (first 500 chars): {response.text[:500]}")
                llm_response = {
                    "reasoning_summary": [
                        {"step": "Error", "icon": "❌", "description": f"Failed to parse response"}
                    ],
                    "content_segments": [
                        {"text": "I apologize, but I encountered an error processing this request. Please try again.", "type": "GENERAL"}
                    ],
                    "product_card": None,
                    "policy_warnings": []
                }

    # Step 13: Build response objects
    reasoning_steps = []
    for step_data in llm_response.get("reasoning_summary", []):
        reasoning_steps.append(ReasoningSummaryStep(
            step=step_data.get("step", ""),
            icon=step_data.get("icon", "🔍"),
            description=step_data.get("description", "")
        ))

    # Add programmatic steps for filtering
    if rejected_entities:
        reasoning_steps.insert(0, ReasoningSummaryStep(
            step="Filter Applied",
            icon="🔍",
            description=f"Filtered {len(rejected_entities)} entity(ies) based on numeric constraints"
        ))

    # Add variance detection step if applicable
    if variance_analysis["has_variance"] and not intent.has_specific_constraint:
        reasoning_steps.insert(0, ReasoningSummaryStep(
            step="Gatekeeper",
            icon="🛑",
            description=f"Variance detected in '{variance_analysis['suggested_differentiator']}' - clarification may be needed"
        ))

    content_segments = []
    graph_facts = 0
    inferences = 0

    for seg_data in llm_response.get("content_segments", []):
        seg_type = seg_data.get("type", "GENERAL")
        if seg_type == "GRAPH_FACT":
            graph_facts += 1
        elif seg_type == "INFERENCE":
            inferences += 1

        content_segments.append(ContentSegment(
            text=seg_data.get("text", ""),
            type=seg_type,
            inference_logic=seg_data.get("inference_logic"),
            source_id=seg_data.get("source_id"),
            source_text=seg_data.get("source_text"),
            # Rich evidence fields
            node_type=seg_data.get("node_type"),
            evidence_snippet=seg_data.get("evidence_snippet"),
            source_document=seg_data.get("source_document"),
            page_number=seg_data.get("page_number"),
            key_specs=seg_data.get("key_specs")
        ))

    product_card = None  # Will be set in clarification handling section below

    # Collect warnings
    warnings = llm_response.get("policy_warnings", [])
    for pr in policy_results:
        if not pr.passed and pr.message:
            warnings.append(pr.message)

    # Extract risk_detected flag and severity from LLM response (Autonomous Guardian)
    risk_detected = llm_response.get("risk_detected", False)
    risk_severity = llm_response.get("risk_severity", None)
    risk_resolved = llm_response.get("risk_resolved", False)

    # If risk was resolved by the recommendation, clear the risk flags
    if risk_resolved:
        risk_detected = False
        risk_severity = None

    # If LLM detected risk, ensure we have warnings
    if risk_detected and not warnings:
        if risk_severity == "CRITICAL":
            warnings.append("⛔ CRITICAL: Product is technically unsuitable for this application.")
        elif risk_severity == "WARNING":
            warnings.append("⚠️ WARNING: Review material/specification for this application.")
        else:
            warnings.append("Potential engineering risk detected - review recommendation details.")

    # Extract clarification fields (supports both old and new format)
    response_type = llm_response.get("response_type", "FINAL_ANSWER")
    clarification_needed = response_type == "CLARIFICATION_NEEDED" or llm_response.get("clarification_needed", False)
    clarification = None

    # Handle new format: clarification_data
    clar_data = llm_response.get("clarification_data") or llm_response.get("clarification")

    if clarification_needed and clar_data:
        clarification = ClarificationRequest(
            missing_info=clar_data.get("missing_attribute") or clar_data.get("missing_info", "Missing information"),
            why_needed=clar_data.get("why_needed", "Information required for proper selection"),
            options=[
                ClarificationOption(
                    value=opt.get("value", ""),
                    description=opt.get("description", "")
                )
                for opt in clar_data.get("options", [])
            ],
            question=clar_data.get("question", "Please provide additional information")
        )

    # Handle entity_card (new format) vs product_card (old format)
    entity_card_data = llm_response.get("entity_card") or llm_response.get("product_card")
    if entity_card_data and not clarification_needed:
        product_card = ProductCard(
            title=entity_card_data.get("title", ""),
            specs=entity_card_data.get("specs", {}),
            warning=entity_card_data.get("warning"),
            confidence=entity_card_data.get("confidence", "medium"),
            actions=entity_card_data.get("actions", ["Add to Quote"])
        )

    return DeepExplainableResponse(
        reasoning_summary=reasoning_steps,
        content_segments=content_segments,
        product_card=product_card,
        risk_detected=risk_detected,
        risk_severity=risk_severity,
        risk_resolved=risk_resolved,
        clarification_needed=clarification_needed,
        clarification=clarification,
        query_language=intent.language,
        confidence_level="high" if config_results.get("variants") else "medium",
        policy_warnings=warnings,
        graph_facts_count=graph_facts,
        inference_count=inferences
    )


# Backwards compatibility exports
def extract_product_codes(query: str) -> list[str]:
    """Legacy name for extract_entity_codes."""
    return extract_entity_codes(query)
