"""
3-LLM Graph Audit with Debate Pattern.
Calls Claude, Gemini, and GPT to independently evaluate graph vs PDF,
then runs a rebuttal round for consensus.
"""
import sys, os, json, time, asyncio, concurrent.futures

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from llm_providers import GeminiProvider, OpenAIProvider, AnthropicProvider, LLMResponse

PDF_PATH = os.path.join(os.path.dirname(__file__), "..", "testdata", "filter_housings_sweden.pdf")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── Graph data summary (extracted from Neo4j) ───────────────────────────

GRAPH_DATA = """
## PRODUCT FAMILIES IN GRAPH (Layer 1)

### 1. GDP Planfilterskåp (FAM_GDP)
- Type: Panel Filter Housing
- Corrosion class: C2
- Indoor only: true
- Construction: BOLTED (source: PENDING_MIKAEL)
- Selection priority: 10
- Standard length: 250mm only
- Default frame depth: 50mm
- Available materials: FZ (default), AZ, RF, SF, ZM
- Material icons shown on PDF page: FZ, AZ, RF, SF, ZM (all 5)
- Available sizes in graph: 300x300, 300x600, 600x300, 600x600, 600x900, 600x1200, 900x600, 900x900, 900x1200, 1200x600, 1200x900, 1200x1200, 1500x600, 1800x600
- Options: Left-hinge door (L), Flange 40mm (F)
- Frame depths: 25, 50, 100 (per VariableFeature)
- Code format: GDP-{width}x{height}-{frame_depth}-R-PG-{material}

### 2. GDB Kanalfilterskåp (FAM_GDB)
- Type: Bag Filter Housing
- Corrosion class: C2
- Indoor only: true
- Construction: BOLTED (source: PENDING_MIKAEL)
- Selection priority: 15
- Lengths: 550mm (for short bag filters, max depth 450mm), 750mm (default, for long bags, max depth 650mm)
- Available materials: FZ (default), AZ, RF, SF, ZM
- Material icons on PDF page: FZ, AZ, RF, SF, ZM (all 5)
- Available sizes in graph: 300x300 through 1800x1800 (28 sizes)
- Options: Left-hinge door (L), Flange 40mm (F)
- EXL eccentric locking: standard feature (in Features)
- Code format: GDB-{width}x{height}-{length}-R-PG-{material}

### 3. GDMI Modulfilterskåp (FAM_GDMI)
- Type: Insulated Filter Housing
- Corrosion class: C4
- Indoor only: true
- Outdoor safe: true
- Construction: BOLTED (source: CATALOG_PDF_ANALYSIS)
- Selection priority: 25
- Lengths: 600mm (short), 850mm (long)
- Available materials: ZM (default), AZ (NO RF, NO SF, NO FZ)
- Material icons on PDF page: AZ, ZM (only 2!)
- Available sizes in graph: 300x300 through 1800x1800 (same as GDB, 28 sizes)
- Options: Left-hinge door (L), Flange 40mm (F)
- EXL eccentric locking: standard feature
- Code format: GDMI-{width}x{height}-{length}-R-PG-{material}

### 4. GDC Patronfilterskåp (FAM_GDC)
- Type: Carbon Cartridge Housing
- Corrosion class: C2
- Indoor only: true
- Construction: BOLTED (source: PENDING_MIKAEL)
- Selection priority: 20
- Lengths: 750mm (for 450mm cylinders), 900mm (for 600mm cylinders or with polisfilter)
- Available materials: FZ (default), AZ, RF, SF, ZM
- Material icons on PDF page: FZ, AZ, RF, SF, ZM (all 5)
- Available sizes in graph: 300x300, 300x600, 600x300, 600x600, 900x600, 1200x600, 1200x900, 1200x1200, 1500x600, 1800x600
- Cartridge counts per size in graph:
  300x300: 4, 300x600: 8, 600x300: 8, 600x600: 16, 900x600: 24,
  1200x600: 32, 1200x900: 48, 1200x1200: 64, 1500x600: (none stored), 1800x600: (none stored)
- Options: Left-hinge (L), Flange (F), Polisfilter rail
- Code format: GDC-{width}x{height}-{length}-R-PG-{material}

### 5. GDC FLEX (FAM_GDC_FLEX)
- Type: Carbon Housing with Rail
- Corrosion class: C2
- Indoor only: true
- Construction: RAIL_MOUNTED (source: PENDING_MIKAEL)
- Selection priority: 22
- Service access: FRONT_RAIL
- Lengths: 750mm (for 450mm cylinders), 900mm (for 600mm cylinders)
- Available materials: FZ, AZ, RF, SF, ZM (no explicit default set)
- Material icons on PDF page: FZ, AZ, RF, SF, ZM (all 5)
- Available sizes in graph: 600x300, 600x600, 900x600, 1200x600, 1500x600, 1800x600
- Height is ALWAYS 600mm (fixed) - only width varies
- Cartridge counts per size: 600x300: 7, 600x600: 14, 900x600: 20, 1200x600: 28
- Options: Left-hinge (L), Flange (F)
- Code format: GDC-FLEX-{width}x{height}-{length}-R-PG-{material}

### 6. GDMI FLEX (FAM_GDMI_FLEX)
- Type: Insulated Carbon Housing with Rail
- Corrosion class: C4
- Indoor only: true
- Construction: RAIL_MOUNTED (source: PENDING_MIKAEL)
- Selection priority: 20
- Service access: FRONT_RAIL
- Lengths: 850mm (for 450mm cylinders), 1100mm (for 600mm cylinders)
- Available materials: FZ, AZ, ZM (no RF or SF)
- Material icons on PDF page: FZ, AZ, ZM (only 3!)
- Available sizes in graph: 600x300, 600x600, 900x600, 1200x600, 1200x900, 1500x600, 1500x900, 1800x900
- Options: Left-hinge (L), Flange (F)
- Code format: GDMI-FLEX-{width}x{height}-{length}-R-PG-{material}

### 7. PFF Planfilterram (FAM_PFF)
- Type: Mounting Frame (no housing - just a frame)
- Construction: BOLTED (source: PENDING_MIKAEL)
- Selection priority: 50
- No length variants (it's a flat frame)
- Available sizes in graph: 300x300, 300x600, 600x300, 600x600, 600x900, 600x1200, 900x600, 900x900, 900x1200, 1200x600, 1200x900, 1200x1200, 1500x600

## MATERIALS IN GRAPH (Layer 1)
| Code | Name | Corrosion Class | Max Chlorine PPM |
|------|------|----------------|------------------|
| FZ | Förzinkat | C3 | 0 |
| AZ | Aluzink | C4 | 5 |
| RF | Rostfri (Stainless) | C5 | 50 |
| SF | Syrafast (Acid-proof) | C5.1 | 500 |
| ZM | Zinkmagnesium | C5 | 10 |

## VARIANT LENGTHS IN GRAPH
| Family | Length (mm) | Max Filter Depth | Default |
|--------|-----------|-----------------|---------|
| GDP | 250 | N/A | Yes |
| GDB | 550 | 450mm | No |
| GDB | 750 | 650mm | Yes |
| GDMI | 600 | N/A | No |
| GDMI | 850 | N/A | No |
| GDC | 750 | 450mm | No |
| GDC | 900 | 600mm | No |
| GDC FLEX | 750 | 450mm | No |
| GDC FLEX | 900 | 600mm | No |
| GDMI FLEX | 850 | 450mm | No |
| GDMI FLEX | 1100 | 600mm | No |

## SAMPLE AIRFLOW DATA (from DimensionModules)
| Size | Airflow (m³/h) | Weight ref (kg) |
|------|---------------|-----------------|
| 300x300 | 850 | 14 |
| 300x600 | 1700 | 20 |
| 600x300 | 1700 | 19 |
| 600x600 | 3400 | 27 |
| 600x900 | 5100 | 36 |
| 600x1200 | 6800 | 42 |
| 900x600 | 5100 | 32 |
| 900x900 | 7650 | 42 |
| 1200x1200 | 13600 | 56 |
| 1800x1800 | 30600 | 92 |

## ENVIRONMENTAL STRESSORS IN GRAPH (Layer 2 - Physics)
12 stressors total: Chemical Vapor, Chlorine, Explosive Atmosphere, Formaldehyde,
Grease/Oil, H2S, Humidity, High Temperature, Hygiene Requirements,
Outdoor Condensation, Particulate, Salt Spray.

Key demands:
- Chlorine -> CRITICAL: C5 corrosion resistance required
- Salt Spray -> CRITICAL: C5.1 required
- Outdoor Condensation -> CRITICAL: Thermal Insulation required
- Chemical Vapors -> CRITICAL: Porous Adsorption (carbon)
- Particulate -> CRITICAL: Mechanical Filtration
- Formaldehyde -> CRITICAL: Impregnated/Chemisorption Media
- Hygiene -> WARNING: C5 corrosion resistance
- ATEX -> INFO: Electrostatic Grounding

## MISSING FROM GRAPH (BFF from PDF)
The PDF shows BFF (Påsfilterram / Bag Filter Frame) on pages 2 and 20:
- BFF sizes: 305x305, 610x305, 910x305, 610x610, 910x610
- Fits filter sizes: 287x287, 592x287, 892x287, 592x592, 892x592
- Corrosion class C2, FZ standard
- Available in 5 materials: FZ, AZ, RF, SF, ZM
- This product family is NOT in the graph.
"""

SYSTEM_PROMPT = """You are a senior HVAC engineering auditor specializing in product data integrity.
You are reviewing a Knowledge Graph (Neo4j) that models the MANN+HUMMEL HVAC Filter Housing product catalog.
The source of truth is the attached PDF catalog "HVAC Filterskåp" (Version 01-09-2025).

Your task: Compare the GRAPH DATA against the PDF and identify ALL discrepancies, missing data, and errors.

IMPORTANT AUDIT CATEGORIES:
1. PRODUCT FAMILY COMPLETENESS - Are all families from PDF present in graph?
2. MATERIAL AVAILABILITY - Does each family have correct materials per PDF?
3. SIZE/DIMENSION ACCURACY - Do dimension tables match PDF exactly?
4. AIRFLOW RATINGS - Do airflow values match PDF tables?
5. WEIGHT DATA - Do weights match PDF tables?
6. LENGTH VARIANTS - Are housing lengths correct per PDF?
7. OPTIONS/FEATURES - Are options (left-hinge, flange, polisfilter) correct?
8. CARTRIDGE COUNTS - For GDC/GDC FLEX, do cartridge counts match PDF?
9. CORROSION CLASSES - Are material corrosion classes correct per PDF?
10. CONSTRUCTION TYPE - Is construction metadata correct?
11. CODE FORMAT - Does the code format match PDF examples?
12. FILTER COMPATIBILITY - Filter max depths, PFF frame sizes correct?

For each finding, provide:
- Category (from list above)
- Severity: CRITICAL (wrong data), MAJOR (missing data), MINOR (inconsistency), INFO (suggestion)
- What the PDF says
- What the graph says
- Your assessment

Respond in structured JSON:
{
  "evaluator": "<your_name>",
  "overall_score": "<0-100>",
  "total_findings": <count>,
  "findings": [
    {
      "id": <number>,
      "category": "<category>",
      "severity": "CRITICAL|MAJOR|MINOR|INFO",
      "product_family": "<family or ALL>",
      "description": "<what's wrong>",
      "pdf_says": "<exact PDF reference>",
      "graph_says": "<what graph has>",
      "recommendation": "<how to fix>"
    }
  ],
  "summary": "<overall assessment paragraph>"
}
"""

USER_PROMPT_TEMPLATE = """Here is the complete Knowledge Graph data for HVAC Filter Housings.
Please compare EVERY fact against the attached PDF catalog and report ALL discrepancies.

{graph_data}

CRITICAL CHECK ITEMS:
1. PDF page 3 "SORTIMENT" table: Check lengths for each family
2. PDF page 4: Material specs (FZ=C3, AZ=C4, RF=C5, SF=C5.1, ZM=C5) - verify against graph
3. GDP (page 5-7): All sizes, lengths, airflows, PFF frame sizes, frame depths 25/50/100
4. GDB (page 8-10): All sizes with both 550/600 and 750/800 weights, filter module counts, airflows
5. GDMI (page 11-13): Sizes go up to 2400x2400 in PDF! Check if graph has these.
   GDMI material icons show ONLY AZ and ZM - verify graph matches
   GDMI lengths are 600/650 and 850/900 per table header
6. GDC (page 14-15): Sizes, cartridge counts, length variants 750/800 and 900/950
7. GDC FLEX (page 16-17): Only 6 sizes (height always 600), cartridge counts, lengths
8. GDMI FLEX (page 18-19): Sizes, lengths 850/900 and 1100/1150, material icons show FZ AZ ZM (3 only)
9. BFF (page 20): 5 sizes - check if this product is in the graph
10. PFF data from page 7: Frame sizes, depths

Be extremely thorough. Check EVERY row in EVERY table.
Respond in JSON format as specified in the system prompt.
"""


def run_evaluation():
    """Round 1: Independent evaluations from all 3 LLMs."""
    print("=== ROUND 1: Independent Evaluations ===\n")

    with open(PDF_PATH, "rb") as f:
        pdf_bytes = f.read()
    print(f"PDF loaded: {len(pdf_bytes)} bytes")

    user_prompt = USER_PROMPT_TEMPLATE.format(graph_data=GRAPH_DATA)
    providers = [
        ("Claude (Sonnet 4.5)", AnthropicProvider()),
        ("Gemini 2.0 Flash", GeminiProvider()),
        ("GPT-5.2", OpenAIProvider()),
    ]

    results = {}

    def call_provider(name, provider):
        print(f"  [{name}] Starting evaluation...")
        resp = provider.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            pdf_bytes=pdf_bytes,
            max_tokens=8192,
            temperature=0.1,
        )
        print(f"  [{name}] Done in {resp.duration_s}s (error={resp.error})")
        return name, resp

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(call_provider, name, prov) for name, prov in providers]
        for future in concurrent.futures.as_completed(futures):
            name, resp = future.result()
            results[name] = resp

    # Save Round 1 results
    round1_output = {}
    for name, resp in results.items():
        round1_output[name] = {
            "provider": resp.provider,
            "content": resp.content,
            "error": resp.error,
            "duration_s": resp.duration_s,
        }

    with open(os.path.join(OUTPUT_DIR, "graph_audit_round1.json"), "w") as f:
        json.dump(round1_output, f, indent=2, ensure_ascii=False)
    print(f"\nRound 1 saved to reports/graph_audit_round1.json")

    return results, pdf_bytes


def run_rebuttal(round1_results, pdf_bytes):
    """Round 2: Each LLM reviews the other two's findings."""
    print("\n=== ROUND 2: Rebuttal & Cross-examination ===\n")

    rebuttal_system = """You are a senior HVAC engineering auditor conducting a peer review.
You have already completed your own independent evaluation. Now you are reviewing
the findings of TWO other evaluators (from different LLM providers).

Your task:
1. CONFIRM findings you agree with (especially if all 3 evaluators found the same issue)
2. CHALLENGE findings you believe are incorrect (cite specific PDF page/table evidence)
3. ADD any findings the others missed that you found
4. RETRACT any of your own findings that the others convincingly disproved

Respond in JSON:
{
  "evaluator": "<your_name>",
  "confirmed_findings": [<list of finding IDs from other evaluators you agree with>],
  "challenged_findings": [
    {"finding_id": <id>, "evaluator": "<name>", "reason": "<why it's wrong>", "pdf_evidence": "<cite>"}
  ],
  "new_findings": [<any findings missed by all>],
  "retracted_own_findings": [<any finding IDs you withdraw>],
  "consensus_score": "<0-100 revised overall accuracy score>",
  "final_assessment": "<paragraph summarizing the state of the graph>"
}
"""

    providers_map = {
        "Claude (Sonnet 4.5)": AnthropicProvider(),
        "Gemini 2.0 Flash": GeminiProvider(),
        "GPT-5.2": OpenAIProvider(),
    }

    results = {}

    def call_rebuttal(name, provider, own_result, other_results):
        others_text = ""
        for other_name, other_resp in other_results.items():
            others_text += f"\n\n--- {other_name} EVALUATION ---\n{other_resp.content[:6000]}"

        user_prompt = f"""Here are your own Round 1 findings:
{own_result.content[:6000]}

And here are the other evaluators' findings:
{others_text}

Review the attached PDF again and provide your rebuttal. Focus on disagreements and missed items."""

        print(f"  [{name}] Starting rebuttal...")
        resp = provider.generate(
            system_prompt=rebuttal_system,
            user_prompt=user_prompt,
            pdf_bytes=pdf_bytes,
            max_tokens=4096,
            temperature=0.1,
        )
        print(f"  [{name}] Done in {resp.duration_s}s")
        return name, resp

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = []
        for name, provider in providers_map.items():
            own = round1_results.get(name)
            others = {k: v for k, v in round1_results.items() if k != name}
            futures.append(pool.submit(call_rebuttal, name, provider, own, others))

        for future in concurrent.futures.as_completed(futures):
            name, resp = future.result()
            results[name] = resp

    # Save Round 2 results
    round2_output = {}
    for name, resp in results.items():
        round2_output[name] = {
            "provider": resp.provider,
            "content": resp.content,
            "error": resp.error,
            "duration_s": resp.duration_s,
        }

    with open(os.path.join(OUTPUT_DIR, "graph_audit_round2.json"), "w") as f:
        json.dump(round2_output, f, indent=2, ensure_ascii=False)
    print(f"\nRound 2 saved to reports/graph_audit_round2.json")

    return results


if __name__ == "__main__":
    print("=" * 60)
    print("  GRAPH AUDIT: 3-LLM Debate Protocol")
    print("  PDF: HVAC Filterskåp (MANN+HUMMEL)")
    print("  Evaluators: Claude, Gemini, GPT")
    print("=" * 60)

    round1_results, pdf_bytes = run_evaluation()
    round2_results = run_rebuttal(round1_results, pdf_bytes)

    print("\n" + "=" * 60)
    print("  AUDIT COMPLETE")
    print("  Results in: reports/graph_audit_round1.json")
    print("             reports/graph_audit_round2.json")
    print("=" * 60)
