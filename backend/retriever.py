"""Domain-Agnostic GraphRAG Reasoning Engine.

This module implements a generic Hybrid Retrieval system with a Guardian
reasoning layer. All domain-specific logic is loaded from configuration.

The code contains NO hardcoded domain terms - it works with any domain
by loading the appropriate configuration file.
"""

import os
import re
import json
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

from dotenv import load_dotenv

from database import db
from embeddings import generate_embedding
from config_loader import get_config, reload_config, DomainConfig
from models import (
    ConsultResponse, StructuredResponse, GraphEvidence, PolicyCheckResult,
    ExplainableResponse, ReferenceDetail, ReasoningStep
)
from logic.graph_reasoning import GraphReasoningEngine
from logic.session_graph import _derive_housing_length
from logic.scribe import (
    extract_semantic_intent,
    resolve_derived_actions,
    SemanticIntent,
)
from logic.state import (
    TechnicalState,
    TagSpecification,
    extract_tags_from_query,
    extract_material_from_query,
    extract_project_from_query,
    extract_accessories_from_query,
)

load_dotenv(dotenv_path="../.env")

from llm_router import llm_call, DEFAULT_MODEL
LLM_MODEL = DEFAULT_MODEL


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


def detect_intent_fast(query: str) -> QueryIntent:
    """FALLBACK: Regex-based intent detection. Only called when Scribe LLM
    fails or for fields Scribe didn't extract. Scribe is the primary extractor (v4.0).
    """
    query_lower = query.lower()

    # 1. Detect language
    language = _detect_language_fallback(query)

    # 2. Extract product codes (from config product families)
    _cfg = get_config()
    _families_re = "|".join(re.escape(f) for f in _cfg.product_families) if _cfg.product_families else ""
    if _families_re:
        product_pattern = r'\b(' + _families_re + r')[-\s]?(\d{2,4})?[xX]?(\d{2,4})?\b'
        product_matches = re.findall(product_pattern, query, re.IGNORECASE)
        entity_references = [m[0].upper() for m in product_matches] if product_matches else []
    else:
        entity_references = []

    # Also catch full product codes like "FAMILY-WxH-L"
    full_code_pattern = r'\b([A-Z]{2,4}-\d{2,4}[xX]\d{2,4}(?:-\d{2,4})?)\b'
    full_codes = re.findall(full_code_pattern, query, re.IGNORECASE)
    entity_references.extend([c.upper() for c in full_codes])
    entity_references = list(set(entity_references))  # dedupe

    # 3. Extract numeric constraints
    numeric_constraints = _extract_numeric_constraints_fallback(query)

    # 4. Detect application/environment keywords (from config)
    _app_kw = _cfg.fallback_application_keywords or {}
    context_keywords = []
    for app, keywords in _app_kw.items():
        if any(kw in query_lower for kw in keywords):
            context_keywords.append(app)

    # 5. Detect action intent
    if any(w in query_lower for w in ['compare', 'porównaj', 'vs', 'versus', 'difference']):
        action_intent = "compare"
    elif any(w in query_lower for w in ['configure', 'konfigur', 'setup', 'option']):
        action_intent = "configure"
    elif any(w in query_lower for w in ['problem', 'issue', 'nie działa', 'error', 'troubleshoot']):
        action_intent = "troubleshoot"
    elif entity_references or any(w in query_lower for w in ['recommend', 'suggest', 'need', 'potrzeb', 'want', 'chcę']):
        action_intent = "select"
    else:
        action_intent = "general_info"

    # 6. Check for specific constraints
    has_specific = bool(numeric_constraints) or "context update:" in query_lower

    return QueryIntent({
        "language": language,
        "numeric_constraints": numeric_constraints,
        "entity_references": entity_references,
        "action_intent": action_intent,
        "context_keywords": context_keywords,
        "has_specific_constraint": has_specific
    })


def detect_intent(query: str) -> QueryIntent:
    """FALLBACK: Regex-based intent detection. Scribe LLM is the primary extractor (v4.0).
    Only called when Scribe results need supplementing.
    """
    # Try fast detection first
    fast_intent = detect_intent_fast(query)

    # If we found products or clear application context, fast path is enough
    if fast_intent.entity_references or fast_intent.context_keywords:
        return fast_intent

    # For very short queries or greetings, fast path is enough
    if len(query.split()) < 4:
        return fast_intent

    # Only use LLM for truly ambiguous queries (rare case)
    # For now, just use fast path - LLM fallback disabled for performance
    return fast_intent

    # DISABLED: LLM fallback (uncomment if needed for complex queries)
    # try:
    #     response = client.models.generate_content(...)
    #     return QueryIntent(json.loads(response.text))
    # except:
    #     return fast_intent


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
# NUMERIC NORMALIZATION
# =============================================================================

def _normalize_numeric_string(text: str) -> str:
    """Normalize thousand-separated numbers for regex extraction.

    Handles comma separators (6,000), space separators (6 000),
    and dot separators used in some locales (6.000).

    Examples:
        "6,000 m³/h" → "6000 m³/h"
        "6 000 m³/h" → "6000 m³/h"
        "12,500"     → "12500"
        "600x600"    → "600x600" (unchanged — no separator pattern)
    """
    # Comma thousand separator: 6,000 or 12,500
    text = re.sub(r'(\d{1,3}),(\d{3})\b', r'\1\2', text)
    # Space thousand separator: 6 000 or 12 500
    text = re.sub(r'(\d{1,3})\s(\d{3})\b', r'\1\2', text)
    return text


# =============================================================================
# SEMANTIC SCRIBE — STATE MERGE HELPER (v3.0)
# =============================================================================


def _route_entity_from_config(entity, tag_ref, tag, state, routing_cfg):
    """Route ScribeEntity fields to tag/state using config-driven routing rules."""
    for rule in routing_cfg:
        ef = rule["entity_field"]
        rtype = rule["type"]
        entity_val = getattr(entity, ef, None)
        if entity_val is None:
            continue

        if rtype == "dimension_unpack":
            # entity.dimensions is a dict; unpack to tag fields via mapping
            skip_field = rule.get("skip_if_tag_has")
            if skip_field and getattr(tag, skip_field, None):
                continue
            mapping = rule.get("mapping", {})
            kwargs = {}
            for dim_key, target_field in mapping.items():
                v = entity_val.get(dim_key)
                if v is not None:
                    kwargs[target_field] = int(v)
            if kwargs:
                state.merge_tag(tag_ref, **kwargs)

        elif rtype == "tag_merge":
            target = rule["target"]
            skip_if_set = rule.get("skip_if_set", False)
            if skip_if_set and getattr(tag, target, None):
                continue
            state.merge_tag(tag_ref, **{target: entity_val})
            print(f"🧠 [SCRIBE] {ef}: {entity_val} on {tag_ref}")

        elif rtype == "state_action":
            action = rule["action"]
            if action == "lock_material":
                state.lock_material(entity_val)

        elif rtype == "resolved_param":
            param_key = rule["param_key"]
            # Check skip_if_entity_has (e.g., skip corrosion class if material set)
            skip_field = rule.get("skip_if_entity_has")
            if skip_field and getattr(entity, skip_field, None):
                continue
            state.resolved_params[param_key] = entity_val
            print(f"🧠 [SCRIBE] {param_key}: {entity_val}")


def _route_entity_legacy(entity, tag_ref, tag, state):
    """Route ScribeEntity fields to tag/state using legacy hardcoded mapping."""
    # Dimensions (only fill if structural regex didn't already extract)
    if entity.dimensions and not tag.housing_width:
        w = entity.dimensions.get("width")
        h = entity.dimensions.get("height")
        d = entity.dimensions.get("depth")
        kwargs = {}
        if w is not None:
            kwargs["filter_width"] = int(w)
        if h is not None:
            kwargs["filter_height"] = int(h)
        if d is not None:
            kwargs["filter_depth"] = int(d)
        if kwargs:
            state.merge_tag(tag_ref, **kwargs)

    # Airflow — Scribe is primary
    if entity.airflow_m3h and not tag.airflow_m3h:
        state.merge_tag(tag_ref, airflow_m3h=entity.airflow_m3h)

    # Product family — Scribe is primary (v3.1), always override
    if entity.product_family:
        state.merge_tag(tag_ref, product_family=entity.product_family)

    # Material — Scribe is primary (only when user names a specific material)
    if entity.material:
        state.lock_material(entity.material)

    # Corrosion class requirement — Scribe extracts class, NOT material
    if entity.required_corrosion_class and not entity.material:
        state.resolved_params["required_corrosion_class"] = entity.required_corrosion_class
        print(f"🧠 [SCRIBE] Required corrosion class: {entity.required_corrosion_class} (material will be resolved from graph)")

    # Connection type — Scribe is primary
    if entity.connection_type:
        state.resolved_params["connection_type"] = entity.connection_type
        print(f"🧠 [SCRIBE] Connection type: {entity.connection_type}")

    # Housing length — Scribe is primary (v4.0), overrides auto-derived
    if entity.housing_length:
        state.merge_tag(tag_ref, housing_length=entity.housing_length)
        print(f"🧠 [SCRIBE] Housing length: {entity.housing_length} on {tag_ref}")


def _merge_scribe_into_state(
    intent: SemanticIntent,
    state: TechnicalState,
    detected_family: str = "",
) -> None:
    """Merge Scribe extraction results into TechnicalState.

    v4.0: Scribe is SOLE PRIMARY extractor. Merge priority:
    1. CORRECT actions → always win (user corrections override everything)
    2. Scribe entity data → primary (fill dimensions, airflow, material, etc.)
    3. SET/COPY actions → fill empty fields (references, arithmetic)
    4. Parameters (constraints) → always set from Scribe
    5. Project, accessories, housing_length → Scribe primary
    6. Clarification answers → route to tag attributes or resolved_params
    """
    # 1. CORRECT actions first (override existing values)
    for action in intent.actions:
        if action.type != "CORRECT":
            continue
        tag = state.tags.get(action.target_tag)
        if not tag:
            continue
        # Handle dimension corrections: unpack dict → filter_width/height
        if action.field == "dimensions" and isinstance(action.value, dict):
            w = action.value.get("width")
            h = action.value.get("height")
            d = action.value.get("depth")
            kwargs = {}
            if w is not None:
                kwargs["filter_width"] = int(w)
            if h is not None:
                kwargs["filter_height"] = int(h)
            if d is not None:
                kwargs["filter_depth"] = int(d)
            if kwargs:
                # Force override: temporarily clear existing values
                if "filter_width" in kwargs:
                    tag.filter_width = None
                    tag.housing_width = None
                if "filter_height" in kwargs:
                    tag.filter_height = None
                    tag.housing_height = None
                state.merge_tag(action.target_tag, **kwargs)
                print(f"🧠 [SCRIBE] CORRECT: {action.target_tag} dimensions → "
                      f"{kwargs}")
        elif hasattr(tag, action.field) and action.value is not None:
            # Clear existing value then merge to trigger recomputation
            setattr(tag, action.field, None)
            state.merge_tag(action.target_tag, **{action.field: action.value})
            print(f"🧠 [SCRIBE] CORRECT: {action.target_tag}.{action.field} → "
                  f"{action.value}")

    # 2. Entity data — Scribe is primary (v3.1). Only skip dimensions that
    #    structural regex already extracted (WxH patterns are precise).
    try:
        _entity_routing_cfg = get_config().scribe_entity_routing
    except Exception:
        _entity_routing_cfg = []

    for entity in intent.entities:
        tag_ref = entity.tag_ref
        if tag_ref not in state.tags:
            # Only create new tags if Scribe entity has meaningful data
            # (prevents phantom tags from LLM hallucination)
            has_data = entity.dimensions or entity.airflow_m3h or entity.product_family
            if not has_data:
                continue
            # Use Scribe's product_family (primary), fall back to regex-detected
            tag_family = entity.product_family or detected_family
            state.merge_tag(tag_ref, product_family=tag_family)
            print(f"🧠 [SCRIBE] Created new tag: {tag_ref}")

        tag = state.tags[tag_ref]

        if _entity_routing_cfg:
            _route_entity_from_config(entity, tag_ref, tag, state, _entity_routing_cfg)
        else:
            _route_entity_legacy(entity, tag_ref, tag, state)

    # 2b. Project name from Scribe (v4.0)
    if intent.project_name and not state.project_name:
        state.set_project(intent.project_name)
        print(f"🧠 [SCRIBE] Project: {intent.project_name}")

    # 3. SET/COPY actions (fill empty fields only — regex had priority)
    for action in intent.actions:
        if action.type not in ("SET", "COPY") or action.value is None:
            continue

        # Full copy (all fields from source tag)
        if action.field == "_full_copy" and isinstance(action.value, dict):
            target = action.target_tag
            if target not in state.tags:
                state.merge_tag(target, product_family=detected_family)
            tag = state.tags[target]
            copy_data = action.value

            if copy_data.get("dimensions") and not tag.housing_width:
                dims = copy_data["dimensions"]
                state.merge_tag(target,
                    filter_width=dims.get("width"),
                    filter_height=dims.get("height"))
            if copy_data.get("airflow_m3h") and not tag.airflow_m3h:
                state.merge_tag(target, airflow_m3h=copy_data["airflow_m3h"])
            if copy_data.get("product_family") and not tag.product_family:
                state.merge_tag(target, product_family=copy_data["product_family"])
            print(f"🧠 [SCRIBE] COPY → {target}")
            continue

        # Single field SET
        tag = state.tags.get(action.target_tag)
        if not tag:
            continue

        # Handle dimension SET (unpack dict)
        if action.field == "dimensions" and isinstance(action.value, dict):
            if not tag.housing_width:
                w = action.value.get("width")
                h = action.value.get("height")
                kwargs = {}
                if w is not None:
                    kwargs["filter_width"] = int(w)
                if h is not None:
                    kwargs["filter_height"] = int(h)
                if kwargs:
                    state.merge_tag(action.target_tag, **kwargs)
        elif hasattr(tag, action.field):
            current = getattr(tag, action.field)
            if current is None:
                state.merge_tag(action.target_tag, **{action.field: action.value})
                print(f"🧠 [SCRIBE] SET: {action.target_tag}.{action.field} = "
                      f"{action.value}")

    # 4. Parameters (constraints, generic params — always set, Scribe is primary)
    for key, val in intent.parameters.items():
        if val is None or str(val).lower() in ("none", "null", ""):
            continue
        state.resolved_params[key] = str(val)
        print(f"🧠 [SCRIBE] Param: {key} = {val}")

    # 4b. Route filter_depth parameter to tag (IC constraint needs it on tag)
    if "filter_depth" in intent.parameters:
        fd_val = _safe_int_val(intent.parameters["filter_depth"])
        if fd_val:
            for _tid, _tag in state.tags.items():
                if not _tag.filter_depth:
                    state.merge_tag(_tid, filter_depth=fd_val)
                    print(f"🧠 [SCRIBE] Param → filter_depth={fd_val} on {_tid}")

    # 5. Clarification answers → route to tag attributes or resolved_params (v3.1)
    # Guard: only process when there's an actual pending_clarification.
    # Prevents Scribe from hallucinating answers on Turn 1 (e.g. confusing
    # airflow "2500 m³/h" with housing_length).
    if not state.pending_clarification and intent.clarification_answers:
        print(f"⚠️ [SCRIBE] Ignoring {len(intent.clarification_answers)} clarification "
              f"answers (no pending_clarification): {intent.clarification_answers}")
        intent.clarification_answers = {}

    try:
        _cfg_routing = get_config()
        _param_routing = _cfg_routing.parameter_routing or {}
    except Exception:
        _param_routing = {}

    for param_key, value in intent.clarification_answers.items():
        _routed = False
        pk = param_key.lower().strip()

        if _param_routing:
            _routed = _route_clarification_from_config(
                pk, value, state, _param_routing)
        else:
            _routed = _route_clarification_legacy(pk, value, state)

        # Generic fallback → resolved_params
        if not _routed:
            if value is None or str(value).lower() in ("none", "null", ""):
                continue
            state.resolved_params[pk] = str(value)
            print(f"🧠 [SCRIBE] Clarification → resolved_params[{pk}] = {value}")
            state.pending_clarification = _consume_pending_parts(
                state.pending_clarification, [pk])


def _route_clarification_from_config(
    pk: str, value, state: TechnicalState, param_routing: dict
) -> bool:
    """Route a clarification answer using config-driven parameter_routing."""
    for _route_name, route_config in param_routing.items():
        aliases = tuple(route_config.get("aliases", []))
        if pk not in aliases:
            continue

        target_field = route_config.get("field")
        if not target_field:
            break

        int_val = _safe_int_val(value)
        if int_val is None:
            break

        # Validate bounds
        validation = route_config.get("validation", {})
        if validation:
            min_val = validation.get("min")
            max_val = validation.get("max")
            if min_val is not None and int_val < min_val:
                break
            if max_val is not None and int_val > max_val:
                break

        skip_if_set = route_config.get("skip_if_set", False)

        for _tid, _tag in state.tags.items():
            if skip_if_set and getattr(_tag, target_field, None):
                continue
            state.merge_tag(_tid, **{target_field: int_val})
            print(f"🧠 [SCRIBE] Clarification → {target_field}={int_val} on {_tid}")

        state.pending_clarification = _consume_pending_parts(
            state.pending_clarification, list(aliases))
        return True

    return False


def _route_clarification_legacy(pk: str, value, state: TechnicalState) -> bool:
    """Route a clarification answer using legacy hardcoded aliases."""
    _airflow_aliases = ('airflow', 'airflow_m3h')
    _depth_aliases = ('filter_depth', 'depth')
    _length_aliases = ('housing_length', 'length')

    if pk in _airflow_aliases:
        int_val = _safe_int_val(value)
        if int_val and 500 <= int_val <= 100000:
            for _tid, _tag in state.tags.items():
                if not _tag.airflow_m3h:
                    state.merge_tag(_tid, airflow_m3h=int_val)
                    print(f"🧠 [SCRIBE] Clarification → airflow_m3h={int_val} on {_tid}")
            state.pending_clarification = _consume_pending_parts(
                state.pending_clarification, list(_airflow_aliases))
            return True

    elif pk in _depth_aliases:
        int_val = _safe_int_val(value)
        if int_val:
            for _tid, _tag in state.tags.items():
                if not _tag.filter_depth:
                    state.merge_tag(_tid, filter_depth=int_val)
                    print(f"🧠 [SCRIBE] Clarification → filter_depth={int_val} on {_tid}")
            state.pending_clarification = _consume_pending_parts(
                state.pending_clarification, list(_depth_aliases))
            return True

    elif pk in _length_aliases:
        int_val = _safe_int_val(value)
        if int_val:
            for _tid, _tag in state.tags.items():
                state.merge_tag(_tid, housing_length=int_val)
                print(f"🧠 [SCRIBE] Clarification → housing_length={int_val} on {_tid}")
            state.pending_clarification = _consume_pending_parts(
                state.pending_clarification, list(_length_aliases))
            return True

    return False


def _safe_int_val(val) -> int | None:
    """Safely convert a value to int."""
    if val is None:
        return None
    try:
        return int(float(str(val).replace(",", "").replace(" ", "")))
    except (ValueError, TypeError):
        return None


def _consume_pending_parts(pending: str | None, keywords: list[str]) -> str | None:
    """Remove consumed parts from compound pending_clarification.

    E.g., pending="atex_zone, housing_length", keywords=["housing", "length"]
    → returns "atex_zone"
    """
    if not pending:
        return None
    parts = [p.strip() for p in pending.split(",")]
    remaining = [p for p in parts
                 if not any(kw in p.lower() for kw in keywords)]
    return ", ".join(remaining) if remaining else None


# =============================================================================
# ENTITY EXTRACTION (Configuration-Driven)
# =============================================================================

def extract_entity_codes(query: str) -> list[str]:
    """FALLBACK: Regex-based entity code extraction. Only called when Scribe LLM
    fails or returns no entity_codes. Scribe is the primary extractor (v4.0).

    Patterns come from domain_config.yaml.

    Args:
        query: User's query string

    Returns:
        List of extracted entity codes, normalized for database matching
    """
    config = get_config()
    codes = []
    query_upper = query.upper()

    # Check for configured entity families/categories
    for family in config.product_families:
        if family.upper() in query_upper:
            codes.append(family)

            # Try to extract more context around the family name
            idx = query_upper.find(family.upper())
            if idx >= 0:
                context = query[idx:idx+30]
                clean_context = re.sub(r'[^\w\d\-x/]', ' ', context).strip().split()[0]
                normalized = clean_context.replace(' ', '-').upper()
                if len(normalized) > len(family) and normalized not in codes:
                    codes.append(normalized)

    return list(set(codes))


def extract_project_keywords(query: str) -> list[str]:
    """Extract project identifiers from query. Returns basic word tokens."""
    keywords = []
    for word in re.findall(r'\b[A-Za-z0-9_-]{3,}\b', query):
        keywords.append(word)
    return list(set(keywords))


# =============================================================================
# CONTEXT FORMATTING (Direct — no config dependency)
# =============================================================================


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

Input: "Czy obudowa [PRODUCT] nadaje się do basenu?"
Output: ["Basen", "Swimming Pool", "Pływalnia", "Aquapark", "[PRODUCT]"]

Input: "Potrzebuję wentylacji dla szpitalnego oddziału intensywnej terapii"
Output: ["Szpital", "Hospital", "OIOM", "Oddział Intensywnej Terapii", "ICU", "Healthcare"]

Input: "Filtry węglowe do kuchni przemysłowej"
Output: ["Kuchnia Przemysłowa", "Commercial Kitchen", "Industrial Kitchen", "Gastronomia"]

Return ONLY a JSON array of strings. No explanation.
"""

    try:
        result = llm_call(
            model=LLM_MODEL,
            user_prompt=extraction_prompt,
            json_mode=True,
            temperature=0.0,
        )
        if result.error:
            raise Exception(result.error)

        concepts = json.loads(result.text)
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
        # Common domain-specific terms to look for (from config)
        _cfg_env = get_config()
        environment_terms = _cfg_env.fallback_environment_terms or [
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


def format_configuration_context(config_results: dict, max_variants: int = 5, max_context_chars: int = 4000) -> str:
    """Format graph search results as readable text for LLM consumption.

    Formats variant data directly from graph result dicts — no config dependency.

    Args:
        config_results: Results from configuration graph search
        max_variants: Maximum number of product variants to include (default: 5)
        max_context_chars: Maximum characters in output (default: 4000)

    Returns:
        Formatted context string for LLM consumption
    """
    if not config_results:
        return ""

    context_parts = []

    # Format product variants
    variants = config_results.get("variants", [])[:max_variants]
    if variants:
        context_parts.append("## Product Variants Found")
        for v in variants:
            vid = v.get("id", "Unknown")
            family = v.get("family", "")
            section = [f"\n**{vid}**" + (f" (Family: {family})" if family else "")]

            # Dimensions
            dims = []
            for dk in ("width_mm", "height_mm", "depth_mm"):
                val = v.get(dk)
                if val is not None:
                    dims.append(f"{dk.replace('_mm','')}: {val}mm")
            if dims:
                section.append(f"  Dimensions: {' × '.join(dims)}")

            # Key numeric properties
            for key, label in [
                ("airflow_m3h", "Airflow"),
                ("weight_kg", "Weight"),
                ("price", "Price"),
                ("cartridge_count", "Cartridge count"),
                ("reference_airflow_m3h", "Reference airflow"),
                ("standard_length_mm", "Standard length"),
            ]:
                val = v.get(key)
                if val is not None:
                    section.append(f"  {label}: {val}")

            # List properties
            for key, label in [
                ("available_materials", "Materials"),
                ("compatible_duct_diameters_mm", "Duct diameters"),
                ("available_depths_mm", "Available depths"),
                ("special_features", "Features"),
            ]:
                val = v.get(key)
                if val:
                    if isinstance(val, list):
                        section.append(f"  {label}: {', '.join(str(x) for x in val)}")
                    else:
                        section.append(f"  {label}: {val}")

            if v.get("is_insulated"):
                section.append("  Insulated: Yes")

            # Compatible cartridges / filters
            for key, label in [
                ("compatible_cartridges", "Compatible cartridges"),
                ("compatible_filters", "Compatible filters"),
            ]:
                items = v.get(key, [])
                if items and any(items):
                    section.append(f"  {label}: {', '.join(str(x) for x in items if x)}")

            # Options (from options_json)
            options_json = v.get("options_json")
            if options_json:
                try:
                    options = json.loads(options_json) if isinstance(options_json, str) else options_json
                    if options:
                        section.append("  Options:")
                        for opt in options:
                            code = opt.get("code", "?")
                            desc = opt.get("description", "")
                            section.append(f"    - {code}: {desc}")
                except (json.JSONDecodeError, TypeError):
                    pass
            elif v.get("available_options"):
                opts = v.get("available_options")
                if isinstance(opts, list):
                    section.append(f"  Options: {', '.join(str(o) for o in opts)}")

            context_parts.append("\n".join(section))

    # Format secondary entities (cartridges, filters, materials, option_matches)
    _SECONDARY = {
        "cartridges": ("Cartridges", ("model_name", "weight_kg", "media_type")),
        "filters": ("Filters", ("part_number", "filter_type", "efficiency_class")),
        "materials": ("Materials", ("code", "name", "corrosion_class")),
        "option_matches": ("Option Matches", ("id", "family")),
    }
    for entity_key, (header, fields) in _SECONDARY.items():
        items = config_results.get(entity_key, [])
        if not items:
            continue
        context_parts.append(f"\n## {header}")
        for item in items:
            parts = []
            for f in fields:
                val = item.get(f)
                if val is not None:
                    parts.append(f"{f}: {val}")
            if parts:
                context_parts.append(f"  - {', '.join(parts)}")

    result = "\n".join(context_parts) if context_parts else ""

    # PRUNING: Truncate if too long
    if len(result) > max_context_chars:
        result = result[:max_context_chars] + "\n... [CONTEXT TRUNCATED - too many results]"

    return result


# =============================================================================
# GUARDIAN REASONING ENGINE (Graph-Based)
# =============================================================================

def evaluate_policies(
    query: str,
    graph_data: dict,
    config: DomainConfig
) -> tuple[list[PolicyCheckResult], str]:
    """Evaluate policies via GRAPH traversal - no YAML config.

    This function now uses the GraphReasoningEngine to evaluate rules
    stored in the graph database instead of YAML-based policies.

    Args:
        query: User's query
        graph_data: Retrieved graph data (used for context)
        config: Domain configuration (kept for backwards compatibility, not used for rules)

    Returns:
        Tuple of (policy check results, formatted policy analysis string)
    """
    engine = get_graph_reasoning_engine()
    results = []
    analysis_parts = []

    # Extract product family from graph data or query
    product_family = None
    for variant in graph_data.get("variants", []):
        if "family" in variant:
            product_family = variant["family"]
            break

    # Generate graph-based reasoning report
    report = engine.generate_reasoning_report(query, product_family)

    if not report.application and not report.suitability.warnings:
        return results, "No special policies triggered for this query."

    analysis_parts.append("**Graph-Based Policy Evaluation:**\n")

    # Process application context
    if report.application:
        analysis_parts.append(f"• [APPLICATION] Detected: {report.application.name}")
        analysis_parts.append(f"  Keywords matched: '{report.application.matched_keyword}'")

        # Check for associated risks
        if report.application.risks:
            for risk in report.application.risks:
                analysis_parts.append(f"  ⚠️ Associated Risk: {risk.get('name', '')} ({risk.get('severity', '')})")

        # Check for requirements
        if report.application.requirements:
            for req in report.application.requirements:
                analysis_parts.append(f"  📋 Requires: {req.get('name', '')}")
        analysis_parts.append("")

    # Process suitability warnings
    for warning in report.suitability.warnings:
        result = PolicyCheckResult(
            policy_id=f"GRAPH_{warning.risk_type}",
            policy_name=warning.risk_name,
            triggered=True,
            passed=False if warning.severity in ['CRITICAL', 'WARNING'] else True,
            message=warning.description,
            recommendation=warning.mitigation
        )

        severity_icon = "🔴" if warning.severity == "CRITICAL" else "🟡" if warning.severity == "WARNING" else "🔵"
        analysis_parts.append(f"• [{warning.risk_type}] {warning.risk_name} - {severity_icon} {warning.severity}")
        analysis_parts.append(f"  Description: {warning.description}")
        analysis_parts.append(f"  Consequence: {warning.consequence}")
        analysis_parts.append(f"  → Recommendation: {warning.mitigation}")
        analysis_parts.append(f"  Graph Path: {warning.graph_path}")
        analysis_parts.append("")

        results.append(result)

    # Process required materials
    if report.suitability.required_materials:
        analysis_parts.append("• [MATERIAL_REQUIREMENTS] From Graph:")
        for mat in report.suitability.required_materials:
            analysis_parts.append(f"  ✓ {mat.material_code} ({mat.material_name}) - {mat.reason}")
        analysis_parts.append("")

    return results, "\n".join(analysis_parts)


def build_guardian_prompt(query: str, config: DomainConfig) -> str:
    """DEPRECATED: Use build_graph_reasoning_prompt() instead.

    This function is kept for backwards compatibility but should not be used.
    All rules are now stored in the graph and retrieved via GraphReasoningEngine.
    """
    # Return empty string - all reasoning comes from graph now
    return ""


# =============================================================================
# GRAPH-NATIVE REASONING ENGINE
# =============================================================================

# Global instance of the GraphReasoningEngine
_graph_reasoning_engine = None
_trait_engine = None


def _get_trait_engine():
    """Get or create the TraitBasedEngine singleton."""
    global _trait_engine
    if _trait_engine is None:
        from logic.universal_engine import TraitBasedEngine
        _trait_engine = TraitBasedEngine(db)
    return _trait_engine


def get_graph_reasoning_engine() -> GraphReasoningEngine:
    """Get or create the GraphReasoningEngine singleton."""
    global _graph_reasoning_engine
    if _graph_reasoning_engine is None:
        _graph_reasoning_engine = GraphReasoningEngine(db)
    return _graph_reasoning_engine


def build_graph_reasoning_prompt(query: str, product_family: str = None, context: dict = None) -> str:
    """Build reasoning context from graph traversal instead of YAML config.

    This function replaces build_guardian_prompt() with graph-native reasoning.
    Rules are retrieved via graph queries rather than loaded from YAML.

    Args:
        query: User's query string
        product_family: Optional pre-detected product family
        context: Optional dict of already-known parameters

    Returns:
        Formatted reasoning context for LLM injection
    """
    engine = get_graph_reasoning_engine()
    report = engine.generate_reasoning_report(query, product_family, context)
    return report.to_prompt_injection()


def get_graph_reasoning_report(query: str, product_family: str = None, context: dict = None,
                               material: str = None, accessories: list = None):
    """Get the full GraphReasoningReport for advanced use cases.

    Returns the structured report object for cases where you need
    programmatic access to the reasoning results.

    Uses TraitBasedEngine with full installation constraint pipeline.
    """
    from logic.universal_engine import TraitBasedEngine
    from logic.verdict_adapter import VerdictToReportAdapter
    engine = _get_trait_engine()
    verdict = engine.process_query(query, product_hint=product_family, context=context, accessories=accessories)
    return VerdictToReportAdapter().adapt(verdict)


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

    # Step 9: Build dynamic prompts - GRAPH-ONLY reasoning (no YAML)
    active_policies_prompt = build_graph_reasoning_prompt(user_query)

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
    _llm_result = llm_call(
        model=LLM_MODEL,
        user_prompt=synthesis_prompt,
        system_prompt=system_prompt,
        json_mode=True,
        temperature=0.0,
    )

    # Parse structured response
    try:
        llm_response = json.loads(_llm_result.text)
    except json.JSONDecodeError:
        # Fallback for non-JSON response
        llm_response = {
            "intent_analysis": "Unable to parse structured response",
            "policy_analysis": policy_analysis,
            "graph_evidence": [],
            "general_knowledge": "",
            "final_answer": _llm_result.text,
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
        "final_answer": llm_response.get("final_answer", _llm_result.text),
        "confidence_level": llm_response.get("confidence_level", "medium"),
        "sources": sources + llm_response.get("sources", []),
        "warnings": warnings + llm_response.get("warnings", []),
        "policy_checks": policy_results,
        "thought_process": f"Analyzed query → {len(policy_results)} policies checked → "
                          f"{len(config_results['variants'])} products found → "
                          f"{len(retrieval_results)} cases retrieved",
        # Legacy fields for backwards compatibility
        "answer": llm_response.get("final_answer", _llm_result.text),
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

Format: "The housing is [W]x[H]mm [[REF:product-id]] and weighs [X]kg [[REF:weight-spec]]."

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
    {{"step": "Found [Product]-[Size] with [capacity] [unit]", "source": "GRAPH", "node_id": "[product-id]"}},
    {{"step": "[Technology] effective for [problem]", "source": "LLM", "node_id": null}},
    {{"step": "Capacity Check: PASSED ([value] >= [required])", "source": "POLICY", "node_id": null}},
    {{"step": "Undersized products filtered out: [product-id]", "source": "FILTER", "node_id": null}}
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

    # Step 11: Build prompts - GRAPH-ONLY reasoning (no YAML)
    active_policies_prompt = build_graph_reasoning_prompt(user_query)

    # Always respond in English
    lang_directive = "\n\n## RESPONSE LANGUAGE\n**You MUST respond in ENGLISH.** All responses must be in English regardless of query language.\n"

    system_prompt = EXPLAINABLE_SYSTEM_PROMPT.format(active_policies=active_policies_prompt) + lang_directive
    synthesis_prompt = EXPLAINABLE_SYNTHESIS_PROMPT.format(
        context=graph_context,
        query=user_query,
        policies=policy_analysis
    )

    # Step 11: LLM synthesis
    _llm_result = llm_call(
        model=LLM_MODEL,
        user_prompt=synthesis_prompt,
        system_prompt=system_prompt,
        json_mode=True,
        temperature=0.0,
    )

    # Step 12: Parse and validate response
    try:
        llm_response = json.loads(_llm_result.text)
    except json.JSONDecodeError:
        llm_response = {
            "reasoning_chain": [],
            "reasoning_steps": ["Error: Could not parse LLM response"],
            "final_answer_markdown": _llm_result.text,
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

def _load_system_generic_prompt() -> str:
    """Load the generic system prompt from tenant file, falling back to hardcoded."""
    from config_loader import load_tenant_prompt
    text = load_tenant_prompt("system_generic")
    if text:
        return text
    raise FileNotFoundError("system_generic.txt not found in tenant prompts directory")


def _load_synthesis_prompt() -> str:
    """Load the synthesis prompt from tenant file, falling back to hardcoded."""
    from config_loader import load_tenant_prompt
    text = load_tenant_prompt("synthesis")
    if text:
        return text
    raise FileNotFoundError("synthesis.txt not found in tenant prompts directory")


# Module-level references (lazy-loaded, cached by load_tenant_prompt)
def _get_generic_prompt():
    return _load_system_generic_prompt()

def _get_synthesis_prompt():
    return _load_synthesis_prompt()


# BACKWARD COMPAT: These constants are still referenced by tests.
# They delegate to the file-loaded versions.
class _LazyPrompt:
    """Lazy-loading prompt that reads from tenant files on first access.

    Proxies all string methods so it can be used as a drop-in replacement
    for a regular str constant.
    """
    def __init__(self, loader):
        self._loader = loader
        self._text = None

    def _ensure_loaded(self):
        if self._text is None:
            self._text = self._loader()
        return self._text

    def format(self, **kwargs):
        return self._ensure_loaded().format(**kwargs)

    def __str__(self):
        return self._ensure_loaded()

    def __contains__(self, item):
        return item in self._ensure_loaded()

    def __len__(self):
        return len(self._ensure_loaded())

    def __getattr__(self, name):
        # Proxy all other string methods (lower, upper, split, etc.)
        return getattr(self._ensure_loaded(), name)


DEEP_EXPLAINABLE_SYSTEM_PROMPT_GENERIC = _LazyPrompt(_load_system_generic_prompt)
DEEP_EXPLAINABLE_SYNTHESIS_PROMPT = _LazyPrompt(_load_synthesis_prompt)







def extract_resolved_context(query: str) -> dict:
    """Extract resolved parameters from a query containing "Context Update:" patterns.

    This enables the Graph Reasoning Engine to know which parameters have already
    been provided by the user, so it doesn't ask for them again.

    Input format: "[Original Query]. Context Update: [attribute] is [value]."
    Can also handle multiple context updates.

    Returns:
        Dict of resolved parameters, e.g., {'airflow': '3400', 'airflow_m3h': '3400'}
    """
    import re
    context = {}

    # Normalize thousand separators: "6,000" → "6000", "25 000" → "25000"
    query = re.sub(r'(\d)[,\s](\d{3})', r'\1\2', query)

    # Pattern 1: "Context Update: airflow is 3400" style
    updates = re.findall(r'Context Update:\s*(\w+)\s+is\s+([^\s.,]+)', query, re.IGNORECASE)
    for attr, value in updates:
        attr_lower = attr.lower()
        context[attr_lower] = value
        # Also add common aliases
        if 'airflow' in attr_lower or 'flow' in attr_lower:
            context['airflow'] = value
            context['airflow_m3h'] = value
        elif 'length' in attr_lower:
            context['housing_length'] = value
            context['length'] = value
        elif 'material' in attr_lower:
            context['material'] = value

    # Pattern 2: Numeric values that look like airflow (e.g., "3400 m³/h", "3400m3/h")
    airflow_match = re.search(r'(\d{3,5})\s*m[³3]?\/?h', query, re.IGNORECASE)
    if airflow_match and 'airflow' not in context:
        context['airflow'] = airflow_match.group(1)
        context['airflow_m3h'] = airflow_match.group(1)

    # Pattern 3: Standalone numbers in airflow range (500-20000)
    # Strip dimension patterns first (e.g. "500×500", "300x600") then look for remaining numbers
    if 'airflow' not in context:
        query_no_dims = re.sub(r'\d{2,4}\s*[x\u00d7X]\s*\d{2,4}(?:\s*(?:mm|cm))?', '', query)
        standalone_num = re.search(r'\b(\d{3,5})\b', query_no_dims)
        if standalone_num:
            val = int(standalone_num.group(1))
            if 500 <= val <= 20000:
                context['airflow'] = str(val)
                context['airflow_m3h'] = str(val)

    # Pattern 4: Housing length values
    # BUGFIX: Strip dimension patterns first to avoid matching "600" from "600x600mm"
    query_no_dims_for_length = re.sub(r'\d{2,4}\s*[x\u00d7X]\s*\d{2,4}(?:\s*(?:mm|cm))?', '', query)
    length_match = re.search(r'(550|600|750|800|900)\s*mm', query_no_dims_for_length, re.IGNORECASE)
    if length_match and 'housing_length' not in context:
        context['housing_length'] = length_match.group(1)
        context['length'] = length_match.group(1)

    return context


def _build_resolved_context(
    technical_state: TechnicalState,
    db_conn,
    user_max_width_mm=None,
    user_max_height_mm=None,
) -> dict:
    """Build resolved_context dict from TechnicalState for engine consumption.

    Config-first: uses resolved_context_mappings from DomainConfig when available.
    Falls back to legacy hardcoded mapping if config is absent.

    The resolved_context provides the trait engine with all known parameter values
    so it can skip clarification questions for already-resolved parameters.
    """
    resolved_context = {}

    try:
        cfg = get_config()
        mappings = cfg.resolved_context_mappings
    except Exception:
        mappings = {}

    if mappings and mappings.get("single_fields"):
        resolved_context = _build_resolved_context_from_config(
            technical_state, mappings)
    else:
        resolved_context = _build_resolved_context_legacy(technical_state)

    # --- Generic post-processing (config-independent) ---

    # Pass dimension constraints to engine for sizing arrangement
    if user_max_width_mm:
        resolved_context['max_width_mm'] = int(user_max_width_mm)
    if user_max_height_mm:
        resolved_context['max_height_mm'] = int(user_max_height_mm)

    # Merge generic resolved parameters (gate answers, etc.) into engine context
    if technical_state.resolved_params:
        for rp_key, rp_value in technical_state.resolved_params.items():
            if rp_key not in resolved_context:
                resolved_context[rp_key] = rp_value

    # Chlorine inference from detected application (v3.0)
    if "chlorine_ppm" not in resolved_context:
        app_id_for_chlorine = technical_state.resolved_params.get("detected_application")
        try:
            _e2a_cfg = get_config()
            env_to_app = _e2a_cfg.fallback_env_to_app_inference or {}
        except Exception:
            env_to_app = {}
        if not app_id_for_chlorine:
            inst_env = resolved_context.get("installation_environment")
            app_id_for_chlorine = env_to_app.get(inst_env)
        if app_id_for_chlorine:
            try:
                app_props = db_conn.get_application_properties(app_id_for_chlorine)
                chlorine_val = app_props.get("typical_chlorine_ppm")
                if chlorine_val is not None:
                    resolved_context["chlorine_ppm"] = int(chlorine_val)
                    print(f"🧪 [CONSTRAINT] chlorine_ppm = {chlorine_val} (inferred from {app_id_for_chlorine})")
            except Exception as e:
                print(f"⚠️ [CONSTRAINT] Failed to get application chlorine: {e}")

    # Merge Scribe-extracted params into resolved_context for engine consumption
    for rp_key in ("installation_environment", "detected_application", "max_width_mm", "max_height_mm", "available_space_mm"):
        rp_val = technical_state.resolved_params.get(rp_key)
        if rp_val and rp_key not in resolved_context:
            resolved_context[rp_key] = rp_val
            print(f"🧠 [SCRIBE→CONTEXT] {rp_key} = {rp_val}")

    return resolved_context


def _build_resolved_context_from_config(
    technical_state: TechnicalState,
    mappings: dict,
) -> dict:
    """Build resolved_context using config-driven mappings."""
    ctx = {}

    # 1. Single fields from tags
    for entry in mappings.get("single_fields", []):
        tag_field = entry["tag_field"]
        context_keys = entry["context_keys"]
        for _tag_id, tag in technical_state.tags.items():
            val = getattr(tag, tag_field, None)
            if val is not None:
                for ck in context_keys:
                    ctx[ck] = val

    # 2. Dimension pairs from tags
    for entry in mappings.get("dimension_pairs", []):
        w_field = entry["width_field"]
        h_field = entry["height_field"]
        combined_key = entry.get("combined_key")
        combined_fmt = entry.get("combined_format", "{w}x{h}")
        w_keys = entry.get("width_keys", [])
        h_keys = entry.get("height_keys", [])
        for _tag_id, tag in technical_state.tags.items():
            w_val = getattr(tag, w_field, None)
            h_val = getattr(tag, h_field, None)
            if w_val is not None and h_val is not None:
                if combined_key:
                    ctx[combined_key] = combined_fmt.format(w=w_val, h=h_val)
                for wk in w_keys:
                    ctx[wk] = int(w_val)
                for hk in h_keys:
                    ctx[hk] = int(h_val)

    # 3. Param fallbacks (cross-turn persistence from resolved_params)
    for entry in mappings.get("param_fallbacks", []):
        param_key = entry["param_key"]
        context_keys = entry["context_keys"]
        # Only apply if not already set from tags
        first_key = context_keys[0] if context_keys else None
        if first_key and first_key in ctx:
            continue
        stored = technical_state.resolved_params.get(param_key)
        if stored is not None:
            val = stored
            if entry.get("cast") == "int":
                try:
                    val = int(stored)
                except (ValueError, TypeError):
                    continue
            for ck in context_keys:
                ctx[ck] = val
            print(f"🔄 [GRAPH STATE] {param_key} from Layer 4: {val}")

    # 4. State-level fields
    for entry in mappings.get("state_fields", []):
        source = entry["source"]
        context_key = entry["context_key"]
        val = getattr(technical_state, source, None)
        if val is not None:
            ctx[context_key] = val

    # 5. _mm suffix aliases
    for field_name in mappings.get("mm_suffix_fields", []):
        val = ctx.get(field_name)
        if val is not None:
            ctx[f"{field_name}_mm"] = val

    return ctx


def _build_resolved_context_legacy(technical_state: TechnicalState) -> dict:
    """Build resolved_context using legacy hardcoded mapping."""
    ctx = {}

    for _tag_id, tag in technical_state.tags.items():
        if tag.filter_depth:
            ctx['filter_depth'] = tag.filter_depth
            ctx['depth'] = tag.filter_depth
        if tag.housing_length:
            ctx['housing_length'] = tag.housing_length
            ctx['length'] = tag.housing_length
        if tag.airflow_m3h:
            ctx['airflow'] = tag.airflow_m3h
            ctx['airflow_m3h'] = tag.airflow_m3h
        if tag.housing_width and tag.housing_height:
            ctx['housing_size'] = f"{tag.housing_width}x{tag.housing_height}"
            ctx['housing_width'] = int(tag.housing_width)
            ctx['housing_height'] = int(tag.housing_height)
            ctx['width'] = int(tag.housing_width)
            ctx['height'] = int(tag.housing_height)
        if tag.filter_width and tag.filter_height:
            ctx['filter_width'] = int(tag.filter_width)
            ctx['filter_height'] = int(tag.filter_height)
            ctx['dimensions'] = f"{tag.filter_width}x{tag.filter_height}"

    # Airflow from resolved_params (cross-turn persistence via Layer 4)
    if 'airflow' not in ctx and technical_state.resolved_params.get("airflow_m3h"):
        stored_airflow = technical_state.resolved_params["airflow_m3h"]
        ctx['airflow'] = stored_airflow
        ctx['airflow_m3h'] = stored_airflow
        print(f"🔄 [GRAPH STATE] Airflow from Layer 4: {stored_airflow} m³/h")

    # Filter depth from resolved_params (Scribe extraction)
    if 'filter_depth' not in ctx and technical_state.resolved_params.get("filter_depth"):
        stored_depth = technical_state.resolved_params["filter_depth"]
        try:
            depth_int = int(stored_depth)
            ctx['filter_depth'] = depth_int
            ctx['depth'] = depth_int
            print(f"🔄 [GRAPH STATE] Filter depth from params: {depth_int}mm")
        except (ValueError, TypeError):
            pass

    if technical_state.locked_material:
        ctx['material'] = technical_state.locked_material

    # _mm suffix aliases for HardConstraint compatibility
    for _key in ['housing_length', 'housing_width', 'housing_height']:
        _val = ctx.get(_key)
        if _val is not None:
            ctx[f'{_key}_mm'] = _val

    return ctx


def _generate_airflow_options_from_graph(technical_state, db_conn) -> list[dict]:
    """Generate airflow clarification options from ProductVariant graph data.

    v4.0: Uses family-specific ProductVariant airflow values instead of
    shared DimensionModule pool. This prevents cross-family contamination in
    airflow suggestions for other product families.
    """
    options = []
    seen_airflows = set()

    # Collect per-tag airflow references (v4.0: family-aware)
    tag_refs = []
    detected_family = technical_state.detected_family or ""
    for tag_id, tag in technical_state.tags.items():
        if tag.housing_width and tag.housing_height:
            family = tag.product_family or detected_family
            ref = db_conn.get_reference_airflow_for_dimensions(
                tag.housing_width, tag.housing_height, product_family=family
            )
            if ref and ref.get("reference_airflow_m3h"):
                ref_airflow = int(ref["reference_airflow_m3h"])
                label = ref.get("label", f"{tag.housing_width}x{tag.housing_height}")
                tag_refs.append((tag_id, ref_airflow, label))

    # Detect multi-size scenario
    distinct_airflows = set(r[1] for r in tag_refs)
    multi_size = len(distinct_airflows) > 1

    for tag_id, ref_airflow, label in tag_refs:
        if ref_airflow in seen_airflows:
            continue
        seen_airflows.add(ref_airflow)

        if multi_size:
            matching_tags = [r[0] for r in tag_refs if r[1] == ref_airflow]
            tag_hint = ", ".join(matching_tags)
            description = f"{ref_airflow} m\u00b3/h (Reference for {label} \u2014 {tag_hint})"
        else:
            description = f"{ref_airflow} m\u00b3/h (Reference for {label})"

        options.append({
            "value": str(ref_airflow),
            "description": description,
        })

    # Add reduced-load variants based on the largest reference airflow
    if seen_airflows:
        max_airflow = max(seen_airflows)
        if max_airflow > 1000:
            reduced_75 = int(max_airflow * 0.75)
            reduced_50 = int(max_airflow * 0.5)
            if reduced_75 not in seen_airflows:
                options.append({
                    "value": str(reduced_75),
                    "description": f"{reduced_75} m\u00b3/h (Reduced load)",
                })
            if reduced_50 not in seen_airflows:
                options.append({
                    "value": str(reduced_50),
                    "description": f"{reduced_50} m\u00b3/h (Low load)",
                })

    return options


def _repair_truncated_json(raw: str) -> dict:
    """Attempt to recover a usable dict from a truncated JSON string.

    Common truncation patterns from the Gemini API when max_output_tokens
    is hit mid-object.  We try progressively more aggressive repairs:
      1. Close open strings + brackets.
      2. Fall back to a minimal error payload the frontend can render.
    """
    import json as _json

    # Strip any trailing whitespace / incomplete escape sequences
    text = raw.rstrip()

    # Try closing open strings and brackets
    # Count unclosed delimiters
    in_string = False
    escape_next = False
    stack = []
    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"' and not in_string:
            in_string = True
            continue
        if ch == '"' and in_string:
            in_string = False
            continue
        if not in_string:
            if ch in ('{', '['):
                stack.append(ch)
            elif ch == '}' and stack and stack[-1] == '{':
                stack.pop()
            elif ch == ']' and stack and stack[-1] == '[':
                stack.pop()

    # Close open string first
    repaired = text
    if in_string:
        repaired += '"'

    # Close open brackets/braces in reverse order
    for opener in reversed(stack):
        repaired += ']' if opener == '[' else '}'

    try:
        result = _json.loads(repaired)
        logger.info(f"🔧 [JSON REPAIR] Successfully repaired truncated JSON ({len(stack)} closers added)")
        # Ensure critical fields exist
        if "content_segments" not in result:
            result["content_segments"] = [{"text": "(Response was truncated)", "type": "GENERAL"}]
        return result
    except _json.JSONDecodeError:
        pass

    # Last resort: extract whatever content_segments we can find
    import re as _re
    segments = []
    seg_pattern = _re.compile(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"')
    for m in seg_pattern.finditer(raw):
        segments.append({"text": m.group(1).replace('\\"', '"').replace('\\n', '\n'), "type": "GENERAL"})

    if segments:
        logger.warning(f"🔧 [JSON REPAIR] Extracted {len(segments)} text segments from truncated JSON")
        return {
            "content_segments": segments,
            "response_type": "FINAL_ANSWER",
            "policy_warnings": ["Response was truncated due to length limits."],
        }

    # Total failure — return a safe fallback
    logger.error(f"🔧 [JSON REPAIR] Could not repair JSON ({len(raw)} chars). First 200: {raw[:200]}")
    return {
        "content_segments": [{"text": "The response was truncated. Please try a shorter question or break it into parts.", "type": "GENERAL"}],
        "response_type": "FINAL_ANSWER",
        "policy_warnings": ["STREAM_TRUNCATED: LLM output exceeded token limit."],
    }


def query_deep_explainable(user_query: str, model: str = None) -> "DeepExplainableResponse":
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

    from concurrent.futures import ThreadPoolExecutor, as_completed

    config = get_config()
    model = model or DEFAULT_MODEL
    timings = {}
    total_start = time.time()

    # ============================================================
    # PARALLEL BATCH 1: Intent + Embedding + Config Search
    # These are independent and can run simultaneously
    # ============================================================
    t_batch1 = time.time()

    def task_intent():
        t = time.time()
        result = detect_intent(user_query)  # Now uses fast regex (~0.001s)
        return ("intent", result, time.time() - t)

    def task_embedding():
        t = time.time()
        result = generate_embedding(user_query)
        return ("embedding", result, time.time() - t)

    def task_config_search():
        t = time.time()
        entity_codes = extract_entity_codes(user_query)
        config_results = {
            "variants": [], "cartridges": [], "filters": [],
            "materials": [], "option_matches": []
        }

        # Collect all search terms to run in parallel
        all_keywords = get_config().get_all_search_keywords()
        matching_keywords = [kw for kw in all_keywords if kw.lower() in user_query.lower()]

        def search_code(code):
            """Search for a single entity code."""
            exact_match = db.get_variant_by_name(code)
            if exact_match:
                return [exact_match]
            return db.search_product_variants(code)

        def search_keyword(kw):
            """Search configuration for a single keyword."""
            return db.configuration_graph_search(kw)

        # Run ALL searches in parallel (codes + keywords)
        with ThreadPoolExecutor(max_workers=8) as inner_executor:
            code_futures = {inner_executor.submit(search_code, code): code for code in entity_codes}
            kw_futures = {inner_executor.submit(search_keyword, kw): kw for kw in matching_keywords}

            # Collect code search results
            for future in as_completed(code_futures):
                results = future.result()
                for fr in results:
                    if fr not in config_results["variants"]:
                        config_results["variants"].append(fr)

            # Collect keyword search results
            for future in as_completed(kw_futures):
                general_config = future.result()
                for key in config_results.keys():
                    for item in general_config.get(key, []):
                        if item not in config_results[key]:
                            config_results[key].append(item)

        return ("config_search", (entity_codes, config_results), time.time() - t)

    def task_project_search():
        t = time.time()
        project_keywords = extract_project_keywords(user_query)
        project_results = []

        if project_keywords:
            # Run all project searches in parallel
            with ThreadPoolExecutor(max_workers=4) as inner_executor:
                futures = [inner_executor.submit(db.search_by_project_name, kw) for kw in project_keywords]
                for future in as_completed(futures):
                    results = future.result()
                    if results:
                        project_results.extend(results)

        return ("project_search", project_results, time.time() - t)

    # Run BATCH 1 in parallel
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(task_intent),
            executor.submit(task_embedding),
            executor.submit(task_config_search),
            executor.submit(task_project_search),
        ]
        batch1_results = {}
        for future in as_completed(futures):
            name, result, elapsed = future.result()
            batch1_results[name] = result
            timings[name] = elapsed

    intent = batch1_results["intent"]
    query_embedding = batch1_results["embedding"]
    entity_codes, config_results = batch1_results["config_search"]
    project_results = batch1_results["project_search"]

    timings["batch1_total"] = time.time() - t_batch1

    # ============================================================
    # PARALLEL BATCH 2: Vector Retrieval + Similar Cases + Policies
    # These depend on embedding from Batch 1
    # ============================================================
    t_batch2 = time.time()

    def task_retrieval():
        t = time.time()
        results = db.hybrid_retrieval(query_embedding, top_k=5, min_score=0.5)
        # Add project results
        if project_results:
            results = project_results + results
        return ("retrieval", results, time.time() - t)

    def task_similar_cases():
        t = time.time()
        results = db.get_similar_cases(query_embedding, top_k=3)
        return ("similar_cases", results, time.time() - t)

    def task_policies():
        t = time.time()
        policy_results, policy_analysis = evaluate_policies(user_query, config_results, config)
        return ("policies", (policy_results, policy_analysis), time.time() - t)

    # Run BATCH 2 in parallel
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(task_retrieval),
            executor.submit(task_similar_cases),
            executor.submit(task_policies),
        ]
        batch2_results = {}
        for future in as_completed(futures):
            name, result, elapsed = future.result()
            batch2_results[name] = result
            timings[name] = elapsed

    retrieval_results = batch2_results["retrieval"]
    similar_cases = batch2_results["similar_cases"]
    policy_results, policy_analysis = batch2_results["policies"]

    timings["batch2_total"] = time.time() - t_batch2

    # ============================================================
    # SEQUENTIAL: Filtering, Graph Reasoning, Prompt Building
    # These are fast and need results from above
    # ============================================================

    # Step 6: Filter entities (fast - pure Python)
    t1 = time.time()
    rejected_entities = []
    filtering_note = ""
    for constraint in intent.numeric_constraints:
        value = constraint.get("value")
        if value and config_results.get("variants"):
            for attr_name in ["capacity", "airflow_m3h", "max_flow", "rating", "size_mm", "weight_kg"]:
                sample = config_results["variants"][0] if config_results["variants"] else {}
                if attr_name in sample:
                    suitable, rejected = filter_entities_by_attribute(
                        config_results["variants"], attr_name, value, comparison="gte"
                    )
                    config_results["variants"] = suitable
                    rejected_entities.extend(rejected)
                    break
    timings["filtering"] = time.time() - t1

    # Variance analysis (fast)
    variance_analysis = analyze_entity_variance(config_results.get("variants", []))
    variance_note = ""
    if variance_analysis["has_variance"] and not intent.has_specific_constraint:
        diff_attr = variance_analysis["suggested_differentiator"]
        values = variance_analysis["unique_values"].get(diff_attr, [])[:5]
        variance_note = f"\n\n🛑 **VARIANCE DETECTED**: {len(config_results.get('variants', []))} variants.\n"

    # Step 9: Format contexts (sequential - needs results from batches)
    t1 = time.time()
    config_context = format_configuration_context(config_results)
    graph_context = format_retrieval_context(retrieval_results, similar_cases, config_context)

    # Add variance analysis to context for LLM awareness
    if variance_note:
        graph_context = variance_note + graph_context

    if filtering_note:
        graph_context = filtering_note + graph_context
    timings["format_context"] = time.time() - t1

    # Step 9b: GRAPH-NATIVE REASONING - Query the graph for rules and constraints
    t1 = time.time()
    # Extract product family for graph reasoning
    detected_product_family = None
    _pf_cfg = get_config()
    _pf_families = _pf_cfg.product_families or []
    for code in entity_codes:
        # Longest match first: FAMILY-VARIANT must match before FAMILY
        for family in _pf_families:
            if family in code.upper():
                detected_product_family = family.replace('-', '_')
                break
        if detected_product_family:
            break

    # Extract resolved context from the query (e.g., "Context Update: airflow is 3400")
    # This tells the graph reasoning engine which parameters are already resolved
    resolved_context = extract_resolved_context(user_query)
    if resolved_context:
        print(f"\n📋 [CONTEXT] Extracted resolved parameters: {resolved_context}")

    # Get graph-based reasoning report
    graph_reasoning_report = get_graph_reasoning_report(
        user_query,
        product_family=detected_product_family,
        context=resolved_context
    )
    graph_reasoning_context = graph_reasoning_report.to_prompt_injection()

    if graph_reasoning_context:
        print(f"\n🔗 [GRAPH REASONING] Report generated:")
        if graph_reasoning_report.application:
            print(f"   Application: {graph_reasoning_report.application.name} ({graph_reasoning_report.application.id})")
        if graph_reasoning_report.suitability.warnings:
            print(f"   Warnings: {len(graph_reasoning_report.suitability.warnings)}")
        # NOTE: Don't add to graph_context - it's already in system_prompt via build_graph_reasoning_prompt()
        # This was causing DUPLICATE content in the prompts!

    # Step 9c: ACTIVE LEARNING - DISABLED for performance (was taking 4.6s with no results)
    # TODO: Re-enable when learned rules are populated in the graph
    learned_rules_context = ""
    timings["graph_reasoning"] = time.time() - t1

    # Step 10: Build prompts - GRAPH-ONLY reasoning (no YAML)
    t1 = time.time()
    # Reuse already-generated graph_reasoning_context instead of calling build_graph_reasoning_prompt()
    # which would generate the same report AGAIN (wasting ~0.5s)
    active_policies_prompt = graph_reasoning_context

    # v3.8.1: Inject housing corrosion class into the reasoning report
    # so the LLM cites it when discussing environmental suitability.
    if detected_product_family:
        try:
            _pf_id = f"FAM_{detected_product_family}" if not detected_product_family.startswith("FAM_") else detected_product_family
            from db_result_helpers import result_single
            _pf_rec = result_single(db.connect().query(
                "MATCH (pf:ProductFamily {id: $pf_id}) RETURN pf.corrosion_class AS cc, pf.indoor_only AS io",
                params={"pf_id": _pf_id}
            ))
            if _pf_rec:
                _cc = _pf_rec.get("cc")
                _io = _pf_rec.get("io")
                if _cc:
                    active_policies_prompt += (
                        f"\n\n## HOUSING SPECIFICATION\n"
                        f"- Housing corrosion class: **{_cc}** (the housing itself, regardless of material)\n"
                        f"- Indoor only: {'Yes' if _io else 'No'}\n"
                        f"- You MUST state the housing corrosion class ({_cc}) when discussing environmental suitability.\n"
                    )
        except Exception as e:
            logger.warning(f"Failed to fetch housing corrosion class: {e}")

    system_prompt = DEEP_EXPLAINABLE_SYSTEM_PROMPT_GENERIC.format(active_policies=active_policies_prompt)
    synthesis_prompt = DEEP_EXPLAINABLE_SYNTHESIS_PROMPT.format(
        context=graph_context,
        query=user_query,
        policies=policy_analysis
    )

    # DEBUG: Log prompt sizes
    print(f"\n{'='*80}")
    print(f"📊 PROMPT SIZE ANALYSIS:")
    print(f"   System prompt: {len(system_prompt):,} chars (~{len(system_prompt)//4:,} tokens)")
    print(f"   Synthesis prompt: {len(synthesis_prompt):,} chars (~{len(synthesis_prompt)//4:,} tokens)")
    print(f"   TOTAL: {len(system_prompt) + len(synthesis_prompt):,} chars (~{(len(system_prompt) + len(synthesis_prompt))//4:,} tokens)")
    print(f"{'='*80}")
    timings["build_prompts"] = time.time() - t1

    # Write full prompts to debug file
    debug_dir = "/tmp/claude-prompts"
    os.makedirs(debug_dir, exist_ok=True)
    with open(f"{debug_dir}/last_system_prompt.txt", "w") as f:
        f.write(system_prompt)
    with open(f"{debug_dir}/last_synthesis_prompt.txt", "w") as f:
        f.write(synthesis_prompt)
    print(f"📝 Full prompts saved to {debug_dir}/")

    # Step 11: LLM synthesis
    t1 = time.time()
    _llm_result = llm_call(
        model=model,
        user_prompt=synthesis_prompt,
        system_prompt=system_prompt,
        json_mode=True,
        temperature=0.0,
        max_output_tokens=4096,
    )
    if _llm_result.error:
        raise Exception(_llm_result.error)
    _raw_text = _llm_result.text
    timings["llm"] = time.time() - t1
    timings["total"] = time.time() - total_start

    # TOKEN USAGE LOGGING
    input_tokens = _llm_result.input_tokens
    output_tokens = _llm_result.output_tokens
    total_tokens = input_tokens + output_tokens
    print(f"🔢 TOKEN USAGE: input={input_tokens:,}, output={output_tokens:,}, total={total_tokens:,}")
    if input_tokens > 10000:
        print(f"⚠️ ALERT: Input tokens ({input_tokens:,}) > 10k - prompt too big!")
    if output_tokens >= 4000:
        print(f"⚠️ [TRUNCATION RISK] Output used {output_tokens} tokens (near 4096 limit)")
    timings["input_tokens"] = input_tokens
    timings["output_tokens"] = output_tokens

    # Log timings
    timing_parts = [f"{k}={v:.2f}s" for k, v in timings.items() if k not in ('total', 'input_tokens', 'output_tokens')]
    print(f"⏱️ DEEP-EXPLAINABLE TIMING: {', '.join(timing_parts)}, TOTAL={timings['total']:.2f}s")

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
        llm_response = json.loads(_raw_text)
    except json.JSONDecodeError as e:
        # Try fixing control characters
        try:
            fixed_text = fix_json_control_chars(_raw_text)
            llm_response = json.loads(fixed_text)
        except json.JSONDecodeError:
            # Try to find JSON object directly
            json_start = _raw_text.find('{')
            if json_start != -1:
                try:
                    fixed_text = fix_json_control_chars(_raw_text[json_start:])
                    llm_response = json.loads(fixed_text)
                except json.JSONDecodeError:
                    llm_response = None
            else:
                llm_response = None

            if llm_response is None:
                print(f"[ERROR] Failed to parse JSON: {str(e)}")
                print(f"[DEBUG] Raw response (first 500 chars): {_raw_text[:500]}")
                # Try the truncation repair as a last resort
                llm_response = _repair_truncated_json(_raw_text)

    # Step 13: Build response objects with GRAPH TRAVERSAL details
    # Use graph reasoning report to generate steps with traversal info
    from models import GraphTraversal

    reasoning_steps = []

    # Get graph-based reasoning steps with traversal details
    if graph_reasoning_report:
        graph_steps = graph_reasoning_report.to_reasoning_summary_steps()
        for step_data in graph_steps:
            # Convert traversal dicts to GraphTraversal objects
            traversals = []
            for t in step_data.get("graph_traversals", []):
                traversals.append(GraphTraversal(
                    layer=t.get("layer", 0),
                    layer_name=t.get("layer_name", ""),
                    operation=t.get("operation", ""),
                    cypher_pattern=t.get("cypher_pattern"),
                    nodes_visited=t.get("nodes_visited", []),
                    relationships=t.get("relationships", []),
                    result_summary=t.get("result_summary"),
                    path_description=t.get("path_description")
                ))

            reasoning_steps.append(ReasoningSummaryStep(
                step=step_data.get("step", ""),
                icon=step_data.get("icon", "🔍"),
                description=step_data.get("description", ""),
                graph_traversals=traversals
            ))
    else:
        # Fallback to LLM-generated steps (without graph traversals)
        for step_data in llm_response.get("reasoning_summary", []):
            reasoning_steps.append(ReasoningSummaryStep(
                step=step_data.get("step", ""),
                icon=step_data.get("icon", "🔍"),
                description=step_data.get("description", ""),
                graph_traversals=[]
            ))

    # Add programmatic steps for filtering
    if rejected_entities:
        reasoning_steps.insert(0, ReasoningSummaryStep(
            step="Filter Applied",
            icon="🔍",
            description=f"Filtered {len(rejected_entities)} entity(ies) based on numeric constraints",
            graph_traversals=[]
        ))

    # Add variance detection step if applicable
    if variance_analysis["has_variance"] and not intent.has_specific_constraint:
        reasoning_steps.insert(0, ReasoningSummaryStep(
            step="Gatekeeper",
            icon="🛑",
            description=f"Variance detected in '{variance_analysis['suggested_differentiator']}' - clarification may be needed",
            graph_traversals=[]
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

    # Collect warnings (normalize to strings — LLM sometimes returns objects)
    raw_pw = llm_response.get("policy_warnings", [])
    warnings = [w if isinstance(w, str) else (w.get("message") if isinstance(w, dict) else str(w)) for w in raw_pw if w is not None]
    for pr in policy_results:
        if not pr.passed and pr.message:
            warnings.append(pr.message)

    # Extract risk_detected flag and severity from LLM response (Autonomous Guardian)
    risk_detected = llm_response.get("risk_detected", False)
    risk_severity = llm_response.get("risk_severity", None)
    risk_resolved = llm_response.get("risk_resolved", False)

    # Cap risk_severity based on engine verdict (same as streaming path)
    if (
        risk_severity == "CRITICAL"
        and graph_reasoning_report
        and graph_reasoning_report.suitability
        and graph_reasoning_report.suitability.is_suitable
    ):
        risk_severity = "WARNING"
        print(f"🔇 [RISK CAP] LLM said CRITICAL but engine says is_suitable=True → capped to WARNING")

    # Promote risk to CRITICAL when engine says product is NOT suitable (non-streaming)
    if (
        graph_reasoning_report
        and graph_reasoning_report.suitability
        and not graph_reasoning_report.suitability.is_suitable
        and risk_severity != "CRITICAL"
    ):
        risk_severity = "CRITICAL"
        risk_detected = True
        risk_resolved = False
        print(f"🚫 [RISK PROMOTE] is_suitable=False → forced CRITICAL (non-streaming)")

    # If risk was resolved by the recommendation, clear the risk flags
    if risk_resolved:
        risk_detected = False
        risk_severity = None

    # If LLM detected risk, ensure we have warnings
    # Use specific messages based on risk type - NO EMOJIS (UI shows status visually)
    if risk_detected and not warnings:
        risk_description = llm_response.get("risk_description", "")

        # Determine message based on risk type and severity
        if "incompatible" in risk_description.lower() or "mismatch" in risk_description.lower():
            # Configuration incompatibility (e.g., incompatible product+feature)
            warnings.append(f"Configuration Mismatch: {risk_description}" if risk_description else "Configuration Mismatch: Selected options are incompatible.")
        elif "material" in risk_description.lower() or "hygiene" in risk_description.lower() or "corrosion" in risk_description.lower():
            # Material/safety warning (e.g., FZ in hospital)
            warnings.append(f"Material Warning: {risk_description}" if risk_description else "Material Warning: Review material requirements for this application.")
        elif risk_severity == "CRITICAL":
            warnings.append(risk_description if risk_description else "Technical Issue: Product configuration requires review.")
        elif risk_severity == "WARNING":
            warnings.append(risk_description if risk_description else "Review Recommended: Verify specification for this application.")
        else:
            warnings.append(risk_description if risk_description else "Review the recommendation details for potential concerns.")

    # Extract clarification fields (supports both old and new format)
    response_type = llm_response.get("response_type", "FINAL_ANSWER")
    clarification_needed = response_type == "CLARIFICATION_NEEDED" or llm_response.get("clarification_needed", False)
    clarification = None

    # Handle new format: clarification_data
    clar_data = llm_response.get("clarification_data") or llm_response.get("clarification")

    if clarification_needed and clar_data:
        # Deduplicate options by value (case-insensitive)
        raw_opts = clar_data.get("options", [])
        seen_vals = set()
        deduped_opts = []
        for opt in raw_opts:
            val = opt.get("value", "") if isinstance(opt, dict) else str(opt)
            key = val.lower().strip()
            if key and key not in seen_vals:
                seen_vals.add(key)
                deduped_opts.append(opt)

        clarification = ClarificationRequest(
            missing_info=clar_data.get("missing_attribute") or clar_data.get("missing_info", "Missing information"),
            why_needed=clar_data.get("why_needed", "Information required for proper selection"),
            options=[
                ClarificationOption(
                    value=opt.get("value", ""),
                    description=opt.get("description", "")
                )
                for opt in deduped_opts
            ],
            question=clar_data.get("question", "Please provide additional information")
        )

    # Enrich LLM-generated options with display_labels from graph FeatureOption nodes
    if clarification is not None and graph_reasoning_report and graph_reasoning_report.variable_features:
        label_map = {}
        for feat in graph_reasoning_report.variable_features:
            for opt in feat.options:
                val = str(opt.get('value', '')).strip().lower()
                dl = opt.get('display_label') or opt.get('name', '')
                if val and dl:
                    label_map[val] = dl
        if label_map:
            for opt in clarification.options:
                if not opt.display_label:
                    opt.display_label = label_map.get(opt.value.strip().lower())

    # ==========================================================================
    # FALLBACK: Generic Parameter Validator using Graph Variable Features
    # ==========================================================================
    # If LLM didn't provide clarification_data but there are unresolved variable
    # features in the graph, auto-generate clarification from graph data.
    # This fixes the "missing UI widgets for secondary questions" bug.
    #
    # CRITICAL: Check if the feature is ACTUALLY missing from context first!
    # Don't ask for data we already have (housing_length derivable from depth).
    if clarification is None and graph_reasoning_report and graph_reasoning_report.variable_features:
        unresolved = graph_reasoning_report.variable_features
        truly_unresolved = []

        for feat in unresolved:
            param_name = feat.parameter_name.lower()

            # Check if this is already in resolved_context
            is_already_known = False

            # Housing length / filter depth are derivable from each other
            if 'length' in param_name or 'długość' in param_name:
                if resolved_context.get('housing_length') or resolved_context.get('length'):
                    is_already_known = True
                    print(f"   ✅ [SKIP] {feat.feature_name} already known: {resolved_context.get('housing_length') or resolved_context.get('length')}")
                elif resolved_context.get('filter_depth') or resolved_context.get('depth'):
                    # Depth is known -> length is derivable
                    is_already_known = True
                    print(f"   ✅ [SKIP] {feat.feature_name} derivable from depth: {resolved_context.get('filter_depth') or resolved_context.get('depth')}")

            # Airflow
            if 'airflow' in param_name or 'przepływ' in param_name:
                if resolved_context.get('airflow') or resolved_context.get('airflow_m3h'):
                    is_already_known = True
                    print(f"   ✅ [SKIP] {feat.feature_name} already known: {resolved_context.get('airflow')}")

            # Material
            if 'material' in param_name:
                if resolved_context.get('material'):
                    is_already_known = True
                    print(f"   ✅ [SKIP] {feat.feature_name} already known: {resolved_context.get('material')}")

            # Width / Height / Dimensions
            if any(term in param_name for term in ['width', 'height', 'dimension', 'wymiar', 'size']):
                if (resolved_context.get('housing_size') or resolved_context.get('housing_width')
                        or resolved_context.get('dimensions') or resolved_context.get('width')):
                    is_already_known = True
                    print(f"   ✅ [SKIP] {feat.feature_name} already known from dimensions")

            if not is_already_known:
                truly_unresolved.append(feat)

        if truly_unresolved:
            # Take the first truly unresolved feature
            feat = truly_unresolved[0]
            print(f"\n⚠️ [FALLBACK] LLM didn't provide clarification_data, using graph variable feature: {feat.feature_name}")

            # Build options from graph data
            options = []
            for opt in feat.options:
                # Prefer display_label for UX, fall back to name/value
                label = opt.get('display_label') or opt.get('name', opt.get('value', ''))
                value = opt.get('value', '')
                benefit = opt.get('benefit', '')
                is_recommended = opt.get('is_recommended', False)

                description = label
                if benefit:
                    description = f"{label} - {benefit}"
                if is_recommended:
                    description = f"{label} (Recommended)"

                options.append(ClarificationOption(
                    value=value,
                    description=description,
                    display_label=label
                ))

            # Airflow enrichment skipped in non-streaming path (no technical_state)

            clarification = ClarificationRequest(
                missing_info=feat.parameter_name,
                why_needed=feat.why_needed or f"Required to complete {feat.feature_name} selection",
                options=options,
                question=feat.question or f"Please select {feat.feature_name}"
            )
            clarification_needed = True
            print(f"   Generated clarification with {len(options)} options")
        else:
            print(f"   ✅ [FALLBACK SKIPPED] All variable features are already resolved in context")

    # Handle entity_card (new format) vs product_card (old format)
    # Supports both single card (dict) and multi-card array (assembly)
    entity_card_data = llm_response.get("entity_card") or llm_response.get("product_card")
    product_cards = []

    # Defense-in-depth: suppress product cards when engine says product is NOT suitable
    _is_blocked = (
        graph_reasoning_report
        and graph_reasoning_report.suitability
        and not graph_reasoning_report.suitability.is_suitable
    )
    if _is_blocked:
        print(f"🚫 [BLOCK GUARD] Product cards suppressed (non-streaming): is_suitable=False")

    if entity_card_data and not clarification_needed and not _is_blocked:
        cards = entity_card_data if isinstance(entity_card_data, list) else [entity_card_data]
        for cd in cards:
            if isinstance(cd, dict):
                # Strip null/None values from specs
                raw_specs = cd.get("specs", {})
                clean_specs = {
                    k: v for k, v in raw_specs.items()
                    if v is not None and str(v).lower() != "null"
                } if isinstance(raw_specs, dict) else raw_specs
                product_cards.append(ProductCard(
                    title=cd.get("title", ""),
                    specs=clean_specs,
                    warning=cd.get("warning"),
                    confidence=cd.get("confidence", "medium"),
                    actions=cd.get("actions", ["Add to Quote"])
                ))
        # v4.1: Deduplicate product cards
        if len(product_cards) > 1:
            seen_keys = set()
            deduped = []
            for pc in product_cards:
                dedup_key = (pc.specs.get("Product Code") if pc.specs else None) or pc.title or ""
                if dedup_key and dedup_key in seen_keys:
                    print(f"🗑️ [DEDUP] Removed duplicate product card: {dedup_key}")
                    continue
                seen_keys.add(dedup_key)
                deduped.append(pc)
            product_cards = deduped

        product_card = product_cards[0] if product_cards else None

    # Build product pivot info if physics override occurred
    product_pivot_info = None
    if graph_reasoning_report and graph_reasoning_report.product_pivot:
        from models import ProductPivotInfo
        pivot = graph_reasoning_report.product_pivot
        product_pivot_info = ProductPivotInfo(
            original_product=pivot.original_product,
            pivoted_to=pivot.pivoted_to,
            reason=pivot.reason,
            physics_explanation=pivot.physics_explanation,
            user_misconception=pivot.user_misconception,
            required_feature=pivot.required_feature
        )
        # If pivot occurred, ensure risk is flagged
        risk_detected = True
        risk_severity = "CRITICAL"

    return DeepExplainableResponse(
        reasoning_summary=reasoning_steps,
        content_segments=content_segments,
        product_card=product_card,
        product_cards=product_cards,
        risk_detected=risk_detected,
        risk_severity=risk_severity,
        risk_resolved=risk_resolved,
        product_pivot=product_pivot_info,
        clarification_needed=clarification_needed,
        clarification=clarification,
        query_language=intent.language,
        confidence_level="high" if config_results.get("variants") else "medium",
        policy_warnings=warnings,
        graph_facts_count=graph_facts,
        inference_count=inferences,
        timings=timings
    )


def query_deep_explainable_streaming(user_query: str, session_id: str = None, model: str = None, user_id: str = "default"):
    """Streaming version of deep explainable query with real-time inference chain.

    Yields SSE events showing the actual reasoning process:
    - Intent detection with discovered context
    - Domain rule matching (e.g., Hospital -> VDI 6022)
    - Guardian risk detection (e.g., FZ vs C5 conflict)
    - Product matching and sizing
    - Final recommendation

    Each yield is a dict with: {"type": "inference", "step": "...", "detail": "...", "data": {...}}

    Args:
        user_query: The user's question
        session_id: Optional session ID for Layer 4 graph state persistence
    """
    import json
    from models import (
        DeepExplainableResponse, ReasoningSummaryStep, ContentSegment, ProductCard,
        ClarificationRequest, ClarificationOption
    )
    from concurrent.futures import ThreadPoolExecutor, as_completed

    config = get_config()
    model = model or DEFAULT_MODEL

    # Layer 4: Session Graph Manager (if session_id provided)
    session_graph_mgr = None
    if session_id:
        try:
            session_graph_mgr = db.get_session_graph_manager()
            session_graph_mgr.ensure_session(session_id, user_id=user_id)
        except Exception as e:
            logger.warning(f"Session graph init failed (non-fatal): {e}")
    timings = {}
    total_start = time.time()

    # Dimension constraint variables — extracted early so they're available for
    # resolved_context + engine sizing. Actual regex extraction follows query_lower init.
    user_max_width_mm = None
    user_max_height_mm = None
    user_max_length_mm = None

    # ============================================================
    # SIMPLIFIED STREAMING: 5 Key Steps Only
    # ============================================================

    # STEP 1: CONTEXT DETECTION (combines intent + application)
    yield {"type": "inference", "step": "context", "status": "active",
           "detail": "🔍 Analyzing project context..."}

    t1 = time.time()

    # Check if full state is present (if so, we should NOT create new entities)
    has_full_state = bool(re.search(r'\[STATE:\s*\{', user_query, re.IGNORECASE))

    # v4.0: Scribe-first pipeline. Product family and other fields are set by Scribe.
    # These will be populated by Scribe merge or regex fallback below.
    detected_product_family = None
    multi_entity_context = ""
    dimension_mappings = []

    timings["intent"] = time.time() - t1

    # ============================================================
    # TECHNICAL STATE MANAGER: Cumulative Engineering Specification
    # ============================================================
    # This replaces simple variable locking with a full state manager
    # that tracks per-tag specifications and never forgets parameters.

    # Initialize state: try graph first (Layer 4), then fall back to frontend state
    technical_state = TechnicalState()

    if session_graph_mgr and session_id:
        try:
            graph_state = session_graph_mgr.get_project_state(session_id)
            if graph_state.get("tags") or graph_state.get("project"):
                technical_state = TechnicalState.load_from_graph(session_graph_mgr, session_id)
                print(f"🔒 [GRAPH STATE] Loaded {len(technical_state.tags)} tags from Layer 4")
        except Exception as e:
            logger.warning(f"Graph state load failed (non-fatal): {e}")

    # v3.0: Store user turn in Layer 4 for Scribe conversation history
    if session_graph_mgr and session_id:
        try:
            session_graph_mgr.store_turn(
                session_id, "user", user_query, technical_state.turn_count + 1
            )
        except Exception as e:
            logger.warning(f"Failed to store user turn (non-fatal): {e}")

    # Parse locked context from frontend [LOCKED: material=RF; project=Nouryon; filter_depths=292,600]
    # Also check for full technical state JSON
    locked_match = re.search(r'\[LOCKED:\s*([^\]]+)\]', user_query, re.IGNORECASE)

    # BUGFIX: Use greedy match for nested JSON - find [STATE: then match until the last } before ]
    state_json_match = re.search(r'\[STATE:\s*(\{.+\})\]', user_query, re.IGNORECASE | re.DOTALL)

    if state_json_match:
        # Full state JSON provided - deserialize it
        try:
            state_dict = json.loads(state_json_match.group(1))
            technical_state = TechnicalState.from_dict(state_dict)
            print(f"🔒 [STATE] Restored full technical state with {len(technical_state.tags)} tags")
            # BUGFIX: Validate restored state has expected data
            for tag_id, tag in technical_state.tags.items():
                depth_status = f"depth={tag.filter_depth}mm" if tag.filter_depth else "NO DEPTH"
                airflow_status = f"airflow={tag.airflow_m3h}" if tag.airflow_m3h else "NO AIRFLOW"
                print(f"   📋 Tag {tag_id}: {tag.filter_width}x{tag.filter_height}, {depth_status}, {airflow_status}, complete={tag.is_complete}")
        except json.JSONDecodeError as e:
            print(f"⚠️ [STATE] Failed to parse state JSON: {e}, falling back to locked context")

    if locked_match and not state_json_match:
        locked_str = locked_match.group(1)
        print(f"🔒 [ENTITY LOCK] Parsing locked context from frontend: {locked_str}")

        # Parse material
        mat_match = re.search(r'material=(\w+)', locked_str)
        if mat_match:
            technical_state.lock_material(mat_match.group(1).upper())
            print(f"   📌 Material locked: {technical_state.locked_material}")

        # Parse project
        proj_match = re.search(r'project=([^;]+)', locked_str)
        if proj_match:
            technical_state.set_project(proj_match.group(1).strip())
            print(f"   📌 Project locked: {technical_state.project_name}")

        # Parse filter depths (legacy format)
        depths_match = re.search(r'filter_depths=([\d,]+)', locked_str)
        if depths_match:
            locked_depths = [int(d) for d in depths_match.group(1).split(',') if d]
            print(f"   📌 Filter depths from lock: {locked_depths}")

        # BUGFIX: Parse dimensions from locked context (e.g., dimensions=305x610x150,610x610x292)
        # GUARD: Skip creating bare item_N tags when assembly state already exists
        # (assembly stage tags already carry their dimensions from create_assembly_tags)
        dims_match = re.search(r'dimensions=([\d,x]+)', locked_str, re.IGNORECASE)
        if dims_match and not technical_state.assembly_group:
            dims_str = dims_match.group(1)
            for i, dim in enumerate(dims_str.split(',')):
                parts = dim.lower().split('x')
                if len(parts) >= 2:
                    tag_id = f"item_{i + 1}"
                    technical_state.merge_tag(
                        tag_id,
                        filter_width=int(parts[0]) if parts[0] else None,
                        filter_height=int(parts[1]) if parts[1] else None,
                        filter_depth=int(parts[2]) if len(parts) > 2 and parts[2] else None
                    )
                    print(f"   📌 Parsed dimensions for {tag_id}: {dim}")

    # Remove the [LOCKED: ...] and [STATE: ...] from query for processing
    user_query = re.sub(r'\s*\[LOCKED:[^\]]+\]', '', user_query).strip()
    user_query = re.sub(r'\s*\[STATE:\s*\{.+\}\s*\]', '', user_query, flags=re.IGNORECASE | re.DOTALL).strip()
    query_lower = user_query.lower()

    # Clean query for extraction (sanitization, not intent detection)
    clean_query_for_extraction = re.sub(r'\[LOCKED:[^\]]+\]', '', user_query, flags=re.IGNORECASE)
    clean_query_for_extraction = re.sub(r'\[STATE:\s*\{.+\}\]', '', clean_query_for_extraction, flags=re.IGNORECASE | re.DOTALL)

    # =========================================================================
    # SEMANTIC SCRIBE: LLM-based intent extraction (v4.0 — SOLE PRIMARY)
    # Scribe runs FIRST. All extraction (dimensions, airflow, material,
    # constraints, product family, accessories, project, action intent)
    # is done by LLM. Regex is ONLY a post-Scribe fallback safety net.
    # =========================================================================
    scribe_intent = None
    scribe_succeeded = False
    try:
        yield {"type": "inference", "step": "scribe", "status": "active",
               "detail": "Analyzing intent..."}

        recent_turns = []
        if session_graph_mgr and session_id:
            try:
                recent_turns = session_graph_mgr.get_recent_turns(session_id, n=3)
            except Exception:
                pass  # Non-fatal: Scribe works without history

        scribe_intent = extract_semantic_intent(
            query=clean_query_for_extraction,
            recent_turns=recent_turns,
            technical_state=technical_state,
            db=db,
            model=model,
        )

        if scribe_intent:
            scribe_intent = resolve_derived_actions(scribe_intent, technical_state)
            _merge_scribe_into_state(scribe_intent, technical_state, detected_product_family or "")
            scribe_succeeded = bool(
                scribe_intent.entities or scribe_intent.clarification_answers or scribe_intent.actions
            )
            # Scribe is primary for family detection (v3.3): override regex-detected family
            for _ent in scribe_intent.entities:
                if _ent.product_family:
                    detected_product_family = _ent.product_family
                    technical_state.detected_family = _ent.product_family
                    print(f"🧠 [SCRIBE] Family override: {detected_product_family}")
                    break
            # Sync airflow to resolved_params (use FIRST tag's airflow for cross-turn continuity)
            for _tid, _tag in technical_state.tags.items():
                if _tag.airflow_m3h:
                    technical_state.resolved_params["airflow_m3h"] = str(_tag.airflow_m3h)
                    break
            n_entities = len(scribe_intent.entities)
            n_actions = len(scribe_intent.actions)
            n_hints = len(scribe_intent.context_hints)
            n_clar = len(scribe_intent.clarification_answers)
            print(f"🧠 [SCRIBE] Extracted {n_entities} entities, "
                  f"{n_actions} actions, {n_hints} context hints, "
                  f"{n_clar} clarification answers")

        # Report the CUMULATIVE count of resolved parameters (from state), not the
        # number of derivations in this single turn — otherwise a continuation turn
        # (e.g. answering "750mm") shows a misleading "Resolved 0 derived values".
        _resolved_keys = set()
        for _k, _v in (technical_state.resolved_params or {}).items():
            if _v is not None and str(_v).strip().lower() not in ("", "none"):
                _resolved_keys.add(_k.lower())
        for _tag in technical_state.tags.values():
            if getattr(_tag, "airflow_m3h", None):
                _resolved_keys.add("airflow")
            if getattr(_tag, "housing_width", None) and getattr(_tag, "housing_height", None):
                _resolved_keys.add("dimensions")
            if getattr(_tag, "housing_length", None):
                _resolved_keys.add("housing_length")
            if getattr(_tag, "product_family", None):
                _resolved_keys.add("product_family")
        if getattr(technical_state, "locked_material", None):
            _resolved_keys.add("material")
        _n_resolved = len(_resolved_keys)
        yield {"type": "inference", "step": "scribe", "status": "done",
               "detail": f"Resolved {_n_resolved} parameter{'s' if _n_resolved != 1 else ''}"}

    except Exception as e:
        logger.warning(f"Scribe extraction failed (regex safety net): {e}")
        yield {"type": "inference", "step": "scribe", "status": "done",
               "detail": "Scribe failed — regex safety net active"}

    # =========================================================================
    # REGEX FALLBACK: Only fires for fields Scribe did NOT extract (v4.0)
    # =========================================================================

    # Fallback: entity codes + product family
    if scribe_intent and scribe_intent.entity_codes:
        entity_codes = scribe_intent.entity_codes
    else:
        entity_codes = extract_entity_codes(user_query)
        if entity_codes:
            print(f"🔄 [FALLBACK] Entity codes from regex: {entity_codes}")

    # Product family from Scribe entities (already set above in merge), then entity codes
    if not detected_product_family:
        _pf_cfg2 = get_config()
        _pf_families2 = _pf_cfg2.product_families or []
        for code in entity_codes:
            for family in _pf_families2:
                if family in code.upper():
                    detected_product_family = family.replace('-', '_')
                    print(f"🔄 [FALLBACK] Product family from entity codes: {detected_product_family}")
                    break
            if detected_product_family:
                break

    # Set detected product family on state
    if detected_product_family:
        technical_state.detected_family = detected_product_family
    # Graph-driven fallback: on continuation turns (button clicks, bare answers),
    # the query text may not contain a product code. Read the active product family
    # from the Graph (Layer 4), which was persisted in the previous turn.
    elif technical_state.detected_family:
        detected_product_family = technical_state.detected_family
        print(f"🔄 [GRAPH STATE] Active product family from Layer 4: {detected_product_family}")

    # Fallback: material (only if Scribe didn't extract it)
    if not technical_state.locked_material:
        detected_material = extract_material_from_query(user_query)
        if detected_material:
            technical_state.lock_material(detected_material)
            print(f"🔄 [FALLBACK] Material from regex: {detected_material}")

    # =========================================================================
    # CORROSION CLASS → MATERIAL RESOLUTION (graph-driven)
    # When Scribe extracted required_corrosion_class (not a material code),
    # resolve to available materials for the detected product family from graph.
    # =========================================================================
    _req_corr_class = technical_state.resolved_params.get("required_corrosion_class")
    if _req_corr_class and not technical_state.locked_material and detected_product_family:
        _fam_id = f"FAM_{detected_product_family}" if not detected_product_family.startswith("FAM_") else detected_product_family
        _matching_materials = db.get_materials_by_corrosion_class(_fam_id, _req_corr_class)
        if _matching_materials:
            if len(_matching_materials) == 1:
                # Single match → auto-lock
                _auto_mat = _matching_materials[0]["code"]
                # Strip MAT_ prefix if present
                if _auto_mat.startswith("MAT_"):
                    _auto_mat = _auto_mat[4:]
                technical_state.lock_material(_auto_mat)
                print(f"✅ [CORROSION→MATERIAL] {_req_corr_class} → auto-resolved to {_auto_mat} "
                      f"(only available {_req_corr_class}+ material for {detected_product_family})")
            else:
                # Multiple matches → store for LLM to present options, pick cheapest default
                _mat_names = [f"{m['code']} ({m['name']}, {m.get('corrosion_class', '?')})" for m in _matching_materials]
                print(f"ℹ️ [CORROSION→MATERIAL] {_req_corr_class} → {len(_matching_materials)} materials available: {', '.join(_mat_names)}")
                # Store as context for the LLM prompt
                technical_state.resolved_params["corrosion_material_options"] = [
                    {"code": m["code"].replace("MAT_", ""), "name": m["name"], "class": m.get("corrosion_class", "")}
                    for m in _matching_materials
                ]
        else:
            print(f"⚠️ [CORROSION→MATERIAL] No materials meeting {_req_corr_class} available for {detected_product_family}")
            technical_state.resolved_params["corrosion_no_match"] = _req_corr_class

    # Fallback: project name (only if Scribe didn't extract it)
    if not technical_state.project_name:
        detected_project = extract_project_from_query(user_query)
        if detected_project:
            technical_state.set_project(detected_project)
            print(f"🔄 [FALLBACK] Project from regex: {detected_project}")

    # Fallback: airflow (only if Scribe didn't extract it into any tag or resolved_params)
    _any_tag_has_airflow = any(tag.airflow_m3h for tag in technical_state.tags.values())
    if not _any_tag_has_airflow and not technical_state.resolved_params.get("airflow_m3h"):
        _q_normalized = re.sub(r'(\d)[,\s](\d{3})', r'\1\2', clean_query_for_extraction)
        _airflow_match = re.search(r'(\d{3,6})\s*m[³3]?\/?h', _q_normalized, re.IGNORECASE)
        if _airflow_match:
            _airflow_val = int(_airflow_match.group(1))
            if 500 <= _airflow_val <= 100000:
                if technical_state.tags:
                    for _tid in technical_state.tags:
                        technical_state.merge_tag(_tid, airflow_m3h=_airflow_val)
                        break
                technical_state.resolved_params["airflow_m3h"] = str(_airflow_val)
                print(f"🔄 [FALLBACK] Airflow from regex: {_airflow_val} m³/h")

    # Fallback: tags/dimensions (only if Scribe failed entirely)
    if not scribe_succeeded and not technical_state.tags:
        print(f"⚠️ [SAFETY NET] Scribe produced no results — falling back to regex extraction")
        extracted_tags = extract_tags_from_query(clean_query_for_extraction.strip())
        for tag_data in extracted_tags:
            if technical_state.assembly_group:
                target_tid = None
                for stage in technical_state.assembly_group.get("stages", []):
                    if stage.get("role") == "TARGET":
                        target_tid = stage["tag_id"]
                        break
                if not target_tid:
                    stages = technical_state.assembly_group.get("stages", [])
                    target_tid = stages[-1]["tag_id"] if stages else None
                if target_tid and target_tid in technical_state.tags:
                    technical_state.merge_tag(
                        target_tid,
                        filter_width=tag_data.get("filter_width"),
                        filter_height=tag_data.get("filter_height"),
                        filter_depth=tag_data.get("filter_depth"),
                        airflow_m3h=tag_data.get("airflow_m3h"),
                        product_family=detected_product_family
                    )
                    print(f"🔒 [SAFETY NET] Assembly: merged into TARGET tag {target_tid}")
                    technical_state._sync_assembly_params()
                continue

            if tag_data.get("tag_id"):
                tag_id = tag_data["tag_id"]
            elif not technical_state.tags:
                tag_id = f"item_{len(technical_state.tags) + 1}"
            elif len(technical_state.tags) == 1:
                tag_id = list(technical_state.tags.keys())[0]
            else:
                continue
            technical_state.merge_tag(
                tag_id,
                filter_width=tag_data.get("filter_width"),
                filter_height=tag_data.get("filter_height"),
                filter_depth=tag_data.get("filter_depth"),
                airflow_m3h=tag_data.get("airflow_m3h"),
                product_family=detected_product_family
            )
            print(f"🔒 [SAFETY NET] Merged tag {tag_id}: {tag_data}")

    # ============================================================
    # DIMENSION VALIDATION: Snap non-standard sizes to nearest catalog module
    # ============================================================
    # Graph-driven — no hardcoded sizes.
    for tag_id, tag in technical_state.tags.items():
        if tag.housing_width and tag.housing_height:
            _w, _h = tag.housing_width, tag.housing_height
            pf = tag.product_family or detected_product_family or technical_state.detected_family
            if pf:
                pf_id = f"FAM_{pf}" if pf and not pf.startswith("FAM_") else pf
                avail = db.get_available_dimension_modules(pf_id)
                if avail:
                    exact = any(m["width_mm"] == _w and m["height_mm"] == _h for m in avail)
                    if not exact:
                        nearest = min(
                            avail,
                            key=lambda m: ((m["width_mm"] - _w) ** 2 + (m["height_mm"] - _h) ** 2)
                        )
                        nw, nh = nearest["width_mm"], nearest["height_mm"]
                        print(
                            f"⚠️ [VALIDATION] Non-standard size {_w}x{_h}mm for {pf}. "
                            f"Snapping to nearest catalog module: {nw}x{nh}mm"
                        )
                        technical_state.merge_tag(
                            tag_id,
                            housing_width=nw,
                            housing_height=nh,
                            filter_width=nw,
                            filter_height=nh,
                        )

    print(f"🔍 [EXTRACTION] Result: {[(t.tag_id, t.airflow_m3h, t.housing_width, t.housing_height) for t in technical_state.tags.values()]}")

    # ============================================================
    # MULTI-ENTITY CONTEXT: Build from TechnicalState tags (post-extraction)
    # ============================================================
    if len(technical_state.tags) > 1:
        weight_data = {}
        for tag_id, tag in technical_state.tags.items():
            if tag.housing_width and tag.housing_height:
                size = f"{tag.housing_width}x{tag.housing_height}"
                length = tag.housing_length or 550
                _default_pf = get_config().default_product_family
                pf = tag.product_family or detected_product_family or _default_pf
                variant_name = f"{pf}-{size}-{length}"
                try:
                    weight_result = db.get_variant_weight(variant_name)
                    if weight_result:
                        weight_data[variant_name] = weight_result
                except Exception:
                    pass

        multi_entity_context = "\n## MULTI-ENTITY REQUEST DETECTED\n\n"
        multi_entity_context += "The user has provided multiple Tags/Items. Handle EACH SEPARATELY in your response.\n\n"
        multi_entity_context += "## WEIGHT DATA (FROM GRAPH - USE EXACTLY):\n"
        for variant, weight in weight_data.items():
            multi_entity_context += f"- {variant}: **{weight} kg**\n"
        if not weight_data:
            multi_entity_context += "- No weight data available in database\n"
        multi_entity_context += "\n"

        for tag_id, tag in technical_state.tags.items():
            if tag.housing_width and tag.housing_height:
                size = f"{tag.housing_width}x{tag.housing_height}"
                length = tag.housing_length or 550
                pf = tag.product_family or detected_product_family or _default_pf
                variant_name = f"{pf}-{size}-{length}"
                weight = weight_data.get(variant_name, "See datasheet")
                filter_dims = f"{tag.filter_width}x{tag.filter_height}"
                if tag.filter_depth:
                    filter_dims += f"x{tag.filter_depth}"

                multi_entity_context += f"### {tag_id}:\n"
                multi_entity_context += f"- **Filter dimensions:** {filter_dims}mm\n"
                multi_entity_context += f"- **Mapped housing size:** {size}mm\n"
                multi_entity_context += f"- **Recommended variant:** {variant_name}\n"
                multi_entity_context += f"- **VERIFIED WEIGHT:** {weight} kg\n"
                multi_entity_context += f"- **Width (horizontal):** {tag.housing_width} mm\n"
                multi_entity_context += f"- **Height (vertical):** {tag.housing_height} mm\n"
                if tag.housing_length:
                    multi_entity_context += f"- **Auto-selected length:** {tag.housing_length}mm"
                    if tag.filter_depth:
                        multi_entity_context += f" (based on {tag.filter_depth}mm filter depth)"
                    multi_entity_context += "\n"
                multi_entity_context += "\n"

        multi_entity_context += "**CRITICAL:** Use the EXACT weight values listed above. Do NOT invent weights.\n"

    # Accessories: Scribe is primary (already merged above), regex fallback.
    # An empty scribe_intent.accessories list is a valid LLM answer ("no
    # accessories mentioned"), NOT a signal that Scribe failed — only fall
    # back to regex when Scribe genuinely didn't produce a result at all.
    if scribe_intent is not None:
        for acc in scribe_intent.accessories:
            if acc not in technical_state.accessories:
                technical_state.accessories.append(acc)
                print(f"🧠 [SCRIBE] Accessory: {acc}")
    else:
        extracted_accessories = extract_accessories_from_query(user_query)
        if extracted_accessories:
            for acc in extracted_accessories:
                if acc not in technical_state.accessories:
                    technical_state.accessories.append(acc)
                    print(f"🔄 [FALLBACK] Accessory from regex: {acc}")

    # =========================================================================
    # MATERIAL AVAILABILITY VALIDATION: Check if locked material is available
    # for the detected product family. If not, warn and suggest alternatives.
    # =========================================================================
    material_availability_warning = None
    _unavailable_material_code = None
    _available_material_names = []
    if technical_state.locked_material and detected_product_family:
        _mat_code = technical_state.locked_material
        _fam_id = f"FAM_{detected_product_family}" if not detected_product_family.startswith("FAM_") else detected_product_family
        _available_mats = db.get_available_materials(_fam_id)
        if _available_mats:
            _mat_ids = [m["id"] for m in _available_mats]
            if f"MAT_{_mat_code}" not in _mat_ids:
                _available_material_names = [m["name"] for m in _available_mats]
                _unavailable_material_code = _mat_code
                material_availability_warning = (
                    f"⚠️ MATERIAL NOT AVAILABLE: {_mat_code} is NOT available for "
                    f"{detected_product_family}. "
                    f"Available materials: {', '.join(_available_material_names)}."
                )
                print(f"⚠️ [VALIDATION] {material_availability_warning}")
                # UNLOCK the unavailable material so the system doesn't proceed with it
                technical_state.locked_material = None
                print(f"🔓 [VALIDATION] Unlocked unavailable material {_mat_code}")
        else:
            print(f"ℹ️ [VALIDATION] No AVAILABLE_IN_MATERIAL links for {_fam_id} — skipping material check")

    # Increment turn count
    technical_state.turn_count += 1

    # =========================================================================
    # FINAL TURN ENRICHMENT: Look up weights when all tags are complete
    # =========================================================================
    if technical_state.all_tags_complete():
        print(f"✅ [STATE] All {len(technical_state.tags)} tags complete - enriching with weights")
        technical_state.enrich_with_weights(db)

    # Verify material codes (only when all tags complete)
    if technical_state.all_tags_complete():
        material_warnings = technical_state.verify_material_codes()
        for warning in material_warnings:
            print(f"⚠️ [STATE] {warning}")
        # v4.2: Also enforce available materials when no material is locked
        avail_warnings = technical_state.enforce_available_materials(db)
        for warning in avail_warnings:
            print(f"⚠️ [STATE] {warning}")

    # Build locked context for backwards compatibility
    locked_material = technical_state.locked_material if technical_state.locked_material else None
    locked_project = technical_state.project_name
    locked_depths = []
    for tag in technical_state.tags.values():
        if tag.filter_depth and tag.filter_depth not in locked_depths:
            locked_depths.append(tag.filter_depth)

    # NOTE: locked_context is built AFTER product code rebuild (see below, after line ~4642)
    # to ensure the LLM receives the final product codes with housing_length included.
    locked_context = ""

    # Check if user asked for weight/drawings/etc
    user_asked_for_weight = any(w in query_lower for w in ['weight', 'weights', 'waga', 'masa', 'kg'])
    user_asked_for_drawings = any(w in query_lower for w in ['drawing', 'drawings', 'cad', 'rysunek'])

    additional_data_context = ""
    if user_asked_for_weight:
        additional_data_context += "\n**USER ASKED FOR WEIGHT:** Include assembly weight in your response for each product.\n"
    if user_asked_for_drawings:
        additional_data_context += "\n**USER ASKED FOR DRAWINGS:** Mention drawing/CAD availability.\n"

    # Transition piece advisory: if round duct detected, inject explicit scope-of-delivery reminder
    _round_duct_accs = [a for a in technical_state.accessories if "Round duct" in a]
    if _round_duct_accs:
        _duct_desc = ", ".join(_round_duct_accs)
        additional_data_context += (
            f"\n**⚠️ TRANSITION PIECE REQUIRED:** The customer has a round duct ({_duct_desc}). "
            f"The housing has rectangular connections. A transition piece (PT flat or TT conical) "
            f"is required and must be ordered SEPARATELY — it is NOT included with the housing. "
            f"You MUST mention this to the customer.\n"
        )

    # ============================================================
    # DIMENSION CONSTRAINTS: Read from Scribe-extracted resolved_params
    # (No regex — Scribe is the sole extractor)
    # ============================================================
    if technical_state.resolved_params.get("max_width_mm"):
        user_max_width_mm = int(technical_state.resolved_params["max_width_mm"])
        print(f"📏 [CONSTRAINT] max_width_mm = {user_max_width_mm}mm")

    if technical_state.resolved_params.get("max_height_mm"):
        user_max_height_mm = int(technical_state.resolved_params["max_height_mm"])
        print(f"📏 [CONSTRAINT] max_height_mm = {user_max_height_mm}mm")

    if technical_state.resolved_params.get("max_length_mm"):
        user_max_length_mm = int(technical_state.resolved_params["max_length_mm"])

    # Installation constraint extraction — regex fallback (v3.0)
    # Available space (shaft/opening)
    if not technical_state.resolved_params.get("available_space_mm"):
        space_match = re.search(
            r'(?:shaft|opening|gap|available\s+(?:width|space)|fixed\s+width)'
            r'[^0-9]{0,20}?(\d{3,5})\s*(?:mm)?',
            clean_query_for_extraction, re.IGNORECASE
        )
        if space_match:
            technical_state.resolved_params["available_space_mm"] = space_match.group(1)
            print(f"📏 [CONSTRAINT] available_space_mm = {space_match.group(1)}mm (regex fallback)")

    # Installation environment
    if not technical_state.resolved_params.get("installation_environment"):
        _env_cfg = get_config()
        _env_keywords = _env_cfg.fallback_environment_mapping or {
            "outdoor": "ENV_OUTDOOR", "rooftop": "ENV_OUTDOOR", "outside": "ENV_OUTDOOR",
            "roof": "ENV_OUTDOOR", "exterior": "ENV_OUTDOOR",
            "indoor": "ENV_INDOOR", "inside": "ENV_INDOOR",
            "hospital": "ENV_HOSPITAL", "clinic": "ENV_HOSPITAL",
            "pool": "ENV_POOL", "swimming": "ENV_POOL",
            "kitchen": "ENV_KITCHEN", "restaurant": "ENV_KITCHEN",
            "kuchnia": "ENV_KITCHEN", "fryer": "ENV_KITCHEN",
            "atex": "ENV_ATEX", "explosive": "ENV_ATEX",
            "ex zone": "ENV_ATEX", "wybuch": "ENV_ATEX",
            "marine": "ENV_MARINE", "ship": "ENV_MARINE", "cruise": "ENV_MARINE",
            "offshore": "ENV_MARINE", "vessel": "ENV_MARINE", "naval": "ENV_MARINE",
            "pharma": "ENV_PHARMACEUTICAL", "cleanroom": "ENV_PHARMACEUTICAL",
            "wastewater": "ENV_WASTEWATER", "sewage": "ENV_WASTEWATER",
        }
        for kw, env_val in _env_keywords.items():
            if re.search(r'\b' + re.escape(kw) + r'\b', clean_query_for_extraction, re.IGNORECASE):
                technical_state.resolved_params["installation_environment"] = env_val
                print(f"🌍 [CONSTRAINT] installation_environment = {env_val} (regex fallback: '{kw}')")
                break

    # Chlorine ppm (explicit mention)
    if not technical_state.resolved_params.get("chlorine_ppm"):
        chlorine_match = re.search(
            r'(\d{1,4})\s*(?:ppm)?\s*chlorine|chlorine[^0-9]{0,10}?(\d{1,4})\s*(?:ppm)?',
            clean_query_for_extraction, re.IGNORECASE
        )
        if chlorine_match:
            val = chlorine_match.group(1) or chlorine_match.group(2)
            technical_state.resolved_params["chlorine_ppm"] = val
            print(f"🧪 [CONSTRAINT] chlorine_ppm = {val} (regex fallback)")

    # Build resolved_context FROM technical_state only (no query re-parsing)
    t1 = time.time()
    resolved_context = _build_resolved_context(
        technical_state, db,
        user_max_width_mm=user_max_width_mm,
        user_max_height_mm=user_max_height_mm,
    )
    print(f"📋 [GRAPH REASONING] Resolved context for feature check: {resolved_context}")

    # On continuation turns (button clicks / bare answers), the query lacks application
    # context (e.g., "Zone 20" has no "powder coating"). Augment the query with the
    # persisted application name so the engine can re-detect stressors correctly. (v2.8)
    engine_query = user_query
    if technical_state.resolved_params.get("detected_application"):
        app_name = technical_state.resolved_params["detected_application"]
        # Only augment if the application context is NOT already in the query
        if app_name.lower() not in user_query.lower():
            engine_query = f"{user_query} [Application context: {app_name}]"
            print(f"🔄 [GRAPH STATE] Augmented engine query with application: {app_name}")

    # v3.0: Wire Scribe context_hints into engine query for stressor detection
    if scribe_intent and scribe_intent.context_hints:
        hint_str = ", ".join(scribe_intent.context_hints)
        if hint_str.lower() not in engine_query.lower():
            engine_query = f"{engine_query} [Environment context: {hint_str}]"
            print(f"🧠 [SCRIBE] Augmented engine query with context hints: {hint_str}")

    graph_reasoning_report = get_graph_reasoning_report(
        engine_query,
        product_family=detected_product_family,
        context=resolved_context,
        material=technical_state.locked_material if technical_state.locked_material else None,
        accessories=technical_state.accessories or None,
    )
    timings["graph_reasoning"] = time.time() - t1

    # Persist application context for Turn 2+ (v2.8)
    if (hasattr(graph_reasoning_report, 'application')
            and graph_reasoning_report.application
            and not technical_state.resolved_params.get("detected_application")):
        technical_state.resolved_params["detected_application"] = graph_reasoning_report.application.name
        print(f"💾 [STATE] Persisted detected_application={graph_reasoning_report.application.name}")

    # =========================================================================
    # PERSIST DETECTED FAMILY: Even when a gate blocks, the engine identifies
    # the recommended product family. Store it for Turn 2 continuity. (v2.8)
    # =========================================================================
    _has_verdict = hasattr(graph_reasoning_report, '_verdict')
    if _has_verdict and not technical_state.detected_family:
        _v = graph_reasoning_report._verdict
        if _v.recommended_product:
            technical_state.detected_family = _v.recommended_product.product_family_id.replace("FAM_", "")
            detected_product_family = technical_state.detected_family
            print(f"💾 [STATE] Persisted detected_family={technical_state.detected_family} from engine verdict")
        elif _v.is_assembly and _v.assembly:
            # For assemblies, use the TARGET stage's family
            target = next((s for s in _v.assembly if s.role == "TARGET"), None)
            if target:
                technical_state.detected_family = target.product_family_id.replace("FAM_", "")
                detected_product_family = technical_state.detected_family
                print(f"💾 [STATE] Persisted detected_family={technical_state.detected_family} from assembly TARGET")

    # =========================================================================
    # VETO PERSISTENCE: Store vetoed families in Layer 4 (v3.8)
    # Ensures continuation turns don't forget the veto decision.
    # =========================================================================
    if _has_verdict:
        _v = graph_reasoning_report._verdict
        if _v.vetoed_products:
            new_vetoes = [tm.product_family_id for tm in _v.vetoed_products]
            # Merge with previously persisted vetoes (don't lose old ones)
            existing = set(technical_state.vetoed_families)
            for nv in new_vetoes:
                if nv not in existing:
                    technical_state.vetoed_families.append(nv)
            if technical_state.vetoed_families:
                print(f"🚫 [VETO PERSIST] vetoed_families={technical_state.vetoed_families}")

    # =========================================================================
    # ASSEMBLY STATE: Create assembly tags from engine verdict (v2.4)
    # =========================================================================
    _has_verdict = hasattr(graph_reasoning_report, '_verdict')
    logger.info(f"[ASSEMBLY DEBUG] has _verdict: {_has_verdict}, report type: {type(graph_reasoning_report).__name__}")
    if _has_verdict:
        _v = graph_reasoning_report._verdict
        logger.info(f"[ASSEMBLY DEBUG] is_assembly={_v.is_assembly}, assembly={_v.assembly}, assembly_rationale={getattr(_v, 'assembly_rationale', None)}")
    if (_has_verdict
            and graph_reasoning_report._verdict.is_assembly
            and graph_reasoning_report._verdict.assembly):
        verdict = graph_reasoning_report._verdict
        if not technical_state.assembly_group:
            # First time seeing assembly — create stage-prefixed tags
            # Find the base tag: prefer "item_1" (bare), else first non-stage tag
            existing_ids = list(technical_state.tags.keys())
            bare_ids = [tid for tid in existing_ids if '_stage_' not in tid]
            base_id = bare_ids[0] if bare_ids else (existing_ids[0] if existing_ids else "item_1")
            technical_state.create_assembly_tags(verdict.assembly, base_tag_id=base_id)
            technical_state.assembly_group["rationale"] = verdict.assembly_rationale or ""
            logger.info(f"[ASSEMBLY] Created {len(verdict.assembly)} assembly tags from verdict")
            for stage in technical_state.assembly_group["stages"]:
                logger.info(f"   → {stage['role']}: {stage['product_family']} [tag: {stage['tag_id']}]")

        # Cleanup: remove orphan item_N tags that aren't part of the assembly
        assembly_tag_ids = {s["tag_id"] for s in technical_state.assembly_group.get("stages", [])}
        orphan_ids = [tid for tid in list(technical_state.tags.keys())
                      if tid not in assembly_tag_ids and '_stage_' not in tid]
        for oid in orphan_ids:
            del technical_state.tags[oid]
            logger.info(f"[ASSEMBLY] Removed orphan tag: {oid}")

        # Sync shared params every turn
        technical_state._sync_assembly_params()

    # Defense-in-depth: cleanup orphan bare tags even when engine didn't re-detect assembly
    # (e.g., Turn 2 query "3400" might not trigger assembly detection, but LOCKED dims may have leaked item_1)
    if technical_state.assembly_group and technical_state.assembly_group.get("stages"):
        assembly_tag_ids = {s["tag_id"] for s in technical_state.assembly_group["stages"]}
        orphan_ids = [tid for tid in list(technical_state.tags.keys())
                      if tid not in assembly_tag_ids and '_stage_' not in tid]
        for oid in orphan_ids:
            del technical_state.tags[oid]
            logger.info(f"[ASSEMBLY] Defense cleanup: removed orphan tag: {oid}")
        # Sync shared params (dimensions, airflow) across assembly siblings
        technical_state._sync_assembly_params()

        # Apply auto-resolve defaults to each assembly stage's product family
        # (e.g., some products use fixed housing_length from graph)
        for stage in technical_state.assembly_group["stages"]:
            tag_id = stage["tag_id"]
            pf_name = stage.get("product_family", "")
            tag = technical_state.tags.get(tag_id)
            if not tag or not pf_name:
                continue
            try:
                vf_list = db.get_variable_features(pf_name.replace("FAM_", "").split()[0])
                for vf in vf_list:
                    if vf.get("auto_resolve") and vf.get("default_value") is not None:
                        p_name = vf.get("parameter_name", "")
                        if p_name and hasattr(tag, p_name):
                            old_val = getattr(tag, p_name, None)
                            default_val = vf["default_value"]
                            if old_val != default_val:
                                technical_state.merge_tag(tag_id, **{p_name: default_val})
                                logger.info(
                                    f"[ASSEMBLY] Auto-resolved {p_name}={default_val} for "
                                    f"{stage['role']} ({pf_name}) [was {old_val}]"
                                )
            except Exception as e:
                logger.warning(f"[ASSEMBLY] Auto-resolve failed for {pf_name}: {e}")

        # Apply HardConstraint overrides to assembly tags (v3.0b)
        # When engine corrected housing_length_mm for a product,
        # propagate the corrected value to the appropriate assembly stage tags
        if graph_reasoning_report._verdict.constraint_overrides:
            for override in graph_reasoning_report._verdict.constraint_overrides:
                prop_key = override.property_key  # e.g., "housing_length_mm"
                attr_name = prop_key.replace("_mm", "") if prop_key.endswith("_mm") else prop_key
                corrected = int(override.corrected_value) if override.corrected_value else None
                if corrected:
                    for tag_id, tag in technical_state.tags.items():
                        fam_id = f"FAM_{tag.product_family}" if tag.product_family else ""
                        if fam_id == override.item_id and hasattr(tag, attr_name):
                            old_val = getattr(tag, attr_name, None)
                            if old_val != corrected:
                                setattr(tag, attr_name, corrected)
                                print(f"🔒 [CONSTRAINT] {tag_id}: {attr_name} {old_val} → {corrected} (min for {tag.product_family})")

    # =========================================================================
    # SIZING ARRANGEMENT: Apply module dimensions from engine sizing (v2.5)
    # =========================================================================
    if _has_verdict and graph_reasoning_report._verdict.sizing_arrangement:
        sa = graph_reasoning_report._verdict.sizing_arrangement
        # Use effective dimensions (v2.8) which account for vertical stacking
        sa_width = sa.get("effective_width") or sa.get("selected_module_width")
        sa_height = sa.get("effective_height") or sa.get("selected_module_height")
        if sa_width and sa_height:
            # Apply to tags that don't have dimensions yet
            for tag_id, tag in technical_state.tags.items():
                if not tag.housing_width or not tag.housing_height:
                    technical_state.merge_tag(
                        tag_id,
                        housing_width=int(sa_width),
                        housing_height=int(sa_height),
                        filter_width=int(sa_width),
                        filter_height=int(sa_height),
                    )
                    print(
                        f"📏 [SIZING] Applied module {sa_width}×{sa_height}mm "
                        f"to tag {tag_id} (from graph sizing)"
                    )

        # Propagate modules_needed to all tags for multi-module aggregation (v3.0b)
        modules = sa.get("modules_needed", 1)
        if modules > 1:
            for tag_id, tag in technical_state.tags.items():
                tag.modules_needed = modules
            print(f"📏 [SIZING] Propagated modules_needed={modules} to all tags")

        # v3.8: Propagate rated airflow per module from sizing arrangement
        ref_per_module = sa.get("reference_airflow_per_module")
        if ref_per_module:
            for tag_id, tag in technical_state.tags.items():
                tag.rated_airflow_m3h = int(ref_per_module)
            print(f"📏 [SIZING] Set rated_airflow_m3h={int(ref_per_module)} on all tags")

    # =========================================================================
    # PER-STAGE SIZING: Graph-driven DimensionModule selection for assemblies (v2.7)
    # =========================================================================
    # When assembly exists and stages still lack dimensions (engine sizing may have
    # used a different product family), compute sizing per-stage using each stage's
    # own product family and the graph's DimensionModule data. Domain-agnostic.
    if technical_state.assembly_group and technical_state.assembly_group.get("stages"):
        _any_unsized = any(
            technical_state.tags.get(s["tag_id"]) and
            not technical_state.tags[s["tag_id"]].housing_width
            for s in technical_state.assembly_group["stages"]
            if s["tag_id"] in technical_state.tags
        )
        if _any_unsized:
            try:
                _sizing_engine = _get_trait_engine()
                for stage in technical_state.assembly_group["stages"]:
                    tag = technical_state.tags.get(stage["tag_id"])
                    if not tag or (tag.housing_width and tag.housing_height):
                        continue  # Already has dimensions
                    pf = stage.get("product_family", "")
                    pf_id = f"FAM_{pf}" if pf and not pf.startswith("FAM_") else pf
                    if not pf_id:
                        continue
                    sa = _sizing_engine.compute_sizing_arrangement(pf_id, resolved_context)
                    # Use effective dimensions (v2.8) which account for stacking
                    eff_w = sa.get("effective_width") or sa.get("selected_module_width") if sa else None
                    eff_h = sa.get("effective_height") or sa.get("selected_module_height") if sa else None
                    if eff_w and eff_h:
                        technical_state.merge_tag(
                            stage["tag_id"],
                            housing_width=int(eff_w),
                            housing_height=int(eff_h),
                            filter_width=int(eff_w),
                            filter_height=int(eff_h),
                        )
                        logger.info(
                            f"[ASSEMBLY] Graph-driven sizing: {eff_w}x"
                            f"{eff_h}mm for {stage['tag_id']}"
                        )
                        break  # Same duct — _sync_assembly_params() propagates to siblings
            except Exception as e:
                logger.warning(f"[ASSEMBLY] Per-stage sizing failed: {e}")

    # =========================================================================
    # POST-ASSEMBLY: Enrich weights + pre-build product codes (v3.0b)
    # Must run AFTER constraints + sizing so housing_length is finalized
    # =========================================================================
    if technical_state.all_tags_complete():
        technical_state.enrich_with_weights(db)

    # Resolve connection_type offset before building product codes
    # If connection_type was auto-resolved by engine or set by Scribe, query the length offset
    _conn_type = technical_state.resolved_params.get("connection_type")
    if not _conn_type:
        # Engine auto-resolves connection_type=PG in its context, mirror to resolved_params
        technical_state.resolved_params["connection_type"] = "PG"
        _conn_type = "PG"
    if "connection_length_offset" not in technical_state.resolved_params:
        _fam_for_conn = technical_state.detected_family or ""
        _fam_id_for_conn = f"FAM_{_fam_for_conn}" if _fam_for_conn and not _fam_for_conn.startswith("FAM_") else _fam_for_conn
        if _fam_id_for_conn:
            _offset = db.get_connection_length_offset(_fam_id_for_conn, _conn_type)
            if _offset:
                technical_state.resolved_params["connection_length_offset"] = str(_offset)
                print(f"🔌 [CONNECTION] {_conn_type} offset: +{_offset}mm")

    # =========================================================================
    # POST-ENGINE MATERIAL RE-VALIDATION: After product pivot or assembly
    # creation, verify locked_material is available for each tag's product
    # family. If not, select the first available material for that tag.
    # This handles pivots (e.g., product A→B where material is not available).
    # =========================================================================
    _mat_code = technical_state.locked_material if technical_state.locked_material else None
    _material_overrides_applied = []
    if _mat_code:
        for _tag_id, _tag in technical_state.tags.items():
            if not _tag.product_family:
                continue
            _fam = _tag.product_family
            _fam_id = f"FAM_{_fam}" if not _fam.startswith("FAM_") else _fam
            _available_mats = db.get_available_materials(_fam_id)
            if not _available_mats:
                continue
            _mat_ids = [m["id"] for m in _available_mats]
            if f"MAT_{_mat_code}" not in _mat_ids:
                # Locked material not available for this tag's product family
                _fallback_code = _available_mats[0]["code"]
                _tag.material_override = _fallback_code
                _available_codes = [m["code"] for m in _available_mats]
                _material_overrides_applied.append(
                    f"{_fam} ({_tag_id}): {_mat_code} not available, using {_fallback_code}. "
                    f"Available: {', '.join(_available_codes)}"
                )
                print(f"⚠️ [MATERIAL] {_mat_code} not available for {_fam}, "
                      f"using {_fallback_code} for {_tag_id}")

    # Pre-build product codes for ALL tags — always rebuild to reflect constraint overrides
    # Runs after constraints so product gets correct housing_length before code is built
    for _tag_id, _tag in technical_state.tags.items():
        if _tag.product_family and _tag.housing_width and _tag.housing_height:
            _fam = _tag.product_family or technical_state.detected_family or ""
            _fam_id = f"FAM_{_fam}" if _fam and not _fam.startswith("FAM_") else _fam
            _code_fmt = db.get_product_family_code_format(_fam_id) if _fam_id else None
            _new_code = technical_state.build_product_code(_tag, code_format=_code_fmt)
            if _new_code and _new_code != _tag.product_code:
                print(f"🏷️ [CODE] {'Rebuilt' if _tag.product_code else 'Pre-built'}: {_tag_id} → {_new_code}")
                _tag.product_code = _new_code

    # =========================================================================
    # Build LOCKED CONTEXT for injection using TechnicalState
    # MUST run AFTER product code rebuild so LLM receives final codes
    # (e.g., FAMILY-600x600-750-..., not FAMILY-600x600-...)
    # =========================================================================
    if technical_state.tags or locked_material or locked_project:
        locked_context = technical_state.to_prompt_context()

        # If all tags are complete, add the B2B response format
        if technical_state.all_tags_complete():
            locked_context += "\n\n## 🎯 READY FOR FINAL RESPONSE - OUTPUT NOW\n"
            locked_context += "**ALL PARAMETERS KNOWN - DO NOT ASK ANY QUESTIONS**\n\n"
            locked_context += "Generate the structured B2B response IMMEDIATELY:\n"
            locked_context += "- One header per Tag with product code and weight\n"
            locked_context += "- Use the EXACT data from the pre-filled table below\n"
            locked_context += "- FORBIDDEN: Asking for dimensions, airflow, or material (all known)\n"
            locked_context += "- FORBIDDEN: Filler phrases like 'let me confirm' or 'I understand you need'\n"
            locked_context += "\n### PRE-COMPUTED ANSWER (USE THIS):\n"
            locked_context += technical_state.generate_b2b_response()

    # Build context message
    context_parts = []
    if detected_product_family:
        context_parts.append(detected_product_family)
    if graph_reasoning_report.application:
        context_parts.append(graph_reasoning_report.application.name)

    context_msg = " + ".join(context_parts) if context_parts else "General inquiry"
    yield {"type": "inference", "step": "context", "status": "done",
           "detail": f"🔍 {context_msg}"}

    # STEP 2: GUARDIAN CHECK — Engine handles technology mismatch via stressor→trait→veto→pivot
    if graph_reasoning_report.suitability.warnings:
        # Material/compliance risk
        warning = graph_reasoning_report.suitability.warnings[0]
        mitigation = getattr(warning, 'mitigation', '')
        yield {"type": "inference", "step": "guardian", "status": "done",
               "detail": f"🛡️ Risk: {mitigation}" if mitigation else "🛡️ Material risk detected"}
    else:
        yield {"type": "inference", "step": "guardian", "status": "done",
               "detail": "🛡️ OK"}

    # ============================================================
    # HOLISTIC VALIDATION: Collect ALL conflicts BEFORE suggestions
    # ============================================================
    # This prevents "sequential disappointment" where we suggest fixing
    # a minor issue when a CRITICAL incompatibility makes it pointless.

    all_conflicts = []  # Collect all conflicts with severity

    # CHECK 1: Accessory Compatibility (HIGHEST PRIORITY)
    # If product + feature is impossible, don't suggest "increase space"
    incompatible_accessories = [
        c for c in graph_reasoning_report.accessory_compatibility
        if not c.is_compatible
    ]
    for compat in incompatible_accessories:
        all_conflicts.append({
            "type": "COMPATIBILITY",
            "severity": "CRITICAL",
            "option": compat.accessory_name,
            "product": compat.product_family,
            "reason": compat.reason,
            "status": compat.status,
            "alternatives": compat.compatible_alternatives,
            "detail": f"❌ {compat.accessory_name} is NOT compatible with {compat.product_family}"
        })
        yield {"type": "inference", "step": "compatibility", "status": "done",
               "detail": f"❌ INCOMPATIBLE: {compat.accessory_name} + {compat.product_family}"}

    # ============================================================
    # GEOMETRIC CONSTRAINT VALIDATION (Physical Space Check)
    # ============================================================

    # ============================================================
    # STEP 0: DETECT RESOLUTION ACTIONS (Context Update Handling)
    # ============================================================
    # Check if this is a follow-up that resolves a previous conflict
    resolution_action = None
    resolution_context = ""

    # Parse Context Update if present
    context_update_match = re.search(r'context update[:\s]+(\w+)\s+is\s+(\w+)', query_lower)
    if context_update_match:
        update_key = context_update_match.group(1)
        update_value = context_update_match.group(2)

        # Handle space increase resolution
        if update_value in ['increase_space', 'increase', '900mm', '900']:
            resolution_action = 'SPACE_INCREASED'
            yield {"type": "inference", "step": "resolution", "status": "done",
                   "detail": "✅ Space constraint updated to 900mm"}

        # Handle Polis removal resolution
        elif update_value in ['no_polis', 'without_polis', 'remove_polis', 'remove']:
            resolution_action = 'POLIS_REMOVED'
            yield {"type": "inference", "step": "resolution", "status": "done",
                   "detail": "✅ Polis option removed from configuration"}

    # (Dimension constraint extraction moved to BEFORE engine call — v2.8)
    # user_max_width_mm and user_max_length_mm already set above.

    # CONSTRAINT OVERWRITER: Apply resolution actions
    if resolution_action == 'SPACE_INCREASED':
        # User agreed to increase space - remove the constraint or set to 900
        user_max_length_mm = None  # No longer constrained
        resolution_context = """
## ✅ CONSTRAINT RESOLVED: Space Increased
The user has confirmed they can accommodate the required housing length for the selected accessory.

**YOU MUST:**
1. DO NOT repeat the geometric conflict warning - it has been resolved
2. Acknowledge the resolution positively and confirm compatibility
3. PROCEED immediately to the next missing parameter
4. Recommend the longer housing variant with the accessory
"""

    elif resolution_action == 'POLIS_REMOVED':
        # User chose to remove Polis - clear it from selected options later
        resolution_context = """
## ✅ CONSTRAINT RESOLVED: Accessory Removed
The user has chosen to remove the accessory option to fit within their space constraint.

**YOU MUST:**
1. DO NOT repeat the geometric conflict warning - it has been resolved
2. Acknowledge the removal and confirm the shorter housing variant fits
3. PROCEED immediately to sizing
4. Ask for the next missing parameter
"""

    # Extract option requests (e.g., "Polis", "after-filter rail", "polishing")
    # Use ordered list to check longest patterns first, avoiding partial matches
    OPTION_PATTERNS = [
        ('after-filter rail', 'Polis'),
        ('after-filter', 'Polis'),
        ('polis', 'Polis'),
        # Add more option patterns here as needed
    ]
    selected_options = set()  # Use set to avoid duplicates
    for pattern, opt_name in OPTION_PATTERNS:
        if pattern in query_lower:
            selected_options.add(opt_name)
    selected_options = list(selected_options)

    # CONSTRAINT OVERWRITER: Remove Polis if user chose that resolution
    if resolution_action == 'POLIS_REMOVED' and 'Polis' in selected_options:
        selected_options.remove('Polis')

    # Check geometric constraints if we have both options and space limits
    # SKIP if a resolution action was just taken (constraint already resolved)
    geometric_conflicts = []
    if selected_options and detected_product_family and not resolution_action:
        geometric_conflicts = get_graph_reasoning_engine().check_geometric_constraints(
            product_family=detected_product_family,
            selected_options=selected_options,
            user_max_length_mm=user_max_length_mm,
            housing_length_mm=750 if '750' in user_query else (900 if '900' in user_query else None)
        )

    # CHECK 2: Geometric Constraints (add to all_conflicts)
    geometric_conflict_context = ""
    if geometric_conflicts:
        for conflict in geometric_conflicts:
            all_conflicts.append({
                "type": "GEOMETRIC",
                "severity": "HIGH",  # Not CRITICAL - can be resolved
                "option": conflict.option_name,
                "required_mm": conflict.required_length_mm,
                "user_limit_mm": conflict.user_max_length_mm,
                "reason": conflict.physics_explanation,
                "detail": f"🛑 {conflict.option_name} requires {conflict.required_length_mm}mm, user has {conflict.user_max_length_mm}mm"
            })
            yield {"type": "inference", "step": "geometry", "status": "done",
                   "detail": f"🛑 GEOMETRIC: '{conflict.option_name}' requires {conflict.required_length_mm}mm"}

    # ============================================================
    # HOLISTIC CONFLICT RESOLUTION: Present ALL issues together
    # ============================================================
    # Rule: Don't suggest "increase space" if there's also a compatibility block
    has_compatibility_block = any(c["type"] == "COMPATIBILITY" for c in all_conflicts)
    has_geometric_block = any(c["type"] == "GEOMETRIC" for c in all_conflicts)

    if all_conflicts:
        # Build combined conflict context for LLM
        conflict_parts = ["## 🛑 MULTIPLE CONFLICTS DETECTED (HOLISTIC VALIDATION)"]
        conflict_parts.append("")

        for i, conflict in enumerate(all_conflicts, 1):
            if conflict["type"] == "COMPATIBILITY":
                conflict_parts.append(f"### Conflict {i}: Mechanical Incompatibility (CRITICAL)")
                conflict_parts.append(f"- **Issue:** {conflict['option']} is NOT compatible with {conflict['product']}")
                conflict_parts.append(f"- **Reason:** {conflict['reason']}")
                if conflict.get('alternatives'):
                    conflict_parts.append(f"- **Compatible products for {conflict['option']}:** {', '.join(conflict['alternatives'])}")
                conflict_parts.append("")

            elif conflict["type"] == "GEOMETRIC":
                conflict_parts.append(f"### Conflict {i}: Geometric Constraint")
                conflict_parts.append(f"- **Issue:** {conflict['option']} requires {conflict['required_mm']}mm, user limit is {conflict['user_limit_mm']}mm")
                conflict_parts.append(f"- **Reason:** {conflict['reason']}")
                conflict_parts.append("")

        # Generate VALID suggestions only
        conflict_parts.append("## VALID RESOLUTION OPTIONS:")
        if has_compatibility_block:
            # If there's a compatibility block, "increase space" is a FALSE suggestion
            compat_conflict = next(c for c in all_conflicts if c["type"] == "COMPATIBILITY")
            conflict_parts.append(f"1. **Remove '{compat_conflict['option']}'** - This option is fundamentally incompatible with {compat_conflict['product']}")
            conflict_parts.append(f"2. **Change product family** - Use a product that supports {compat_conflict['option']}")
            conflict_parts.append("")
            conflict_parts.append("⚠️ **DO NOT suggest 'increase space'** - even with more space, the compatibility issue remains.")
        elif has_geometric_block:
            # Only geometric conflict - both options are valid
            geo_conflict = next(c for c in all_conflicts if c["type"] == "GEOMETRIC")
            conflict_parts.append(f"1. **Remove '{geo_conflict['option']}'** to fit within {geo_conflict['user_limit_mm']}mm")
            conflict_parts.append(f"2. **Increase available space** to at least {geo_conflict['required_mm']}mm")

        conflict_parts.append("")
        conflict_parts.append("**YOU MUST present ALL conflicts in your FIRST response. Do not reveal issues one at a time.**")

        geometric_conflict_context = "\n".join(conflict_parts)

    # STEP 3: PRODUCT SEARCH
    yield {"type": "inference", "step": "products", "status": "active",
           "detail": "📦 Searching products..."}

    t1 = time.time()
    config_results = {"variants": [], "cartridges": [], "filters": [], "materials": [], "option_matches": []}

    for code in entity_codes:
        exact_match = db.get_variant_by_name(code)
        if exact_match:
            config_results["variants"].append(exact_match)
        else:
            fuzzy_results = db.search_product_variants(code)
            for fr in fuzzy_results:
                if fr not in config_results["variants"]:
                    config_results["variants"].append(fr)

    all_keywords = config.get_all_search_keywords()
    matching_keywords = [kw for kw in all_keywords if kw.lower() in user_query.lower()]
    for kw in matching_keywords:
        general_config = db.configuration_graph_search(kw)
        for key in config_results.keys():
            for item in general_config.get(key, []):
                if item not in config_results[key]:
                    config_results[key].append(item)

    timings["config_search"] = time.time() - t1
    variant_count = len(config_results["variants"])

    # Status display only (does NOT touch config_results, so variance/clarification
    # logic below is unaffected). Report how many products match the specification
    # SO FAR, so the count aligns with the single product the user ultimately sees
    # rather than the whole family catalogue:
    #   1. start from this turn's query matches;
    #   2. on a continuation turn (query is just a clarification answer, no product
    #      code) fall back to the resolved family so it isn't a misleading 0;
    #   3. narrow by the resolved dimensions when known — e.g. GDC 600×600 resolves
    #      to a single variant, so show "1 product found", not the 10 family sizes.
    _status_variants = list(config_results["variants"])
    _resolved_fam = detected_product_family or technical_state.detected_family
    if not _status_variants and _resolved_fam:
        try:
            _status_variants = db.search_product_variants(_resolved_fam)
        except Exception:
            _status_variants = []

    def _vint(x):
        try:
            return int(float(x))
        except (TypeError, ValueError):
            return None

    _dim_wh = None
    for _tag in technical_state.tags.values():
        if getattr(_tag, "housing_width", None) and getattr(_tag, "housing_height", None):
            _dim_wh = (_vint(_tag.housing_width), _vint(_tag.housing_height))
            break
    if _dim_wh and _dim_wh[0] and _status_variants:
        _narrowed = [v for v in _status_variants
                     if _vint(v.get("width_mm")) == _dim_wh[0] and _vint(v.get("height_mm")) == _dim_wh[1]]
        if _narrowed:
            _status_variants = _narrowed

    _status_count = len(_status_variants)
    if _status_count == 0 and _resolved_fam:
        _status_count = 1

    yield {"type": "inference", "step": "products", "status": "done",
           "detail": f"📦 {_status_count} product{'s' if _status_count != 1 else ''} found"}

    # STEP 4: CLARIFICATION CHECK (only if needed)
    # CRITICAL: Check technical state first - if all data is known, skip clarification
    variance_analysis = analyze_entity_variance(config_results.get("variants", []))

    # Filter out variable features that are already resolved in context OR in technical_state
    # BUGFIX: Also check technical_state tags for resolved parameters
    truly_unresolved_features = []
    for feat in (graph_reasoning_report.variable_features or []):
        param_name = feat.parameter_name.lower() if feat.parameter_name else ""

        is_resolved = False

        # Check resolved_context first (from query parsing)
        if 'length' in param_name or 'długość' in param_name:
            if resolved_context.get('housing_length') or resolved_context.get('length') or resolved_context.get('filter_depth') or resolved_context.get('depth'):
                is_resolved = True
        elif 'airflow' in param_name:
            if resolved_context.get('airflow') or resolved_context.get('airflow_m3h'):
                is_resolved = True
        elif 'material' in param_name:
            if resolved_context.get('material'):
                is_resolved = True
        elif 'dimension' in param_name or 'wymiar' in param_name or 'size' in param_name:
            if resolved_context.get('housing_size') or resolved_context.get('dimensions'):
                is_resolved = True

        # BUGFIX: Also check technical_state tags for ANY tag having this parameter
        if not is_resolved and technical_state.tags:
            for tag in technical_state.tags.values():
                if 'length' in param_name and (tag.housing_length or tag.filter_depth):
                    is_resolved = True
                    break
                elif 'airflow' in param_name and tag.airflow_m3h:
                    is_resolved = True
                    break
                elif 'depth' in param_name and tag.filter_depth:
                    is_resolved = True
                    break
                elif ('dimension' in param_name or 'size' in param_name) and tag.housing_width and tag.housing_height:
                    is_resolved = True
                    break

        if not is_resolved:
            truly_unresolved_features.append(feat)
        else:
            print(f"🔇 [CLARIFICATION] Skipping '{param_name}' - already resolved in state")

    # Check if all tags in technical state are complete
    all_tags_complete = technical_state.all_tags_complete() if technical_state.tags else False

    # v4.0: Derive has_specific_constraint from Scribe data instead of regex intent
    _has_specific_constraint = bool(
        technical_state.resolved_params
        or (scribe_intent and scribe_intent.parameters)
        or "context update:" in user_query.lower()
    )
    needs_clarification = (
        (variance_analysis["has_variance"] and not _has_specific_constraint) or
        bool(truly_unresolved_features)
    ) and not all_tags_complete

    # Installation block overrides clarifications — don't ask for params when BLOCKED
    if graph_reasoning_report.suitability and not graph_reasoning_report.suitability.is_suitable:
        needs_clarification = False

    if needs_clarification:
        yield {"type": "inference", "step": "clarify", "status": "done",
               "detail": "♟️ Additional info needed"}
    elif all_tags_complete:
        yield {"type": "inference", "step": "clarify", "status": "done",
               "detail": "✅ All parameters resolved"}

    # STEP 5: GENERATE RECOMMENDATION
    yield {"type": "inference", "step": "thinking", "status": "active",
           "detail": "👔 Generating recommendation..."}

    # Now run the actual LLM synthesis (reusing existing logic)
    t1 = time.time()

    # Format contexts
    config_context = format_configuration_context(config_results)

    # Get retrieval results and similar cases (simplified for streaming)
    query_embedding = generate_embedding(user_query)
    retrieval_results = db.hybrid_retrieval(query_embedding, top_k=3, min_score=0.7)
    similar_cases = db.get_similar_cases(query_embedding, top_k=2)
    graph_context = format_retrieval_context(retrieval_results, similar_cases, config_context)

    # Build prompts
    graph_reasoning_context = graph_reasoning_report.to_prompt_injection()

    # v3.8.1: Inject housing corrosion class into reasoning context
    if technical_state.detected_family:
        try:
            _pf_id = f"FAM_{technical_state.detected_family}" if not technical_state.detected_family.startswith("FAM_") else technical_state.detected_family
            from db_result_helpers import result_single
            _pf_rec = result_single(db.connect().query(
                "MATCH (pf:ProductFamily {id: $pf_id}) RETURN pf.corrosion_class AS cc, pf.indoor_only AS io",
                params={"pf_id": _pf_id}
            ))
            if _pf_rec:
                _cc = _pf_rec.get("cc")
                _io = _pf_rec.get("io")
                if _cc:
                    graph_reasoning_context += (
                        f"\n\n## HOUSING SPECIFICATION\n"
                        f"- Housing corrosion class: **{_cc}** (the housing itself, regardless of material)\n"
                        f"- Indoor only: {'Yes' if _io else 'No'}\n"
                        f"- You MUST state the housing corrosion class ({_cc}) when discussing environmental suitability.\n"
                    )
        except Exception as e:
            logger.warning(f"Failed to fetch housing corrosion class: {e}")

    # Combine all constraint contexts (resolution > geometric > graph policies)
    constraint_contexts = []
    if resolution_context:
        constraint_contexts.append(resolution_context)
    if locked_context:
        constraint_contexts.append(locked_context)
    if multi_entity_context:
        constraint_contexts.append(multi_entity_context)
    if additional_data_context:
        constraint_contexts.append(additional_data_context)
    if geometric_conflict_context:
        constraint_contexts.append(geometric_conflict_context)
    if graph_reasoning_context:
        constraint_contexts.append(f"**Graph-Based Policy Evaluation:**\n{graph_reasoning_context}")
    if material_availability_warning:
        constraint_contexts.append(
            f"**⚠️ CRITICAL MATERIAL RESTRICTION:**\n{material_availability_warning}\n"
            f"You MUST inform the customer that this material is not available for this product. "
            f"Suggest the available alternatives listed above. Do NOT proceed with the unavailable material."
        )
    if _material_overrides_applied:
        _override_text = "\n".join(f"  - {o}" for o in _material_overrides_applied)
        constraint_contexts.append(
            f"**⚠️ MATERIAL OVERRIDE (post-pivot):**\n{_override_text}\n"
            f"The user's requested material is NOT available for the recommended product. "
            f"Product codes have been corrected to use an available material. "
            f"Inform the customer about the available material options."
        )

    # v4.3: Inject corrosion class material options when Scribe extracted class, not material
    _corr_mat_options = technical_state.resolved_params.get("corrosion_material_options")
    _corr_no_match = technical_state.resolved_params.get("corrosion_no_match")
    _req_corr = technical_state.resolved_params.get("required_corrosion_class")
    if _corr_mat_options and _req_corr:
        _opt_lines = [f"  - **{o['code']}** ({o['name']}) — corrosion class {o['class']}" for o in _corr_mat_options]
        constraint_contexts.append(
            f"**CORROSION CLASS REQUIREMENT: {_req_corr}**\n"
            f"The customer requires corrosion class {_req_corr}. "
            f"The following materials meet this requirement and are available for this product:\n"
            + "\n".join(_opt_lines) + "\n"
            f"Present these options to the customer and recommend the most suitable one for their environment."
        )
    elif _corr_no_match and _req_corr:
        constraint_contexts.append(
            f"**⚠️ CORROSION CLASS REQUIREMENT: {_req_corr} — NO MATCH**\n"
            f"The customer requires corrosion class {_req_corr}, but no available materials "
            f"for this product meet that class. Inform the customer and suggest alternatives."
        )

    # v3.13: Inject material alternatives when blocked (all products vetoed for material)
    # Query graph for available materials on the user's detected product family
    _is_blocked = (
        graph_reasoning_report.suitability
        and not graph_reasoning_report.suitability.is_suitable
    )
    if _is_blocked and technical_state.detected_family:
        try:
            _fam_id = f"FAM_{technical_state.detected_family}" if not technical_state.detected_family.startswith("FAM_") else technical_state.detected_family
            from db_result_helpers import result_to_dicts
            _mat_records = result_to_dicts(db.connect().query(
                """
                MATCH (pf:ProductFamily {id: $fam_id})-[:AVAILABLE_IN_MATERIAL]->(m:Material)
                RETURN m.id AS id, m.name AS name, m.corrosion_class AS corrosion_class
                ORDER BY m.corrosion_class DESC
                """,
                params={"fam_id": _fam_id}
            ))
            if _mat_records:
                _mat_lines = []
                for rec in _mat_records:
                    _mat_lines.append(f"  - **{rec['name']}** (corrosion class {rec['corrosion_class']})")
                _mat_text = (
                    f"**⚡ AVAILABLE MATERIALS for {technical_state.detected_family}:**\n"
                    + "\n".join(_mat_lines)
                    + "\n\nYou MUST suggest these specific material options to the user. "
                    + "Explain which material(s) meet the environmental requirement."
                )
                constraint_contexts.append(_mat_text)
                print(f"📢 [PROMPT] Injected {len(_mat_records)} material alternatives for {technical_state.detected_family}")
        except Exception as e:
            logger.warning(f"Failed to fetch material alternatives: {e}")

    combined_policies = "\n".join(constraint_contexts) if constraint_contexts else "No additional context."

    # Inject material availability warning into system prompt active_policies
    _active_policies = graph_reasoning_context or ""
    if material_availability_warning:
        _active_policies += f"\n\n⚠️ CRITICAL MATERIAL RESTRICTION:\n{material_availability_warning}\nYou MUST warn the customer and suggest available alternatives."
        print(f"📢 [PROMPT] Material warning injected into active_policies and combined_policies")
    if _material_overrides_applied:
        _override_text = "\n".join(f"  - {o}" for o in _material_overrides_applied)
        _active_policies += f"\n\n⚠️ MATERIAL OVERRIDE (post-pivot):\n{_override_text}\nThe user's requested material is NOT available for the recommended product. Suggest available alternatives."
        print(f"📢 [PROMPT] Post-pivot material override injected: {len(_material_overrides_applied)} tag(s)")
    system_prompt = DEEP_EXPLAINABLE_SYSTEM_PROMPT_GENERIC.format(active_policies=_active_policies)
    synthesis_prompt = DEEP_EXPLAINABLE_SYNTHESIS_PROMPT.format(
        context=graph_context,
        query=user_query,
        policies=combined_policies
    )

    # Call LLM
    try:
        _llm_result = llm_call(
            model=model,
            user_prompt=synthesis_prompt,
            system_prompt=system_prompt,
            json_mode=True,
            temperature=0.0,
            max_output_tokens=4096,
        )
        if _llm_result.error:
            raise Exception(_llm_result.error)
        raw_text = _llm_result.text
        try:
            _log_keys = list(json.loads(raw_text).keys()) if raw_text.strip().startswith('{') else 'NOT_JSON'
        except json.JSONDecodeError:
            _log_keys = 'TRUNCATED_JSON'
        print(f"📝 [SYNTHESIS] Model={model}, {len(raw_text)} chars, keys={_log_keys}")

        # Detect silent truncation
        if _llm_result.output_tokens >= 4000:
            print(f"⚠️ [TRUNCATION RISK] Output used {_llm_result.output_tokens} tokens (near 4096 limit)")

        try:
            llm_response = json.loads(raw_text)
        except json.JSONDecodeError as je:
            # JSON truncation safety net — attempt repair
            print(f"⚠️ JSON parse failed ({je}), attempting repair on {len(raw_text)} chars")
            llm_response = _repair_truncated_json(raw_text)
    except Exception as e:
        llm_response = {
            "content_segments": [{"text": f"Error generating response: {str(e)}", "type": "GENERAL"}],
            "response_type": "FINAL_ANSWER"
        }

    timings["llm"] = time.time() - t1
    timings["total"] = time.time() - total_start

    # Corrosion-class hygiene (deterministic): 'C2' is never a valid class in this
    # catalogue — galvanized FZ = C3, stainless RF/SF = C5/C5.1. The LLM has a
    # persistent prior that a "standard housing frame" carries a C2 rating, which no
    # graph/config data supports and prompt guards do not reliably suppress (it recurs
    # in blocked/pivot verdicts). Correct any stray corrosion-context 'C2' to 'C3' so
    # a response never states a fabricated, self-contradictory class.
    _corr_ctx = ("corros", "class", "rating", "galvan")
    for _seg in llm_response.get("content_segments", []):
        _txt = _seg.get("text", "")
        if "C2" in _txt and any(_w in _txt.lower() for _w in _corr_ctx):
            _fixed = re.sub(r'\bC2\b', 'C3', _txt)
            if _fixed != _txt:
                _seg["text"] = _fixed
                print("🧹 [CORROSION] Corrected stray 'C2' → 'C3' in response segment")

    yield {"type": "inference", "step": "thinking", "status": "done",
           "detail": "👔 Done"}

    # ============================================================
    # FINAL: Transform LLM response to match frontend expectations
    # ============================================================
    # First, determine if clarification is needed (needed for validation check)
    response_type = llm_response.get("response_type", "FINAL_ANSWER")
    clarification_needed = response_type == "CLARIFICATION_NEEDED" or llm_response.get("clarification_needed", False)

    # ============================================================
    # MULTI-TAG VALIDATION LOOP: Verify material and weights before sending
    # ============================================================
    # This catches cases where the LLM reverted to FZ or used wrong weights

    if technical_state.locked_material and not clarification_needed:
        expected_suffix = f"-{technical_state.locked_material}"

        # Check each content segment for product codes with wrong material
        for segment in llm_response.get("content_segments", []):
            text = segment.get("text", "")

            # Look for product codes that might have wrong suffix
            product_codes = re.findall(r'(GD[BCPMI]+-\d+x\d+-\d+[A-Z\-]+)', text)

            for code in product_codes:
                if not code.endswith(expected_suffix):
                    # FZ DEFAULT DETECTED - Fix it
                    old_suffix = "-FZ" if "-FZ" in code else "-ZM" if "-ZM" in code else "-SF" if "-SF" in code else ""
                    if old_suffix:
                        fixed_code = code.replace(old_suffix, expected_suffix)
                        segment["text"] = text.replace(code, fixed_code)
                        print(f"🔧 [VALIDATION] Fixed material suffix: {code} → {fixed_code}")
                    elif not code.endswith(("-RF", "-FZ", "-ZM", "-SF")):
                        # No material suffix - add one
                        fixed_code = code + expected_suffix
                        segment["text"] = text.replace(code, fixed_code)
                        print(f"🔧 [VALIDATION] Added material suffix: {code} → {fixed_code}")

        # Verify material warnings list doesn't have conflicts
        material_warnings = technical_state.verify_material_codes()
        if material_warnings:
            print(f"⚠️ [VALIDATION] Material code warnings: {material_warnings}")
            # Only surface warnings the LLM's own prose hasn't already covered
            # (checked by the rewritten/flagged product code appearing in the text).
            _existing_text = " ".join(
                s.get("text", "").lower() for s in llm_response.get("content_segments", [])
            )
            new_material_warnings = [
                w for w in material_warnings
                if not any(code.lower() in _existing_text for code in re.findall(r"'([^']+)'", w))
            ]
            if new_material_warnings:
                existing_warnings = llm_response.get("policy_warnings", [])
                existing_warnings.extend(new_material_warnings)
                llm_response["policy_warnings"] = existing_warnings

    # v4.2: Enforce available materials when no material is locked (outside locked_material gate)
    if not clarification_needed:
        avail_warnings = technical_state.enforce_available_materials(db)
        if avail_warnings:
            print(f"⚠️ [VALIDATION] Available material warnings: {avail_warnings}")

    # Inject material availability warning into response
    if material_availability_warning and _unavailable_material_code:
        # Check the LLM's own prose FIRST — badge and prose share the same guard
        # so the badge never restates a fact the LLM already covered.
        segments = llm_response.get("content_segments", [])
        has_material_warning = any(
            "not available" in s.get("text", "").lower() and _unavailable_material_code.lower() in s.get("text", "").lower()
            for s in segments
        )
        existing_warnings = llm_response.get("policy_warnings", [])
        # Only add if no similar warning about this material already exists (as a badge or in prose)
        _has_similar = has_material_warning or any(
            _unavailable_material_code in str(w) and ("not available" in str(w).lower() or "NOT AVAILABLE" in str(w))
            for w in existing_warnings
        )
        if not _has_similar:
            existing_warnings.append(material_availability_warning)
        llm_response["policy_warnings"] = existing_warnings
        # Also prepend warning to the response content if LLM missed it
        if not has_material_warning and _unavailable_material_code:
            warning_text = (
                f"**Important:** {_unavailable_material_code} (stainless steel) is **not available** "
                f"for {detected_product_family}. "
                f"Available material options: {', '.join(_available_material_names)}. "
                f"Please select an available material to proceed."
            )
            segments.insert(0, {"text": warning_text, "type": "GENERAL"})
            llm_response["content_segments"] = segments
            print(f"📢 [VALIDATION] Injected material warning into response segments")

    # v3.9: Inject capacity overload warning (same pattern as material warning)
    # Ensures capacity risk is visible even if LLM doesn't surface it.
    _verdict = getattr(graph_reasoning_report, '_verdict', None)
    if _verdict and _verdict.capacity_calculation:
        cap = _verdict.capacity_calculation
        if cap.get("input_value", 0) > cap.get("output_rating", 0):
            # v3.9: Include single-module alternatives in warning if available
            sa = _verdict.sizing_arrangement or {}
            alt_text = ""
            sma = sa.get("single_module_alternatives", [])
            if sma:
                best_alt = sma[0]
                alt_text = (
                    f" Alternative: single {best_alt['label']} module "
                    f"({best_alt['reference_airflow_m3h']:.0f} m³/h capacity)."
                )
            cap_warning = (
                f"⚠️ CAPACITY NOTE: Requested {cap['input_value']:.0f} "
                f"{cap.get('input_requirement', '')} exceeds the recommended flow of "
                f"{cap['output_rating']:.0f} for a single module. Modules needed: {cap.get('modules_needed')}.{alt_text}"
            )
            # Check the LLM's own prose FIRST — badge and prose share the same guard
            # so the badge never restates a fact the LLM already covered. Match on
            # the actual figures (not just "exceed"/"capacity" keywords) since the
            # LLM may paraphrase ("cannot handle" instead of "exceeds") while still
            # citing the same numbers.
            segments = llm_response.get("content_segments", [])
            _cap_in = f"{cap['input_value']:.0f}"
            _cap_out = f"{cap['output_rating']:.0f}"
            # Normalize thousands separators/spaces so "2,800 m³/h" matches "2800"
            def _norm_num(s: str) -> str:
                return s.replace(",", "").replace(" ", "").replace(" ", "")
            has_capacity_mention = any(
                (_cap_in in _norm_num(s.get("text", "")) and _cap_out in _norm_num(s.get("text", "")))
                or ("capacity" in s.get("text", "").lower() and "exceed" in s.get("text", "").lower())
                for s in segments
            )
            existing_warnings = llm_response.get("policy_warnings", [])
            if not has_capacity_mention and not any("CAPACITY" in str(w) for w in existing_warnings):
                existing_warnings.append(cap_warning)
                llm_response["policy_warnings"] = existing_warnings
            # v3.8: Only inject capacity segment on the first turn — suppress on follow-ups
            # to avoid verbatim repetition of the same warning
            if not has_capacity_mention and technical_state.turn_count <= 1:
                alt_segment = ""
                if sma:
                    best_alt = sma[0]
                    alt_segment = (
                        f" Alternatively, a single {best_alt['label']} module "
                        f"can handle {best_alt['reference_airflow_m3h']:.0f} m³/h."
                    )
                segments.append({
                    "text": (
                        f"The requested airflow of {cap['input_value']:.0f} m³/h exceeds the "
                        f"{cap['output_rating']:.0f} m³/h rating of a single {cap.get('module_descriptor', '')} "
                        f"module, so {cap.get('modules_needed')} parallel units are required.{alt_segment}"
                    ),
                    "type": "GENERAL",
                })
                llm_response["content_segments"] = segments
                print(f"📢 [VALIDATION] Injected capacity note into response segments")

    # v3.10: Inject oversizing warning when module is massively oversized
    if _verdict and _verdict.sizing_arrangement:
        ow = _verdict.sizing_arrangement.get("oversizing_warning")
        if ow:
            util_pct = ow.get("utilization_pct", 100)
            mod_cap = ow.get("module_capacity", 0)
            req_air = ow.get("required_airflow", 0)
            smaller_alts = ow.get("smaller_alternatives", [])
            alt_text = ""
            if smaller_alts:
                best_sm = smaller_alts[0]
                alt_text = (
                    f" A more appropriate option would be a {best_sm['label']} module "
                    f"({best_sm['reference_airflow_m3h']:.0f} m³/h capacity)."
                )
            ow_warning = (
                f"⚠️ OVERSIZING WARNING: The selected module has {mod_cap:.0f} m³/h "
                f"capacity but only {req_air:.0f} m³/h is required "
                f"({util_pct:.0f}% utilization). This extreme oversizing can cause "
                f"uneven air distribution and reduced efficiency.{alt_text}"
            )
            # Check the LLM's own prose FIRST — badge and prose share the same guard
            # so the badge never restates a fact the LLM already covered. Match on
            # the actual figures too, in case the LLM paraphrases without literally
            # saying "oversize"/"oversized".
            segments = llm_response.get("content_segments", [])
            _ow_cap = f"{mod_cap:.0f}"
            _ow_req = f"{req_air:.0f}"
            has_oversize_mention = any(
                "oversize" in s.get("text", "").lower() or "oversized" in s.get("text", "").lower()
                or (_ow_cap in s.get("text", "") and _ow_req in s.get("text", ""))
                for s in segments
            )
            existing_warnings = llm_response.get("policy_warnings", [])
            if not has_oversize_mention and not any("OVERSIZ" in str(w).upper() for w in existing_warnings):
                existing_warnings.append(ow_warning)
                llm_response["policy_warnings"] = existing_warnings
            if not has_oversize_mention:
                segments.append({
                    "text": (
                        f"The selected module ({mod_cap:.0f} m³/h capacity) is significantly "
                        f"oversized for the requested {req_air:.0f} m³/h "
                        f"({util_pct:.0f}% utilization). This can lead to uneven air distribution "
                        f"and reduced efficiency.{alt_text}"
                    ),
                    "type": "GENERAL",
                })
                llm_response["content_segments"] = segments
                print(f"📢 [VALIDATION] Injected oversizing warning into response segments")

    # v3.11: Inject WARNING-level trait neutralization warnings (e.g., humidity degrades carbon)
    # The engine detects these but LLM sometimes ignores them during clarification.
    # Inject into policy_warnings so they always surface to the user.
    # v3.13: Only inject if the product actually HAS the affected trait (e.g., don't warn
    # about porous adsorption degradation for a mechanical-only filter housing).
    # v3.14: Skip ALL warnings when blocked — warnings about the rejected material just add noise.
    _has_product_context = False
    _product_traits = set()
    if _verdict and _verdict.recommended_product:
        _has_product_context = True
        _product_traits = set(_verdict.recommended_product.traits_present) | set(_verdict.recommended_product.traits_neutralized)
    elif _verdict and _verdict.ranked_products:
        # v3.13: When all products vetoed (no recommended), use user's preferred product
        _has_product_context = True
        _user_pf = _verdict.ranked_products[0]
        _product_traits = set(_user_pf.traits_present) | set(_user_pf.traits_neutralized)
    if _is_blocked:
        print(f"🔇 [VALIDATION] Skipping ALL WARNING neutralizations — configuration is blocked")
    elif _verdict and _verdict.active_causal_rules:
        for rule in _verdict.active_causal_rules:
            if rule.rule_type == "NEUTRALIZED_BY" and rule.severity == "WARNING":
                # Skip if we know the product and it doesn't have the affected trait
                # (empty traits = product has no relevant traits, so warning is irrelevant)
                if _has_product_context and rule.trait_name not in _product_traits:
                    print(f"🔇 [VALIDATION] Skipped irrelevant WARNING: {rule.stressor_name} → {rule.trait_name} (product lacks trait)")
                    continue
                warning_text = (
                    f"⚠️ {rule.explanation} "
                    f"(Stressor: {rule.stressor_name}, affects: {rule.trait_name})"
                )
                # Check the LLM's own prose FIRST — badge and prose share the same
                # guard so the badge never restates a fact the LLM already covered.
                segments = llm_response.get("content_segments", [])
                has_mention = any(
                    rule.stressor_name.lower() in s.get("text", "").lower()
                    for s in segments
                )
                existing_warnings = llm_response.get("policy_warnings", [])
                already_badged = any(rule.stressor_name.lower() in str(w).lower() for w in existing_warnings)
                if not has_mention and not already_badged:
                    existing_warnings.append(warning_text)
                    llm_response["policy_warnings"] = existing_warnings
                    segments.append({
                        "text": rule.explanation,
                        "type": "GENERAL",
                    })
                    llm_response["content_segments"] = segments
                    print(f"📢 [VALIDATION] Injected WARNING neutralization: {rule.stressor_name} → {rule.trait_name}")

    # v3.12: Inject suitability warnings into content_segments on FINAL_ANSWER
    # Ensures environment/material concerns (e.g., 95% RH, corrosion risk) survive
    # into the final product card response even if LLM drops them on follow-up turns.
    if (
        graph_reasoning_report.suitability
        and graph_reasoning_report.suitability.is_suitable
        and graph_reasoning_report.suitability.warnings
        and not clarification_needed
    ):
        segments = llm_response.get("content_segments", [])
        existing_text = " ".join(s.get("text", "").lower() for s in segments)
        for w in graph_reasoning_report.suitability.warnings:
            # Check if warning topic is already mentioned in content
            keyword = w.risk_name.lower().replace("_", " ")
            if keyword not in existing_text and w.description:
                severity_prefix = "**Warning**" if w.severity == "WARNING" else "**Note**"
                segments.append({
                    "text": f"{severity_prefix}: {w.description}" + (f" {w.mitigation}" if w.mitigation and w.mitigation.lower() not in ("none", "n/a", "") else ""),
                    "type": "GENERAL",
                })
                print(f"📢 [v3.12] Injected suitability warning into content: {w.risk_name}")
        llm_response["content_segments"] = segments

    # ============================================================
    # CLARIFICATION SUPPRESSION: Don't ask for data we already have
    # ============================================================
    # BUGFIX: Per-tag suppression.  Only suppress when the SPECIFIC tag
    # the LLM is asking about already has the parameter.  If no tag_id
    # is specified in the clarification, only suppress when ALL tags
    # have the parameter (conservative — avoids hiding valid questions).
    clar_data = llm_response.get("clarification_data") or llm_response.get("clarification")

    if clarification_needed and clar_data:
        missing_attr = clar_data.get("missing_attribute", "").lower()

        # Try to identify which tag the clarification targets
        clar_tag_id = clar_data.get("tag_id", "").lower() or clar_data.get("for_tag", "").lower()
        # Also check the question text for a tag reference like "Tag 5684"
        clar_question = clar_data.get("question", "")
        tag_ref_match = re.search(r'tag\s*(\d+)', clar_question, re.IGNORECASE)
        if not clar_tag_id and tag_ref_match:
            clar_tag_id = tag_ref_match.group(1)

        # Build the set of tags to check (specific tag or all tags)
        if clar_tag_id and clar_tag_id in technical_state.tags:
            tags_to_check = [technical_state.tags[clar_tag_id]]
            check_mode = "specific"
        else:
            tags_to_check = list(technical_state.tags.values())
            check_mode = "all"  # must be True for ALL tags to suppress

        suppress_clarification = False

        # Material is project-wide, not per-tag
        if 'material' in missing_attr:
            if technical_state.locked_material:
                suppress_clarification = True
                print(f"🔇 [SUPPRESS] Skipping clarification for material - locked to {technical_state.locked_material}")

        # Per-tag parameter checks
        elif tags_to_check:
            def _tag_has_attr(tag, attr: str) -> bool:
                """Check if a specific tag has the requested attribute."""
                if any(term in attr for term in ['length', 'długość', 'depth']):
                    return bool(tag.housing_length or tag.filter_depth)
                elif 'airflow' in attr or 'przepływ' in attr:
                    return bool(tag.airflow_m3h)
                elif any(term in attr for term in ['dimension', 'wymiar', 'size']):
                    return bool(tag.housing_width and tag.housing_height)
                return False

            if check_mode == "specific":
                # Only suppress if the SPECIFIC tag already has the data
                if _tag_has_attr(tags_to_check[0], missing_attr):
                    suppress_clarification = True
                    print(f"🔇 [SUPPRESS] Tag '{clar_tag_id}' already has '{missing_attr}'")
            else:
                # No specific tag targeted — suppress only if ALL tags have it
                if tags_to_check and all(_tag_has_attr(t, missing_attr) for t in tags_to_check):
                    suppress_clarification = True
                    print(f"🔇 [SUPPRESS] All {len(tags_to_check)} tag(s) already have '{missing_attr}'")

        # resolved_params check: suppress if missing_attr is already answered
        # (catches gate parameters like atex_zone, chlorine_ppm, etc.)
        # BUGFIX: Do NOT suppress when the value is None/empty — that means
        # the param was seen but NOT provided, so clarification IS valid.
        if not suppress_clarification and missing_attr:
            normalized_attr = missing_attr.replace(" ", "_").lower()
            rp_value = technical_state.resolved_params.get(normalized_attr)
            if normalized_attr in technical_state.resolved_params and rp_value is not None and str(rp_value).lower() not in ("none", ""):
                suppress_clarification = True
                print(f"🔇 [SUPPRESS] Skipping clarification for '{missing_attr}' "
                      f"- already in resolved_params: {rp_value}")
            elif normalized_attr in technical_state.resolved_params:
                print(f"🔇 [SUPPRESS] NOT suppressing '{missing_attr}' - resolved_params value is None/empty")

        if suppress_clarification:
            # Convert to final answer - we have all the data
            clarification_needed = False
            clar_data = None
            response_type = "FINAL_ANSWER"
            print(f"✅ [SUPPRESS] Clarification suppressed - data available in state")

    # Convert clarification_data to clarification format
    clarification = None
    if clarification_needed and clar_data:
        # Airflow options are graph-authoritative: the graph holds deterministic
        # per-family reference airflow (ProductVariant), so it MUST win over any
        # options the synthesis LLM authored. The old `and not clar_data.get(...)`
        # guard ceded authority to LLM free text, which fabricated non-deterministic
        # airflow tiers (e.g. 1500/2500) because the reasoning injection gives the
        # model only the question text, not the numbers. Override whenever the graph
        # returns options; keep LLM options only as a fallback when it returns none.
        missing_attr_lower = (clar_data.get("missing_attribute") or "").lower()
        if 'airflow' in missing_attr_lower or 'przepływ' in missing_attr_lower:
            airflow_opts = _generate_airflow_options_from_graph(technical_state, db)
            if airflow_opts:
                clar_data["options"] = airflow_opts
                print(f"🎯 [ENRICHMENT] Overrode with {len(airflow_opts)} airflow options from ProductVariant graph data")
            else:
                # Graph-derived airflow tiers require the housing dimensions. With no
                # dimensions resolved the LLM cannot know real airflow values, so any
                # options it authored are fabricated (e.g. hallucinated 10200/25500).
                # Clear them so the user enters airflow via free input instead of
                # picking an invented tier (the clarification card always offers an
                # "Other…" text field, so this is not a dead end).
                _has_dims = any(
                    getattr(t, "housing_width", None) and getattr(t, "housing_height", None)
                    for t in technical_state.tags.values()
                )
                if not _has_dims and clar_data.get("options"):
                    print(f"🎯 [ENRICHMENT] Cleared {len(clar_data['options'])} fabricated airflow options (no dimensions → no graph tiers)")
                    clar_data["options"] = []

        # Deduplicate options by value (case-insensitive)
        raw_options = clar_data.get("options", [])
        if raw_options:
            seen = set()
            deduped = []
            for opt in raw_options:
                val = opt if isinstance(opt, str) else opt.get("value", opt.get("label", str(opt)))
                key = str(val).lower().strip()
                if key not in seen:
                    seen.add(key)
                    deduped.append(opt)
            raw_options = deduped

        clarification = {
            "missing_info": clar_data.get("missing_attribute") or clar_data.get("missing_info", "Missing information"),
            "why_needed": clar_data.get("why_needed", "Information required"),
            "options": raw_options,
            "question": clar_data.get("question", "Please provide additional information")
        }

        # Enrich LLM-generated options with display_labels from graph FeatureOption nodes
        if clarification and graph_reasoning_report and graph_reasoning_report.variable_features:
            label_map = {}
            for feat in graph_reasoning_report.variable_features:
                for opt_data in feat.options:
                    val = str(opt_data.get('value', '')).strip().lower()
                    dl = opt_data.get('display_label') or opt_data.get('name', '')
                    if val and dl:
                        label_map[val] = dl
            if label_map:
                for opt in clarification.get("options", []):
                    if isinstance(opt, dict) and not opt.get("display_label"):
                        opt["display_label"] = label_map.get(
                            str(opt.get("value", "")).strip().lower()
                        )

    # Handle entity_card (supports both single dict and multi-card array for assemblies)
    entity_card_data = llm_response.get("entity_card") or llm_response.get("product_card")

    # Defense-in-depth: If clarification was suppressed (→ FINAL_ANSWER) but LLM
    # didn't generate an entity_card (because it was in clarification mode),
    # build a minimal card from technical state so the user sees a product config.
    if not entity_card_data and not clarification_needed and technical_state.all_tags_complete():
        for tag_id, tag in technical_state.tags.items():
            if tag.product_code:
                fallback_specs = {}
                if tag.product_code:
                    fallback_specs["Product Code"] = tag.product_code
                if tag.housing_width and tag.housing_height:
                    fallback_specs["Dimensions"] = f"{tag.housing_width}x{tag.housing_height} mm"
                if tag.airflow_m3h:
                    fallback_specs["Airflow"] = f"{tag.airflow_m3h} m³/h"
                if tag.rated_airflow_m3h:
                    fallback_specs["Rated Capacity"] = f"{tag.rated_airflow_m3h} m³/h"
                if tag.housing_length:
                    fallback_specs["Housing Length"] = f"{tag.housing_length} mm"
                if tag.weight_kg:
                    fallback_specs["Weight"] = f"~{tag.weight_kg} kg"
                if tag.material_override or technical_state.locked_material:
                    fallback_specs["Material"] = tag.material_override or technical_state.locked_material
                entity_card_data = {
                    "title": tag.product_code,
                    "specs": fallback_specs,
                    "confidence": "high",
                }
                print(f"📋 [FALLBACK] Built entity_card from technical state: {tag.product_code}")
                break

    product_card_dict = None
    product_cards_list = []
    is_assembly = bool(technical_state.assembly_group and technical_state.assembly_group.get("stages"))

    # Defense-in-depth: suppress product cards when engine says product is NOT suitable
    _is_blocked = (
        graph_reasoning_report.suitability
        and not graph_reasoning_report.suitability.is_suitable
    )
    if _is_blocked:
        print(f"🚫 [BLOCK GUARD] Product cards suppressed: is_suitable=False")

        # v3.12: Inject block explanation if LLM returned empty/minimal content_segments.
        # When the engine blocks a configuration, the user must see WHY it was blocked
        # and what alternatives exist — never an empty response.
        segments = llm_response.get("content_segments", [])
        total_text = sum(len(s.get("text", "")) for s in segments)
        if total_text < 50:
            block_segments = []
            # Build explanation from suitability warnings (CRITICAL ones = block reasons)
            suit = graph_reasoning_report.suitability
            critical_warnings = [w for w in suit.warnings if w.severity == "CRITICAL"]
            if critical_warnings:
                for w in critical_warnings:
                    block_segments.append({
                        "text": f"**Configuration Blocked**: {w.description}",
                        "type": "INFERENCE",
                        "inference_logic": w.consequence,
                    })
                    if w.mitigation and w.mitigation.lower() not in ("none", "n/a", ""):
                        block_segments.append({
                            "text": f"**Recommendation**: {w.mitigation}",
                            "type": "GENERAL",
                        })
            else:
                # Fallback: generic block message from any warnings
                all_warnings = suit.warnings
                if all_warnings:
                    desc_parts = [w.description for w in all_warnings if w.description]
                    block_segments.append({
                        "text": f"**Configuration Blocked**: {'; '.join(desc_parts) if desc_parts else 'This configuration does not meet the required constraints.'}",
                        "type": "INFERENCE",
                    })
                else:
                    block_segments.append({
                        "text": "**Configuration Blocked**: This product/material combination is not suitable for the specified environment. Please contact engineering for alternatives.",
                        "type": "GENERAL",
                    })

            # Add alternatives if available from verdict
            _verdict_obj = getattr(graph_reasoning_report, '_verdict', None)
            if _verdict_obj and hasattr(_verdict_obj, 'installation_violations'):
                for iv in _verdict_obj.installation_violations:
                    alts = getattr(iv, 'alternatives', [])
                    if alts:
                        alt_names = [a.product_family_name for a in alts[:3]]
                        block_segments.append({
                            "text": f"**Suitable alternatives**: {', '.join(alt_names)}",
                            "type": "GENERAL",
                        })

            llm_response["content_segments"] = block_segments
            print(f"📢 [BLOCK INJECT] Injected {len(block_segments)} block explanation segments (LLM returned {total_text} chars)")

    if entity_card_data and not clarification_needed and not _is_blocked:
        cards = entity_card_data if isinstance(entity_card_data, list) else [entity_card_data]
        for cd in cards:
            if isinstance(cd, dict):
                # Assembly cards are always "high" confidence — the assembly IS the recommendation
                raw_confidence = cd.get("confidence", "medium")
                confidence = "high" if is_assembly else raw_confidence
                # Strip null/None values from specs (LLM sometimes emits "weight": null)
                raw_specs = cd.get("specs", {})
                clean_specs = {
                    k: v for k, v in raw_specs.items()
                    if v is not None and str(v).lower() != "null"
                } if isinstance(raw_specs, dict) else raw_specs
                product_cards_list.append({
                    "title": cd.get("title", ""),
                    "specs": clean_specs,
                    "warning": cd.get("warning"),
                    "confidence": confidence,
                    "actions": cd.get("actions", ["Add to Quote"])
                })
        # v4.1: Deduplicate product cards by product code or title
        if len(product_cards_list) > 1:
            seen_keys = set()
            deduped = []
            for pc in product_cards_list:
                # Use product code from specs as dedup key, fallback to title
                dedup_key = (pc.get("specs", {}).get("Product Code") or pc.get("title", "")).strip()
                if dedup_key and dedup_key in seen_keys:
                    print(f"🗑️ [DEDUP] Removed duplicate product card: {dedup_key}")
                    continue
                seen_keys.add(dedup_key)
                deduped.append(pc)
            product_cards_list = deduped

        product_card_dict = product_cards_list[0] if product_cards_list else None

        # v4.2: Surface sibling-size ALTERNATIVES as extra product cards on the
        # happy path. Experts asked for several options, not a single answer.
        # Deterministic — built from graph ProductVariant data + the code builder,
        # never from the LLM. Skipped for assemblies (cards = stages, not options).
        try:
            if (product_cards_list and not is_assembly and len(product_cards_list) == 1):
                _primary_tag = next(
                    (t for t in technical_state.tags.values() if t.product_code), None
                )
                _req_af = None
                if _primary_tag:
                    _req_af = _primary_tag.airflow_m3h or technical_state.resolved_params.get("airflow_m3h")
                _fam = (
                    (_primary_tag.product_family or technical_state.detected_family)
                    if _primary_tag else technical_state.detected_family
                )
                if (_primary_tag and _fam and _req_af
                        and _primary_tag.housing_width and _primary_tag.housing_height):
                    _alts = db.get_family_size_alternatives(
                        _fam, int(_req_af),
                        int(_primary_tag.housing_width), int(_primary_tag.housing_height),
                        limit=2,
                    )
                    _fam_id = _fam if str(_fam).startswith("FAM_") else f"FAM_{_fam}"
                    _code_fmt = db.get_product_family_code_format(_fam_id)
                    import copy as _copy
                    for _a in _alts:
                        # Keep the user's chosen housing_length/depth; only the
                        # footprint (size) changes. Weight is length-dependent and
                        # not reliably known for the alt length → omit it.
                        _alt_tag = _copy.copy(_primary_tag)
                        _alt_tag.housing_width = int(_a["width"])
                        _alt_tag.housing_height = int(_a["height"])
                        _alt_tag.product_code = None
                        _alt_code = technical_state.build_product_code(_alt_tag, code_format=_code_fmt)
                        _specs = {
                            "Product Code": _alt_code,
                            "Housing Size": f"{int(_a['width'])}x{int(_a['height'])}mm",
                        }
                        if _primary_tag.housing_length:
                            _specs["Housing Length"] = f"{int(_primary_tag.housing_length)}mm"
                        _mat = _primary_tag.material_override or technical_state.locked_material
                        if _mat:
                            _specs["Material"] = _mat
                        _conn = technical_state.resolved_params.get("connection_type")
                        if _conn:
                            _specs["Connection"] = _conn
                        if _a.get("airflow"):
                            _specs["Rated Airflow"] = f"{int(_a['airflow'])} m³/h"
                        product_cards_list.append({
                            "title": _alt_code,
                            "specs": _specs,
                            "warning": None,
                            "confidence": "medium",
                            "card_role": "alternative",
                            "actions": ["Add to Quote"],
                        })
                    if _alts:
                        print(f"🔀 [ALTERNATIVES] Added {len(_alts)} sibling-size alternative cards for {_fam}")
        except Exception as _alt_e:
            logger.warning(f"Alternative cards generation failed (non-fatal): {_alt_e}")

    # Installation block overrides clarifications in final response (defense-in-depth)
    if graph_reasoning_report.suitability and not graph_reasoning_report.suitability.is_suitable:
        clarification_needed = False
        clarification = None

    # Cap risk_severity based on engine verdict: if the product is suitable
    # (no veto, no installation block), the LLM should not mark it CRITICAL.
    # CRITICAL = UNSUITABLE badge in the UI, reserved for truly blocked products.
    llm_risk_severity = llm_response.get("risk_severity")
    if (
        llm_risk_severity == "CRITICAL"
        and graph_reasoning_report.suitability
        and graph_reasoning_report.suitability.is_suitable
    ):
        llm_risk_severity = "WARNING"
        print(f"🔇 [RISK CAP] LLM said CRITICAL but engine says is_suitable=True → capped to WARNING")

    # Promote risk to CRITICAL when engine says product is NOT suitable
    # (defense-in-depth: LLM might say WARNING or None, but engine verdict overrides)
    if _is_blocked and llm_risk_severity != "CRITICAL":
        llm_risk_severity = "CRITICAL"
        print(f"🚫 [RISK PROMOTE] is_suitable=False → forced CRITICAL")

    # Build transformed response
    transformed_response = {
        "content_segments": llm_response.get("content_segments", []),
        "clarification_needed": clarification_needed,
        "clarification": clarification,
        "risk_detected": True if _is_blocked else llm_response.get("risk_detected", False),
        "risk_severity": llm_risk_severity,
        "risk_resolved": False if _is_blocked else llm_response.get("risk_resolved", False),
        "status_badges": [{"type": "WARNING", "text": "Blocked"}] if _is_blocked else llm_response.get("status_badges", []),
    }

    # Defense-in-depth: Override COMPLETE badge if tags are actually incomplete
    if not _is_blocked and technical_state and not technical_state.all_tags_complete():
        badges = transformed_response["status_badges"]
        has_false_complete = any(
            b.get("type") == "SUCCESS" and "COMPLETE" in (b.get("text") or "").upper()
            for b in badges
        )
        if has_false_complete:
            incomplete_tags = [
                tid for tid, t in technical_state.tags.items()
                if not t.is_complete
            ]
            print(f"⚠️ [BADGE OVERRIDE] LLM said COMPLETE but tags incomplete: {incomplete_tags}")
            transformed_response["status_badges"] = [
                b for b in badges
                if not (b.get("type") == "SUCCESS" and "COMPLETE" in (b.get("text") or "").upper())
            ]

    transformed_response.update({
        "policy_warnings": list(dict.fromkeys(
            w if isinstance(w, str) else (w.get("message") if isinstance(w, dict) else str(w))
            for w in llm_response.get("policy_warnings", [])
            if w is not None
        )),
        "product_card": product_card_dict,
        "product_cards": product_cards_list,
        "timings": timings
    })

    # Build locked_context for frontend to persist across turns (simple format)
    session_locked = {}
    if locked_material:
        session_locked["material"] = locked_material
    if locked_project:
        session_locked["project"] = locked_project
    if locked_depths:
        session_locked["filter_depths"] = locked_depths
    # Also extract from dimension mappings if present
    if dimension_mappings:
        session_locked["dimension_mappings"] = dimension_mappings

    # BUGFIX: Also build dimension_mappings from technical state tags if not already populated
    if not dimension_mappings and technical_state.tags:
        state_dimension_mappings = []
        for tag_id, tag in technical_state.tags.items():
            if tag.filter_width and tag.filter_height:
                state_dimension_mappings.append({
                    "width": tag.filter_width,
                    "height": tag.filter_height,
                    "depth": tag.filter_depth
                })
        if state_dimension_mappings:
            session_locked["dimension_mappings"] = state_dimension_mappings

    # Track what clarification we're asking so next turn can interpret bare answers
    if clarification_needed and clar_data:
        technical_state.pending_clarification = (
            clar_data.get("missing_attribute") or clar_data.get("missing_info") or ""
        ).lower()
    else:
        technical_state.pending_clarification = None

    # Include full technical state for advanced persistence
    # This allows complete tag-by-tag tracking across turns
    technical_state_dict = technical_state.to_dict()

    # Layer 4: Persist state to graph after processing
    if session_graph_mgr and session_id:
        try:
            technical_state.persist_to_graph(session_graph_mgr, session_id)
            print(f"💾 [GRAPH STATE] Persisted {len(technical_state.tags)} tags to Layer 4")
        except Exception as e:
            logger.warning(f"Graph state persist failed (non-fatal): {e}")

        # v3.0: Store assistant turn summary for Scribe conversation history
        try:
            clar_flag = "clarification" if clarification_needed else "answer"
            fam = detected_product_family or technical_state.detected_family or "TBD"
            assistant_summary = f"Recommended: {fam}, type={clar_flag}, tags={len(technical_state.tags)}"
            session_graph_mgr.store_turn(
                session_id, "assistant", assistant_summary, technical_state.turn_count
            )
        except Exception as e:
            logger.warning(f"Failed to store assistant turn (non-fatal): {e}")

    yield {"type": "complete", "response": transformed_response, "timings": timings,
           "turn_number": technical_state.turn_count,
           "locked_context": session_locked,
           "technical_state": technical_state_dict,
           "graph_report": {
               "application": graph_reasoning_report.application.name if graph_reasoning_report.application else None,
               "warnings_count": len(graph_reasoning_report.suitability.warnings) if graph_reasoning_report.suitability else 0,
               "variable_features": len(graph_reasoning_report.variable_features) if graph_reasoning_report.variable_features else 0,
               "tags_complete": technical_state.all_tags_complete(),
               "tags_count": len(technical_state.tags)
           }}

    # Layer 4: Emit session graph state for frontend visualization
    if session_graph_mgr and session_id:
        try:
            session_state = session_graph_mgr.get_project_state(session_id)
            reasoning_paths = session_graph_mgr.get_reasoning_path(session_id)
            session_state["reasoning_paths"] = reasoning_paths
            yield {"type": "session_state", "data": session_state}
        except Exception as e:
            logger.warning(f"Session state emit failed (non-fatal): {e}")


# Backwards compatibility exports
def extract_product_codes(query: str) -> list[str]:
    """Legacy name for extract_entity_codes."""
    return extract_entity_codes(query)
