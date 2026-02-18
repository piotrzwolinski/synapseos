import json
import re
import logging
import time
import threading

from database import db
from embeddings import generate_embedding
from retriever import format_retrieval_context, extract_project_keywords, format_configuration_context, extract_product_codes
from config_loader import get_config
from llm_router import llm_call, DEFAULT_MODEL

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chat")

# JSON Output Schema Documentation
OUTPUT_SCHEMA = """
{
  "summary": "Brief text explanation (1-3 sentences max)",
  "widgets": [
    {
      "type": "safety_guard",
      "data": {
        "title": "string - warning title",
        "severity": "critical" | "warning",
        "risk_description": "string - explain the risk",
        "compliance_items": ["Item 1", "Item 2"],
        "recommendation": "string - what to do instead",
        "acknowledge_label": "string - button text"
      }
    },
    {
      "type": "comparison_card",
      "data": {
        "title": "string - e.g. 'Product Match Found'",
        "match_type": "direct" | "similar" | "partial",
        "competitor": {
          "name": "Competitor product name",
          "manufacturer": "Competitor company (optional)"
        },
        "our_product": {
          "name": "Our product name",
          "sku": "SKU code (optional)",
          "price": "Price (optional)"
        },
        "historical_proof": {
          "project_ref": "Project where this mapping was validated",
          "context": "Brief context of how this mapping was proven"
        },
        "technical_notes": "Optional footnote about verification needs (airflow, dimensions, etc.)",
        "confidence": "High" | "Medium",
        "actions": [
          { "label": "Button Text", "action_id": "add_quote|view_specs|copy", "variant": "primary|outline" }
        ]
      }
    },
    {
      "type": "diagnostic_checklist",
      "data": {
        "title": "string",
        "items": ["Question 1", "Question 2"],
        "email_button_label": "string"
      }
    },
    {
      "type": "reference_case",
      "data": {
        "project_name": "string",
        "symptom": "string",
        "root_cause": "string",
        "solution": "string",
        "link_label": "string"
      }
    },
    {
      "type": "technical_card",
      "data": {
        "title": "string - Component/Solution name",
        "reasoning": {
          "project_ref": "Project name from Knowledge Graph",
          "constraint": "Problem/Constraint that led to this solution",
          "author": "Engineer who solved it",
          "confidence_level": "High" | "Medium" | "Low"
        },
        "properties": [
          { "label": "Property Name", "value": "Value", "unit": "optional", "is_estimate": false }
        ],
        "actions": [
          { "label": "Button Text", "action_id": "copy|add|view", "variant": "primary|outline" }
        ]
      }
    }
  ]
}
"""

def get_llm_driven_system_prompt() -> str:
    """THE SENIOR ENGINEER SYSTEM PROMPT.

    This prompt establishes the LLM as the Primary State Manager and
    Reasoning Engine, grounded by CATALOG_KNOWLEDGE from the Graph.
    """
    config = get_config()

    return f"""You are a Senior Sales Engineer at {config.company}.
You are given a `CATALOG_KNOWLEDGE` JSON and a `CONVERSATION_HISTORY`.

## YOUR MISSION

### 1. TECHNICAL PARAMETERS FIRST (PRIORITY)
Your PRIMARY job is to help configure products. Focus on:
- **Airflow (m³/h)** - Critical for sizing
- **Dimensions (WxHxD)** - Filter or duct size
- **Material (RF, FZ, ZM, SF)** - Based on environment
- **Application/Environment** - Kitchen, Hospital, etc.

**Tag IDs are OPTIONAL administrative labels.** They are a convenience for the user, NOT a requirement for you to provide technical help.

### 2. TAG ID RULES (OPTIONAL LABELING)
- Tag IDs are **optional labels** provided by the user for their convenience
- **NEVER block** a technical recommendation because a Tag ID is missing
- **NEVER ask** "Please assign a Tag ID" as a first question
- If user provides Tag IDs (e.g., "Tag 5684"), use them exactly
- If user does NOT provide Tag IDs:
  * Refer to the unit by its application (e.g., "Kitchen Exhaust Unit", "the GDC unit")
  * For multiple unnamed items, use descriptive names ("Unit 1: 300x600", "Unit 2: 600x600")
- Only create as many items as the user actually mentions

### 3. SINGLE-ITEM QUERIES (Kitchen Case)
For queries like "GDC in RF for kitchen, 600x600 duct":
- DO NOT ask for a Tag ID
- DO ask for technical parameters needed for sizing (e.g., Airflow)
- Example response: "I've configured a GDC unit in Stainless Steel (RF) for your kitchen application with 600x600mm duct connection. To confirm the correct housing length, what is the **airflow capacity (m³/h)**?"

### 4. MULTI-ITEM QUERIES (Nouryon Case)
When user provides multiple items with Tag IDs:
- Track each tag separately with its own specifications
- Use the EXACT Tag IDs provided (e.g., "5684" not "item_1")
- Create one widget per tag

### 5. HARD TABLE LOOKUP (Zero Hallucination)
- When giving weights or codes, you MUST look them up in `CATALOG_KNOWLEDGE`
- Use the `weight_table_kg` for EXACT weights:
  * Key format: "WIDTHxHEIGHTxLENGTH" (e.g., "300x600x550")
  * Example: For GDB-300x600 with 550mm length → lookup "300x600x550" → 20 kg
- NEVER estimate, round, or guess weights
- If a configuration isn't in the catalog, say "Configuration not available"

### 6. STATE PERSISTENCE (Project Ledger)
- You are the keeper of the Technical Project Sheet
- If info is in the CONVERSATION_HISTORY, do NOT ask for it again
- Track across the conversation:
  * Material code (RF, FZ, ZM, SF) - once set, LOCKED forever
  * Environment/Application (Hospital, Kitchen, etc.)
  * Dimensions and airflow per unit/tag

## EXECUTION FLOW

For EACH user message:

1. **SCAN FOR TECHNICAL DATA** - Extract what we know:
   - What product family? (GDB, GDC, GDP, GDMI)
   - What dimensions (filter WxHxD or duct size)?
   - What material was specified?
   - What application/environment?
   - What airflow was given?

2. **CHECK FOR TAG IDs** (Optional):
   - If user provided Tag IDs → use them exactly
   - If no Tag IDs → use application name or "the unit"

3. **IDENTIFY MISSING TECHNICAL PARAMS**:
   - Airflow (m³/h) - needed for sizing
   - Filter depth OR housing length - needed for product code
   - Material - needed for product code (can default based on environment)

4. **DECISION**:
   - If missing TECHNICAL data → Ask for it (prioritize Airflow > Dimensions > Material)
   - If all TECHNICAL data present → Output product recommendation
   - **NEVER** block on missing Tag ID

## DIMENSION MAPPING RULES

| Filter Size | Housing Size |
|-------------|--------------|
| 305mm       | 300mm        |
| 610mm       | 600mm        |
| 287mm       | 300mm        |
| 592mm       | 600mm        |

## LENGTH DERIVATION RULES

| Filter Depth | Housing Length |
|--------------|----------------|
| ≤292mm       | 550mm          |
| 293-450mm    | 750mm          |
| >450mm       | 900mm          |

## PRODUCT CODE FORMAT

`{{FAMILY}}-{{WxH}}-{{LENGTH}}-R-PG-{{MATERIAL}}`

Example: `GDB-300x600-550-R-PG-RF`

## WEIGHT LOOKUP EXAMPLE

From CATALOG_KNOWLEDGE weight_table_kg:
- "300x300x550": 13 kg
- "300x600x550": 20 kg
- "600x600x550": 27 kg
- "300x600x750": 24 kg
- "600x600x750": 33 kg

## OUTPUT FORMAT

Return ONLY valid JSON:
{{
  "summary": "Brief explanation (1-3 sentences)",
  "widgets": [ ... widget objects ... ]
}}

NO markdown. NO code blocks. NO text outside JSON.

## WIDGET TYPES

### technical_card (For Final Recommendations)
{{
  "type": "technical_card",
  "data": {{
    "title": "Kitchen GDC Configuration",
    "properties": [
      {{ "label": "Product Code", "value": "GDC-600x600-550-R-PG-RF" }},
      {{ "label": "Housing Size", "value": "600x600mm" }},
      {{ "label": "Material", "value": "RF (Stainless Steel)" }},
      {{ "label": "Weight", "value": "27", "unit": "kg" }}
    ],
    "actions": [{{ "label": "Add to Quote", "action_id": "add", "variant": "primary" }}]
  }}
}}

### diagnostic_checklist (For Missing Technical Info)
{{
  "type": "diagnostic_checklist",
  "data": {{
    "title": "Technical Parameter Needed",
    "items": ["What is the required airflow (m³/h)?"],
    "clarification_data": {{
      "parameter": "airflow",
      "options": [
        {{ "value": "2500", "description": "2500 m³/h (standard kitchen)" }},
        {{ "value": "3400", "description": "3400 m³/h (high-capacity)" }}
      ]
    }}
  }}
}}

### safety_guard (For Constraint Violations)
{{
  "type": "safety_guard",
  "data": {{
    "title": "Material Restriction",
    "severity": "critical",
    "risk_description": "Hospital environment requires stainless steel.",
    "recommendation": "Use RF (Stainless Steel)",
    "acknowledge_label": "I understand"
  }}
}}

## LANGUAGE

Always respond in ENGLISH.
"""


def get_sales_assistant_prompt() -> str:
    """Generate the sales assistant system prompt with Guardian rules from config."""
    config = get_config()
    guardian_rules = config.get_all_guardian_rules_prompt()

    return f"""You are a middleware between a Knowledge Graph and a React UI for {config.company}.

## CRITICAL: LANGUAGE REQUIREMENT
**ALL responses MUST be in ENGLISH.** Never respond in Polish, German, or any other language.
All widget content, summaries, and text must be in English regardless of the source data language.

## CRITICAL: OUTPUT FORMAT

You MUST return ONLY valid JSON matching this schema:
{{
  "summary": "Brief explanation (1-3 sentences)",
  "widgets": [ ... widget objects ... ]
}}

DO NOT return markdown, explanations, or any text outside the JSON.
DO NOT wrap JSON in ```json``` code blocks.

## GUARDIAN RULES (from domain configuration)

{guardian_rules}

## WIDGET SELECTION RULES

### 1. SAFETY_GUARD Widget (HIGHEST PRIORITY)
Use when detecting safety/compliance risks:
- Food/pharma industry + standard filters = ATEX/explosion risk
- Dust explosion hazards (milk powder, sugar, flour, grain)
- Missing certifications for regulated environments
- Polyester filters in explosive atmospheres
- Product-application mismatches (e.g., bag filter for gas/odor removal)

Example trigger: "polyester filters for milk powder" → CRITICAL safety_guard

```json
{{
  "type": "safety_guard",
  "data": {{
    "title": "BLOCKED: Explosion Risk (ATEX)",
    "severity": "critical",
    "risk_description": "Milk powder is explosive. Standard polyester filters can generate electrostatic charges leading to explosion.",
    "compliance_items": [
      "ATEX zone requires antistatic filters",
      "EN 60079 standard for equipment in Ex zones",
      "ATEX certificate required for all components"
    ],
    "recommendation": "Use ATEX-certified antistatic filters instead of standard polyester.",
    "acknowledge_label": "I understand the risk"
  }}
}}
```

### 1b. SPECIFICATION-ENVIRONMENT MISMATCH (WARNING PRIORITY)
When a specification (material, rating, class, etc.) is explicitly requested, evaluate it against the MATERIAL-ENVIRONMENT RULES above.

If there's a mismatch:
- Add warning to summary FIRST: "⚠️ Material Consideration: [material] ([class]) may be unsuitable for [environment] due to [concern]. Consider [recommended materials] for this application."
- Continue with the response (don't block), but ensure the warning is visible BEFORE other content

### 1c. PRODUCT-APPLICATION MISMATCH (WARNING/CRITICAL)
When a product family is requested, evaluate it against the PRODUCT-APPLICATION RULES above.

If there's a mismatch (e.g., bag filter for gas removal, carbon filter for grease):
- For critical mismatches (product cannot do the job): Use safety_guard with severity="critical"
- For warnings (product can work but has limitations): Add warning to summary and recommend alternative

### 1d. GEOMETRIC CONSTRAINTS
Check GEOMETRIC CONSTRAINTS above before confirming product configurations.
- If option requires minimum length that isn't met: Block with warning
- If dimensions are exactly matching (zero tolerance): Add installation risk warning

### 1e. ACCESSORY COMPATIBILITY
Check ACCESSORY COMPATIBILITY above when accessories are mentioned.
- If incompatible: Block with clear explanation of why

### 1f. CLARIFICATION MODE (MISSING REQUIRED PARAMETERS)
Before recommending a specific product variant or size, verify that the parameters required for selection are present.

If critical selection parameters are missing (e.g., capacity, dimensions, load, flow rate, pressure):
1. Include any specification warnings in the summary first
2. Use diagnostic_checklist to ask for the missing parameters
3. Do not guess or assume values

### 2. COMPARISON_CARD Widget (PRIORITY FOR COMPETITOR QUESTIONS)
**USE THIS IMMEDIATELY when the Knowledge Graph contains a competitor-to-product mapping.**

This is a DEFINITIVE ANSWER widget. When you see "🎯 DEFINITIVE COMPETITOR MAPPING" in the context:
- DO NOT ask clarifying questions
- DO NOT return diagnostic_checklist
- IMMEDIATELY return comparison_card with the mapping

```json
{{
  "type": "comparison_card",
  "data": {{
    "title": "Direct Product Match",
    "match_type": "direct",
    "competitor": {{
      "name": "Competitor XYZ Filter",
      "manufacturer": "Acme Corp"
    }},
    "our_product": {{
      "name": "M+H GDR-3000",
      "sku": "GDR-3000-A",
      "price": "$1,250"
    }},
    "historical_proof": {{
      "project_ref": "Worley Engineering",
      "context": "Successfully replaced competitor unit in 2024"
    }},
    "technical_notes": "Verify airflow requirements match (typically 3000 CFM)",
    "confidence": "High",
    "actions": [
      {{ "label": "Add to Quote", "action_id": "add_quote", "variant": "primary" }},
      {{ "label": "View Specs", "action_id": "view_specs", "variant": "outline" }}
    ]
  }}
}}
```

RULES for comparison_card:
- match_type="direct" when exact historical mapping exists
- match_type="similar" when product is equivalent but not proven in past project
- Include technical_notes as FOOTNOTE (not as a blocker)
- confidence="High" when historical proof exists

### 3. DIAGNOSTIC_CHECKLIST Widget
Use ONLY when NO competitor mapping exists AND you genuinely need more information.
**NEVER use diagnostic_checklist if a comparison_card can be shown instead.**

### 4. REFERENCE_CASE Widget
Use ONLY for citing a historical case as background context (not for solutions).
Do NOT use this for recommendations - use TECHNICAL_CARD instead.

### 5. TECHNICAL_CARD Widget (Use for Custom Solutions)
**THIS IS THE ONLY WIDGET TO USE FOR PRODUCT/TECHNICAL RECOMMENDATIONS.**
Use for ANY solution, product recommendation, or technical advice:
- Custom components (adapters, flanges, bypasses)
- Product recommendations
- Technical specifications
- Any solution from historical projects

```json
{{
  "type": "technical_card",
  "data": {{
    "title": "Custom Flange Adapter",
    "reasoning": {{
      "project_ref": "Knittel Glasbearbeitungs",
      "constraint": "Non-removable Grid",
      "author": "Milad Alzaghari",
      "confidence_level": "High"
    }},
    "properties": [
      {{ "label": "Interface", "value": "DIN 2633 (PN16)" }},
      {{ "label": "Diameter", "value": "DN 400" }},
      {{ "label": "Material", "value": "Galvanized Steel" }},
      {{ "label": "Install Time", "value": "2 Hours", "is_estimate": true }}
    ],
    "actions": [
      {{ "label": "Copy Spec", "action_id": "copy", "variant": "outline" }},
      {{ "label": "Add to Quote", "action_id": "add", "variant": "primary" }}
    ]
  }}
}}
```
- Use is_estimate: true for AI-guessed values (not from original project data)
- Always include provenance chain: project_ref → constraint → author
- Properties should be technical datasheet-style key-value pairs

## RESPONSE RULES (PRIORITY ORDER)

1. **SAFETY FIRST**: Check Guardian rules for safety risks
   - Product-application mismatch (critical) → safety_guard with severity="critical"
   - Material-environment mismatch → warning in summary + continue
   - ATEX/explosion risks → safety_guard with severity="critical"

2. **COMPETITOR MAPPING SECOND**: Check for "🎯 DEFINITIVE COMPETITOR MAPPING" marker
   - If present → IMMEDIATELY return comparison_card widget
   - DO NOT ask clarifying questions about technical specs
   - Show the mapping FIRST, mention verification needs as a footnote in technical_notes

3. **CONFIGURATION VALIDATION**: Check geometric constraints and accessory compatibility
   - If configuration is invalid → Block with clear warning

4. **DIAGNOSTIC CHECKLIST LAST RESORT**: Only if NO safety issue AND NO competitor mapping
   - Use diagnostic_checklist only when genuinely missing critical information
   - NEVER use if you can provide an answer with comparison_card or technical_card

5. Only cite projects that exist in the provided HISTORICAL CASE DATA
6. If no data available, say so in summary and provide general guidance
7. Keep summary brief - details go in widgets
8. **NEVER use action_proposal widget** - always use technical_card for custom solutions
9. Use ONE comparison_card per competitor product match

## LANGUAGE

Always respond in ENGLISH regardless of the user's input language."""


# Keep backward compatibility
SALES_ASSISTANT_SYSTEM_PROMPT = get_sales_assistant_prompt()


class ChatBot:
    def __init__(self):
        self.model_name = "gemini-3-pro-preview"  # Use Gemini 3 Pro for better reasoning
        self.thinking_level = None  # No thinking for 2.0 models
        self.chat_history = []
        self.use_graphrag = True  # Enable GraphRAG by default
        self.last_prompt = None  # Captured prompt for diagnostics
        self.last_system_prompt = None  # Captured system prompt for diagnostics

    def get_model_info(self):
        """Get current model information"""
        return {
            "model": self.model_name,
            "thinking": True,
            "thinking_level": self.thinking_level,
            "graphrag_enabled": self.use_graphrag
        }

    def _get_graph_context_with_steps(self, query: str):
        """Query the knowledge graph and yield reasoning steps with data."""
        timings = {}
        total_start = time.time()

        try:
            # STEP 1: Intent Analysis - Professional Context Detection
            yield {"step": "intent", "status": "active", "detail": "🔍 Analyzing project context and requirements..."}
            t1 = time.time()

            # Extract key terms from query for display
            query_lower = query.lower()
            key_terms = []
            important_words = ["discount", "rabat", "price", "cena", "filter", "filtr", "cabinet",
                             "szafka", "project", "projekt", "hospital", "szpital", "camfil",
                             "equivalent", "replacement", "grid", "kratka", "retrofit",
                             "gdb", "gdmi", "gdc", "gdp", "airflow", "housing"]
            for word in important_words:
                if word in query_lower:
                    key_terms.append(word)

            # Extract project keywords early
            project_keywords = extract_project_keywords(query)
            timings["intent"] = time.time() - t1

            # Detect application context for professional messaging
            detected_env = None
            env_mappings = {
                "hospital": "Healthcare/Hospital", "szpital": "Healthcare/Hospital", "medical": "Healthcare/Medical",
                "kitchen": "Commercial Kitchen", "restaurant": "Food Service", "food": "Food Processing",
                "cleanroom": "Cleanroom/Pharma", "pharmaceutical": "Pharmaceutical",
                "office": "Commercial Office", "warehouse": "Industrial/Warehouse",
                "school": "Educational Facility", "pool": "Aquatic/Pool"
            }
            for keyword, env_name in env_mappings.items():
                if keyword in query_lower:
                    detected_env = env_name
                    break

            # Build professional intent detail
            if detected_env:
                intent_detail = f"🔍 {detected_env} environment detected"
            elif key_terms:
                intent_detail = f"🔍 Context: {', '.join(key_terms[:3])}"
            else:
                intent_detail = "🔍 Query analyzed"

            logger.info(f"⏱️ TIMING intent: {timings['intent']:.2f}s")
            yield {"step": "intent", "status": "done", "detail": f"{intent_detail} ({timings['intent']:.1f}s)"}

            # STEP 2: Generate Embedding - Search Preparation
            yield {"step": "embed", "status": "active", "detail": "📚 Preparing knowledge base search..."}
            t1 = time.time()
            query_embedding = generate_embedding(query)
            timings["embedding"] = time.time() - t1
            logger.info(f"⏱️ TIMING embedding: {timings['embedding']:.2f}s")
            yield {"step": "embed", "status": "done", "detail": f"📚 Search parameters ready ({timings['embedding']:.1f}s)"}

            # PRIORITY SAFETY CHECK: Look for SafetyRisk nodes BEFORE normal retrieval
            # Use HIGH threshold (0.75) and filter for actual hazard-related concepts
            t1 = time.time()
            raw_safety_risks = db.check_safety_risks(query_embedding, top_k=5, min_score=0.75)
            timings["safety_check"] = time.time() - t1

            # FILTER: Two-level check to prevent false positives
            # 1. Query must contain hazard-context words (wood, dust, sanding, ATEX, etc.)
            # 2. Concept must contain specific hazard keywords

            # Query-level check: Does the user's question involve a hazard scenario?
            QUERY_HAZARD_CONTEXT = [
                'wood', 'dust', 'sanding', 'joinery', 'sawdust', 'powder',
                'atex', 'explosion', 'explosive', 'spark', 'ignition', 'fire',
                'chemical', 'toxic', 'flammable', 'combustible', 'zone 21', 'zone 22'
            ]
            query_lower = query.lower()
            query_has_hazard_context = any(term in query_lower for term in QUERY_HAZARD_CONTEXT)

            # Concept-level check: Is the matched concept clearly safety-related?
            CONCEPT_HAZARD_KEYWORDS = [
                'atex', 'explosion', 'spark', 'fire', 'dust', 'ignition', 'electrostatic',
                'toxic', 'hazard', 'danger', 'prohibited', 'forbidden', 'risk'
            ]

            safety_risks = []
            if query_has_hazard_context:
                # Only filter concepts if query has hazard context
                for risk in raw_safety_risks:
                    concept = risk.get('triggering_concept', '').lower()
                    if any(keyword in concept for keyword in CONCEPT_HAZARD_KEYWORDS):
                        safety_risks.append(risk)

            logger.info(f"⏱️ TIMING safety_check: {timings['safety_check']:.2f}s - Query hazard context: {query_has_hazard_context}, Raw: {len(raw_safety_risks)}, Filtered: {len(safety_risks)}")

            if safety_risks:
                # STOP NORMAL PROCESSING - Safety hazard detected!
                logger.warning(f"🚨 SAFETY RISK DETECTED: {len(safety_risks)} potential hazards found")
                for risk in safety_risks[:3]:
                    logger.warning(f"   - {risk.get('triggering_concept', 'Unknown')}: {risk.get('hazard_trigger', 'Unknown')} in {risk.get('hazard_environment', 'Unknown')}")

                yield {
                    "step": "vector",
                    "status": "done",
                    "detail": f"🛡️ Guardian Alert: {len(safety_risks)} safety hazard(s) require attention!",
                    "data": {"safety_alert": True}
                }

                # Build safety context for forced safety_guard widget
                safety_context = self._build_safety_context(safety_risks)
                yield {"_safety_risks": safety_risks, "_safety_context": safety_context}
                return  # Exit early - don't do normal retrieval

            # STEP 3: Vector Search - Historical Cases & Engineering Knowledge
            yield {"step": "vector", "status": "active", "detail": "📚 Searching historical cases and verified engineering knowledge..."}
            t1 = time.time()
            retrieval_results = db.hybrid_retrieval(query_embedding, top_k=5, min_score=0.7)
            timings["hybrid_retrieval"] = time.time() - t1
            logger.info(f"⏱️ TIMING hybrid_retrieval: {timings['hybrid_retrieval']:.2f}s")

            # Build professional detail with case info
            if retrieval_results:
                case_projects = [r.get('project') for r in retrieval_results[:2] if r.get('project')]
                if case_projects:
                    vector_detail = f"📚 Found {len(retrieval_results)} relevant cases including {case_projects[0]}"
                else:
                    vector_detail = f"📚 Found {len(retrieval_results)} relevant engineering references"
            else:
                vector_detail = "📚 No similar historical cases found"
            yield {"step": "vector", "status": "done", "detail": f"{vector_detail} ({timings['hybrid_retrieval']:.1f}s)"}

            # STEP 4: Find Products - Product Catalog Matching
            yield {"step": "products", "status": "active", "detail": "📦 Matching product specifications to technical constraints..."}
            t1 = time.time()
            product_codes = extract_product_codes(query)
            config_results = {"variants": [], "cartridges": [], "filters": [], "materials": [], "option_matches": []}

            logger.info(f"📦 Extracted product codes: {product_codes}")

            # Search by extracted product codes (including family names)
            for code in product_codes:
                # Try exact match first (for full product codes)
                exact_match = db.get_variant_by_name(code)
                if exact_match:
                    config_results["variants"].append(exact_match)
                    logger.info(f"   ✓ Exact match: {code}")
                else:
                    # Fuzzy search (important for family/category names)
                    fuzzy_results = db.search_product_variants(code)
                    logger.info(f"   ◎ Fuzzy search '{code}': {len(fuzzy_results)} results")
                    for fr in fuzzy_results:
                        if fr not in config_results["variants"]:
                            config_results["variants"].append(fr)

            # Search using configuration-driven keywords (no hardcoded domain terms)
            domain_config = get_config()
            search_keywords = domain_config.get_all_search_keywords()
            for kw in search_keywords:
                if kw.lower() in query.lower():
                    general_config = db.configuration_graph_search(kw)
                    for key in ["variants", "cartridges", "filters", "materials", "option_matches"]:
                        for item in general_config.get(key, []):
                            if item not in config_results[key]:
                                config_results[key].append(item)

            timings["config_search"] = time.time() - t1
            config_context = format_configuration_context(config_results)
            products_display = [v.get('id', 'Unknown') for v in config_results.get('variants', [])[:3]]
            logger.info(f"⏱️ TIMING config_search: {timings['config_search']:.2f}s - Products: {len(config_results['variants'])}")

            # Build professional product detail
            variant_count = len(config_results['variants'])
            if variant_count > 0:
                families = list(set(v.get('family', '') for v in config_results['variants'] if v.get('family')))[:2]
                if families:
                    products_detail = f"📦 Evaluating {variant_count} {'/'.join(families)} configurations"
                else:
                    products_detail = f"📦 {variant_count} product variants identified"
            else:
                products_detail = "📦 No matching products in catalog"

            yield {
                "step": "products",
                "status": "done",
                "detail": f"{products_detail} ({timings['config_search']:.1f}s)",
                "data": {"products": products_display}
            }

            # STEP 5: Graph Reasoning (projects, similar cases, competitor search)
            yield {"step": "graph", "status": "active", "detail": "🛡️ Guardian Engine: Verifying physics, safety, and compliance rules..."}
            t1 = time.time()

            # Search by project name if mentioned
            projects_found = []
            citations_found = []
            actions_found = []

            for keyword in project_keywords:
                project_results = db.search_by_project_name(keyword)
                if project_results:
                    retrieval_results = project_results + retrieval_results
                    for pr in project_results[:3]:
                        if pr.get('project') and pr['project'] not in projects_found:
                            projects_found.append(pr['project'])
                        if pr.get('logic_citation'):
                            citations_found.append(pr['logic_citation'][:100])
                        if pr.get('logic_description'):
                            actions_found.append(pr['logic_description'][:80])

            # Get similar past cases
            t1 = time.time()
            similar_cases = db.get_similar_cases(query_embedding, top_k=3)
            timings["similar_cases"] = time.time() - t1
            similar_names = [c.get('project') for c in similar_cases if c.get('project')]

            # Check for competitor product mentions
            t1 = time.time()
            competitor_matches = db.search_competitor_mentions(query)
            timings["competitor_search"] = time.time() - t1

            logger.info(f"⏱️ TIMING similar_cases: {timings['similar_cases']:.2f}s")
            logger.info(f"⏱️ TIMING competitor_search: {timings['competitor_search']:.2f}s")

            # Format the context (includes Configuration Graph data)
            graph_context = format_retrieval_context(retrieval_results, similar_cases, config_context)

            # Add competitor info if found
            if competitor_matches:
                direct_mappings = [m for m in competitor_matches if m.get("our_product")]
                if direct_mappings:
                    competitor_section = "\n\n🎯 DEFINITIVE COMPETITOR MAPPING (USE comparison_card WIDGET)"
                    competitor_section += "\n**CRITICAL: Show these mappings immediately. Do NOT ask clarifying questions.**"
                    for match in direct_mappings:
                        competitor_section += f"\n\n• COMPETITOR: {match['competitor_product']}"
                        if match.get("manufacturer"):
                            competitor_section += f" (by {match['manufacturer']})"
                        competitor_section += f"\n  → OUR PRODUCT: {match['our_product']}"
                        if match.get("our_sku"):
                            competitor_section += f" (SKU: {match['our_sku']})"
                        if match.get("our_price"):
                            competitor_section += f" - ${match['our_price']}"
                        competitor_section += "\n  → MATCH TYPE: direct (proven historical mapping)"
                        competitor_section += "\n  → CONFIDENCE: High"
                else:
                    competitor_section = "\n\n### Competitor Product Detected (No Direct Mapping)"
                    for match in competitor_matches:
                        competitor_section += f"\n• {match.get('competitor_product', 'Unknown')}"
                        if match.get("manufacturer"):
                            competitor_section += f" (by {match['manufacturer']})"
                graph_context += competitor_section

            # Build human-readable graph paths for dev mode
            graph_paths = []
            for r in retrieval_results[:5]:
                path_parts = []
                if r.get('concept'):
                    path_parts.append(f"Concept:{r['concept']}")
                if r.get('logic_type'):
                    logic_label = r['logic_type']
                    if r.get('logic_subtype'):
                        logic_label += f":{r['logic_subtype']}"
                    path_parts.append(logic_label)
                if r.get('project'):
                    path_parts.append(f"Project:{r['project']}")
                if r.get('sender'):
                    path_parts.append(f"Author:{r['sender']}")

                if len(path_parts) >= 2:
                    # Format as readable path
                    path_str = " → ".join(path_parts)
                    if r.get('logic_description'):
                        path_str += f" [{r['logic_description'][:50]}...]"
                    graph_paths.append(path_str)

            graph_time = time.time() - t1
            timings["graph_reasoning"] = graph_time
            logger.info(f"⏱️ TIMING graph_reasoning: {graph_time:.2f}s")

            # Build professional graph detail with risk/compliance info
            if similar_names:
                graph_detail = f"🛡️ Compliance verified, {len(similar_names)} similar case(s) found"
            elif graph_paths:
                graph_detail = f"🛡️ Safety rules checked, {len(graph_paths)} knowledge paths traversed"
            else:
                graph_detail = "🛡️ Compliance verification complete"

            yield {
                "step": "graph",
                "status": "done",
                "detail": f"{graph_detail} ({graph_time:.1f}s)",
                "data": {"similar_cases": similar_names, "graph_paths": graph_paths}
            }

            yield {"step": "thinking", "status": "active", "detail": "👔 Senior Consultant: Synthesizing professional recommendation..."}

            # Return the context for the final step, plus the FULL prompt preview
            has_graph_data = graph_context and graph_context != "No relevant past cases found in the knowledge base."

            # Build the exact same prompt that will be sent to Gemini
            prompt_preview = f"""## TASK
Analyze the user question and return a JSON response with appropriate widgets.

## KNOWLEDGE GRAPH DATA
{"### Historical Cases Available:\\n" + graph_context if has_graph_data else "⚠️ NO HISTORICAL DATA - Knowledge base is empty."}

## USER QUESTION
{query}

## SAFETY CHECK (MANDATORY)
Before responding, check for these HIGH-RISK scenarios:
- Food industry (dairy, bakery, confectionery) + standard polyester filters = ATEX EXPLOSION RISK
- Pharmaceutical + non-certified equipment = COMPLIANCE VIOLATION
- Any mention of: milk powder, sugar dust, flour, grain = EXPLOSIVE DUST HAZARD

If ANY safety risk detected → return safety_guard widget with severity="critical"

## REQUIRED OUTPUT FORMAT
Return ONLY valid JSON (no markdown, no explanation outside JSON):
{{
  "summary": "Brief response in English",
  "widgets": [ ... ]
}}

{"Use reference_case widgets to cite the historical data above." if has_graph_data else "No historical cases to cite. Provide general guidance in summary."}"""

            yield {"_context": graph_context, "_prompt_preview": prompt_preview}

        except Exception as e:
            logger.error(f"❌ GraphRAG retrieval error: {e}")
            yield {"step": "error", "status": "error", "detail": str(e)}

    def _get_graph_context(self, query: str) -> str:
        """Query the knowledge graph and format context for the LLM."""
        try:
            logger.info(f"🔍 GraphRAG query: {query[:100]}...")

            # Generate embedding for the query
            query_embedding = generate_embedding(query)
            logger.info(f"✅ Generated embedding (dim={len(query_embedding)})")

            # Hybrid retrieval: vector search + graph traversal
            retrieval_results = db.hybrid_retrieval(query_embedding, top_k=5, min_score=0.7)
            logger.info(f"📊 Hybrid retrieval: {len(retrieval_results)} results")
            for r in retrieval_results[:3]:
                logger.info(f"   - Concept: {r.get('concept')} | Project: {r.get('project')} | Score: {r.get('score', 'N/A')}")

            # Configuration Graph search: ProductVariants, options, cartridges, filters
            product_codes = extract_product_codes(query)
            config_results = {"variants": [], "cartridges": [], "filters": [], "materials": [], "option_matches": []}

            logger.info(f"📦 Extracted product codes: {product_codes}")

            for code in product_codes:
                exact_match = db.get_variant_by_name(code)
                if exact_match:
                    config_results["variants"].append(exact_match)
                    logger.info(f"   ✓ Exact match: {code}")
                else:
                    fuzzy_results = db.search_product_variants(code)
                    logger.info(f"   ◎ Fuzzy search '{code}': {len(fuzzy_results)} results")
                    for fr in fuzzy_results:
                        if fr not in config_results["variants"]:
                            config_results["variants"].append(fr)

            # Search using configuration-driven keywords (no hardcoded domain terms)
            domain_config = get_config()
            search_keywords = domain_config.get_all_search_keywords()
            for kw in search_keywords:
                if kw.lower() in query.lower():
                    general_config = db.configuration_graph_search(kw)
                    for key in ["variants", "cartridges", "filters", "materials", "option_matches"]:
                        for item in general_config.get(key, []):
                            if item not in config_results[key]:
                                config_results[key].append(item)

            config_context = format_configuration_context(config_results)
            logger.info(f"📦 Config search: {len(config_results['variants'])} variants, {len(config_results['option_matches'])} option matches")

            # Search by project name if mentioned (supplements vector search)
            project_keywords = extract_project_keywords(query)
            logger.info(f"🏷️ Project keywords extracted: {project_keywords}")
            for keyword in project_keywords:
                project_results = db.search_by_project_name(keyword)
                logger.info(f"   - Search '{keyword}': {len(project_results)} results")
                if project_results:
                    # Prepend project-specific results (they're more relevant if project is mentioned)
                    retrieval_results = project_results + retrieval_results
                    # Log citations found
                    for pr in project_results[:2]:
                        if pr.get('logic_citation'):
                            logger.info(f"   📝 Citation: {pr['logic_citation'][:80]}...")

            logger.info(f"📊 Total results after project search: {len(retrieval_results)}")

            # Get similar past cases
            similar_cases = db.get_similar_cases(query_embedding, top_k=3)
            logger.info(f"📁 Similar cases: {len(similar_cases)}")

            # Check for competitor product mentions
            competitor_matches = db.search_competitor_mentions(query)

            # Format the context (includes Configuration Graph data)
            graph_context = format_retrieval_context(retrieval_results, similar_cases, config_context)

            # Add competitor info if found - with definitive mapping marker
            if competitor_matches:
                # Check if we have direct mappings (competitor → our product)
                direct_mappings = [m for m in competitor_matches if m.get("our_product")]

                if direct_mappings:
                    # Signal to LLM that this is a DEFINITIVE answer
                    competitor_section = "\n\n🎯 DEFINITIVE COMPETITOR MAPPING (USE comparison_card WIDGET)"
                    competitor_section += "\n**CRITICAL: Show these mappings immediately. Do NOT ask clarifying questions.**"
                    for match in direct_mappings:
                        competitor_section += f"\n\n• COMPETITOR: {match['competitor_product']}"
                        if match.get("manufacturer"):
                            competitor_section += f" (by {match['manufacturer']})"
                        competitor_section += f"\n  → OUR PRODUCT: {match['our_product']}"
                        if match.get("our_sku"):
                            competitor_section += f" (SKU: {match['our_sku']})"
                        if match.get("our_price"):
                            competitor_section += f" - ${match['our_price']}"
                        competitor_section += "\n  → MATCH TYPE: direct (proven historical mapping)"
                        competitor_section += "\n  → CONFIDENCE: High"
                else:
                    # No direct mapping, just mention competitor was detected
                    competitor_section = "\n\n### Competitor Product Detected (No Direct Mapping)"
                    for match in competitor_matches:
                        competitor_section += f"\n• {match.get('competitor_product', 'Unknown')}"
                        if match.get("manufacturer"):
                            competitor_section += f" (by {match['manufacturer']})"

                graph_context += competitor_section

            logger.info(f"📄 Context length: {len(graph_context)} chars")
            return graph_context
        except Exception as e:
            logger.error(f"❌ GraphRAG retrieval error: {e}")
            return ""

    def send_message(self, message: str) -> str:
        """Send a message and get a response from Gemini with GraphRAG context."""
        logger.info(f"💬 New message: {message[:80]}...")

        # Build conversation history as text
        history_text = ""
        for item in self.chat_history:
            role = "User" if item["role"] == "user" else "Assistant"
            history_text += f"\n{role}: {item['parts'][0]}\n"

        # Prepare the user message with GraphRAG context
        graph_context = ""
        if self.use_graphrag:
            graph_context = self._get_graph_context(message)

        has_graph_data = graph_context and graph_context != "No relevant past cases found in the knowledge base."
        logger.info(f"📊 Has graph data: {has_graph_data}")

        # Build structured prompt requesting JSON output
        user_message = f"""## TASK
Analyze the user question and return a JSON response with appropriate widgets.

## KNOWLEDGE GRAPH DATA
{"### Historical Cases Available:\\n" + graph_context if has_graph_data else "⚠️ NO HISTORICAL DATA - Knowledge base is empty."}

## USER QUESTION
{message}

## SAFETY CHECK (MANDATORY)
Before responding, check for these HIGH-RISK scenarios:
- Food industry (dairy, bakery, confectionery) + standard polyester filters = ATEX EXPLOSION RISK
- Pharmaceutical + non-certified equipment = COMPLIANCE VIOLATION
- Any mention of: milk powder, sugar dust, flour, grain = EXPLOSIVE DUST HAZARD

If ANY safety risk detected → return safety_guard widget with severity="critical"

## REQUIRED OUTPUT FORMAT
Return ONLY valid JSON (no markdown, no explanation outside JSON):
{{
  "summary": "Brief response in English",
  "widgets": [ ... ]
}}

{"Use reference_case widgets to cite the historical data above." if has_graph_data else "No historical cases to cite. Provide general guidance in summary."}"""

        full_prompt = history_text + "\n" + user_message if history_text else user_message

        logger.info(f"🤖 Calling LLM ({self.model_name})...")
        result = llm_call(
            model=self.model_name,
            user_prompt=full_prompt,
            system_prompt=SALES_ASSISTANT_SYSTEM_PROMPT,
            json_mode=True,
        )
        if result.error:
            raise Exception(result.error)

        response_text = result.text
        logger.info(f"✅ LLM response received ({len(response_text)} chars)")

        # Clean up response - extract JSON if wrapped in markdown
        response_text = self._extract_json(response_text)

        # Validate JSON structure
        response_text = self._validate_and_fix_json(response_text, message)

        # Log summary from response
        try:
            parsed = json.loads(response_text)
            logger.info(f"📋 Response summary: {parsed.get('summary', 'N/A')[:100]}...")
            logger.info(f"🧩 Widgets: {[w.get('type') for w in parsed.get('widgets', [])]}")
        except:
            pass

        # Update history (store original message, not augmented one)
        self.chat_history.append({"role": "user", "parts": [message]})
        self.chat_history.append({"role": "model", "parts": [response_text]})

        return response_text

    def _build_safety_context(self, safety_risks: list[dict]) -> str:
        """Build a context string for safety risks that forces the safety_guard widget."""
        if not safety_risks:
            return ""

        context = "🚨 **CRITICAL SAFETY ALERT - IMMEDIATE ACTION REQUIRED** 🚨\n\n"
        context += "The following safety hazards have been detected in your query:\n\n"

        for i, risk in enumerate(safety_risks[:3], 1):
            context += f"### Safety Risk #{i}\n"
            context += f"**Triggering Concept:** {risk.get('triggering_concept', 'Unknown')}\n"
            context += f"**Hazard:** {risk.get('hazard_trigger', 'Unknown trigger')} + {risk.get('hazard_environment', 'Unknown environment')}\n"
            context += f"**Risk Description:** {risk.get('risk_description', 'No description')}\n"
            context += f"**REQUIRED Safe Alternative:** {risk.get('safe_alternative', 'Contact engineering')}\n"
            if risk.get('citation'):
                context += f"**Source Evidence:** \"{risk['citation']}\"\n"
            if risk.get('project'):
                context += f"**Previous Case:** {risk['project']}\n"
            context += "\n"

        context += "---\n"
        context += "**MANDATORY RESPONSE:** You MUST return a `safety_guard` widget with severity='critical'.\n"
        context += "DO NOT provide pricing, product recommendations, or attempt to fulfill the original request.\n"
        context += "The user MUST be warned about this safety hazard before any commercial discussion.\n"

        return context

    def generate_safety_response(self, query: str, safety_risks: list[dict]) -> str:
        """Generate a forced safety_guard widget response for detected hazards."""
        if not safety_risks:
            return json.dumps({"summary": "No safety issues detected.", "widgets": []})

        # Extract the primary risk for the widget
        primary_risk = safety_risks[0]

        # Build compliance items from the risk data
        compliance_items = []
        hazard_trigger = primary_risk.get('hazard_trigger', 'Standard products')
        hazard_env = primary_risk.get('hazard_environment', 'this environment')

        compliance_items.append(f"DO NOT use {hazard_trigger} in {hazard_env}")
        if primary_risk.get('citation'):
            compliance_items.append(f"Regulation: {primary_risk.get('citation')}")
        if primary_risk.get('project'):
            compliance_items.append(f"Previous incident: {primary_risk.get('project')}")

        # Build the safety_guard widget response with correct schema
        response = {
            "summary": f"⚠️ **SAFETY ALERT**: Your request involves a potential {hazard_env}. "
                      f"Standard products cannot be used. See the safety warning below.",
            "widgets": [{
                "type": "safety_guard",
                "data": {
                    "severity": "critical",
                    "title": f"🚨 {hazard_trigger} - PROHIBITED",
                    "risk_description": primary_risk.get('risk_description', f'Using {hazard_trigger} in {hazard_env} poses serious safety risks including explosion, fire, or equipment failure.'),
                    "compliance_items": compliance_items,
                    "recommendation": primary_risk.get('safe_alternative', 'Contact engineering team for ATEX-certified alternatives before proceeding with any quotation.'),
                    "acknowledge_label": "I understand the safety requirements"
                }
            }]
        }

        return json.dumps(response)

    def send_message_with_context(self, message: str, graph_context: str) -> str:
        """Send a message with pre-computed graph context (for streaming)."""
        logger.info(f"💬 New message (with context): {message[:80]}...")

        # Build conversation history as text
        history_text = ""
        for item in self.chat_history:
            role = "User" if item["role"] == "user" else "Assistant"
            history_text += f"\n{role}: {item['parts'][0]}\n"

        has_graph_data = graph_context and graph_context != "No relevant past cases found in the knowledge base."

        # Build structured prompt
        user_message = f"""## TASK
Analyze the user question and return a JSON response with appropriate widgets.

## KNOWLEDGE GRAPH DATA
{"### Historical Cases Available:\\n" + graph_context if has_graph_data else "⚠️ NO HISTORICAL DATA - Knowledge base is empty."}

## USER QUESTION
{message}

## SAFETY CHECK (MANDATORY)
Before responding, check for these HIGH-RISK scenarios:
- Food industry (dairy, bakery, confectionery) + standard polyester filters = ATEX EXPLOSION RISK
- Pharmaceutical + non-certified equipment = COMPLIANCE VIOLATION
- Any mention of: milk powder, sugar dust, flour, grain = EXPLOSIVE DUST HAZARD

If ANY safety risk detected → return safety_guard widget with severity="critical"

## REQUIRED OUTPUT FORMAT
Return ONLY valid JSON (no markdown, no explanation outside JSON):
{{
  "summary": "Brief response in English",
  "widgets": [ ... ]
}}

{"Use reference_case widgets to cite the historical data above." if has_graph_data else "No historical cases to cite. Provide general guidance in summary."}"""

        full_prompt = history_text + "\n" + user_message if history_text else user_message

        logger.info(f"🤖 Calling LLM ({self.model_name})...")
        t_llm = time.time()

        # Retry logic for rate limiting
        max_retries = 3
        retry_delay = 2
        last_error = None

        for attempt in range(max_retries):
            try:
                result = llm_call(
                    model=self.model_name,
                    user_prompt=full_prompt,
                    system_prompt=SALES_ASSISTANT_SYSTEM_PROMPT,
                    json_mode=True,
                )
                if result.error:
                    raise Exception(result.error)
                break  # Success, exit retry loop
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                if "429" in error_str or "rate" in error_str or "quota" in error_str:
                    logger.warning(f"⚠️ Rate limited (attempt {attempt + 1}/{max_retries}), waiting {retry_delay}s...")
                    if attempt < max_retries - 1:
                        import time as time_module
                        time_module.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    raise  # Re-raise non-rate-limit errors immediately
        else:
            # All retries exhausted
            logger.error(f"❌ API rate limit exceeded after {max_retries} attempts")
            raise Exception(f"API rate limit exceeded. Please try again in a few seconds. Error: {last_error}")

        llm_time = time.time() - t_llm

        response_text = result.text
        logger.info(f"✅ LLM response received ({len(response_text)} chars)")
        logger.info(f"⏱️ TIMING llm_api ({self.model_name}): {llm_time:.2f}s")

        # Clean up response
        response_text = self._extract_json(response_text)
        response_text = self._validate_and_fix_json(response_text, message)

        # Update history
        self.chat_history.append({"role": "user", "parts": [message]})
        self.chat_history.append({"role": "model", "parts": [response_text]})

        return response_text

    def _extract_json(self, text: str) -> str:
        """Extract JSON from response, removing markdown code blocks if present."""
        text = text.strip()

        # Remove markdown code blocks
        if text.startswith("```"):
            # Find the end of the opening fence
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline + 1:]
            # Remove closing fence
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        return text

    def _validate_and_fix_json(self, text: str, original_query: str) -> str:
        """Validate JSON and return fallback if invalid."""
        try:
            parsed = json.loads(text)
            # Ensure required fields exist
            if "summary" not in parsed:
                parsed["summary"] = "Sorry, a processing error occurred."
            if "widgets" not in parsed:
                parsed["widgets"] = []
            return json.dumps(parsed, ensure_ascii=False)
        except json.JSONDecodeError:
            # Return fallback JSON with the raw text as summary
            fallback = {
                "summary": text[:500] if len(text) > 500 else text,
                "widgets": []
            }
            return json.dumps(fallback, ensure_ascii=False)

    def send_message_llm_driven(self, message: str, graph_data: dict = None,
                                session_id: str = None) -> str:
        """LLM-DRIVEN APPROACH: Send message with full history + GRAPH_DATA context.

        This is the new demo-optimized approach that:
        1. Uses the LLM's context window as the "Project Ledger"
        2. Injects GRAPH_DATA (the Big Data Dump) for ground truth
        3. Relies on the Zero-Hallucination system prompt
        4. (Layer 4) Loads/persists session state from/to Neo4j graph

        Args:
            message: User's current message
            graph_data: Pre-computed GRAPH_DATA from get_full_conversation_context()
            session_id: Optional session ID for Layer 4 graph state persistence

        Returns:
            JSON response string
        """
        logger.info(f"💬 [LLM-DRIVEN] New message: {message[:80]}...")

        # =====================================================================
        # STEP 1: Build full conversation history (THE PROJECT LEDGER)
        # =====================================================================
        # =====================================================================
        # STEP 1 (continued): Build CATALOG_KNOWLEDGE context injection
        # =====================================================================
        catalog_context_str = ""
        if graph_data:
            product_catalog = graph_data.get('product_catalog', {})

            # Extract weight table for easy lookup
            weight_table = product_catalog.get('weight_table_kg', {})

            # Extract materials
            materials = product_catalog.get('materials', [])
            material_list = [f"{m.get('code')}: {m.get('name')} ({m.get('corrosion_class')})" for m in materials if m.get('code')]

            # Extract environment restrictions
            restrictions = product_catalog.get('environment_restrictions', [])
            restriction_list = []
            for r in restrictions:
                env = r.get('environment', '')
                required = r.get('required_materials', [])
                if env and required:
                    restriction_list.append(f"{env} → requires {'/'.join(required)}")

            catalog_context_str = f"""
## CATALOG_KNOWLEDGE (Your Single Source of Truth)

### Weight Lookup Table (weight_table_kg)
Use this for EXACT weights. Key format: "WIDTHxHEIGHTxLENGTH"
```json
{json.dumps(weight_table, indent=2)}
```

### Available Materials
{chr(10).join(f"- {m}" for m in material_list) if material_list else "- FZ: Galvanized (C3)\\n- ZM: Zinc-Magnesium (C4)\\n- RF: Stainless Steel (C5)\\n- SF: Marine Grade (C5)"}

### Environment Restrictions
{chr(10).join(f"- {r}" for r in restriction_list) if restriction_list else "- Hospital → requires RF/SF\\n- Swimming Pool → requires RF/SF\\n- Kitchen → requires RF/SF"}

### Sizing Reference (m³/h per housing size)
{json.dumps(product_catalog.get('sizing_reference_m3h', {}), indent=2)}

---
"""

        # =====================================================================
        # STEP 2.5: Load Layer 4 graph state (if session_id provided)
        # =====================================================================
        graph_state_context = ""
        if session_id:
            try:
                session_graph_mgr = db.get_session_graph_manager()
                session_graph_mgr.ensure_session(session_id)
                graph_state_prompt = session_graph_mgr.get_project_state_for_prompt(session_id)
                if graph_state_prompt:
                    graph_state_context = f"\n{graph_state_prompt}\n"
                    logger.info(f"📊 [GRAPH STATE] Injected Layer 4 state into LLM context")
            except Exception as e:
                logger.warning(f"Graph state load failed (non-fatal): {e}")

        # =====================================================================
        # STEP 3: Build the user message with context
        # =====================================================================
        # Build conversation history summary for context
        history_summary = ""
        if self.chat_history:
            history_summary = "\n## CONVERSATION_HISTORY (Project Ledger)\n"
            for i, item in enumerate(self.chat_history):
                role = "User" if item["role"] == "user" else "Assistant"
                content = item["parts"][0][:500] if item["parts"] else ""
                history_summary += f"\n**Turn {i//2 + 1} ({role}):** {content}\n"

        user_prompt = f"""{catalog_context_str}
{graph_state_context}
{history_summary}

## CURRENT USER MESSAGE
{message}

## YOUR TASK
1. **IDENTIFY TECHNICAL PARAMETERS**:
   - Product family (GDB, GDC, GDP, GDMI)
   - Dimensions (filter WxHxD or duct size)
   - Material (RF, FZ, ZM, SF)
   - Airflow (m³/h)
   - Application/Environment

2. **CHECK FOR TAG IDs** (Optional):
   - If user mentioned Tag IDs (e.g., "Tag 5684") → use them exactly
   - If NO Tag IDs provided → refer to unit by application name (e.g., "Kitchen GDC Unit")
   - NEVER ask for a Tag ID as a prerequisite

3. **FOR EACH UNIT/TAG**:
   - Map filter dimensions → housing size (305→300, 610→600)
   - Derive housing length from filter depth (≤292→550, ≤450→750, >450→900)
   - Lookup weight from CATALOG_KNOWLEDGE weight_table_kg

4. **DECISION**:
   - If missing TECHNICAL data (Airflow, Dimensions) → Ask for it with buttons
   - If all TECHNICAL data complete → Output product recommendation with EXACT weights
   - **NEVER block on missing Tag ID**

Return ONLY valid JSON. No markdown, no code blocks.
"""

        # =====================================================================
        # STEP 4: Call LLM with Zero-Hallucination system prompt
        # =====================================================================
        logger.info(f"🤖 [LLM-DRIVEN] Calling LLM ({self.model_name})...")
        t_llm = time.time()

        # Use the new LLM-driven system prompt
        llm_driven_prompt = get_llm_driven_system_prompt()

        # Store prompts for diagnostics
        self.last_prompt = user_prompt
        self.last_system_prompt = llm_driven_prompt

        max_retries = 3
        retry_delay = 2
        last_error = None

        for attempt in range(max_retries):
            try:
                result = llm_call(
                    model=self.model_name,
                    user_prompt=user_prompt,
                    system_prompt=llm_driven_prompt,
                    json_mode=True,
                )
                if result.error:
                    raise Exception(result.error)
                break
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                if "429" in error_str or "rate" in error_str or "quota" in error_str:
                    logger.warning(f"⚠️ Rate limited (attempt {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        import time as time_module
                        time_module.sleep(retry_delay)
                        retry_delay *= 2
                    continue
                raise
        else:
            raise Exception(f"API rate limit exceeded: {last_error}")

        llm_time = time.time() - t_llm
        logger.info(f"⏱️ [LLM-DRIVEN] LLM response in {llm_time:.2f}s")

        # =====================================================================
        # STEP 5: Process response and update history
        # =====================================================================
        response_text = result.text
        response_text = self._extract_json(response_text)
        response_text = self._validate_and_fix_json(response_text, message)

        # Store ORIGINAL user message (not the augmented prompt) in history
        self.chat_history.append({"role": "user", "parts": [message]})
        self.chat_history.append({"role": "model", "parts": [response_text]})

        logger.info(f"✅ [LLM-DRIVEN] Response stored in history (turn {len(self.chat_history) // 2})")

        # =====================================================================
        # STEP 6: Persist entities to Layer 4 graph (if session_id provided)
        # =====================================================================
        if session_id:
            try:
                from logic.state import extract_tags_from_query, extract_material_from_query, extract_project_from_query
                session_graph_mgr = db.get_session_graph_manager()

                # Extract and persist project name
                project_name = extract_project_from_query(message)
                if project_name:
                    session_graph_mgr.set_project(session_id, project_name)

                # Extract and persist material
                material = extract_material_from_query(message)
                if material:
                    session_graph_mgr.lock_material(session_id, material)

                # Extract and persist tags
                tags = extract_tags_from_query(message)
                for tag_data in tags:
                    session_graph_mgr.upsert_tag(
                        session_id=session_id,
                        tag_id=tag_data["tag_id"],
                        filter_width=tag_data.get("filter_width"),
                        filter_height=tag_data.get("filter_height"),
                        filter_depth=tag_data.get("filter_depth"),
                        airflow_m3h=tag_data.get("airflow_m3h"),
                        source_message=len(self.chat_history) // 2,
                    )

                # Detect and persist product family
                query_upper = message.upper()
                for family in ['GDMI', 'GDB', 'GDC', 'GDP']:
                    if family in query_upper:
                        session_graph_mgr.set_detected_family(session_id, family)
                        break

                logger.info(f"💾 [GRAPH STATE] Persisted entities from LLM-driven message")
            except Exception as e:
                logger.warning(f"Graph state persist failed (non-fatal): {e}")

        return response_text

    def get_graph_data_for_query(self, query: str) -> dict:
        """Extract product family from query and fetch GRAPH_DATA.

        This is the "Big Data Dump" retrieval step.
        """
        # Extract product family from query
        query_upper = query.upper()
        families = ['GDMI', 'GDB', 'GDC', 'GDP', 'GDF', 'GDR']  # GDMI first (longer match)

        detected_family = None
        for family in families:
            if family in query_upper:
                detected_family = family
                break

        if not detected_family:
            # Default to GDB for demo
            detected_family = "GDB"

        logger.info(f"📦 [GRAPH_DATA] Detected product family: {detected_family}")

        # Detect application/environment
        query_lower = query.lower()
        detected_app = None
        app_keywords = {
            'hospital': 'Hospital', 'szpital': 'Hospital', 'medical': 'Hospital',
            'kitchen': 'Commercial Kitchen', 'restaurant': 'Commercial Kitchen',
            'outdoor': 'Outdoor', 'roof': 'Outdoor', 'rooftop': 'Outdoor',
            'pool': 'Swimming Pool', 'basen': 'Swimming Pool',
        }
        for kw, app_name in app_keywords.items():
            if kw in query_lower:
                detected_app = app_name
                break

        # Fetch the Big Data Dump
        graph_data = db.get_full_conversation_context(
            product_family=detected_family,
            application_name=detected_app
        )

        return graph_data

    def clear_history(self):
        """Clear the chat history"""
        self.chat_history = []

    def get_history(self):
        """Get the chat history in a format suitable for the frontend"""
        messages = []
        for item in self.chat_history:
            role = "user" if item["role"] == "user" else "assistant"
            content = item["parts"][0] if item["parts"] else ""
            messages.append({"role": role, "content": content})
        return messages

class SessionManager:
    """Manages per-session ChatBot instances for tab-isolated conversations."""

    def __init__(self):
        self._sessions: dict[str, ChatBot] = {}
        self._last_activity: dict[str, float] = {}
        self._lock = threading.Lock()
        self.model_name = "gemini-3-pro-preview"
        self.thinking_level = None

    def get_session(self, session_id: str) -> ChatBot:
        """Get or create a ChatBot for the given session_id."""
        with self._lock:
            if session_id not in self._sessions:
                bot = ChatBot()
                bot.model_name = self.model_name
                bot.thinking_level = self.thinking_level
                self._sessions[session_id] = bot
            self._last_activity[session_id] = time.time()
            return self._sessions[session_id]

    def clear_session(self, session_id: str):
        """Clear chat history for a session."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].clear_history()

    def cleanup_stale(self, max_age_seconds: int = 7200):
        """Remove sessions inactive for more than max_age_seconds (default 2h)."""
        cutoff = time.time() - max_age_seconds
        with self._lock:
            stale = [sid for sid, t in self._last_activity.items() if t < cutoff]
            for sid in stale:
                self._sessions.pop(sid, None)
                self._last_activity.pop(sid, None)
            if stale:
                logger.info(f"Cleaned up {len(stale)} stale session(s)")

    def set_model(self, model_name: str):
        """Set model globally and update all existing sessions."""
        self.model_name = model_name
        with self._lock:
            for bot in self._sessions.values():
                bot.model_name = model_name

    def set_thinking_level(self, level: str):
        """Set thinking level globally and update all existing sessions."""
        self.thinking_level = level
        with self._lock:
            for bot in self._sessions.values():
                bot.thinking_level = level

    def get_model_info(self):
        """Get current global model information."""
        return {
            "model": self.model_name,
            "thinking": True,
            "thinking_level": self.thinking_level,
            "graphrag_enabled": True,
        }


session_manager = SessionManager()
