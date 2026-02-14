// =============================================================================
// GENERIC NEURO-SYMBOLIC REASONING SCHEMA
// Domain-Agnostic 3-Layer Graph Architecture for FalkorDB
// =============================================================================
//
// This schema can represent ANY business domain (HVAC, Insurance, E-commerce)
// by changing only the DATA, not the structure.
//
// LAYER 1: INVENTORY (What exists)
// LAYER 2: DOMAIN RULES (How the world works)
// LAYER 3: PLAYBOOK (How to inquire)
// =============================================================================

// -----------------------------------------------------------------------------
// LAYER 1: INVENTORY (The "Items")
// -----------------------------------------------------------------------------
// Items are the core entities being selected/recommended.
// Examples: Products, Services, Policies, Courses, etc.

// Item - The main entity (product, service, policy, etc.)
// Properties are stored as separate nodes to enable graph queries
CREATE CONSTRAINT item_id IF NOT EXISTS FOR (i:Item) REQUIRE i.id IS UNIQUE;

// Property - Key-value attributes of Items
// Stored separately to enable constraint matching via graph traversal
CREATE CONSTRAINT property_id IF NOT EXISTS FOR (p:Property) REQUIRE p.id IS UNIQUE;

// Category - Optional grouping/classification of Items
CREATE CONSTRAINT category_id IF NOT EXISTS FOR (c:Category) REQUIRE c.id IS UNIQUE;

// Relationship: Item has Properties
// (Item)-[:HAS_PROP]->(Property)

// Relationship: Item belongs to Category
// (Item)-[:IN_CATEGORY]->(Category)

// -----------------------------------------------------------------------------
// LAYER 2: DOMAIN RULES (The "Physics & Context")
// -----------------------------------------------------------------------------
// Contexts are semantic situations detected from user queries.
// Constraints are requirements that Contexts impose on Items.

// Context - A semantic situation/environment detected via vector search
// CRITICAL: Must have vector index for embedding-based retrieval
CREATE CONSTRAINT context_id IF NOT EXISTS FOR (ctx:Context) REQUIRE ctx.id IS UNIQUE;

// Create vector index for semantic search on Context descriptions
// FalkorDB syntax for vector index
// Note: Run this after creating Context nodes with embeddings
// CALL db.idx.vector.createNodeIndex('Context', 'embedding', 1536, 'cosine');

// Constraint - A requirement imposed by a Context
// target_key: which Property key this constrains
// operator: EQUALS, NOT_EQUALS, GREATER_THAN, LESS_THAN, IN, NOT_IN, EXISTS
// required_value: the value required by this constraint
// severity: CRITICAL (blocks), WARNING (warns), INFO (informs)
CREATE CONSTRAINT constraint_id IF NOT EXISTS FOR (con:Constraint) REQUIRE con.id IS UNIQUE;

// Risk - A potential problem that a Context can cause
CREATE CONSTRAINT risk_id IF NOT EXISTS FOR (r:Risk) REQUIRE r.id IS UNIQUE;

// Solution - A way to mitigate a Risk
CREATE CONSTRAINT solution_id IF NOT EXISTS FOR (s:Solution) REQUIRE s.id IS UNIQUE;

// Relationships:
// (Context)-[:IMPLIES_CONSTRAINT {reason}]->(Constraint)
// (Context)-[:GENERATES_RISK {probability}]->(Risk)
// (Item)-[:SATISFIES]->(Constraint) - pre-calculated or dynamic
// (Item)-[:VULNERABLE_TO {severity}]->(Risk)
// (Item)-[:MITIGATES]->(Risk)
// (Property)-[:MEETS]->(Constraint) - property value satisfies constraint

// -----------------------------------------------------------------------------
// LAYER 2B: PHYSICS-BASED MITIGATION (The "Safety Engine")
// -----------------------------------------------------------------------------
// This pattern encodes physical/engineering constraints that CANNOT be overridden
// by user arguments. The graph is authoritative on physics.
//
// Pattern: Environment -[:CAUSES]-> Risk -[:MITIGATED_BY]-> Feature <-[:INCLUDES_FEATURE]- Product
//
// If a Product lacks the Feature required to mitigate a Risk caused by an Environment,
// the configuration is BLOCKED regardless of user arguments.

// Environment - A context that causes physical risks (e.g., Outdoor, ATEX Zone)
CREATE CONSTRAINT environment_id IF NOT EXISTS FOR (e:Environment) REQUIRE e.id IS UNIQUE;

// Feature - A capability that mitigates a risk (e.g., Thermal Insulation, Explosion-proof)
CREATE CONSTRAINT feature_id IF NOT EXISTS FOR (f:Feature) REQUIRE f.id IS UNIQUE;

// Relationships for Mitigation Path:
// (Environment)-[:CAUSES {certainty: "Absolute"}]->(Risk)
// (Risk)-[:MITIGATED_BY {mandatory: true}]->(Feature)
// (Item)-[:INCLUDES_FEATURE]->(Feature)  -- Product HAS the mitigation
// (Item)-[:VULNERABLE_TO]->(Risk)        -- Product LACKS the mitigation
// (Item)-[:PROTECTS_AGAINST]->(Risk)     -- Product directly protects against risk

// MITIGATION PATH VALIDATOR LOGIC:
// 1. Detect Environment from query keywords (env.keywords property)
// 2. Find Risks caused by Environment: MATCH (env)-[:CAUSES]->(risk:Risk)
// 3. Find required Feature: MATCH (risk)-[:MITIGATED_BY]->(feat:Feature)
// 4. Check if Product has Feature: MATCH (prod)-[:INCLUDES_FEATURE]->(feat)
// 5. If NO match: BLOCK the configuration, suggest products that DO have the feature

// -----------------------------------------------------------------------------
// LAYER 3: PLAYBOOK (The "Inquiry Logic")
// -----------------------------------------------------------------------------
// Discriminators are questions that reduce entropy in item selection.
// They are triggered when multiple valid items exist with variable properties.

// Discriminator - A question to ask the user
// name: identifier (e.g., "airflow", "budget", "destination")
// question: the actual question text
// priority: order of asking (lower = ask first)
CREATE CONSTRAINT discriminator_id IF NOT EXISTS FOR (d:Discriminator) REQUIRE d.id IS UNIQUE;

// Option - A possible answer to a Discriminator
CREATE CONSTRAINT option_id IF NOT EXISTS FOR (o:Option) REQUIRE o.id IS UNIQUE;

// Strategy - A recommended action or cross-sell
CREATE CONSTRAINT strategy_id IF NOT EXISTS FOR (st:Strategy) REQUIRE st.id IS UNIQUE;

// Relationships:
// (Property)-[:DEPENDS_ON]->(Discriminator) - property selection requires this question
// (Discriminator)-[:HAS_OPTION]->(Option)
// (Option)-[:SELECTS_VALUE {property_key}]->(Property) - choosing option sets property
// (Context)-[:TRIGGERS_STRATEGY]->(Strategy)
// (Item)-[:ENABLES_STRATEGY]->(Strategy)

// -----------------------------------------------------------------------------
// INDEXES FOR PERFORMANCE
// -----------------------------------------------------------------------------
CREATE INDEX item_name IF NOT EXISTS FOR (i:Item) ON (i.name);
CREATE INDEX property_key IF NOT EXISTS FOR (p:Property) ON (p.key);
CREATE INDEX context_name IF NOT EXISTS FOR (ctx:Context) ON (ctx.name);
CREATE INDEX constraint_key IF NOT EXISTS FOR (con:Constraint) ON (con.target_key);
CREATE INDEX discriminator_name IF NOT EXISTS FOR (d:Discriminator) ON (d.name);

// -----------------------------------------------------------------------------
// EXAMPLE: How this maps to HVAC domain (for reference only, not executed)
// -----------------------------------------------------------------------------
// Item: {id: "GDC-600x600", name: "GDC Housing 600x600", description: "Carbon filter housing"}
// Property: {id: "GDC-600x600:material:FZ", key: "material", value: "FZ"}
// Context: {id: "CTX_HOSPITAL", name: "Hospital", description: "Medical facility with hygiene requirements", embedding: [...]}
// Constraint: {id: "CON_CORROSION_C5", target_key: "material", operator: "IN", required_value: "RF,SF", severity: "CRITICAL"}
// (Context:Hospital)-[:IMPLIES_CONSTRAINT {reason: "VDI 6022 hygiene requirements"}]->(Constraint:Corrosion_C5)
// Discriminator: {id: "DISC_AIRFLOW", name: "airflow", question: "What is the required airflow capacity?", priority: 1}

// -----------------------------------------------------------------------------
// EXAMPLE: Physics-Based Mitigation (Condensation Risk)
// -----------------------------------------------------------------------------
// Environment: {id: "ENV_OUTDOOR", name: "Outdoor Installation", keywords: ["outdoor", "roof", "rooftop"]}
// Risk: {id: "RISK_COND", name: "Condensation / Dew Point", severity: "CRITICAL",
//        physics_explanation: "Warm moist air contacts cold metal -> water condenses",
//        user_misconception: "Warm air is NOT safe - it holds MORE moisture"}
// Feature: {id: "FEAT_INSUL", name: "Thermal Insulation",
//          physics_function: "Maintains surface above dew point"}
//
// Relationships:
// (Environment:Outdoor)-[:CAUSES {certainty: "Absolute"}]->(Risk:Condensation)
// (Risk:Condensation)-[:MITIGATED_BY {mandatory: true}]->(Feature:Insulation)
// (Item:GDMI)-[:INCLUDES_FEATURE]->(Feature:Insulation)  -- GDMI is SAFE
// (Item:GDB)-[:VULNERABLE_TO]->(Risk:Condensation)       -- GDB is BLOCKED
//
// Query to find unmitigated risks:
// MATCH (env:Environment)-[:CAUSES]->(risk:Risk)-[:MITIGATED_BY]->(feat:Feature)
// MATCH (prod:ProductFamily)
// WHERE NOT EXISTS { (prod)-[:INCLUDES_FEATURE]->(feat) }
// RETURN prod.name AS blocked_product, risk.name AS risk, feat.name AS required_feature
