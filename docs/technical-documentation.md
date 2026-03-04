# AI Solutions Finder — Technical Documentation

## 1. Graph Schema

The knowledge graph stores all product, physics, and decision logic. It uses **FalkorDB** (Cypher query language, Redis wire protocol).

### Node Types

| Node Type | Layer | Description |
|-----------|-------|-------------|
| `ProductFamily` | Inventory | Product categories (GDB, GDC, GDMI, GDP, GDC-FLEX, etc.) |
| `Item` | Inventory | Specific product instances |
| `Trait` | Inventory | Product capabilities (e.g., grease-rated, corrosion-resistant) |
| `Material` | Inventory | Material types (FZ, ZM, RF, SF) with corrosion class |
| `DimensionModule` | Inventory | Available sizes and module configurations |
| `CapacityRule` | Inventory | Airflow capacity per product/size combination |
| `Stressor` | Physics | Environmental stressors (grease, particles, gas, odor) |
| `CausalRule` | Physics | Cause-effect rules linking stressors to required traits |
| `Environment` | Physics | Installation environments (indoor, outdoor, hospital, marine, etc.) |
| `Application` | Physics | Application types (kitchen, lab, pool, food processing, etc.) |
| `InstallationConstraint` | Physics | Material/spatial compatibility rules |
| `LogicGate` | Playbook | Decision tree nodes |
| `Parameter` | Playbook | Required input parameters with priority ordering |
| `VariableFeature` | Playbook | Configurable product features with defaults |
| `Session` | State | Active user session |
| `ActiveProject` | State | Current project within a session |
| `TagUnit` | State | Product recommendation unit with resolved specifications |
| `ConversationTurn` | State | Individual message in the conversation |

### Key Relationships

| Relationship | From → To | Description |
|-------------|-----------|-------------|
| `REQUIRES_MATERIAL` | Application → Material | Which materials an application demands |
| `REQUIRES_RESISTANCE` | Application → Requirement | Resistance requirements for an application |
| `MEETS_REQUIREMENT` | Material → Requirement | What requirements a material satisfies |
| `SUITABLE_FOR` | ProductFamily → Environment | Environment compatibility |
| `HAS_VARIABLE_FEATURE` | ProductFamily → VariableFeature | Configurable features per product |
| `GENERATES` | Application → Substance | What stressors an application produces |
| `TRIGGERS` | Stressor → CausalRule | Which rules a stressor activates |
| `HAS_TRAIT` | Item → Trait | Traits assigned to a product |

---

## 2. Configuration

All domain-specific data is maintained in the configuration file. This is where product rules, material hierarchies, and system behavior are defined.

### Configuration Sections

| Section | Purpose |
|---------|---------|
| `domain` | System identity: id, name, company, version, graph name |
| `entity_patterns` | Product family codes (GDC-FLEX, GDC, GDP, etc.), material codes (FZ, ZM, RF, SS), option codes |
| `material_environment_rules` | Material hierarchy with corrosion classes, environment-specific material constraints |
| `product_application_rules` | Product capabilities and limitations (e.g., GDB = particles only, GDC = gas/odor) |
| `geometric_constraints` | Physical dimension rules (e.g., polisfilter requires 900mm length) |
| `accessory_compatibility` | Which accessories work with which products |
| `clarification_rules` | Required parameters before a recommendation can be made |
| `assembly` | Shared properties that auto-sync across multi-stage assemblies |
| `dimension_mapping` | Filter-to-housing size lookup table |
| `corrosion_class_map` | Material code → corrosion class (FZ→C3, RF→C5) |
| `housing_length_derivation` | Product-specific depth-to-length tables |
| `material_codes_extended` | Code aliases and multilingual extraction keywords |
| `scribe_hints` | Keywords that help the LLM infer product types (e.g., "insulated" → GDMI) |
| `prompt_context` | Controls which fields appear in the output and how they are formatted |
| `parameter_routing` | How extracted parameters map to internal fields |

### Adding a New Product Rule

To add a new constraint or rule, update the relevant section in the configuration file. For example, adding a new environment-material restriction:

```yaml
material_environment_rules:
  demanding_environments:
    new_environment:
      required_materials: ["RF", "SF"]
      reason: "Requires high corrosion resistance"
```

No code changes needed — the engine reads these rules at query time.

### Adding Graph Data

New products, traits, stressors, and rules are added directly to the knowledge graph via Cypher queries. Examples:

**Add a new product family:**
```cypher
CREATE (:ProductFamily {
  id: "NEW_PRODUCT",
  name: "New Product Name",
  description: "Description",
  construction_type: "BOLTED"
})
```

**Add an environment compatibility:**
```cypher
MATCH (p:ProductFamily {id: "NEW_PRODUCT"})
MATCH (e:Environment {id: "ENV_INDOOR"})
CREATE (p)-[:SUITABLE_FOR]->(e)
```

**Add a stressor-to-trait rule:**
```cypher
MATCH (s:Stressor {id: "GREASE"})
CREATE (s)-[:TRIGGERS]->(:CausalRule {
  id: "RULE_NEW",
  required_trait: "NEUTRALIZATION",
  description: "Grease requires neutralization capability"
})
```

---

## 3. Prompt Templates

The system uses five prompt templates that control how the AI generates responses and evaluations.

### `system_generic.txt` — System Prompt
Defines the AI's role and response rules:
- Present verified engineering data with clear source attribution
- Distinguish between graph-verified facts and advisory information
- Response structure: short paragraphs (2–3 sentences), one topic each
- Never fabricate product specifications

### `synthesis.txt` — Response Synthesis
Controls how the engine's analysis is turned into a user-facing response:
1. Acknowledge the user's context
2. Present the system's analysis with engineering notes
3. Check and report any constraint violations
4. Ask clarification questions if needed

Output format: structured JSON with segments marked as `GRAPH_FACT` (verified from graph) or `INFERENCE` (derived by LLM).

### `judge_system.txt` — Evaluation Criteria
Defines the AI-as-Judge scoring framework with 6 dimensions:

| Dimension | What it measures |
|-----------|-----------------|
| Correctness | Product specs match catalog data |
| Completeness | All relevant information included |
| Safety | No dangerous recommendations |
| Tone | Professional engineering communication |
| Reasoning quality | Logical, traceable decision path |
| Constraint adherence | Respects material, spatial, and environmental rules |

### `judge_question.txt` — Test Question Generation
Template for generating diverse test questions covering:
- Environment detection scenarios
- Material constraint edge cases
- Sizing and capacity calculations
- Assembly configurations
- Clarification handling
- Multi-turn conversation flows

### `judge_user.txt` — Evaluation Instructions
Detailed instructions for the judge to verify:
- Product specifications against catalog PDF
- Engineering correctness of recommendations
- Full multi-turn conversation coherence

---

## 4. API Reference

### Core Consultation

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/consult/deep-explainable/stream` | POST | **Primary endpoint.** Full graph reasoning with SSE streaming. Returns real-time reasoning chain + final response. |

**Request body:**
```json
{
  "query": "I need air filtration for a commercial kitchen, 5000 m³/h",
  "session_id": "optional-session-uuid"
}
```

**SSE event types:**
| Event | Description |
|-------|-------------|
| `status` | Processing step update (e.g., "Analyzing intent…", "Querying graph…") |
| `reasoning` | Intermediate reasoning chain data |
| `response` | Final structured response with product recommendations |
| `error` | Error details if processing fails |

### Session Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/session/graph/{session_id}` | GET | Retrieve current project state for a session |
| `/session/graph/{session_id}/visualization` | GET | Session state formatted for graph visualization |
| `/session/{session_id}` | DELETE | Clear all session state |

### Graph Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/graph/stats` | GET | Node and relationship counts |
| `/graph/data` | GET | Full graph data for visualization |
| `/graph/neighborhood/{node_id}` | GET | Neighborhood traversal (params: `depth`, `max_nodes`) |

### Configuration

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/config/domain` | GET | Current active configuration |
| `/config/domain/{domain_id}/reload` | POST | Reload configuration from disk (no restart needed) |
| `/products` | GET | List all product families |

### Testing & Evaluation

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/judge/run/stream` | POST | Run AI-as-Judge evaluation on a single question (SSE) |
| `/judge/questions` | GET | List saved evaluation questions |
| `/test-lab/results` | GET | Latest test results |
| `/test-lab/batches` | GET | List all test batches with statistics |
| `/test-lab/batches/{batch_id}` | GET | Results for a specific batch |
| `/test-generator/debate/stream` | POST | Generate test cases via multi-model debate (SSE) |
| `/test-generator/approved` | GET | List approved test cases |

### Authentication

All endpoints require JWT authentication.

```
POST /auth/login
Body: { "username": "...", "password": "..." }
Response: { "access_token": "...", "role": "admin|expert" }
```

Include the token in subsequent requests:
```
Authorization: Bearer <access_token>
```

---

## 5. Testing & Evaluation

### AI-as-Judge Framework

The system includes a built-in evaluation framework that uses LLMs to score the quality of the reasoning engine's responses.

**Evaluation flow:**
1. Test questions are generated from product catalog PDFs or created manually
2. Each question is run through the reasoning engine
3. The response is scored by an AI judge across 6 dimensions (see Prompt Templates above)
4. Results are stored with batch tracking for comparison over time

**Batch testing:**
- Run entire test suites against the engine
- Compare results across batches to track improvements or regressions
- View per-question scores and aggregate statistics

### Expert Review

Domain experts can review AI conversations and provide feedback:
- Rate individual responses
- Flag incorrect recommendations
- The system learns from expert corrections to improve future responses

---

## 6. Session State (Layer 4)

Each conversation creates a persistent session in the graph that tracks:

| Field | Description |
|-------|-------------|
| Session ID | Unique identifier for the conversation |
| Active project | Current product selection project |
| Detected application | Identified application type (kitchen, hospital, etc.) |
| Detected environment | Installation environment |
| Resolved parameters | All user-provided specifications (airflow, dimensions, material) |
| Selected products | Recommended product families and configurations |
| Assembly groups | Multi-stage product assemblies |
| Conversation turns | Full message history with timestamps |

**Key behavior:**
- Parameters persist across turns — the user never needs to repeat information
- New information overrides previous values; unmentioned parameters are preserved
- Assembly groups auto-synchronize shared properties (dimensions, airflow) across stages
- Session state is queryable via the API for debugging or review

---

## 7. Extending the System

### Adding a New Product Family
1. Create `ProductFamily` node in the graph with id, name, construction type
2. Link to environments via `SUITABLE_FOR` relationships
3. Add `DimensionModule` nodes for available sizes
4. Add `CapacityRule` nodes for airflow capacity per size
5. Add `Trait` relationships for product capabilities
6. Update configuration with product codes and entity patterns

### Adding a New Environment Rule
1. Create or update `Environment` node in the graph
2. Add `InstallationConstraint` nodes for material/spatial restrictions
3. Link `Application` nodes to stressors and required materials
4. Update configuration with environment keywords for intent recognition

### Adding a New Stressor
1. Create `Stressor` node in the graph
2. Create `CausalRule` linking the stressor to required traits
3. Link applications that produce this stressor via `GENERATES`
4. The reasoning engine will automatically pick up the new stressor

### Modifying Prompt Behavior
Edit the relevant prompt template file and reload the configuration via:
```
POST /config/domain/{domain_id}/reload
```
No server restart required.
