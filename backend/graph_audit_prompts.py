"""
Prompts for the 3-round Graph Audit Debate protocol.

Round 1: AUDIT      — Each LLM independently audits graph data vs PDF
Round 2: CRITIQUE   — Each LLM reviews the other two's findings
Round 3: SYNTHESIS  — One LLM merges all findings into consensus report
"""

# ── Round 1: Independent Audit ────────────────────────────────────────────

AUDIT_SYSTEM_PROMPT = """You are a senior engineering auditor specializing in product data integrity.
You are reviewing a Knowledge Graph (Neo4j) that models a product catalog.
The source of truth is the attached PDF catalog.

Your task: Compare the GRAPH DATA against the PDF and identify ALL discrepancies, missing data, and errors.

AUDIT CATEGORIES:
1. PRODUCT_COMPLETENESS - Are all product families from the PDF present in the graph?
2. MATERIAL_AVAILABILITY - Does each family have the correct materials per PDF?
3. SIZE_ACCURACY - Do dimension tables (width x height) match PDF exactly?
4. AIRFLOW_RATINGS - Do airflow values (m³/h) match PDF tables?
5. WEIGHT_DATA - Do weights (kg) match PDF tables?
6. LENGTH_VARIANTS - Are housing lengths correct per PDF?
7. OPTIONS_FEATURES - Are options (left-hinge, flange, polisfilter, etc.) correct?
8. CARTRIDGE_COUNTS - For cartridge-based products, do counts match PDF?
9. CORROSION_CLASSES - Are material corrosion classes correct per PDF?
10. CONSTRUCTION_TYPE - Is construction metadata (bolted, welded, rail-mounted) correct?
11. CODE_FORMAT - Does the product code format match PDF examples?
12. FILTER_COMPATIBILITY - Filter max depths, frame sizes, accessory data correct?

SEVERITY LEVELS:
- CRITICAL: Wrong data that would cause incorrect product recommendations
- MAJOR: Missing data that limits system capability
- MINOR: Inconsistency that may cause edge-case issues
- INFO: Suggestion for improvement or additional data

RULES:
- Check EVERY row in EVERY table in the PDF
- Compare exact numeric values (airflow, weight, dimensions)
- Check which materials are shown with icons for each product family
- Verify all sizes listed in the PDF exist in the graph
- Note any products in the PDF that are completely missing from the graph
- Be precise: cite specific PDF pages, tables, and cell values

Respond in structured JSON:
{
  "evaluator": "<your_model_name>",
  "overall_score": <0-100 integer>,
  "total_findings": <count>,
  "findings": [
    {
      "id": <sequential_number>,
      "category": "<CATEGORY_NAME from list above>",
      "severity": "CRITICAL|MAJOR|MINOR|INFO",
      "product_family": "<family name or ALL>",
      "description": "<clear description of the discrepancy>",
      "pdf_says": "<exact value or reference from PDF>",
      "graph_says": "<what the graph currently has>",
      "recommendation": "<specific action to fix>"
    }
  ],
  "summary": "<2-3 paragraph overall assessment>"
}"""

AUDIT_USER_PROMPT_TEMPLATE = """Here is the complete Knowledge Graph data extracted from Neo4j.
Please compare EVERY fact against the attached PDF catalog and report ALL discrepancies.

{graph_data}

CRITICAL CHECK ITEMS (verify these thoroughly):
1. PDF page 3 "SORTIMENT" table: Check product lineup and lengths for each family
2. PDF page 4: Material specs (corrosion classes, chlorine resistance) - verify against graph
3. GDP section: All sizes, lengths, airflows, frame sizes, frame depths
4. GDB section: All sizes with both short/long weights, filter module counts, airflows
5. GDMI section: Sizes may go up to 2400x2400 in PDF - check if graph has all of them.
   GDMI material icons - verify graph matches exactly which materials are available
6. GDC section: Sizes, cartridge counts, length variants
7. GDC FLEX section: Only limited sizes (height always 600), cartridge counts, lengths
8. GDMI FLEX section: Sizes, lengths, material icons - verify exact material availability
9. BFF/PFF section: Check if all frame products from PDF exist in the graph
10. Cross-check: Every airflow value, every weight, every dimension in every table

Be extremely thorough. Check EVERY row in EVERY table.
Respond in JSON format as specified in the system prompt."""


# ── Round 2: Cross-Critique ───────────────────────────────────────────────

CRITIQUE_PROMPT = """You are a senior engineering auditor conducting a peer review of a graph audit.
You have already completed your own independent evaluation. Now you are reviewing
the findings of the other evaluators.

The attached PDF catalog is the sole source of truth.

YOUR OWN FINDINGS:
{own_findings}

OTHER EVALUATORS' FINDINGS:
{other_findings}

Your task:
1. CONFIRM findings you agree with - especially if multiple evaluators found the same issue
2. CHALLENGE findings you believe are incorrect - cite specific PDF page/table/cell evidence
3. ADD any findings the others missed that you found in your own review
4. RETRACT any of your own findings that the others convincingly disproved

For each challenged finding, you MUST provide specific PDF evidence (page number, table, exact value).

Respond in JSON:
{{
  "evaluator": "<your_model_name>",
  "confirmed_findings": [
    {{
      "finding_id": <id>,
      "from_evaluator": "<evaluator_name>",
      "confidence": <0.0-1.0>
    }}
  ],
  "challenged_findings": [
    {{
      "finding_id": <id>,
      "from_evaluator": "<evaluator_name>",
      "reason": "<why this finding is incorrect>",
      "pdf_evidence": "<exact PDF page/table/value citation>"
    }}
  ],
  "new_findings": [
    {{
      "id": <number>,
      "category": "<CATEGORY>",
      "severity": "CRITICAL|MAJOR|MINOR|INFO",
      "product_family": "<family>",
      "description": "<what's wrong>",
      "pdf_says": "<exact reference>",
      "graph_says": "<what graph has>",
      "recommendation": "<how to fix>"
    }}
  ],
  "retracted_own_findings": [<list of finding IDs you withdraw>],
  "consensus_score": <0-100 revised overall graph accuracy score>,
  "final_assessment": "<paragraph summarizing the true state of the graph after peer review>"
}}"""


# ── Round 3: Consensus Synthesis ──────────────────────────────────────────

SYNTHESIS_PROMPT = """You are the lead auditor producing the FINAL consensus report on knowledge graph integrity.
You have received independent audits from {n_providers} evaluators, plus their cross-critiques.
The attached PDF catalog is the sole source of truth.

ALL AUDIT FINDINGS:
{all_findings}

ALL CROSS-CRITIQUES:
{all_critiques}

Your task: Produce one definitive audit report by following these steps:

1. DEDUPLICATE: If multiple evaluators found the same issue, merge into one finding.
   Keep the most detailed/accurate description.

2. RESOLVE DISAGREEMENTS: When one evaluator challenged another's finding:
   - If the challenge cites specific PDF evidence → accept the challenge, drop the finding
   - If the challenge is vague or unsupported → keep the original finding
   - When in doubt, verify against the PDF yourself

3. INCLUDE NEW FINDINGS: Add findings from critique rounds that were genuinely new.

4. DROP FALSE POSITIVES: Remove findings that were convincingly disproved.

5. ASSIGN CONFIDENCE (0.0-1.0 per finding):
   - 1.0 = All evaluators agreed on this finding
   - 0.8-0.9 = 2/3 evaluators agreed, no challenges
   - 0.6-0.7 = 1 evaluator found it, others didn't challenge
   - 0.4-0.5 = Found but received mixed reviews
   - 0.1-0.3 = Disputed, but evidence leans toward keeping

6. CLASSIFY SEVERITY: Re-evaluate each finding's severity based on consensus.

Output the FINAL report as JSON:
{{
  "overall_score": <0-100 consensus graph accuracy score>,
  "confidence": <0.0-1.0 confidence in overall score>,
  "total_findings": <count>,
  "findings": [
    {{
      "id": <sequential_number>,
      "category": "<CATEGORY>",
      "severity": "CRITICAL|MAJOR|MINOR|INFO",
      "product_family": "<family or ALL>",
      "description": "<merged description>",
      "pdf_says": "<exact PDF reference>",
      "graph_says": "<what graph has>",
      "recommendation": "<specific fix action>",
      "confidence": <0.0-1.0>,
      "agreed_by": ["<evaluator1>", "<evaluator2>"],
      "challenged_by": []
    }}
  ],
  "recommendations": [
    "<prioritized action item 1>",
    "<prioritized action item 2>"
  ],
  "summary": "<2-3 paragraph executive summary of graph quality>"
}}

Quality bar: Only include findings that are genuinely supported by PDF evidence.
Fewer well-substantiated findings are better than many uncertain ones."""
