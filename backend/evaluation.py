"""
Evaluation Script for GraphRAG Sales Assistant
Tests system responses against expected answers using LLM evaluation.
"""

import time
import json
import httpx
from dataclasses import dataclass
from typing import Optional
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv
from tabulate import tabulate

load_dotenv(dotenv_path="../.env")

# Initialize Gemini client for evaluation
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# =============================================================================
# TEST CASES
# =============================================================================

@dataclass
class TestCase:
    id: str
    question: str
    expected_behavior: str
    key_checks: list[str]  # What the evaluator should look for


TEST_CASES = [
    TestCase(
        id="Q1",
        question="Potrzebuję taniej obudowy GDB w standardowym ocynku do wentylacji hali basenowej. Czy to dobry wybór?",
        expected_behavior="OSTRZEŻENIE/BLOKADA - Basen=Chlor/Korozja wymaga C4/C5. Ocynk (FZ) to klasa C3. Rekomendacja: ZM lub RF.",
        key_checks=[
            "Wykrycie ryzyka korozji (chlor/basen)",
            "Ostrzeżenie o nieodpowiednim materiale (FZ/ocynk)",
            "Rekomendacja materiału odpornego na korozję (ZM, RF, stal nierdzewna)",
            "Wskazanie klasy korozyjności (C3 vs C4/C5)"
        ]
    ),
    TestCase(
        id="Q2",
        question="Mamy problem z zapachem spalin na parkingu podziemnym. Jaki model workowy (GDB) polecacie?",
        expected_behavior="KOREKTA SERII - GDB (workowy) do pyłów, nie gazów. Dla zapachu/spalin potrzeba filtracji molekularnej (węgiel) = seria GDC.",
        key_checks=[
            "Rozpoznanie że GDB nie nadaje się do gazów/zapachów",
            "Wskazanie że filtr workowy jest do pyłów",
            "Rekomendacja serii GDC (węglowa/patronowa)",
            "Wyjaśnienie różnicy między filtracją cząsteczkową a molekularną"
        ]
    ),
    TestCase(
        id="Q3",
        question="Muszę wstawić filtr węglowy w istniejący kanał. Mam nietypową lukę montażową dokładnie 1050 mm. Co tam wejdzie?",
        expected_behavior="DOBÓR WERSJI FLEX - Nietypowy wymiar wymaga wersji z regulowaną długością. Rekomendacja: GDMI FLEX lub GDC FLEX.",
        key_checks=[
            "Rozpoznanie potrzeby retrofitu/nietypowego wymiaru",
            "Rekomendacja wersji FLEX z regulowaną długością",
            "Podanie zakresu regulacji (850-1100mm lub podobny)",
            "Wskazanie konkretnego modelu FLEX"
        ]
    ),
    TestCase(
        id="Q4",
        question="Projektuję centralę na dachu w strefie zimnej. Czy model GDB-600x600 będzie odpowiedni?",
        expected_behavior="WYMÓG IZOLACJI - Dach/Zimno = ryzyko kondensacji. GDB jest nieizolowane. Rekomendacja: seria GDMI (izolowana).",
        key_checks=[
            "Wykrycie ryzyka kondensacji (dach + zimno)",
            "Informacja że GDB jest nieizolowane",
            "Rekomendacja serii GDMI (izolowana termicznie)",
            "Wyjaśnienie problemu kondensacji"
        ]
    ),
    TestCase(
        id="Q5",
        question="Chcę zamówić obudowę GDC o długości 750 mm i dołożyć do niej szynę na filtr doczyszczający (polisfiltr). Poproszę kod.",
        expected_behavior="KONFLIKT KONFIGURACJI - Opcja 'Polis' wymaga min. 900mm długości. Rekomendacja: zmiana długości na 900mm.",
        key_checks=[
            "Wykrycie konfliktu konfiguracji",
            "Informacja o wymaganiach opcji Polis (wymaga większej długości)",
            "Rekomendacja zmiany długości na 900mm lub więcej",
            "Wyjaśnienie ograniczeń konfiguracyjnych"
        ]
    ),
    TestCase(
        id="Q6",
        question="Potrzebuję filtra do hali produkcyjnej. Jaki polecacie?",
        expected_behavior="KLARYFIKACJA - Brak kluczowych parametrów. System powinien zapytać o: typ zanieczyszczenia (pył/gaz), przepływ, środowisko.",
        key_checks=[
            "Wykrycie braku kluczowych parametrów",
            "Zapytanie o typ zanieczyszczenia (pył vs gaz)",
            "Zapytanie o wymagany przepływ powietrza",
            "Opcjonalnie: zapytanie o środowisko/aplikację"
        ]
    ),
    # =========================================================================
    # COMPLEX FILTER HOUSING SELECTION TEST CASES (Q7-Q11)
    # =========================================================================
    TestCase(
        id="Q7",
        question="Potrzebuję obudowy na filtr węglowy do kuchni przemysłowej. Przepływ 4500 m³/h, ale mam tylko 700mm przestrzeni montażowej na długość. Budget jest ograniczony.",
        expected_behavior="KONFLIKT WYMIAROWY + DOBÓR - 4500 m³/h wymaga większej obudowy (min. GDC-900x600). 700mm to za mało. System powinien: (1) wskazać konflikt przestrzeni, (2) zaproponować alternatywy: mniejszy przepływ lub układ 2x mniejsze jednostki równolegle.",
        key_checks=[
            "Rozpoznanie konfliktu: wymagana wydajność vs dostępna przestrzeń",
            "Informacja że 4500 m³/h wymaga obudowy min. 900mm długości",
            "Propozycja alternatyw: redukcja przepływu LUB układ równoległy",
            "Wskazanie że kuchnia wymaga filtracji tłuszczów przed węglem (pre-filter)",
            "Uwzględnienie budżetu w rekomendacji"
        ]
    ),
    TestCase(
        id="Q8",
        question="Szukam najtańszej obudowy GDC do filtracji zapachów z lakierni. Wystarczy standardowy ocynk. Przepływ około 2000 m³/h.",
        expected_behavior="OSTRZEŻENIE CHEMICZNE - Lakiernia = rozpuszczalniki, LZO (VOC). Agresywne środowisko wymaga odpornych materiałów. Standardowy ocynk może korodować. Rekomendacja: min. ZM lub powłoka chemoodporna + węgiel aktywny dedykowany do VOC.",
        key_checks=[
            "Wykrycie agresywnego środowiska chemicznego (rozpuszczalniki/VOC)",
            "Ostrzeżenie o nieodpowiednim materiale (ocynk) do lakierni",
            "Rekomendacja materiału chemoodpornego (ZM, RF, powłoka)",
            "Informacja o potrzebie węgla dedykowanego do VOC (nie zwykły węgiel)",
            "Wyjaśnienie ryzyka korozji chemicznej"
        ]
    ),
    TestCase(
        id="Q9",
        question="Mam stację obsługi samochodów - na warsztacie pył z szlifowania karoserii, a przy wjeździe spaliny z silników. Czy jedna obudowa załatwi sprawę? Przepływ razem jakieś 3000 m³/h.",
        expected_behavior="WYMAGANE DWA TYPY FILTRACJI - Pył (cząstki) wymaga filtra workowego/kasetowego, spaliny (gazy) wymagają węgla aktywnego. Jedna obudowa workowa NIE usunie spalin. Rekomendacja: osobne systemy LUB obudowa kombinowana z pre-filtrem + węglem.",
        key_checks=[
            "Rozpoznanie dwóch różnych typów zanieczyszczeń (pył + gazy)",
            "Wyjaśnienie że filtr workowy nie usuwa gazów",
            "Wyjaśnienie że filtr węglowy nie nadaje się do dużych ilości pyłu",
            "Propozycja rozwiązania: osobne systemy LUB kombinowany (pre-filtr + węgiel)",
            "Prawidłowy dobór wydajności dla obu zastosowań"
        ]
    ),
    TestCase(
        id="Q10",
        question="Wymieniamy stary filtr w istniejącej instalacji. Otwór w kanale ma wymiary 580x580mm (kołnierz). Potrzebujemy filtracji węglowej na zapachy z gastronomii. Co pasuje?",
        expected_behavior="DOBÓR RETROFIT - Niestandardowy wymiar 580x580 nie pasuje do standardowych modułów (300/600/900). Rekomendacja: (1) adapter/przejściówka na 600x600, lub (2) wersja FLEX z regulacją, lub (3) obudowa na zamówienie.",
        key_checks=[
            "Rozpoznanie niestandardowego wymiaru (580 ≠ moduły 600)",
            "Informacja o standardowych modułach wymiarowych (300/600/900)",
            "Propozycja adaptera/przejściówki jako rozwiązania",
            "Alternatywnie: propozycja wersji FLEX lub custom",
            "Dobór typu filtracji do gastronomii (węgiel + pre-filtr tłuszczowy)"
        ]
    ),
    TestCase(
        id="Q11",
        question="Projektuję wentylację dla chłodni (-25°C) z częstym otwieraniem wrót (duże różnice temperatur). Potrzebuję filtracji pyłu. Który model obudowy będzie najlepszy?",
        expected_behavior="WYMOGI TERMICZNE EKSTREMALNE - Niska temperatura + szok termiczny = ryzyko kondensacji, szronu, uszkodzenia materiału. Wymagania: (1) izolacja termiczna (GDMI), (2) materiał odporny na niskie temp, (3) możliwy grzałka antykondensacyjna.",
        key_checks=[
            "Wykrycie ekstremalnych warunków termicznych (-25°C)",
            "Identyfikacja ryzyka kondensacji przy różnicach temperatur",
            "Rekomendacja obudowy izolowanej (seria GDMI)",
            "Informacja o materiałach odpornych na mróz",
            "Opcjonalnie: sugestia grzałki antykondensacyjnej lub klapy przeciwszronowej"
        ]
    ),
]

# =============================================================================
# EVALUATION PROMPT
# =============================================================================

EVALUATION_PROMPT = """Jesteś ewaluatorem systemu AI do wspomagania sprzedaży inżynierskiej.

## OCZEKIWANE ZACHOWANIE SYSTEMU
{expected_behavior}

## KLUCZOWE ELEMENTY DO SPRAWDZENIA
{key_checks}

## ODPOWIEDŹ SYSTEMU DO OCENY
{system_response}

## INSTRUKCJE OCENY
Oceń odpowiedź systemu w skali 0-10 dla każdego kryterium:

1. **Wykrycie Ryzyka (0-10)**: Czy system poprawnie zidentyfikował potencjalny problem/ryzyko?
2. **Trafność Rekomendacji (0-10)**: Czy rekomendacja jest technicznie poprawna?
3. **Kompletność (0-10)**: Czy odpowiedź zawiera wszystkie kluczowe elementy?
4. **Jasność (0-10)**: Czy odpowiedź jest zrozumiała i dobrze ustrukturyzowana?

## FORMAT ODPOWIEDZI (JSON)
{{
  "risk_detection": <0-10>,
  "recommendation_accuracy": <0-10>,
  "completeness": <0-10>,
  "clarity": <0-10>,
  "overall_score": <0-10>,
  "detected_issues": ["lista wykrytych przez system problemów"],
  "missing_elements": ["lista brakujących elementów"],
  "comment": "krótki komentarz do oceny"
}}

Zwróć TYLKO valid JSON."""

# =============================================================================
# API CALLS
# =============================================================================

BASE_URL = "http://localhost:8000"



async def query_system(question: str) -> tuple[dict, float]:
    """Query the deep-explainable endpoint and return response + time."""
    async with httpx.AsyncClient() as client:
        start_time = time.time()
        try:
            response = await client.post(
                f"{BASE_URL}/consult/deep-explainable",
                json={"query": question},
                timeout=120.0
            )
            elapsed = time.time() - start_time

            if response.status_code == 200:
                return response.json(), elapsed
            else:
                return {"error": f"HTTP {response.status_code}"}, elapsed
        except Exception as e:
            elapsed = time.time() - start_time
            return {"error": str(e)}, elapsed


def evaluate_response(test_case: TestCase, system_response: dict) -> dict:
    """Use LLM to evaluate the system response."""

    # Extract content from response
    if "error" in system_response:
        return {
            "risk_detection": 0,
            "recommendation_accuracy": 0,
            "completeness": 0,
            "clarity": 0,
            "overall_score": 0,
            "detected_issues": [],
            "missing_elements": ["System error"],
            "comment": f"Error: {system_response['error']}"
        }

    # Build response text from segments
    content_text = ""
    if "content_segments" in system_response:
        content_text = "".join(seg.get("text", "") for seg in system_response["content_segments"])

    # Add reasoning summary
    reasoning_text = ""
    if "reasoning_summary" in system_response:
        reasoning_text = "\n".join(
            f"- {step.get('step', '')}: {step.get('description', '')}"
            for step in system_response["reasoning_summary"]
        )

    # Add warnings
    warnings_text = ""
    if system_response.get("policy_warnings"):
        warnings_text = "\nOstrzeżenia: " + "; ".join(system_response["policy_warnings"])

    # Add risk detection flag
    risk_flag = ""
    if system_response.get("risk_detected"):
        risk_flag = "\n[SYSTEM WYKRYŁ RYZYKO INŻYNIERYJNE]"

    # Add clarification flag
    clarification_flag = ""
    if system_response.get("clarification_needed"):
        clarification_flag = "\n[SYSTEM WYMAGA KLARYFIKACJI]"
        if system_response.get("clarification"):
            clar = system_response["clarification"]
            clarification_flag += f"\nBrakuje: {clar.get('missing_info', 'N/A')}"
            clarification_flag += f"\nDlaczego: {clar.get('why_needed', 'N/A')}"
            clarification_flag += f"\nPytanie: {clar.get('question', 'N/A')}"

    full_response = f"""
REASONING:
{reasoning_text}

ODPOWIEDŹ:
{content_text}
{warnings_text}
{risk_flag}
{clarification_flag}

PRODUCT CARD:
{json.dumps(system_response.get('product_card'), ensure_ascii=False, indent=2) if system_response.get('product_card') else 'Brak'}

STATYSTYKI:
- Graph Facts: {system_response.get('graph_facts_count', 0)}
- Inferences: {system_response.get('inference_count', 0)}
- Confidence: {system_response.get('confidence_level', 'unknown')}
- Clarification Needed: {system_response.get('clarification_needed', False)}
"""

    # Build evaluation prompt
    key_checks_formatted = "\n".join(f"- {check}" for check in test_case.key_checks)

    prompt = EVALUATION_PROMPT.format(
        expected_behavior=test_case.expected_behavior,
        key_checks=key_checks_formatted,
        system_response=full_response
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=prompt)]
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        return {
            "risk_detection": 0,
            "recommendation_accuracy": 0,
            "completeness": 0,
            "clarity": 0,
            "overall_score": 0,
            "detected_issues": [],
            "missing_elements": ["Evaluation error"],
            "comment": f"Evaluation error: {str(e)}"
        }


# =============================================================================
# MAIN EVALUATION
# =============================================================================

async def run_evaluation():
    """Run full evaluation across models and thinking levels."""

    # Configuration combinations
    MODELS = [
        ("gemini-3-pro-preview", "Pro"),
        ("gemini-3-flash-preview", "Flash"),
    ]
    THINKING_LEVELS = [
        ("low", "Low"),
        ("high", "High"),
    ]

    # Results storage
    results = []

    print("=" * 80)
    print("GRAPHRAG SALES ASSISTANT - EVALUATION")
    print("=" * 80)
    print(f"\nRunning {len(TEST_CASES)} test cases x {len(MODELS)} models x {len(THINKING_LEVELS)} thinking levels")
    print(f"Total tests: {len(TEST_CASES) * len(MODELS) * len(THINKING_LEVELS)}")
    print()

    for model_id, model_name in MODELS:
        for thinking_id, thinking_name in THINKING_LEVELS:
            config_name = f"{model_name}/{thinking_name}"
            print(f"\n{'='*60}")
            print(f"Configuration: {config_name}")
            print(f"{'='*60}")


            for test_case in TEST_CASES:
                print(f"\n  [{test_case.id}] {test_case.question[:50]}...")

                # Query system
                response, elapsed = await query_system(test_case.question)
                print(f"      Response time: {elapsed:.2f}s")

                # Evaluate
                evaluation = evaluate_response(test_case, response)
                print(f"      Score: {evaluation.get('overall_score', 0)}/10")

                results.append({
                    "test_id": test_case.id,
                    "question": test_case.question[:40] + "...",
                    "config": config_name,
                    "model": model_name,
                    "thinking": thinking_name,
                    "time_s": round(elapsed, 2),
                    "risk_detection": evaluation.get("risk_detection", 0),
                    "recommendation": evaluation.get("recommendation_accuracy", 0),
                    "completeness": evaluation.get("completeness", 0),
                    "clarity": evaluation.get("clarity", 0),
                    "overall": evaluation.get("overall_score", 0),
                    "comment": evaluation.get("comment", "")[:50],
                    "risk_detected": response.get("risk_detected", False),
                    "clarification_needed": response.get("clarification_needed", False),
                })

    return results


def generate_results_table(results: list[dict]) -> str:
    """Generate a formatted results table."""

    # Pivot table: Questions as rows, Config combinations as columns
    configs = sorted(set(r["config"] for r in results))
    test_ids = sorted(set(r["test_id"] for r in results), key=lambda x: int(x[1:]))

    # Build header
    headers = ["Test", "Question"]
    for config in configs:
        headers.extend([f"{config}\nScore", f"{config}\nTime(s)"])

    # Build rows
    rows = []
    for test_id in test_ids:
        test_results = [r for r in results if r["test_id"] == test_id]
        question = test_results[0]["question"] if test_results else ""

        row = [test_id, question]
        for config in configs:
            config_result = next((r for r in test_results if r["config"] == config), None)
            if config_result:
                score = config_result["overall"]
                time_s = config_result["time_s"]
                # Add risk/clarification indicators
                indicator = ""
                if config_result.get("risk_detected"):
                    indicator = "🛡️"
                elif config_result.get("clarification_needed"):
                    indicator = "❓"
                row.extend([f"{score}/10 {indicator}", f"{time_s}s"])
            else:
                row.extend(["N/A", "N/A"])

        rows.append(row)

    # Add summary row
    summary_row = ["", "ŚREDNIA"]
    for config in configs:
        config_results = [r for r in results if r["config"] == config]
        avg_score = sum(r["overall"] for r in config_results) / len(config_results) if config_results else 0
        avg_time = sum(r["time_s"] for r in config_results) / len(config_results) if config_results else 0
        summary_row.extend([f"{avg_score:.1f}/10", f"{avg_time:.1f}s"])
    rows.append(summary_row)

    return tabulate(rows, headers=headers, tablefmt="grid")


def generate_detailed_report(results: list[dict]) -> str:
    """Generate a detailed evaluation report."""

    report = []
    report.append("\n" + "=" * 80)
    report.append("SZCZEGÓŁOWY RAPORT EWALUACJI")
    report.append("=" * 80)

    for test_id in sorted(set(r["test_id"] for r in results), key=lambda x: int(x[1:])):
        test_results = [r for r in results if r["test_id"] == test_id]
        if not test_results:
            continue

        question = next((tc.question for tc in TEST_CASES if tc.id == test_id), "")
        expected = next((tc.expected_behavior for tc in TEST_CASES if tc.id == test_id), "")

        report.append(f"\n{'─'*80}")
        report.append(f"[{test_id}] {question}")
        report.append(f"{'─'*80}")
        report.append(f"OCZEKIWANE: {expected}")
        report.append("")

        for r in test_results:
            risk_flag = "🛡️ RYZYKO" if r.get("risk_detected") else ""
            report.append(f"  {r['config']:15} | Score: {r['overall']:2}/10 | Time: {r['time_s']:5.1f}s | {risk_flag}")
            report.append(f"                    | Ryzyko: {r['risk_detection']}/10 | Rekomendacja: {r['recommendation']}/10 | Kompletność: {r['completeness']}/10")
            if r.get("comment"):
                report.append(f"                    | Komentarz: {r['comment']}")

    return "\n".join(report)


async def main():
    """Main entry point."""
    import sys

    print("\nStarting evaluation...\n")

    try:
        results = await run_evaluation()
    except Exception as e:
        print(f"\nError during evaluation: {e}")
        sys.exit(1)

    # Generate and print results table
    print("\n" + "=" * 80)
    print("TABELA WYNIKÓW")
    print("=" * 80)
    print(generate_results_table(results))

    # Generate detailed report
    print(generate_detailed_report(results))

    # Save results to JSON
    output_file = "evaluation_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nWyniki zapisane do: {output_file}")

    # Summary
    print("\n" + "=" * 80)
    print("PODSUMOWANIE")
    print("=" * 80)

    configs = sorted(set(r["config"] for r in results))
    for config in configs:
        config_results = [r for r in results if r["config"] == config]
        avg_score = sum(r["overall"] for r in config_results) / len(config_results)
        avg_time = sum(r["time_s"] for r in config_results) / len(config_results)
        risk_detected_count = sum(1 for r in config_results if r.get("risk_detected"))

        print(f"{config:20} | Avg Score: {avg_score:.1f}/10 | Avg Time: {avg_time:.1f}s | Risk Detected: {risk_detected_count}/{len(config_results)}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
