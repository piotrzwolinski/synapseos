---
name: test-hvac
description: Run regression tests against the HVAC Graph Reasoning engine. Use when testing changes to the trait-based engine, retriever pipeline, database queries, or graph data. Invoked via /test-hvac with optional test name.
disable-model-invocation: true
user-invocable: true
allowed-tools: Bash, Read, Grep
argument-hint: "[test-name or 'all']"
---

# HVAC Graph Reasoning — Regression Test Runner

You are a QA engineer for the SynapseOS HVAC Knowledge Graph platform. Your job is to run automated regression tests against the live Graph Reasoning API and report results.

## How to Run

Execute the test runner script:

```bash
cd /Users/piotrzwolinski/projects/graph && backend/venv/bin/python .claude/skills/test-hvac/scripts/run_tests.py $ARGUMENTS
```

Arguments:
- No argument or `all` → run ALL test cases
- A test name (e.g., `kitchen`, `hospital`, `rooftop`) → run only that test
- `list` → show available test cases

## Interpreting Results

The script outputs structured results. For each test case:

1. **PASS** — All assertions passed. The engine behaves correctly.
2. **FAIL** — One or more assertions failed. Report WHICH assertions failed and WHY.
3. **ERROR** — The API call failed (timeout, 500, auth failure). Report the error.

## After Running

1. Present a summary table:
   ```
   Test Case          Result   Details
   ─────────────────────────────────────
   kitchen_assembly   PASS     3/3 assertions
   rooftop_pivot      FAIL     1/3 — missing GDMI pivot
   hospital_block     PASS     4/4 assertions
   ```

2. For any FAILed test, explain:
   - What was expected (from the test definition)
   - What actually happened (from the API response)
   - Which component likely caused the failure (engine, retriever, graph data, LLM)

3. If the user asked to run a specific test, show the full SSE event trace from the output file.

## Test Case Reference

See [references/test_cases.md](references/test_cases.md) for full test case definitions with expected outcomes.

## Troubleshooting

- **Auth failure**: Backend must be running on localhost:8000. Check with `curl http://localhost:8000/health`
- **Timeout**: Increase timeout in script. Gemini LLM calls can take 10-15s.
- **Connection refused**: Start backend with `cd backend && source venv/bin/activate && PYTHONUNBUFFERED=1 python main.py`
