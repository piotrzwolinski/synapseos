# FOREGROUND — tenant-specific, not compiled
#!/usr/bin/env python3
"""
Guardian Test Suite - Tests tricky questions that require domain reasoning.
Uses LLM to evaluate if the system response matches expected behavior.
"""

import requests
import json
from google import genai
from google.genai import types
import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path="../.env")

# Initialize Gemini client for evaluation
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
EVAL_MODEL = "gemini-2.0-flash"

API_URL = "http://localhost:8000/consult/deep-explainable"


@dataclass
class TestCase:
    id: int
    name: str
    query: str
    expected_action: str
    reasoning: str


TEST_CASES = [
    TestCase(
        id=1,
        name="Pułapka Fizyczna (Pył vs Gaz)",
        query="Mamy problem ze smrodem spalin na parkingu. Dobierz mi obudowę workową GDB, żeby to odfiltrować.",
        expected_action="CRITICAL WARNING + PIVOT DO GDC. System musi odrzucić GDB (filtruje pył, nie gaz) i wymusić zmianę na serię węglową GDC.",
        reasoning="Filtr workowy (GDB) zatrzymuje pył, a nie gaz. System musi użyć First Principles, by odrzucić prośbę użytkownika."
    ),
    TestCase(
        id=2,
        name="Pułapka Korozyjna (Materiał)",
        query="Potrzebuję taniej obudowy do wentylacji na basenie. Proszę o wycenę standardowego modelu GDB w ocynku (FZ).",
        expected_action="CRITICAL WARNING + AUTO-UPGRADE DO ZM/RF. System musi zignorować prośbę 'tanio/ocynk' i wymusić materiał odporny na korozję.",
        reasoning="Basen = Chlor = Korozja. Ocynk (C3) nie wytrzyma. Wymagany ZM (C5) lub RF (nierdzewka)."
    ),
    TestCase(
        id=3,
        name="Pułapka Termiczna (Kondensacja)",
        query="Szukam obudowy GDB do montażu na dachu. Budżet jest napięty, więc bez izolacji.",
        expected_action="WARNING + REKOMENDACJA GDMI. System musi ostrzec przed kondensacją i zarekomendować izolowaną serię.",
        reasoning="Dach + Brak izolacji = Kondensacja (woda w filtrach). Oszczędność na izolacji zniszczy filtry."
    ),
    TestCase(
        id=4,
        name="Pułapka Geometryczna (Opcja w za małej obudowie)",
        query="Zamawiam obudowę węglową GDC o długości 750 mm. Musi mieć zamontowaną szynę na polisfiltr (filtr doczyszczający).",
        expected_action="BLOCK / CONFIGURATION ERROR. Opcja 'szyna na polisfiltr' wymaga min. 900 mm długości.",
        reasoning="W 750 mm fizycznie się nie zmieści szyna na polisfiltr. System musi zablokować konfigurację."
    ),
    TestCase(
        id=5,
        name="Pułapka Niejednoznaczności (Brak Danych)",
        query="Dobierz mi obudowę GDB do biurowca. Montaż wewnątrz.",
        expected_action="CLARIFICATION NEEDED. System musi zapytać o wymagany przepływ/wielkość.",
        reasoning="GDB występuje w wielu rozmiarach. System nie może zgadnąć przepływu dla 'biurowiec'."
    ),
    TestCase(
        id=6,
        name="Pułapka Higieniczna (Szpital)",
        query="Projekt: Szpital Wojewódzki. Klient chce przyoszczędzić i prosi o obudowy GDB w ocynku. Czy mogę to wycenić?",
        expected_action="CRITICAL WARNING (Hygiene Violation). Ocynk niedopuszczalny w szpitalu, wymagana stal nierdzewna (RF).",
        reasoning="Szpital = Wymogi Higieniczne (VDI 6022). Ocynk to ryzyko w strefach czystych."
    ),
    TestCase(
        id=7,
        name="Pułapka Terminologiczna (Produkt vs Komponent)",
        query="Chcę zbudować ścianę filtracyjną w murowanym kanale. Potrzebuję 20 sztuk obudów GDP-600x600, ale bez blachy, same ramki.",
        expected_action="PIVOT DO PFF. System powinien rozpoznać intencję i zaproponować PFF zamiast GDP.",
        reasoning="Użytkownik prosi o GDP (szafkę), ale opisuje PFF (ramę montażową)."
    ),
    TestCase(
        id=8,
        name="Pułapka Kompatybilności (Złe akcesorium)",
        query="Czy do obudowy GDC (Węglowej) mogę zamówić mechanizm dociskowy EXL?",
        expected_action="BLOCK / INCOMPATIBLE. EXL jest dla GDB/GDMI, GDC używa mocowania bagnetowego.",
        reasoning="Mechanizm EXL dedykowany do filtrów workowych. GDC ma inny system mocowania."
    ),
    TestCase(
        id=9,
        name="Pułapka Montażowa (Retrofit 'na styk')",
        query="Mam wnękę o długości 800 mm. Czy zmieszczę tam GDB-Long (750mm) plus ramkę na filtr wstępny (50mm)?",
        expected_action="WARNING (Zero Tolerance). 750 + 50 = 800 teoretycznie pasuje, ale praktycznie brak marginesu.",
        reasoning="Matematyka: 750 + 50 = 800. W praktyce (błędy montażowe) to ryzyko."
    ),
    TestCase(
        id=10,
        name="Pułapka Zastosowania (Tłuszcz)",
        query="Potrzebuję filtrów węglowych (GDC) do okapu w smażalni frytek.",
        expected_action="APPLICATION WARNING. Węgiel aktywny zaklei się tłuszczem bez silnej prefiltracji.",
        reasoning="Węgiel aktywny w GDC natychmiast zaklei się tłuszczem. Wymaga prefiltracji (separatory tłuszczu)."
    ),
]


def query_system(query: str) -> dict:
    """Send query to the deep-explainable endpoint."""
    try:
        response = requests.post(
            API_URL,
            json={"query": query},
            timeout=120
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def evaluate_response(test_case: TestCase, system_response: dict) -> dict:
    """Use LLM to evaluate if system response matches expected behavior."""

    eval_prompt = f"""You are evaluating a Product Recommendation System's response.

## TEST CASE: {test_case.name}

### User Query:
{test_case.query}

### Expected System Behavior:
{test_case.expected_action}

### Why This Is Tricky (Expected Reasoning):
{test_case.reasoning}

### Actual System Response:
```json
{json.dumps(system_response, indent=2, ensure_ascii=False)}
```

## EVALUATION TASK:
Analyze the system's response and determine:

1. **DETECTION** (0-10): Did the system detect the trap/risk in the query?
   - 10 = Explicitly identified the exact risk
   - 5 = Partially identified or hinted at the issue
   - 0 = Completely missed the trap

2. **ACTION** (0-10): Did the system take the correct action?
   - 10 = Exactly matched expected action (warning, block, pivot, clarification)
   - 5 = Partially correct (warned but didn't pivot, or weak warning)
   - 0 = Wrong action (proceeded without warning, wrong recommendation)

3. **REASONING** (0-10): Did the system explain the physical/chemical/domain reasoning?
   - 10 = Clear explanation of WHY (first principles physics/chemistry)
   - 5 = Mentioned the issue but weak reasoning
   - 0 = No reasoning provided

4. **OVERALL PASS/FAIL**: Based on above scores

Return JSON:
{{
  "detection_score": <0-10>,
  "detection_analysis": "<what did system detect or miss>",
  "action_score": <0-10>,
  "action_analysis": "<what action did system take vs expected>",
  "reasoning_score": <0-10>,
  "reasoning_analysis": "<quality of system's reasoning>",
  "overall_score": <0-10 average>,
  "pass": <true if overall >= 7>,
  "summary": "<1-2 sentence verdict>"
}}
"""

    try:
        response = client.models.generate_content(
            model=EVAL_MODEL,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=eval_prompt)])],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        return {"error": str(e), "pass": False, "overall_score": 0}


def run_tests():
    """Run all test cases and print results."""
    print("=" * 80)
    print("🧪 GUARDIAN TEST SUITE - Tricky Questions Evaluation")
    print("=" * 80)

    results = []
    passed = 0
    failed = 0

    for test in TEST_CASES:
        print(f"\n{'─' * 80}")
        print(f"📋 Test {test.id}: {test.name}")
        print(f"{'─' * 80}")
        print(f"Q: {test.query[:100]}...")
        print(f"Expected: {test.expected_action[:80]}...")
        print()

        # Query the system
        print("⏳ Querying system...")
        system_response = query_system(test.query)

        if "error" in system_response:
            print(f"❌ API Error: {system_response['error']}")
            results.append({"test_id": test.id, "pass": False, "error": system_response['error']})
            failed += 1
            continue

        # Show key parts of response
        response_type = system_response.get("response_type", "unknown")
        risk_detected = system_response.get("risk_detected", False)
        risk_severity = system_response.get("risk_severity", "none")

        print(f"📤 Response Type: {response_type}")
        print(f"⚠️  Risk Detected: {risk_detected} (Severity: {risk_severity})")

        # Show reasoning summary
        reasoning = system_response.get("reasoning_summary", [])
        if reasoning:
            print("🧠 Reasoning:")
            for step in reasoning[:3]:
                print(f"   {step.get('icon', '•')} {step.get('step', '')}: {step.get('description', '')[:60]}...")

        # Evaluate with LLM
        print("\n🤖 LLM Evaluation...")
        evaluation = evaluate_response(test, system_response)

        if "error" in evaluation:
            print(f"❌ Eval Error: {evaluation['error']}")
            results.append({"test_id": test.id, "pass": False, "error": evaluation['error']})
            failed += 1
            continue

        # Print evaluation results
        d_score = evaluation.get('detection_score', 0)
        a_score = evaluation.get('action_score', 0)
        r_score = evaluation.get('reasoning_score', 0)
        overall = evaluation.get('overall_score', 0)
        test_passed = evaluation.get('pass', False)

        print(f"\n📊 SCORES:")
        print(f"   Detection:  {d_score}/10 - {evaluation.get('detection_analysis', '')[:50]}...")
        print(f"   Action:     {a_score}/10 - {evaluation.get('action_analysis', '')[:50]}...")
        print(f"   Reasoning:  {r_score}/10 - {evaluation.get('reasoning_analysis', '')[:50]}...")
        print(f"   {'─' * 40}")
        print(f"   OVERALL:    {overall}/10")

        if test_passed:
            print(f"\n✅ PASS: {evaluation.get('summary', '')}")
            passed += 1
        else:
            print(f"\n❌ FAIL: {evaluation.get('summary', '')}")
            failed += 1

        results.append({
            "test_id": test.id,
            "test_name": test.name,
            "pass": test_passed,
            "scores": {
                "detection": d_score,
                "action": a_score,
                "reasoning": r_score,
                "overall": overall
            },
            "summary": evaluation.get('summary', '')
        })

    # Final Summary
    print("\n" + "=" * 80)
    print("📈 FINAL RESULTS")
    print("=" * 80)
    print(f"✅ Passed: {passed}/{len(TEST_CASES)}")
    print(f"❌ Failed: {failed}/{len(TEST_CASES)}")
    print(f"📊 Pass Rate: {(passed/len(TEST_CASES))*100:.1f}%")

    # Average scores
    valid_results = [r for r in results if "scores" in r]
    if valid_results:
        avg_detection = sum(r["scores"]["detection"] for r in valid_results) / len(valid_results)
        avg_action = sum(r["scores"]["action"] for r in valid_results) / len(valid_results)
        avg_reasoning = sum(r["scores"]["reasoning"] for r in valid_results) / len(valid_results)
        avg_overall = sum(r["scores"]["overall"] for r in valid_results) / len(valid_results)

        print(f"\n📊 Average Scores:")
        print(f"   Detection:  {avg_detection:.1f}/10")
        print(f"   Action:     {avg_action:.1f}/10")
        print(f"   Reasoning:  {avg_reasoning:.1f}/10")
        print(f"   Overall:    {avg_overall:.1f}/10")

    # List failures
    failures = [r for r in results if not r.get("pass", False)]
    if failures:
        print(f"\n❌ Failed Tests:")
        for f in failures:
            print(f"   • Test {f['test_id']}: {f.get('test_name', 'Unknown')} - {f.get('summary', f.get('error', 'Unknown error'))[:60]}")

    return results


if __name__ == "__main__":
    run_tests()
