# HVAC Graph Reasoning — Test Matrix v2.0

## Source of Truth: MH Product Catalog (PDF)

All expected outcomes are derived from the MH product catalog analysis. Each test documents:
- What the PDF says should happen
- What graph data the test depends on
- What assertion category (detection/logic/output) each check falls into

## Test Categories

| Category | Count | Tests |
|----------|-------|-------|
| env | 8 | Environment-based decisions (whitelist, pivot, block) |
| assembly | 3 | Multi-stage assembly triggers |
| atex | 2 | ATEX / explosive atmosphere gate |
| sizing | 5 | Multi-module sizing, dimension mapping, space constraints |
| material | 2 | Material-specific constraints (chlorine, salt) |
| positive | 4 | Positive controls (should pass without blocks) |
| clarif | 3 | Missing parameter clarification flow |

**Total: 27 test cases**

---

## Decision Matrix (PDF Ground Truth)

### Environment × Product × Material → Expected Decision

| Environment | Product | Material | Expected Decision | Key Graph Dependency |
|-------------|---------|----------|-------------------|---------------------|
| Office | GDB | FZ | PASS | No stressors |
| Warehouse | GDB | FZ | PASS | ENV_INDOOR |
| Hospital | GDB | FZ | BLOCK (env + material) | ENV_HOSPITAL, IC_ENVIRONMENT_WHITELIST |
| Hospital | GDMI | RF | PASS | GDMI.allowed_environments includes hospital |
| Outdoor | GDB | FZ | RISK → pivot GDMI | STRESSOR_OUTDOOR_CONDENSATION |
| Outdoor | GDMI | FZ | PASS | GDMI rated outdoor |
| Marine | GDB | FZ | BLOCK (salt + outdoor) | STRESSOR_SALT_SPRAY |
| Kitchen | GDB | FZ | WARN (grease) | STRESSOR_GREASE_EXPOSURE |
| Kitchen | GDC-FLEX | RF | ASSEMBLY (GDP) | DEP_KITCHEN_CARBON |
| Kitchen | GDC | RF | ASSEMBLY (GDP) | DEP_KITCHEN_CARBON |
| Office | GDC | FZ | PASS (no assembly) | No grease → no NEUTRALIZATION |
| Pool | GDB | FZ | BLOCK (chlorine) | IC_MATERIAL_CHLORINE |
| ATEX Zone | GDB | FZ | GATE (ask zone) | GATE_ATEX_ZONE |
| Pharma | any | any | STRICT (hygiene) | STRESSOR_HYGIENE_REQUIREMENTS |
| Outdoor Kitchen | GDC-FLEX | RF | DOUBLE (grease + condensation) | Multiple stressors |

### Sizing Rules

| Scenario | Expected | Graph Dependency |
|----------|----------|-----------------|
| 600x600, 3400 m³/h | Single module | DIM_600x600, CAP_GDB_600 |
| 10,000 m³/h, max 1300mm | Multi-module (3× 600x600) | compute_sizing_arrangement |
| Filter 305x610 | Map to housing 300x600 | Dimension normalization |
| Two tags, different sizes | Separate sizing per tag | Multi-tag handling |
| 650mm shaft, 600mm housing | Service clearance warning | IC_SERVICE_CLEARANCE |

---

## Assertion Categories

Each assertion is tagged with a category for gap analysis:

- **detection** — Did the system detect the right environment/application/stressors? Failure = Scribe or keyword gap.
- **logic** — Did the engine make the right decision (block/pass/assembly/gate)? Failure = engine logic or graph data gap.
- **output** — Does the response contain expected content? Failure = LLM generation or adapter.
- **data** — Is the graph data correct and complete? Failure = missing nodes/properties.

## Running Tests

```bash
# All tests
python run_tests.py all

# Single test (fuzzy match)
python run_tests.py hospital
python run_tests.py kitchen

# By category
python run_tests.py --category env
python run_tests.py --category assembly

# With gap analysis
python run_tests.py --gap

# List all tests
python run_tests.py list
```

## Gap Analysis

When tests fail, the runner produces a gap analysis that:
1. Groups failures by likely cause (graph_data, scribe, engine, llm)
2. Lists which graph nodes each failing test depends on
3. Shows pass rate per category
4. Suggests specific graph fixes

This allows bulk-fixing: instead of fixing one test at a time, you see ALL graph data gaps at once and fix them in a single Cypher session.
