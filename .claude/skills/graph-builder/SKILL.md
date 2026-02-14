---
name: graph-builder
description: Create and modify Knowledge Graph data (nodes, relationships, properties) in the SynapseOS Neo4j database. Use when adding new Applications, Stressors, Traits, Products, InstallationConstraints, CapacityRules, DependencyRules, or any graph data. Also for writing seed scripts.
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Glob, Edit, Write, Bash, mcp__neo4j__read_neo4j_cypher, mcp__neo4j__write_neo4j_cypher, mcp__neo4j__get_neo4j_schema
argument-hint: "[what to add/modify, e.g. 'add APP_PHARMACEUTICAL' or 'new stressor for UV exposure']"
---

# Graph Builder — Creating and Modifying Knowledge Graph Data

You are a graph data engineer for the SynapseOS Knowledge Graph. You add, modify, and validate graph data following strict naming conventions and relationship patterns.

## GOLDEN RULES

1. **Graph holds ALL intelligence** — domain logic lives in nodes/relationships, NOT Python code
2. **ID prefixes are mandatory** — every node type has a prefix (see Naming Conventions below)
3. **Verify after write** — always run a read query to confirm the data was created correctly
4. **Batch with UNWIND** — never query in a loop, use `UNWIND $list AS item`
5. **COALESCE for updates** — use `COALESCE(n.prop, $val)` pattern, NOT `ON CREATE SET`

## THE 4-LAYER MODEL

| Layer | Purpose | Node Types | Mutability |
|-------|---------|-----------|------------|
| 1 — Inventory | What we sell | ProductFamily, DimensionModule, Material, PhysicalTrait | Seed data, rarely changes |
| 2 — Physics | How the world works | EnvironmentalStressor, CausalRule (via DEMANDS_TRAIT), DependencyRule | Domain expert adds |
| 3 — Playbook | Decision logic | LogicGate, Parameter, HardConstraint, Strategy, InstallationConstraint | Engineering rules |
| 4 — State | Session twin | Session, ActiveProject, TagUnit, ConversationTurn | Runtime, per-session |

**RULE:** Layers 1-3 are seeded. Layer 4 is runtime. Never manually create Layer 4 nodes.

## NAMING CONVENTIONS

| Node Type | ID Prefix | Example |
|-----------|-----------|---------|
| Application | `APP_` | `APP_KITCHEN`, `APP_HOSPITAL`, `APP_POWDER_COATING` |
| Environment | `ENV_` | `ENV_OUTDOOR`, `ENV_INDOOR`, `ENV_KITCHEN` |
| EnvironmentalStressor | `STRESSOR_` | `STRESSOR_CHEMICAL_VAPORS`, `STRESSOR_CHLORINE` |
| PhysicalTrait | `TRAIT_` | `TRAIT_POROUS_ADSORPTION`, `TRAIT_MECHANICAL_FILTRATION` |
| ProductFamily | `FAM_` | `FAM_GDB`, `FAM_GDC_FLEX` |
| DimensionModule | `DIM_` | `DIM_600x600`, `DIM_1200x600` |
| Material | `MAT_` | `MAT_FZ`, `MAT_RF`, `MAT_SF` |
| LogicGate | `GATE_` | `GATE_ATEX_ZONE`, `GATE_DEW_POINT` |
| Parameter | `PARAM_` | `PARAM_AIRFLOW`, `PARAM_ATEX_ZONE` |
| HardConstraint | `HC_FAM_` | `HC_FAM_GDB_HOUSING_LENGTH_MM` |
| InstallationConstraint | `IC_` | `IC_SERVICE_CLEARANCE`, `IC_ENVIRONMENT_WHITELIST` |
| DependencyRule | `DEP_` | `DEP_KITCHEN_CARBON`, `DEP_DUSTY_CARBON` |
| CapacityRule | `CAP_` | `CAP_GDB_600`, `CAP_GDC_600` |
| FunctionalGoal | `GOAL_` | `GOAL_ODOR_REMOVAL` |
| VariableFeature | `FEAT_` | `FEAT_HOUSING_LENGTH_GDB` |
| Risk | `RISK_` | `RISK_COND`, `RISK_CORR` |
| Strategy | `STRAT_` | `STRAT_BLOCK`, `STRAT_WARN_AND_CONFIRM` |

## RELATIONSHIP PATTERNS

See references/relationship-patterns.md for the complete relationship catalog.

## CREATE PATTERNS (Cypher Templates)

See references/cypher-templates.md for ready-to-use Cypher patterns for each node type.

## SEED SCRIPT TEMPLATE

When creating a seed script, place it in `backend/database/` and follow this pattern:

```python
#!/usr/bin/env python3
"""Seed script: Add [description].

Run: cd backend && source venv/bin/activate && python database/my_seed_script.py
"""
import sys
sys.path.insert(0, ".")
from database import db

def seed():
    driver = db.get_driver()
    with driver.session() as session:
        # Create nodes
        session.run("""
            MERGE (n:NodeType {id: $id})
            SET n.name = $name,
                n.description = $desc
        """, id="PREFIX_ID", name="Name", desc="Description")

        # Create relationships
        session.run("""
            MATCH (a:NodeType {id: $a_id})
            MATCH (b:OtherType {id: $b_id})
            MERGE (a)-[:RELATIONSHIP_TYPE]->(b)
        """, a_id="PREFIX_A", b_id="PREFIX_B")

    print("Seed complete.")

if __name__ == "__main__":
    seed()
```

## VERIFICATION WORKFLOW

After every write operation:

1. **Read back** — query the created/modified node with all properties
2. **Check relationships** — verify all expected relationships exist
3. **Check engine compatibility** — ensure ID format matches what database.py queries expect
4. **Update schema doc** — if new node types or relationships added, update `docs/current_schema.txt`

## COMMON TASKS

### Add a new Application
See references/cypher-templates.md → "New Application"

### Add a new Stressor
See references/cypher-templates.md → "New Stressor"

### Link Application to Stressor
See references/cypher-templates.md → "Application → Stressor"

### Add a DependencyRule (Assembly Trigger)
See references/cypher-templates.md → "New DependencyRule"

### Add an InstallationConstraint
See references/cypher-templates.md → "New InstallationConstraint"

### Add a new ProductFamily
See references/cypher-templates.md → "New ProductFamily"

## CYPHER GOTCHAS

1. **`ON CREATE SET`** — Not supported in all Neo4j versions. Use `COALESCE(n.prop, $val)` instead.
2. **`allowed_environments` is StringArray** — Don't use `split()`. Use `$val IN pf.allowed_environments`.
3. **`UNWIND` for batch** — Never loop in Python. Use `UNWIND $items AS item MERGE (n {id: item.id})`.
4. **ID normalization** — Database queries normalize with `FAM_` prefix. Store IDs WITH prefix.
5. **Property types** — Neo4j is strict. `keywords` must be `list`, not comma-separated string. Use `["kw1", "kw2"]`.
6. **Embedding generation** — For Application nodes with `embedding` property, use `backend/embeddings.py:generate_embedding()`.
