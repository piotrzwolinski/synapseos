import os
import json
import re
import logging
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

from database import db
from embeddings import generate_embedding
from retriever import format_retrieval_context, extract_project_keywords, format_configuration_context, extract_product_codes
from config_loader import get_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chat")

load_dotenv(dotenv_path="../.env")

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

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
        self.model_name = "gemini-3-pro-preview"
        self.thinking_level = "high"
        self.chat_history = []
        self.use_graphrag = True  # Enable GraphRAG by default

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
            yield {"step": "embed", "status": "active", "detail": "Analyzing question..."}

            # Extract key terms from query for display
            t0 = time.time()
            query_lower = query.lower()
            key_terms = []
            # Extract meaningful words (simple approach)
            important_words = ["discount", "rabat", "price", "cena", "filter", "filtr", "cabinet",
                             "szafka", "project", "projekt", "hospital", "szpital", "camfil",
                             "equivalent", "replacement", "grid", "kratka", "retrofit"]
            for word in important_words:
                if word in query_lower:
                    key_terms.append(word)

            # Generate embedding for the query
            t1 = time.time()
            query_embedding = generate_embedding(query)
            timings["embedding"] = time.time() - t1

            # Also extract project keywords early for display
            project_keywords = extract_project_keywords(query)

            analyzed_detail = f"Keywords: {', '.join(key_terms[:4])}" if key_terms else "Query understood"
            if project_keywords:
                analyzed_detail += f" | Projects: {', '.join(project_keywords[:2])}"

            logger.info(f"⏱️ TIMING embedding: {timings['embedding']:.2f}s")
            yield {"step": "embed", "status": "done", "detail": analyzed_detail}

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
                    "step": "search",
                    "status": "done",
                    "detail": f"⚠️ SAFETY CHECK: {len(safety_risks)} potential hazards detected!",
                    "data": {"safety_alert": True}
                }

                # Build safety context for forced safety_guard widget
                safety_context = self._build_safety_context(safety_risks)
                yield {"_safety_risks": safety_risks, "_safety_context": safety_context}
                return  # Exit early - don't do normal retrieval

            yield {"step": "search", "status": "active", "detail": "Searching knowledge base..."}

            # Hybrid retrieval: vector search + graph traversal
            t1 = time.time()
            retrieval_results = db.hybrid_retrieval(query_embedding, top_k=5, min_score=0.7)
            timings["hybrid_retrieval"] = time.time() - t1

            # Configuration Graph search: ProductVariants, options, cartridges, filters
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
            logger.info(f"⏱️ TIMING config_search: {timings['config_search']:.2f}s - Products: {len(config_results['variants'])}, Options: {len(config_results['option_matches'])}")

            # Format top concepts found (more readable)
            concepts_found = []
            for r in retrieval_results[:5]:
                if r.get('concept'):
                    concepts_found.append(r.get('concept'))

            concepts_display = concepts_found[:3] if concepts_found else []
            products_display = [v.get('id', 'Unknown') for v in config_results.get('variants', [])[:3]]

            logger.info(f"⏱️ TIMING hybrid_retrieval: {timings['hybrid_retrieval']:.2f}s")
            yield {
                "step": "search",
                "status": "done",
                "detail": f"Found {len(retrieval_results)} cases" + (f", {len(config_results['variants'])} products" if config_results['variants'] else ""),
                "data": {"concepts": concepts_display, "products": products_display}
            }

            yield {"step": "projects", "status": "active", "detail": "Finding matching projects..."}

            # Search by project name if mentioned
            t1 = time.time()
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
            timings["project_search"] = time.time() - t1

            detail = f"Found: {', '.join(projects_found)}" if projects_found else "No direct project match"
            logger.info(f"⏱️ TIMING project_search: {timings['project_search']:.2f}s")
            yield {
                "step": "projects",
                "status": "done",
                "detail": detail,
                "data": {
                    "projects": projects_found,
                    "citations": citations_found[:1],
                    "actions": actions_found[:2]
                }
            }

            yield {"step": "context", "status": "active", "detail": "Gathering evidence..."}

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

            yield {
                "step": "context",
                "status": "done",
                "detail": f"Ready with {len(retrieval_results)} data points",
                "data": {"similar_cases": similar_names, "graph_paths": graph_paths}
            }

            yield {"step": "thinking", "status": "active", "detail": "Generating response..."}

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

        # Build conversation contents
        contents = []
        for item in self.chat_history:
            contents.append(types.Content(
                role=item["role"],
                parts=[types.Part.from_text(text=item["parts"][0])]
            ))

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

        contents.append(types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_message)]
        ))

        logger.info(f"🤖 Calling Gemini ({self.model_name})...")
        config_kwargs = {"system_instruction": SALES_ASSISTANT_SYSTEM_PROMPT}
        if self.thinking_level:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=self.thinking_level)
        response = client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )

        response_text = response.text
        logger.info(f"✅ Gemini response received ({len(response_text)} chars)")

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

        # Build conversation contents
        contents = []
        for item in self.chat_history:
            contents.append(types.Content(
                role=item["role"],
                parts=[types.Part.from_text(text=item["parts"][0])]
            ))

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

        contents.append(types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_message)]
        ))

        logger.info(f"🤖 Calling Gemini ({self.model_name}, thinking={self.thinking_level})...")
        t_gemini = time.time()

        # Retry logic for rate limiting
        max_retries = 3
        retry_delay = 2
        last_error = None

        config_kwargs = {"system_instruction": SALES_ASSISTANT_SYSTEM_PROMPT}
        if self.thinking_level:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=self.thinking_level)

        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
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
            raise Exception(f"API rate limit exceeded. Please try again in a few seconds or switch to Flash model. Error: {last_error}")

        gemini_time = time.time() - t_gemini

        response_text = response.text
        logger.info(f"✅ Gemini response received ({len(response_text)} chars)")
        logger.info(f"⏱️ TIMING gemini_api ({self.model_name}, {self.thinking_level}): {gemini_time:.2f}s")

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

chatbot = ChatBot()
