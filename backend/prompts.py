"""LLM prompt templates for the Hybrid GraphRAG Sales Assistant."""

EXTRACTION_PROMPT = """You are a sales knowledge extraction assistant. Analyze the following case study and extract structured information.

Extract two categories of information:

1. **HARD DATA** (strict product information):
   - Products: Our products mentioned (include SKU if available, name, price, dimensions, type: Consumable or Capital)
   - Competitor Products: Competitor products mentioned (name, manufacturer)
   - Product Mappings: Which of our products compete with which competitor products

2. **SOFT KNOWLEDGE** (fuzzy engineering knowledge):
   - Concepts: 2-4 key concepts that summarize this case (e.g., "scope mismatch", "competitor pricing", "installation constraints", "technical adaptation")
   - Observations: Key observations or problems encountered (2-4 bullet points)
   - Actions: Actions taken and their outcomes (2-4 bullet points)

Respond with a JSON object in this exact format:
{{
    "hard_data": {{
        "products": [
            {{"sku": "string or null", "name": "string", "price": number or null, "dimensions": "string or null", "type": "Consumable" or "Capital"}}
        ],
        "competitor_products": [
            {{"name": "string", "manufacturer": "string or null"}}
        ],
        "product_mappings": [
            {{"competitor_product": "string", "our_product_sku": "string", "notes": "string or null"}}
        ]
    }},
    "soft_knowledge": {{
        "concepts": ["concept1", "concept2"],
        "observations": ["observation1", "observation2"],
        "actions": ["action1 -> outcome1", "action2 -> outcome2"]
    }}
}}

CASE STUDY:
{text}

PROJECT NAME: {project_name}

Respond ONLY with the JSON object, no additional text."""


SYNTHESIS_PROMPT = """You are a helpful sales assistant for an air filtration company. Use the following retrieved context from past cases to help answer the sales question.

RETRIEVED CONTEXT:
{context}

RELEVANT PRODUCTS:
{products}

SALES QUESTION:
{query}

Based on the past cases and product information, provide a helpful, actionable response. Include:
1. Relevant insights from similar past situations
2. Recommended actions based on what worked before
3. Product recommendations if applicable
4. Any warnings or things to watch out for

Keep your response concise and focused on actionable advice. If the context doesn't contain relevant information, say so and provide general guidance."""


CONCEPT_EXTRACTION_PROMPT = """Extract 2-4 key semantic concepts from this case study that would be useful for future similarity matching.

These concepts should be:
- Abstract enough to match similar situations (e.g., "scope mismatch" not "customer asked for filters")
- Specific enough to be meaningful (e.g., "competitor price pressure" not just "pricing")
- Focused on the sales/engineering challenge, not the specific products

Case study:
{text}

Return a JSON array of concept strings, e.g.:
["scope mismatch", "installation constraints", "competitor displacement"]"""


EVENT_GRAPH_EXTRACTION_PROMPT = """Analyze this email thread. Segment it into individual messages and extract the engineering decision-making process.

IMPORTANT: Ignore all Outlook UI elements (toolbars, buttons, sidebars), email signatures, disclaimers, and boilerplate text. Focus ONLY on the actual message content.

Your task is to reconstruct the CHRONOLOGICAL TIMELINE of emails and identify the CAUSE-AND-EFFECT chain of engineering logic.

## EXTRACTION RULES:

1. **PROJECT**: Identify the project/client name from context.

2. **TIMELINE**: Extract each email as a separate event (Oldest to Newest order).
   For each email, identify:
   - `sender`: Person's name (and email if visible)
   - `date`: Date if visible in format "YYYY-MM-DD" (or "Unknown")
   - `time`: Time if visible in format "HH:MM" 24h (or null if not visible)
   - `summary`: One-sentence summary of the email content
   - `logic_type`: What engineering logic does this email introduce?
     - `"Symptom"`: Initial problem report (e.g., "CAD file is dummy solid")
     - `"Constraint"`: Physical/technical limitation discovered (e.g., "Grid is welded")
     - `"Blocker"`: Something preventing standard solution (e.g., "No clearance for standard unit")
     - `"SAFETY_CRITICAL"`: **HIGHEST PRIORITY** - Safety/compliance risk that PROHIBITS a product/action (see Safety Detection Rules below)
     - `"Standard"`: Standard approach attempted (e.g., "Requested full 3D model")
     - `"Workaround"`: Creative solution to bypass blocker (e.g., "Use flange adapter")
     - `"ProductMapping"`: **CRITICAL** - Product selection or competitor equivalence (e.g., "GDR Nano = Camfil Cambox")
     - `"Commercial"`: **CRITICAL** - Pricing, discounts, or commercial terms with HARD NUMBERS (e.g., "20% discount", "45444 SEK")
     - `null`: If no specific engineering logic (e.g., simple acknowledgment)
   - `logic_description`: Description of the logic if type is not null
   - `citation`: **EXACT verbatim quote** from the email that justifies this classification. Copy the exact substring from the original email (10-50 words). This is the SOURCE EVIDENCE for why you classified this step. Example: "...the grid is welded to the frame and cannot be removed without cutting..."
   - `local_concepts`: 1-3 technical concepts SPECIFIC to THIS step only (not the whole case!)
     - Example: A "Symptom" step about CAD issues might have: ["Dummy Solid", "CAD File"]
     - Example: A "Workaround" step about using flanges might have: ["Flange Adapter", "Welded Connection"]
     - Example: A "ProductMapping" step should have SPECIFIC product names: ["GDR Nano 1/1", "Camfil Cambox 610-S"]
     - Leave empty [] if no specific technical concept in this step
     - CRITICAL: Do NOT assign solution concepts (like "Stainless Steel") to problem steps!

## SPECIAL HANDLING: PRODUCT MAPPINGS & PRICING EMAILS

**If an email contains product lists, SKU codes, price calculations, or competitor equivalence statements, you MUST:**

1. Set `logic_type` to `"ProductMapping"`
2. `logic_description` MUST explicitly state the mapping, e.g.:
   - "Selected GDR Nano 1/1 as equivalent to Camfil Cambox 610-S"
   - "Priced M+H filters at 1,250 EUR vs competitor 1,400 EUR"
   - "Defined product substitution: OurProduct A replaces Competitor B"
3. `local_concepts` MUST include SPECIFIC product names (not generic terms):
   - GOOD: ["GDR Nano 1/1", "Camfil Cambox 610-S", "Filter Bank Replacement"]
   - BAD: ["Filter Banks", "Pricing"] (too generic!)
4. `citation` should capture the actual mapping text from the email

Example ProductMapping extraction:
{{
    "step": 4,
    "sender": "Sales Engineer",
    "date": "2024-03-15",
    "time": "10:30",
    "summary": "Provided pricing calculation with product equivalences",
    "logic_type": "ProductMapping",
    "logic_description": "Defined GDR Nano 1/1 as direct replacement for Camfil Cambox 610-S at competitive pricing",
    "citation": "For the filter bank replacement: GDR Nano 1/1 = Camfil Cambox 610-S, price per unit 1,250 EUR",
    "local_concepts": ["GDR Nano 1/1", "Camfil Cambox 610-S", "Competitive Pricing"]
}}

## SPECIAL HANDLING: COMMERCIAL DATA (PRICING, DISCOUNTS)

**RULE: Extract HARD NUMBERS. Never summarize commercial data.**

If an email contains specific commercial logic (discounts, prices, payment terms), you MUST extract the EXACT values.

**Trigger Keywords (Multi-language):**
- English: discount, price, list price, net price, margin, payment terms
- Swedish: rabatt, pris, listpris, nettopris, betalningsvillkor
- German: Rabatt, Nachlass, Preis, Listenpreis, Nettopreis, Zahlungsbedingungen

**Extraction Rules:**
1. Set `logic_type` to `"Commercial"`
2. `logic_description` MUST contain the RAW NUMBERS:
   - **BAD:** "Calculated the final price" (too vague!)
   - **BAD:** "Applied a discount" (missing the value!)
   - **GOOD:** "Applied 20% discount to list price 45,444 SEK, final price 36,355 SEK"
   - **GOOD:** "Offered 3% extra rabatt for bulk order over 50 units"
3. `local_concepts` MUST include the specific commercial terms:
   - **GOOD:** ["20% Discount", "Project Pricing", "45444 SEK List Price"]
   - **BAD:** ["Pricing", "Discount"] (too generic!)
4. `citation` MUST capture the exact numbers from the email

Example Commercial extraction:
{{
    "step": 5,
    "sender": "Milad Alzaghari",
    "date": "2024-03-18",
    "time": "14:22",
    "summary": "Sent final pricing with 20% project discount",
    "logic_type": "Commercial",
    "logic_description": "Applied 20% project discount: List price 45,444 SEK reduced to 36,355 SEK final price",
    "citation": "Price 45444 SEK = 20% discount = 36356 SEK",
    "local_concepts": ["20% Discount", "45444 SEK List Price", "36355 SEK Final Price"]
}}

## CRITICAL: SAFETY & COMPLIANCE DETECTION LAYER

**You are a Safety Auditor FIRST.** Before any other classification, actively HUNT for danger signals.

**SAFETY KEYWORD SCAN (Multi-language):**
Scan EVERY email for these critical safety keywords:
- **Explosion/Fire Risk:** ATEX, explosion, explosive, ignition, spark, fire, combustible, Kst value, dust cloud, triboelectric
- **Chemical/Toxic:** poison, toxic, hazardous, chemical reaction, VHP, H2O2, corrosive
- **Compliance/Legal:** "strictly forbidden", "prohibited", "violation", "not permitted", "must be", "mandatory", "machinery directive"
- **Structural/Physical:** structural failure, collapse, pressure rating, load limit

**SAFETY_CRITICAL Classification Rules:**

If ANY of these patterns are detected, classify as `"SAFETY_CRITICAL"` (NOT "Constraint" or "Blocker"):

1. **Pattern: Product X is PROHIBITED in Environment Y**
   - "Standard filters are prohibited in ATEX zones"
   - "Cannot sell standard Eco filters for this application"
   - "Violation of the machinery directive"

2. **Pattern: Input A + Condition B = Hazard**
   - "Wood dust + standard synthetic = spark risk"
   - "Polyester + explosive dust = electrostatic ignition"
   - "Milk powder + non-ATEX = explosion hazard"

3. **Pattern: Regulatory MUST/MUST NOT**
   - "Filter media MUST be conductive"
   - "Standard media is NOT permitted"
   - "Leakage resistance < 10^8 Ohm required"

**SAFETY_CRITICAL Extraction Format:**

When detecting a safety risk, you MUST extract:
- `logic_type`: `"SAFETY_CRITICAL"` (NOT "Constraint"!)
- `logic_description`: MUST follow this format:
  **"HAZARD: [Trigger] + [Condition] = [Risk]. PROHIBITION: [What is forbidden]. REQUIRED: [Safe alternative]."**
- `hazard_trigger`: The specific input that causes the risk (e.g., "Standard Polyester Filters")
- `hazard_environment`: The condition that makes it dangerous (e.g., "Wood Sanding / ATEX Zone 22")
- `safe_alternative`: The required safe product/action (e.g., "Conductive Filters with Carbon Threads")
- `citation`: EXACT quote showing the prohibition/risk
- `local_concepts`: MUST include: the hazard trigger, the risk type, the safe alternative

**Example SAFETY_CRITICAL extraction:**
{{
    "step": 4,
    "sender": "Lukas Weber",
    "date": "2024-01-22",
    "time": "16:45",
    "summary": "Enforced conductive filter requirement due to ATEX explosion risk",
    "logic_type": "SAFETY_CRITICAL",
    "logic_description": "HAZARD: Standard synthetic filters + Wood dust sanding = Electrostatic spark ignition. PROHIBITION: Standard Eco filters forbidden in ATEX Zone 22. REQUIRED: Airpocket Ex-Protect with carbon threads (conductive media).",
    "hazard_trigger": "Standard Synthetic Filters",
    "hazard_environment": "Wood Sanding / ATEX Zone 22 / Explosive Dust",
    "safe_alternative": "Airpocket Ex-Protect (Conductive) with integrated carbon threads",
    "citation": "For ATEX Zone 22, the filter media MUST be conductive. Therefore, I cannot sell you the standard Eco filters for this application. It would be a violation of the machinery directive.",
    "local_concepts": ["ATEX Zone 22", "Electrostatic Spark Risk", "Standard Filters Prohibited", "Conductive Filter Required", "Wood Dust Explosion"]
}}

**CRITICAL: DO NOT downgrade safety issues!**
- If someone says "standard filters are prohibited" → SAFETY_CRITICAL (not Constraint)
- If someone mentions "spark risk" or "explosion" → SAFETY_CRITICAL (not Blocker)
- If a regulatory "MUST" appears → SAFETY_CRITICAL (not Constraint)

3. **CAUSALITY**: Identify which observations led to other observations or actions.
   - Format: `[step_number, "REVEALED" or "ADDRESSES", step_number]`
   - Example: Symptom (step 1) REVEALED Constraint (step 3)
   - Example: Workaround (step 5) ADDRESSES Blocker (step 4)

4. **FORENSIC KNOWLEDGE DISCOVERY** (Hidden Institutional Assets):
   You are a **Forensic Engineering Auditor**. Your job is to identify "invisible" tools, datasets, SOPs, and standards that experts implicitly rely on but don't explicitly name.

   ## FORENSIC DETECTION RULES:

   **A. DATA PRECISION → Infer "Master Dataset"**
   If you see precise, non-rounded data that couldn't be memorized:
   - Exact SKU codes (e.g., "7101011329", "800481002927")
   - Precise prices with decimals or odd numbers (e.g., "45,444 SEK", "1,250.47 EUR")
   - Specific technical values (e.g., "140 Pa initial pressure drop", "3400m3/h")
   - Part numbers, article codes, weight specifications
   → **Inference:** "This precise data suggests a Master Dataset or Product Database"
   → **Type:** "Data"

   **B. PROCEDURAL CLUES → Infer "SOP/Playbook"**
   If you see language suggesting established procedures:
   - "standard logic", "following protocol", "as per usual", "normal procedure"
   - "wie üblich", "enligt rutin", "standard process"
   - "the standard approach is", "we typically", "our policy"
   → **Inference:** "Procedural language suggests an unwritten SOP or Playbook"
   → **Type:** "Process"

   **C. VALIDATION TRACES → Infer "Engineering Standard"**
   If a design is rejected/confirmed based on hidden rules:
   - Compliance references (ATEX, VHP, EN standards, ISO)
   - Technical constraints ("must be stainless steel for cleanroom", "not compatible with VHP")
   - Rejection reasons citing unstated rules
   → **Inference:** "Validation logic suggests an Engineering Standard or Compliance Checklist"
   → **Type:** "Manual"

   **D. CALCULATIONS → Infer "Calculation Tool/Matrix"**
   If outputs are derived from inputs via non-trivial math:
   - Net price derived from List price with discount (e.g., "45444 SEK = 20% discount = 36356 SEK")
   - Filter sizing from airflow requirements
   - Pressure drop calculations
   - Any "the tool calculated" or "according to the calculation"
   → **Inference:** "Derived values suggest a Calculation Tool, Pricing Matrix, or Configurator"
   → **Type:** "Software"

   **E. EXPLICIT MENTIONS → Direct extraction**
   Direct references to tools, systems, documents:
   - "HABE tool", "SAP", "discount matrix", "framework agreement"
   - "beräkningsverktyg", "Preisliste", "Rabattmatrix"
   → **Inference:** "Explicitly mentioned in the email"
   → **Type:** Based on context (Software/Data/Manual/Process)

   ## EXTRACTION FORMAT:
   For each discovered source, extract:
   - `raw_name`: The exact term OR your inferred name (e.g., "HABE tool" or "Pricing Matrix")
   - `type`: One of "Software", "Data", "Manual", "Process"
   - `inference_logic`: **CRITICAL** - Explain WHY you inferred this. Use the format:
     - "Explicitly mentioned: [quote]"
     - "Inferred from precise pricing data (45,444 SEK) suggesting a master price list"
     - "Inferred from procedural language ('as per usual') suggesting an SOP"
     - "Inferred from compliance validation (ATEX) suggesting an engineering standard"
   - `citation`: **EXACT verbatim quote** from the email (10-50 words)
   - `mentioned_in_step`: Which timeline step contains this evidence

Return a JSON object in this exact format:
{{
    "project": "Project Name",
    "timeline": [
        {{
            "step": 1,
            "sender": "John Smith",
            "sender_email": "john@company.com",
            "date": "2024-09-05",
            "time": "09:15",
            "summary": "Sent initial CAD file for review",
            "logic_type": "Symptom",
            "logic_description": "Received CAD is a dummy solid without internal details",
            "citation": "Please find attached the CAD model. Note that it's a simplified dummy solid for preliminary layout purposes only.",
            "local_concepts": ["Dummy Solid", "CAD File"]
        }},
        {{
            "step": 2,
            "sender": "Jane Doe",
            "sender_email": "jane@company.com",
            "date": "2024-09-06",
            "time": "14:30",
            "summary": "Requested full 3D model and noted grid concerns",
            "logic_type": "Standard",
            "logic_description": "Request detailed 3D model for proper engineering",
            "citation": "We will need the full 3D model with internal details to proceed with the filter housing design.",
            "local_concepts": ["3D Model Request"]
        }},
        {{
            "step": 3,
            "sender": "John Smith",
            "sender_email": "john@company.com",
            "date": "2024-09-10",
            "time": "11:45",
            "summary": "Confirmed grid is permanently welded",
            "logic_type": "Constraint",
            "logic_description": "Grid is welded and cannot be removed for access",
            "citation": "Unfortunately the intake grid is welded to the frame and cannot be removed without cutting the structure.",
            "local_concepts": ["Welded Grid", "Access Restriction"]
        }},
        {{
            "step": 4,
            "sender": "Jane Doe",
            "sender_email": "jane@company.com",
            "date": "2024-09-12",
            "time": "16:20",
            "summary": "Proposed using flange adapter as workaround",
            "logic_type": "Workaround",
            "logic_description": "Use flange adapter to connect without removing grid",
            "citation": "We can use a custom flange adapter that mounts externally and bypasses the grid entirely.",
            "local_concepts": ["Flange Adapter"]
        }}
    ],
    "causality": [
        [1, "REVEALED", 3],
        [4, "ADDRESSES", 3]
    ],
    "discovered_knowledge": [
        {{
            "raw_name": "HABE tool",
            "type": "Software",
            "inference_logic": "Explicitly mentioned: 'HABE is calculating' indicates a calculation tool",
            "citation": "Returning with filter wall that HABE is calculating",
            "mentioned_in_step": 2
        }},
        {{
            "raw_name": "Project Pricing Matrix",
            "type": "Data",
            "inference_logic": "Inferred from precise pricing data (45,444 SEK with exact 20% calculation to 36,355 SEK) suggesting a master price list",
            "citation": "Price 45444 SEK = 20% discount = 36356 SEK",
            "mentioned_in_step": 4
        }},
        {{
            "raw_name": "Hospital Project Discount Policy",
            "type": "Process",
            "inference_logic": "Inferred from '20% project discount' applied consistently, suggesting a standard discount tier policy",
            "citation": "Filter cabinet GDR Nano 1/1 = Price 45444 SEK = 20% discount",
            "mentioned_in_step": 4
        }}
    ]
}}

RULES:
- Order timeline from OLDEST email to NEWEST (chronological)
- Each email = one timeline entry, even if same sender
- logic_type must be one of: "Symptom", "Constraint", "Blocker", "SAFETY_CRITICAL", "Standard", "Workaround", "ProductMapping", "Commercial", or null
- **SAFETY_CRITICAL is HIGHEST PRIORITY** - If safety keywords detected (ATEX, explosion, prohibited, violation), use SAFETY_CRITICAL not Constraint/Blocker
- **SAFETY_CRITICAL steps MUST include**: `hazard_trigger`, `hazard_environment`, `safe_alternative` fields
- **ProductMapping is MANDATORY** for emails containing: product lists, SKU codes, competitor equivalences
- **Commercial is MANDATORY** for emails containing: discounts, specific prices, payment terms, margins
- NEVER summarize commercial data - always include the EXACT numbers (percentages, amounts, currencies)
- local_concepts must be specific to THAT step only - do not leak solution concepts to problem steps!
- For ProductMapping steps: local_concepts MUST include actual product names (e.g., "GDR Nano 1/1"), NOT generic terms
- For Commercial steps: local_concepts MUST include the exact values (e.g., "20% Discount", "45444 SEK")
- For SAFETY_CRITICAL steps: local_concepts MUST include hazard trigger, risk type, and safe alternative
- If you cannot determine project name, use "Unknown Project"
- sender_email can be null if not visible
- **discovered_knowledge**: Act as a forensic auditor. Extract BOTH explicit mentions AND inferred assets.
  - ALWAYS include `inference_logic` explaining your reasoning
  - Be aggressive: If you see precise data, procedural language, or calculations, infer the underlying tool/dataset
  - It's better to over-detect (experts can dismiss) than to miss institutional knowledge
  - Return empty array [] ONLY if there is genuinely no evidence of external tools, data, or processes

Respond ONLY with the JSON object, no additional text."""
