# AI Solutions Finder — Prompt Reference

This document describes the five prompt templates that control how the AI generates responses and evaluates quality. Each prompt can be modified without code changes — edit the file and call `POST /config/domain/{id}/reload`.

---

## 1. System Prompt (`system_generic.txt`)

**Purpose:** Defines the AI's persona, authority rules, and response structure for all consultation responses.

**When used:** Every Graph Reasoning query — injected as the system message before the LLM generates a response.

### Persona & Source Hierarchy

The AI acts as an **expert engineering narrator**, not a chatbot. It presents data with authority:

| Source Level | Treatment | Example phrasing |
|-------------|-----------|-------------------|
| Reasoning Report data | Present as established fact (GRAPH_FACT) | "This configuration requires..." |
| AI's own engineering knowledge | Mark as advisory (INFERENCE) | "Note: From engineering practice..." |
| No data available | Do not present as verified | Omit or flag explicitly |

**Voice rules:**
- "This configuration requires..." — NOT "I recommend..."
- "Engineering data shows..." — NOT "Based on graph data..."
- "From our specifications..." — NOT "Querying database..."
- English only, regardless of query language

### Response Structure

Every response must follow a two-section format:

**Section 1 — "System Analysis"** (mandatory)
Actionable findings from the Reasoning Report: product confirmation, constraint violations, stressor detections, capacity shortfalls, alternatives. Tagged as `GRAPH_FACT`. Must be concise — only surface details that affect the decision.

**Section 2 — "Engineering Notes"** (optional)
The AI's own observations beyond the report. Tagged as `INFERENCE` with `inference_logic` explaining the reasoning. Include only when genuinely useful. Omit if the report is sufficient.

### Engineering Verdict Handling

The prompt defines how the AI interprets and communicates specific engine outcomes:

| Verdict Type | AI Behavior |
|-------------|-------------|
| **Logic Gate — FIRED** | State the physics constraint as confirmed fact. Non-negotiable. Use the gate's `physics_explanation`. |
| **Logic Gate — VALIDATION_REQUIRED** | Ask for missing parameters before any recommendation. Use the gate's `question` fields. |
| **Logic Gate — PASSED** | Proceed normally — constraint checked and doesn't apply. |
| **Hard Constraint Override** | Inform user of auto-correction, explain physical limitation, do not allow override. |
| **Product Substitution (Veto)** | Acknowledge the pivot, explain WHY using physics, proceed with recommended product. Never offer the vetoed product. |
| **Multi-Stage Assembly** | Present as a complete engineering solution. Explain protector stage is physically necessary. Use same dimensions for all stages. Present in order given by assembly sequence. |
| **Capacity Exceeded** | State the shortfall clearly, recommend upgrading to larger module size. Do not show division formulas. |

### Project State Management

The prompt enforces strict session continuity rules:

- **Locked parameters are sacred** — once specified, never revert without explicit user request
- **Do not re-ask** — if data was provided in a previous turn, use it
- **One parameter per turn** — ask for exactly one missing parameter per clarification
- **Immediate resolution** — if all required data is available, give final recommendation immediately
- **No internal names** — never expose "item_1", "item_2" or internal scores/percentages

### Sales Communication Style

- **Result-first** — present conclusions, not derivations. No formulas or intermediate math.
- **Relevance filter** — only surface technical details when they require action (violation, risk, decision).
- **Brevity** — summarize history in 1–2 sentences, focus 90% on the current step.

### Scope of Delivery

The prompt defines product scope rules:
- Delivers **filter housings only** (with service door, pressure measurement nipples, standard locking)
- **Transition pieces** (PT/TT) are separate items — always inform customer if round ducts are mentioned
- **Filters and filter elements** are separate items — never include filter prices/weights as part of housing

### Output Schema

The AI returns structured JSON:

```
response_type: "FINAL_ANSWER" | "CLARIFICATION_NEEDED"
content_segments: [{text, type: GRAPH_FACT|INFERENCE|GENERAL, key_specs?, inference_logic?}]
clarification_data: {missing_attribute, why_needed, options: [{value, description}], question}
entity_card: {title, specs} or [{title, specs}, ...] for assemblies
risk_detected, risk_severity: CRITICAL|WARNING|null
status_badges, policy_warnings
```

Key rules:
- `CLARIFICATION_NEEDED` → include `clarification_data`, no `entity_card`
- `FINAL_ANSWER` → include `entity_card` (optional), no `clarification_data`
- Assemblies → `entity_card` must be an array with one card per stage
- Product codes must be copied exactly from the Reasoning Report
- Never include null values in specs — omit unknown keys

---

## 2. Synthesis Prompt (`synthesis.txt`)

**Purpose:** Instructs the LLM on how to process the Reasoning Report and generate the final user-facing response.

**When used:** After the Reasoning Engine produces its verdict — this prompt templates the LLM call that turns structured data into natural language.

### Input Placeholders

| Placeholder | Content |
|-------------|---------|
| `{context}` | Available products and their specifications from the graph |
| `{query}` | The user's original question |
| `{policies}` | Technical context and Reasoning Report data |

### Execution Steps

1. **Acknowledge context first** — reference project name, customer, or application
2. **System Analysis section** — report Reasoning Report findings using GRAPH_FACT segments
3. **Engineering Notes section** (optional) — add advisory observations as INFERENCE segments
4. **Check provided info** — if user gave airflow/size, use it, don't ask again
5. **Respect user dimensions** — if user specified a size, use it even if a smaller module could handle the airflow
6. **Variance check** — multiple variants with no constraint → ask for clarification
7. **Context persistence** — "this", "it" references lock to active entity

### Output Rules

- English only, professional tone
- Start with project/application context when available
- Only mention constraints when they require action
- Bundle related questions naturally
- Return valid JSON only, no markdown blocks

---

## 3. Judge System Prompt (`judge_system.txt`)

**Purpose:** Defines the AI-as-Judge evaluation framework — the persona, scoring criteria, and calibration rules for automated quality assessment.

**When used:** During Test Lab evaluations — the judge LLM receives this prompt along with a conversation to score.

### Judge Persona

The judge acts as a **senior HVAC engineer and ventilation product specialist** with expertise in:
- Ventilation system design (airflow, pressure, duct sizing)
- Environmental engineering (corrosion classes C1–C5, marine, chemical exposure)
- Material science (FZ, RF/SS, AZ, ZM and their corrosion resistance)
- Construction types (bolted, welded, rail-mounted)
- Regulatory standards (EN ISO 12944, EN 16798)
- Application-specific requirements (kitchen, hospital, pharma, pool, ATEX)

### Two-Track Verification

| Track | Verification Method | Example |
|-------|---------------------|---------|
| **Product Data** | Check against PDF catalog | Airflow values, sizes, weights, materials |
| **Engineering Reasoning** | Judge's own HVAC expertise | Environment suitability, material recommendations, safety warnings |

**Key principle:** If the system states a correct engineering constraint not in the PDF, that is good advice, not fabrication.

### 6 Scoring Dimensions

| Dimension | Weight | What it measures |
|-----------|--------|-----------------|
| **Correctness** | 25% | Product specs match catalog; engineering reasoning is sound |
| **Safety** | 25% | Risks identified, unsafe configurations blocked, alternatives provided |
| **Completeness** | 15% | All relevant aspects covered (product, material, environment, sizing) |
| **Constraint Adherence** | 15% | Respects product and engineering rules; communicates constraints clearly |
| **Reasoning Quality** | 10% | Transparent, logical cause-effect chain |
| **Tone** | 10% | Professional, consultative, appropriate technical depth |

### Calibration Rules

| Score | Meaning |
|-------|---------|
| **5** | Expected score for a good response — correct data, sound reasoning, addresses the question |
| **3–4** | Clear, specific, verifiable error present |
| **1–2** | Dangerous misinformation, fundamentally wrong data, or complete failure |

**Anti-traps:**
- Do not penalize correct engineering reasoning absent from the PDF
- Do not penalize clarification-stage responses for missing product cards
- Do not double-count one issue across multiple dimensions

### Output Format

The judge returns structured JSON with:
- `scores` — per-dimension scores (1–5)
- `overall_score` — weighted average
- `explanation` — 2–3 sentence summary
- `dimension_explanations` — one sentence per dimension
- `strengths` and `weaknesses` — bullet points
- `pdf_citations` — specific facts verified against the catalog
- `recommendation` — PASS (≥3.5) / BORDERLINE (≥2.5) / FAIL (<2.5 or any dimension ≤2)

---

## 4. Question Generation Prompt (`judge_question.txt`)

**Purpose:** Generates diverse, realistic test questions from product catalog PDFs for the evaluation framework.

**When used:** Test Generator feature — uploads a product catalog PDF and generates test cases via multi-model debate.

### Test Categories

| Category | What it tests | Example |
|----------|--------------|---------|
| **Environment** | Correct environment detection and whitelist enforcement | "Can I use GDB in a swimming pool facility?" |
| **Material** | Corrosion classes, chemical compatibility | "We need housing for a coastal installation with salt spray exposure" |
| **Sizing** | Airflow-to-module mapping, multi-module arrangements | "I need 12,000 m³/h for a 600x600 cross-section" |
| **Assembly** | Multi-stage assembly detection | "Kitchen exhaust system with activated carbon filtration" |
| **Clarification** | Asks for missing parameters instead of guessing | "I need a filter housing" (no other details) |
| **Positive** | Valid configurations accepted without false blocks | "GDB 600x600 for indoor office ventilation, 3000 m³/h" |
| **Edge case** | Boundary conditions, unusual combinations | "ATEX Zone 2 with marine corrosion and 20,000 m³/h" |

### Output Per Question

Each generated question includes:
- `question` — realistic technical sales question
- `category` — one of the 7 categories above
- `difficulty` — easy / medium / hard
- `expected_elements` — what the response should mention or do
- `potential_failures` — what could go wrong

### Distribution Requirements

- At least 2 sizing questions with specific dimensions/airflow values
- At least 2 environment-constraint questions (one PASS, one BLOCK)
- At least 1 multi-parameter question combining environment + material + sizing
- All questions must be self-contained (no cross-references)

---

## 5. Evaluation Instructions (`judge_user.txt`)

**Purpose:** Per-evaluation instructions that accompany the actual conversation being judged. Provides the conversation data and tells the judge how to evaluate it.

**When used:** Each individual judge evaluation — injected as the user message alongside the conversation transcript.

### Input Placeholders

| Placeholder | Content |
|-------------|---------|
| `{conversation}` | Full multi-turn conversation transcript |
| `{product_card}` | Final product card(s) from the response |

### Evaluation Instructions

The judge is instructed to:
1. **Verify product data against the PDF** — look up product family, size, airflow, material options, weight. Flag discrepancies.
2. **Evaluate engineering reasoning** — assess environment assessments, material recommendations, safety warnings, sizing logic using HVAC expertise.
3. **Score each dimension** — using PDF for product specs, expertise for engineering reasoning.
4. **Cite at least one PDF data point** in the correctness explanation.
5. **Evaluate the full conversation** — clarification requests, material warnings, environment blocks, and final recommendation as a complete interaction.

---

## Prompt Modification Guide

### How to Edit

1. Edit the prompt file in `backend/tenants/mann_hummel/prompts/`
2. Reload configuration: `POST /config/domain/{domain_id}/reload`
3. No server restart needed — changes take effect on the next query

### What Can Be Changed Safely

| Change | Risk Level | Notes |
|--------|-----------|-------|
| Voice rules and phrasing style | Low | Adjust tone without affecting logic |
| Section structure (System Analysis / Engineering Notes) | Low | Can rename or restructure response sections |
| Calibration scores in judge prompt | Low | Adjust scoring thresholds |
| Test category requirements | Low | Change distribution of generated test types |
| Scope of delivery rules | Medium | Affects what the AI promises to customers |
| Output schema structure | High | Frontend depends on the JSON structure — coordinate with dev team |
| Verdict handling rules | High | Affects how engine results are communicated — test thoroughly |

### Testing Changes

After modifying a prompt:
1. Reload config via API
2. Run 2–3 representative queries in Graph Reasoning mode
3. Run a Test Lab batch to compare scores before/after
4. Check for JSON parsing errors in the response stream
