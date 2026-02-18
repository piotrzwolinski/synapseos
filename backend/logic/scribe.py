"""Semantic Scribe — LLM-Based Intent Extraction Layer (v4.2).

Primary intent extraction engine using LLM (Gemini or GPT-5.2 via llm_router). Regex is fallback only.

Pipeline:
    [Scribe LLM (primary)] → [resolve_derived_actions()] → merge → [Regex (fallback)]

Architecture:
    - Domain-agnostic: No product names or HVAC terms in prompts or logic
    - Primary extractor: Scribe runs FIRST, regex fills gaps only
    - Clarification-aware: Knows what parameter the system asked for
    - Fail-safe: If Scribe fails, regex results stand unchanged
    - Fast: LLM via llm_router, 768 tokens, temperature 0.0

v4.0 changes:
    - Expanded extraction: action_intent, project_name, accessories, housing_length, entity_codes
    - All fields previously regex-only are now LLM-extracted
    - max_output_tokens: 512 → 768
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from llm_router import llm_call, DEFAULT_MODEL

logger = logging.getLogger(__name__)

_MODEL = DEFAULT_MODEL

# Cached graph-driven mapping for environment + application IDs
# v3.8.1: Cache invalidated on restart; replacement semantics rule added
_cached_scribe_prompt: Optional[str] = None


def _build_env_app_mapping(db) -> tuple[str, str]:
    """Build Scribe prompt mapping from graph Environment + Application nodes.

    Returns (env_mapping_text, app_mapping_text) for insertion into prompt template.
    """
    # Environments
    env_lines = []
    try:
        env_data = db.get_environment_keywords()
        for env_id, keywords in env_data.items():
            kw_str = " / ".join(f'"{k}"' for k in keywords)
            env_lines.append(f'     {kw_str} → {{"installation_environment": "{env_id}"}}')
    except Exception as e:
        logger.warning(f"Failed to load environment keywords from graph: {e}")
        env_lines.append('     "indoor" → {"installation_environment": "ENV_INDOOR"}')

    # Applications
    app_lines = []
    try:
        apps = db.get_all_applications()
        for app in apps:
            keywords = app.get("keywords", [])
            if keywords:
                kw_str = " / ".join(f'"{k}"' for k in keywords)
                app_id = app.get("id", "")
                app_lines.append(f'     {kw_str} → {{"detected_application": "{app_id}"}}')
    except Exception as e:
        logger.warning(f"Failed to load applications from graph: {e}")

    return "\n".join(env_lines), "\n".join(app_lines)


def get_scribe_system_prompt(db=None) -> str:
    """Return the Scribe system prompt, optionally enriched with graph data.

    Caches the result after first successful DB call.
    """
    global _cached_scribe_prompt
    if _cached_scribe_prompt:
        return _cached_scribe_prompt

    if db is not None:
        env_mapping, app_mapping = _build_env_app_mapping(db)
        prompt = _SCRIBE_SYSTEM_PROMPT_TEMPLATE.format(
            env_mapping=env_mapping,
            app_mapping=app_mapping,
        )
        _cached_scribe_prompt = prompt
        logger.info(f"Scribe prompt built from graph ({len(env_mapping)} env chars, {len(app_mapping)} app chars)")
        return prompt

    # Fallback: use template with placeholder text
    return _SCRIBE_SYSTEM_PROMPT_TEMPLATE.format(
        env_mapping='     "indoor" → {"installation_environment": "ENV_INDOOR"}, "outdoor" → {"installation_environment": "ENV_OUTDOOR"}',
        app_mapping='     (no application data available)',
    )


# =============================================================================
# DATA MODEL
# =============================================================================

@dataclass
class ScribeEntity:
    """An entity (item/tag) extracted from the user's message."""
    tag_ref: str                            # "item_1", "item_2"
    action: str = "UPDATE"                  # CREATE, UPDATE, DELETE
    dimensions: Optional[dict] = None       # {"width": 600, "height": 900, "depth": 292}
    airflow_m3h: Optional[int] = None
    product_family: Optional[str] = None
    material: Optional[str] = None
    connection_type: Optional[str] = None   # "PG" or "F" (flange)
    housing_length: Optional[int] = None    # explicit housing length (550/600/750/800/900mm)


@dataclass
class ScribeAction:
    """A derived action that requires state lookup to resolve."""
    type: str                   # SET, COPY, CORRECT
    target_tag: str             # "item_2"
    field: str                  # "airflow_m3h", "dimensions", "material"
    value: Any = None           # Resolved absolute value (filled by resolve_derived_actions)
    derivation: str = ""        # "SAME_AS:item_1", "DOUBLE:item_1.airflow_m3h"


@dataclass
class SemanticIntent:
    """Structured extraction result from the Semantic Scribe."""
    entities: list[ScribeEntity] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    actions: list[ScribeAction] = field(default_factory=list)
    context_hints: list[str] = field(default_factory=list)
    clarification_answers: dict[str, Any] = field(default_factory=dict)
    intent_type: str = "CONFIGURE"  # CONFIGURE | QUESTION | COMPATIBILITY_CHECK
    language: str = "en"
    confidence: float = 0.0
    # v4.0: expanded extraction (previously regex-only)
    action_intent: str = "select"  # select|compare|configure|troubleshoot|general_info
    project_name: Optional[str] = None
    accessories: list[str] = field(default_factory=list)
    entity_codes: list[str] = field(default_factory=list)


# =============================================================================
# SCRIBE PROMPT
# =============================================================================

_SCRIBE_SYSTEM_PROMPT_TEMPLATE = """You are a parameter extraction engine for a technical product configuration system.
Given a user message, recent conversation history, current project state, and any pending clarification questions, extract structured changes.

RULES:
1. Extract entities (items/tags) with their numeric parameters (dimensions, airflow, etc.)
2. Resolve cross-references: "same as item 1" → copy item 1's actual values from the provided state
3. Resolve arithmetic: "double the airflow" → compute 2× the current value from state
4. Detect corrections: "I meant 600x900" → output a CORRECT action with the new absolute values
5. Extract spatial/installation constraints into parameters:
   - Width/height limits: "width cannot exceed 700mm" → {{"max_width_mm": 700}}, "max height 1000mm" → {{"max_height_mm": 1000}}
   - Available space: "shaft is 650mm wide" → {{"available_space_mm": 650}}, "opening is 800mm" → {{"available_space_mm": 800}}
   - Installation environment — match user keywords to the VALID ENVIRONMENT IDs below:
{env_mapping}
     If NO environment matches, do NOT guess. Omit installation_environment.
   - Application context — match user keywords to the VALID APPLICATION IDs below:
{app_mapping}
     If an application matches, include: {{"detected_application": "APP_XXX"}}
     Application and environment can BOTH be set (e.g., kitchen is both ENV_KITCHEN and APP_KITCHEN).
   - Chlorine: "60 ppm chlorine" → {{"chlorine_ppm": 60}}
   - ATEX zone: "ATEX Zone 22" → {{"atex_zone": "22"}}, "Zone 20" → {{"atex_zone": "20"}}, "Ex zone 2" → {{"atex_zone": "2"}}. Extract the zone NUMBER only (0, 1, 2, 20, 21, 22).
6. Extract environment/context hints as lowercase keywords (e.g., "flour dust" → ["flour_dust", "bakery"])
7. For dimension references, always resolve to absolute width×height values (integers in mm)
8. NEVER invent values not present in the message or state. If uncertain, omit the field.
9. Output ONLY valid JSON matching the schema below. No markdown, no explanation.
10. CLARIFICATION ANSWERS: When PENDING_CLARIFICATION is set, the system previously asked the user for a specific parameter. The user's message is the ANSWER. Extract the value into clarification_answers using the pending parameter name as key.
    - Button-click answers often have format "value (description)" e.g. "305 (305mm)" or "Zone 20/21/22 · Dust". Extract just the core value.
    - For numeric answers (airflow, depth, length): extract the integer value
    - For selection answers (zone, material): extract the selection text without description
    - If the pending parameter is "airflow" or similar, also put the value in the entity's airflow_m3h field
    - If the pending parameter is "filter_depth", extract depth as integer
    - If the pending parameter is "housing_length", extract length as integer
11. Extract material codes when mentioned: RF/stainless, FZ/galvanized, AZ/aluzink, ZM/zinkmagnesium, SF/sendzimir.
    Extract connection_type when mentioned: "PG" / "slip-in" / "PG profile" → "PG", "flange" / "fläns" / "flange connection" → "F". Only extract if user explicitly mentions connection type.
12. REFERENCE DATA vs USER REQUIREMENTS: Only create entities for items the user is REQUESTING to configure or design. If the user mentions a product's rated capacity as background info (e.g., "the standard model handles 3,400 m³/h"), do NOT create a separate entity for it. The user's REQUESTED values are preceded by "we need", "target", "our requirement", etc. Reference data is preceded by "handles", "rated", "capacity of", "up to", etc.
    REPLACEMENT SEMANTICS: When the user says "instead of X, we want Y" or "replace X with Y" or "rather than X, give me Y", this means REPLACE. Do NOT create entities for X — only create entities for Y. The "instead of" clause is context/reference, NOT a request. Example: "Instead of one 600x600 housing, we want four 300x300 housings" → create 4 entities of 300x300 only. Do NOT create a 600x600 entity.
13. PRODUCT FAMILY: When the user names a specific product code, extract the product_family INCLUDING any named variant suffix, replacing dashes with underscores. Examples: "GDC-FLEX 600x600" → product_family = "GDC_FLEX". "GDP-900x600" → product_family = "GDP". "GDMI-FLEX 600x600" → product_family = "GDMI_FLEX". Named variants like FLEX, NANO are part of the family identity and MUST be preserved.
    CRITICAL: Material codes (RF, FZ, AZ, ZM, SF) are NOT variant suffixes and MUST NOT be included in product_family. They are separate material selections. Examples: "GDMI-SF" → product_family = "GDMI", material = "SF". "GDC-RF" → product_family = "GDC", material = "RF". "GDB-FZ" → product_family = "GDB", material = "FZ". Only FLEX and NANO are valid variant suffixes.
    PRODUCT INFERENCE: When NO product code is named but the user describes features, infer product_family:
    - "insulated" / "insulation" / "thermal insulation" / "condensation-proof" → product_family = "GDMI"
    - "carbon" / "activated carbon" / "odor" / "gas adsorption" / "VOC" → product_family = "GDC" (or "GDC_FLEX" if "flex" mentioned)
    - "cartridge" / "carbon cartridge" → product_family = "GDC"
    - "pre-filter" / "protector" / "mechanical pre-filtration" → product_family = "GDP"
    - "pocket filter" / "bag filter" / "particle filter" → product_family = "GDB"
    Only infer when the description clearly maps to one family. If ambiguous, omit.
14. You are the PRIMARY and SOLE intent extractor. Extract ALL parameters comprehensively — dimensions, airflow, material, constraints, product family, action intent, accessories, project name. Do not assume another system will catch what you miss.
15. ACTION INTENT: Classify the overall intent into one of:
    - "select" (default): user wants to choose, specify, or configure a product
    - "compare": user wants to compare products or options ("compare", "vs", "difference", "versus", "porównaj")
    - "configure": user wants to set up options ("configure", "setup", "konfiguruj")
    - "troubleshoot": user reports a problem or asks about issues ("problem", "issue", "nie działa", "error", "troubleshoot", "leaking")
    - "general_info": general question not tied to a specific product selection
    Output as "action_intent" in top-level JSON.
16. PROJECT NAME: If the user mentions a project name (e.g., "for Project Nouryon", "Stockholm Mall project", "dla projektu Kraków"), extract it as "project_name" in the top-level JSON. Only extract proper nouns / named projects.
17. ACCESSORIES: Detect requests for accessories or add-ons:
    - Quick-release handles: "EXL" / "eccentric lock" / "quick release" → "EXL"
    - Left hinge: "left hinge" / "L hinge" → "L"
    - Round duct connections: "O500mm" / "500mm round duct" / "circular duct 500" → "Round duct OXXXMM" (with diameter)
    - Transition piece: "transition piece" / "reducer" / "adapter" → "Transition"
    Output as "accessories" array in top-level JSON. Only include if user explicitly requests them.
18. HOUSING LENGTH: When the user specifies a housing length value (typically 550, 600, 750, 800, or 900mm), extract it.
    - Per-entity: put in entity's "housing_length" field
    - Global: put in "parameters.housing_length"
    Housing length is DISTINCT from filter depth. Filter depth goes in dimensions.depth; housing length is the longitudinal dimension of the housing unit itself.
    - Bag/pocket filter depth: "600mm bag filters" / "bag filters 600 mm long" / "filter depth 600" → dimensions.depth = 600. This is the physical length of the filter element inserted into the housing.
19. ENTITY CODES: When the user mentions specific product codes or family names (e.g., "GDB", "GDC-FLEX", "GDC-600x600", "GDP-900x600-1200"), extract them as "entity_codes" array in top-level JSON. Include the raw code as mentioned."""

_SCRIBE_USER_TEMPLATE = """CURRENT PROJECT STATE:
{compact_state}

PENDING CLARIFICATION:
{pending_clarification}

RECENT CONVERSATION:
{recent_turns}

CURRENT USER MESSAGE:
{query}

OUTPUT JSON SCHEMA:
{{
  "entities": [
    {{
      "tag_ref": "item_1",
      "action": "CREATE|UPDATE|DELETE",
      "dimensions": {{"width": 600, "height": 900, "depth": 292}},
      "airflow_m3h": 3400,
      "product_family": "GDB",
      "material": "RF",
      "connection_type": "PG",
      "housing_length": 550
    }}
  ],
  "parameters": {{
    "max_width_mm": 700,
    "housing_length": 550,
    "available_space_mm": 650,
    "filter_depth": 600,
    "installation_environment": "ENV_INDOOR",
    "detected_application": "APP_KITCHEN",
    "chlorine_ppm": 60,
    "atex_zone": "22"
  }},
  "actions": [
    {{
      "type": "SET|COPY|CORRECT",
      "target_tag": "item_2",
      "field": "airflow_m3h|dimensions|material",
      "value": null,
      "derivation": "SAME_AS:item_1|DOUBLE:item_1.airflow_m3h"
    }}
  ],
  "clarification_answers": {{
    "parameter_name": "extracted_value"
  }},
  "intent_type": "CONFIGURE|QUESTION|COMPATIBILITY_CHECK",
  "action_intent": "select|compare|configure|troubleshoot|general_info",
  "project_name": "Nouryon",
  "accessories": ["EXL", "Round duct O500mm"],
  "entity_codes": ["GDB", "GDC-600x600"],
  "context_hints": ["bakery", "flour_dust"],
  "language": "en",
  "confidence": 0.85
}}

INTENT_TYPE RULES:
- CONFIGURE (default): User is selecting, configuring, or providing parameters for a product.
- QUESTION: User asks a yes/no or informational question (e.g., "Can I...?", "Is it possible...?", "What is the difference...?").
- COMPATIBILITY_CHECK: User asks about connecting, fitting, or compatibility between components (e.g., "Can I connect X to Y?", "Does this fit...?", "Will it work with...?").

Extract the structured data now:"""


# =============================================================================
# LLM EXTRACTION
# =============================================================================

def extract_semantic_intent(
    query: str,
    recent_turns: list[dict],
    technical_state,
    db=None,
    model: Optional[str] = None,
) -> Optional[SemanticIntent]:
    """Call LLM to extract structured intent from a conversational query.

    Args:
        query: Cleaned user message (no [STATE:] or [LOCKED:] wrappers)
        recent_turns: Last N conversation turns [{"role": "user", "message": "..."}]
        technical_state: Current TechnicalState with accumulated tags/params
        db: Optional Neo4jConnection for graph-driven environment/application mapping

    Returns:
        SemanticIntent or None if extraction fails
    """
    # Build compact state for prompt
    compact_state = technical_state.to_compact_summary()

    # Build pending clarification context
    pending = getattr(technical_state, 'pending_clarification', None)
    if pending:
        pending_str = f"The system asked for: {pending}\nThe user's message below is the ANSWER to this question. Extract the value."
    else:
        pending_str = "(none — this is a new query, not an answer to a clarification)"

    # Format recent turns
    if recent_turns:
        turns_str = "\n".join(
            f"[{t.get('role', 'user').upper()}] {t.get('message', '')}"
            for t in recent_turns
        )
    else:
        turns_str = "(no previous turns)"

    user_prompt = _SCRIBE_USER_TEMPLATE.format(
        compact_state=compact_state,
        pending_clarification=pending_str,
        recent_turns=turns_str,
        query=query,
    )

    _scribe_model = model or _MODEL
    try:
        print(f"🔍 [SCRIBE] Calling LLM model={_scribe_model}")
        result = llm_call(
            model=_scribe_model,
            user_prompt=user_prompt,
            system_prompt=get_scribe_system_prompt(db=db),
            json_mode=True,
            temperature=0.0,
            max_output_tokens=768,
        )

        if result.error:
            print(f"❌ [SCRIBE] LLM error (model={_scribe_model}): {result.error}")
            logger.warning(f"Scribe LLM call error: {result.error}")
            return None

        raw_text = result.text
        print(f"✅ [SCRIBE] Got {len(raw_text)} chars from {_scribe_model} in {result.duration_s}s")
        if not raw_text:
            logger.warning("Scribe returned empty response")
            return None

        data = json.loads(raw_text)
        return _parse_scribe_response(data)

    except json.JSONDecodeError as e:
        logger.warning(f"Scribe JSON parse failed: {e}")
        # Attempt basic repair for truncated JSON
        try:
            data = _repair_scribe_json(raw_text)
            if data:
                return _parse_scribe_response(data)
        except Exception:
            pass
        return None

    except Exception as e:
        logger.warning(f"Scribe LLM call failed: {e}")
        return None


def _parse_scribe_response(data: dict) -> SemanticIntent:
    """Parse raw JSON dict into SemanticIntent dataclass."""
    entities = []
    for ent in data.get("entities", []):
        if not ent.get("tag_ref"):
            continue
        entities.append(ScribeEntity(
            tag_ref=ent["tag_ref"],
            action=ent.get("action", "UPDATE"),
            dimensions=ent.get("dimensions"),
            airflow_m3h=_safe_int(ent.get("airflow_m3h")),
            product_family=ent.get("product_family"),
            material=ent.get("material"),
            connection_type=ent.get("connection_type"),
            housing_length=_safe_int(ent.get("housing_length")),
        ))

    actions = []
    for act in data.get("actions", []):
        if not act.get("target_tag") or not act.get("type"):
            continue
        actions.append(ScribeAction(
            type=act["type"].upper(),
            target_tag=act["target_tag"],
            field=act.get("field", ""),
            value=act.get("value"),
            derivation=act.get("derivation", ""),
        ))

    parameters = data.get("parameters", {})
    context_hints = data.get("context_hints", [])
    clarification_answers = data.get("clarification_answers", {})
    intent_type = data.get("intent_type", "CONFIGURE")
    if intent_type not in ("CONFIGURE", "QUESTION", "COMPATIBILITY_CHECK"):
        intent_type = "CONFIGURE"
    language = data.get("language", "en")
    confidence = float(data.get("confidence", 0.0))

    # v4.0: Parse expanded fields
    action_intent = data.get("action_intent", "select")
    if action_intent not in ("select", "compare", "configure", "troubleshoot", "general_info"):
        action_intent = "select"

    project_name = data.get("project_name")
    if project_name and not isinstance(project_name, str):
        project_name = None

    accessories = data.get("accessories", [])
    if not isinstance(accessories, list):
        accessories = []

    entity_codes = data.get("entity_codes", [])
    if not isinstance(entity_codes, list):
        entity_codes = []

    return SemanticIntent(
        entities=entities,
        parameters=parameters,
        actions=actions,
        context_hints=context_hints,
        clarification_answers=clarification_answers,
        intent_type=intent_type,
        language=language,
        confidence=confidence,
        action_intent=action_intent,
        project_name=project_name,
        accessories=accessories,
        entity_codes=entity_codes,
    )


def _repair_scribe_json(raw: str) -> Optional[dict]:
    """Minimal JSON repair for Scribe output (512 tokens rarely truncates)."""
    if not raw:
        return None
    # Try closing open brackets
    repaired = raw.rstrip()
    open_braces = repaired.count("{") - repaired.count("}")
    open_brackets = repaired.count("[") - repaired.count("]")
    for _ in range(open_brackets):
        repaired += "]"
    for _ in range(open_braces):
        repaired += "}"
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        return None


def _safe_int(val) -> Optional[int]:
    """Safely convert a value to int, returning None if impossible."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


# =============================================================================
# DERIVED ACTION RESOLVER
# =============================================================================

def resolve_derived_actions(
    intent: SemanticIntent,
    technical_state,
) -> SemanticIntent:
    """Resolve derived actions (SAME_AS, DOUBLE, etc.) against TechnicalState.

    The LLM identifies WHAT the user wants ("same as tag 1", "double the airflow").
    This function does the MATH on hard data from TechnicalState.

    Args:
        intent: Raw SemanticIntent from LLM
        technical_state: Current state with tag values

    Returns:
        Updated SemanticIntent with all derived values resolved to absolutes
    """
    resolved_actions = []

    for action in intent.actions:
        resolved = _resolve_single_action(action, technical_state)
        if resolved:
            resolved_actions.append(resolved)

    intent.actions = resolved_actions
    return intent


def _resolve_single_action(
    action: ScribeAction,
    technical_state,
) -> Optional[ScribeAction]:
    """Resolve a single derived action to absolute values."""
    derivation = action.derivation.upper().strip()

    # ----- CORRECT: value already absolute from LLM -----
    if action.type == "CORRECT":
        # For dimension corrections, unpack dict into separate width/height actions
        if action.field == "dimensions" and isinstance(action.value, dict):
            # Return the action as-is; _merge_scribe_into_state handles unpacking
            return action
        return action

    # ----- SAME_AS: copy from source tag -----
    if derivation.startswith("SAME_AS:"):
        source_ref = derivation.split(":", 1)[1].strip().lower()
        source_tag = technical_state.tags.get(source_ref)
        if not source_tag:
            logger.warning(f"Scribe: SAME_AS references unknown tag '{source_ref}', dropping")
            return None

        # Determine what to copy based on field
        if action.field == "dimensions":
            action.value = {
                "width": source_tag.housing_width,
                "height": source_tag.housing_height,
            }
        elif action.field == "airflow_m3h":
            action.value = source_tag.airflow_m3h
        elif action.field == "material":
            mat = technical_state.locked_material
            action.value = mat.value if mat else None
        elif hasattr(source_tag, action.field):
            action.value = getattr(source_tag, action.field)
        else:
            logger.warning(f"Scribe: SAME_AS field '{action.field}' not found on source tag")
            return None

        if action.value is None:
            logger.warning(f"Scribe: SAME_AS source tag '{source_ref}' has no value for '{action.field}'")
            return None

        action.type = "SET"  # Promote to SET with absolute value
        return action

    # ----- COPY: full tag duplication (all fields) -----
    if derivation.startswith("COPY:") or action.type == "COPY":
        source_ref = derivation.split(":", 1)[1].strip().lower() if ":" in derivation else ""
        if not source_ref:
            # Try to find source from derivation pattern
            return action if action.value is not None else None

        source_tag = technical_state.tags.get(source_ref)
        if not source_tag:
            logger.warning(f"Scribe: COPY references unknown tag '{source_ref}', dropping")
            return None

        # Copy all populated fields from source
        action.value = {
            "dimensions": {
                "width": source_tag.housing_width,
                "height": source_tag.housing_height,
            } if source_tag.housing_width and source_tag.housing_height else None,
            "airflow_m3h": source_tag.airflow_m3h,
            "product_family": source_tag.product_family,
        }
        action.field = "_full_copy"  # Signal to merge function
        action.type = "SET"
        return action

    # ----- DOUBLE / TRIPLE / HALF: arithmetic -----
    multiplier = None
    source_field = action.field.lower() if action.field else action.field

    if derivation.startswith("DOUBLE"):
        multiplier = 2.0
    elif derivation.startswith("TRIPLE"):
        multiplier = 3.0
    elif derivation.startswith("HALF"):
        multiplier = 0.5

    if multiplier is not None:
        # Parse source: "DOUBLE:item_1.airflow_m3h" or just "DOUBLE" (use target tag)
        parts = derivation.split(":", 1)
        if len(parts) > 1:
            ref_parts = parts[1].strip().split(".")
            source_ref = ref_parts[0].lower()
            if len(ref_parts) > 1:
                source_field = ref_parts[1].lower()
        else:
            source_ref = action.target_tag

        source_tag = technical_state.tags.get(source_ref)
        if not source_tag:
            logger.warning(f"Scribe: Arithmetic references unknown tag '{source_ref}', dropping")
            return None

        current_value = getattr(source_tag, source_field, None)
        if current_value is None:
            logger.warning(f"Scribe: Arithmetic field '{source_field}' is None on '{source_ref}'")
            return None

        try:
            action.value = int(float(current_value) * multiplier)
        except (ValueError, TypeError):
            logger.warning(f"Scribe: Cannot compute {multiplier}× on '{current_value}'")
            return None

        action.field = source_field
        action.type = "CORRECT"  # Arithmetic = user-requested value change, must override
        return action

    # ----- No derivation: use value as-is -----
    return action if action.value is not None else None
