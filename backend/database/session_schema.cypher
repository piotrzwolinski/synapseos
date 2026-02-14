// =============================================================================
// LAYER 4: SESSION STATE (Active Project Configuration)
// =============================================================================
// This layer stores active engineering sessions in the graph.
// It survives server restarts and provides the LLM with ground truth
// about the current project configuration.
//
// Nodes:
//   Session      - One per browser tab (keyed by session_id)
//   ActiveProject - Current project being configured
//   TagUnit       - Individual tag/item specifications
//
// Cross-layer links to Layer 1:
//   (ActiveProject)-[:USES_MATERIAL]->(Material)
//   (ActiveProject)-[:TARGETS_FAMILY]->(ProductFamily)
//   (TagUnit)-[:SIZED_AS]->(DimensionModule)
// =============================================================================

// Constraints
CREATE CONSTRAINT IF NOT EXISTS FOR (s:Session) REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (ap:ActiveProject) REQUIRE ap.id IS UNIQUE;

// Indexes for fast lookup
CREATE INDEX session_last_active IF NOT EXISTS FOR (s:Session) ON (s.last_active);
CREATE INDEX tagunit_session IF NOT EXISTS FOR (t:TagUnit) ON (t.session_id);
CREATE INDEX activeproject_session IF NOT EXISTS FOR (ap:ActiveProject) ON (ap.session_id);
