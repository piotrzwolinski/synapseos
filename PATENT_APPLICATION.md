# PATENT APPLICATION

## CONSTRAINT-ENFORCED KNOWLEDGE GRAPH SYSTEM FOR DOMAIN-SPECIFIC LANGUAGE MODEL GENERATION WITH EXPERT-VERIFIED REASONING

---

## FIELD OF THE INVENTION

The present invention relates to artificial intelligence systems, and more particularly to a constraint-enforced knowledge graph system that controls and validates large language model (LLM) outputs through policy-driven reasoning, safety-critical blocking mechanisms, and expert-verified knowledge sources.

---

## BACKGROUND OF THE INVENTION

### Prior Art Limitations

Current approaches to augmenting Large Language Models (LLMs) with knowledge graphs, commonly referred to as "Graph Retrieval-Augmented Generation" (GraphRAG), suffer from several fundamental limitations:

1. **Context-Only Augmentation**: Existing systems merely inject graph-derived context into LLM prompts without enforcing constraints on the generated output. The LLM remains free to generate content that contradicts or ignores the provided graph data.

2. **Lack of Hard Constraints**: Prior art systems provide warnings or suggestions but cannot prevent generation of non-compliant outputs. There is no mechanism to block generation when safety-critical constraints are violated.

3. **Absence of Verification Pipelines**: Existing approaches treat all graph data as equally authoritative, lacking formal workflows for expert verification of knowledge sources and learned rules.

4. **Non-Deterministic Reasoning**: Current systems cannot provide complete audit trails tracing each generated fact back to its authoritative source in the knowledge graph.

5. **Domain Coupling**: Prior implementations hardcode domain-specific logic, requiring code modifications to adapt to new domains.

### Problems Solved by the Present Invention

The present invention addresses these limitations by providing:

- A constraint enforcement mechanism that can **block generation entirely** when safety or compliance criteria are not met
- A policy-driven Guardian layer that validates constraints **before** generation begins
- An expert verification pipeline for knowledge sources with formal attestation workflows
- Deterministic reasoning chains with complete source attribution
- A domain-agnostic architecture enabling deployment across industries without code changes

---

## SUMMARY OF THE INVENTION

The present invention provides a constraint-enforced knowledge graph system comprising:

A **dual-representation knowledge graph** combining symbolic relationships with vector embeddings, enabling both semantic similarity matching and deterministic constraint validation.

A **policy evaluation engine** that activates domain-specific policies based on query analysis and validates constraints before permitting LLM generation.

A **safety-critical risk detection mechanism** employing two-level filtering (query-context and concept-relation) that blocks generation when hazardous configurations are detected.

An **expert verification pipeline** providing formal workflows for knowledge source attestation, rule confirmation, and confidence scoring.

A **reasoning chain generator** that produces deterministic audit trails tracing each output fact to its authoritative graph source.

---

## BRIEF DESCRIPTION OF THE DRAWINGS

**Figure 1**: System architecture overview showing the relationship between the Knowledge Graph, Policy Engine, Safety Detection Layer, and LLM Generation components.

**Figure 2**: Flowchart of the constraint enforcement process from query input to validated output.

**Figure 3**: Dual-representation knowledge graph structure showing symbolic nodes/relationships and vector embedding indices.

**Figure 4**: Policy evaluation workflow showing trigger matching, constraint validation, and generation gating.

**Figure 5**: Safety risk detection two-level filtering mechanism.

**Figure 6**: Expert verification pipeline for knowledge source attestation.

**Figure 7**: Reasoning chain structure with source attribution.

---

## DETAILED DESCRIPTION OF THE INVENTION

### 1. System Architecture Overview

The system comprises the following interconnected components:

#### 1.1 Dual-Representation Knowledge Graph

The knowledge graph maintains two complementary representations:

**Symbolic Layer**: A labeled property graph containing:
- Entity nodes (Products, Materials, Projects, Persons, Events)
- Typed relationships (RELATES_TO, TRIGGERS_RISK, REVEALED, PROPOSED, ADDRESSES)
- Properties with domain-specific attributes

**Vector Layer**: Dense vector embeddings associated with graph nodes, enabling:
- Semantic similarity search via approximate nearest neighbor algorithms
- Concept matching beyond exact keyword matches
- Threshold-based relevance filtering

The dual representation enables a novel two-stage retrieval process:
1. **Stage 1 (Semantic)**: Vector similarity identifies candidate concepts
2. **Stage 2 (Symbolic)**: Graph traversal extracts complete causality chains

#### 1.2 Policy Evaluation Engine

The policy engine comprises:

**Policy Definitions**: Declarative policy objects containing:
- Unique identifier and human-readable name
- Trigger conditions (keyword lists and/or regex patterns)
- Validation rules (required values, minimum/maximum thresholds)
- Priority level (critical, high, medium, low)

**Activation Mechanism**: For each incoming query:
1. Extract semantic concepts from query text
2. Match concepts against policy trigger conditions
3. Activate matching policies sorted by priority
4. Inject policy requirements into generation context

**Validation Execution**: For each active policy:
1. Search graph data for policy's check attribute
2. Apply validation rules against retrieved values
3. Generate PolicyCheckResult with pass/fail status
4. Aggregate results for generation gating decision

#### 1.3 Safety-Critical Risk Detection

The safety detection mechanism implements a novel two-level filtering approach:

**Level 1 - Query Context Analysis**:
- Analyze user query for hazard-context indicators
- Maintain configurable keyword lists for hazard domains (ATEX, explosion, chemical exposure, etc.)
- Query must contain hazard context to proceed to Level 2

**Level 2 - Concept-Relation Validation**:
- Only concepts with explicit TRIGGERS_RISK relationships activate safety responses
- High similarity threshold (≥0.75) prevents false positives
- Returns structured risk data: hazard trigger, environment, safe alternative

**Generation Blocking**:
When both filtering levels are satisfied:
- Normal LLM generation is **prevented entirely**
- System returns mandatory safety_guard response
- User must acknowledge risk before proceeding

This mechanism ensures that safety-critical constraints are enforced at the system level, not merely suggested to the LLM.

#### 1.4 Expert Verification Pipeline

The system implements a formal verification workflow for knowledge sources:

**Stage 1 - Candidate Extraction**:
- System identifies potential knowledge sources from processed documents
- Creates KnowledgeCandidate nodes with:
  - Raw extracted name
  - Inference logic explaining detection rationale
  - Supporting citation quote
  - Status: pending

**Stage 2 - Expert Review**:
- Human experts review pending candidates
- Available actions: reject, create new source, map to existing source
- Review decisions are logged with timestamp and reviewer identity

**Stage 3 - Verification and Aliasing**:
- Approved candidates become VerifiedSource nodes
- ALIASED_AS relationships enable pattern matching
- Verified sources receive confidence scores

**Rule Injection with Verification Status**:
- Verified rules are injected into generation context
- Confidence indicators distinguish: EXACT match, HIGH confidence, SEMANTIC match
- Mandatory citation requirements force LLM to reference rules

#### 1.5 Reasoning Chain Generator

The system produces deterministic reasoning chains with complete source attribution:

**Chain Structure**:
```
{
  "reasoning_chain": [
    {
      "step": "Step description",
      "source": "GRAPH|POLICY|INFERENCE",
      "node_id": "graph_node_identifier",
      "evidence_snippet": "Supporting quote from source"
    }
  ],
  "references": {
    "REF_ID": {
      "name": "Source name",
      "type": "Product|Material|Case|Policy",
      "source_document": "Original document reference"
    }
  }
}
```

**Audit Trail Properties**:
- Every generated fact links to authoritative graph source
- Inference steps are explicitly marked and justified
- Complete chain enables forensic review of any recommendation

### 2. Process Flow

#### 2.1 Query Processing

1. **Input Reception**: System receives natural language query
2. **Intent Detection**: LLM-based analysis extracts:
   - Query language
   - Entity mentions
   - Constraint requirements
   - Action intent

#### 2.2 Constraint Evaluation

3. **Safety Check**: Two-level filtering determines if safety risks present
   - If risks detected: BLOCK generation, return safety response
   - If no risks: proceed to policy evaluation

4. **Policy Activation**: Match query against policy triggers
   - Activate matching policies by priority
   - Execute validation rules against graph data

5. **Constraint Aggregation**: Combine safety and policy results
   - Determine if generation should proceed
   - Prepare constraint context for injection

#### 2.3 Knowledge Retrieval

6. **Hybrid Retrieval**: Execute dual-representation search
   - Vector similarity identifies candidate concepts
   - Graph traversal extracts causality chains
   - Merge results with deduplication

7. **Rule Injection**: Add verified rules to context
   - Match query concepts against rule triggers
   - Inject rules with confidence indicators
   - Mark mandatory citation requirements

#### 2.4 Controlled Generation

8. **Context Assembly**: Prepare generation prompt containing:
   - Retrieved knowledge with source IDs
   - Active policy requirements
   - Verified rules with citation requirements
   - Output format specifications

9. **LLM Generation**: Generate response within constraints
   - System prompt enforces citation requirements
   - Output must include reasoning chain
   - Each fact must reference source ID

10. **Validation and Output**: Verify and deliver response
    - Check all facts have source attribution
    - Package response with audit trail
    - Return structured output to user

### 3. Novel Technical Effects

The present invention achieves the following technical effects not present in prior art:

#### 3.1 Hallucination Reduction
By requiring source attribution for every fact and blocking generation when constraints are violated, the system achieves measurable reduction in unsourced or contradictory outputs.

#### 3.2 Deterministic Reproducibility
Given identical input queries and knowledge graph state, the system produces identical constraint evaluations and reasoning chains, enabling reproducible audits.

#### 3.3 Compliance Enforcement
Safety-critical and regulatory constraints are enforced at the system level, preventing LLM generation of non-compliant recommendations regardless of prompt engineering attempts.

#### 3.4 Domain Adaptability
Complete externalization of domain logic to configuration enables deployment across industries (medical, industrial, legal, financial) without code modifications.

---

## CLAIMS

### Independent Claims

**Claim 1.** A computer-implemented method for constraint-enforced language model generation, the method comprising:

(a) receiving a natural language query from a user;

(b) analyzing the query to detect safety-critical risk indicators using a two-level filtering mechanism comprising:
   (i) a first level analyzing query text for hazard-context keywords, and
   (ii) a second level validating that matched concepts have explicit risk-triggering relationships in a knowledge graph;

(c) when safety-critical risks are detected in step (b), blocking language model generation and returning a mandatory safety response;

(d) when no safety-critical risks are detected, evaluating the query against a plurality of declaratively-defined policies, each policy comprising trigger conditions and validation rules;

(e) executing a hybrid retrieval process on a dual-representation knowledge graph, the hybrid retrieval comprising:
   (i) a semantic search using vector embeddings to identify candidate concepts, and
   (ii) a symbolic traversal of graph relationships to extract causality chains;

(f) generating a response using a large language model, wherein the response is constrained to include source attributions for each stated fact; and

(g) outputting the response together with a deterministic reasoning chain tracing each fact to its authoritative source in the knowledge graph.

---

**Claim 2.** A system for constraint-enforced knowledge graph reasoning, the system comprising:

a processor; and

a non-transitory computer-readable medium storing instructions that, when executed by the processor, cause the system to:

(a) maintain a dual-representation knowledge graph comprising:
   (i) a symbolic layer of labeled nodes and typed relationships, and
   (ii) a vector layer of dense embeddings associated with graph nodes;

(b) implement a policy evaluation engine configured to:
   (i) match incoming queries against declaratively-defined policy triggers,
   (ii) execute validation rules against graph data, and
   (iii) determine whether language model generation should proceed based on validation results;

(c) implement a safety-critical risk detection mechanism configured to:
   (i) analyze queries for hazard-context indicators,
   (ii) validate risk-triggering relationships in the knowledge graph, and
   (iii) block language model generation when safety criteria are not met;

(d) generate responses using a large language model under constraints requiring source attribution for each stated fact; and

(e) produce reasoning chains providing complete audit trails from generated facts to authoritative graph sources.

---

**Claim 3.** A computer-implemented method for expert-verified knowledge source management in a knowledge graph system, the method comprising:

(a) extracting candidate knowledge sources from processed documents, each candidate comprising:
   (i) an extracted name,
   (ii) inference logic explaining detection rationale, and
   (iii) a supporting citation quote;

(b) storing candidates as pending verification nodes in a knowledge graph;

(c) presenting candidates to human experts for review;

(d) receiving expert decisions comprising one of: rejection, creation of new verified source, or mapping to existing verified source;

(e) creating verified source nodes for approved candidates with expert attestation metadata;

(f) establishing alias relationships enabling pattern matching for verified sources;

(g) injecting verified sources into language model generation context with confidence indicators distinguishing exact matches from semantic matches; and

(h) enforcing mandatory citation requirements for injected verified sources.

---

### Dependent Claims

**Claim 4.** The method of Claim 1, wherein the two-level filtering mechanism of step (b) further comprises maintaining configurable keyword lists for multiple hazard domains, the hazard domains including at least explosion risk, chemical exposure, and regulatory compliance.

**Claim 5.** The method of Claim 1, wherein the declaratively-defined policies of step (d) are stored in external configuration files, enabling domain adaptation without modification of executable code.

**Claim 6.** The method of Claim 1, wherein each policy comprises:
   (i) a unique identifier,
   (ii) a priority level selected from critical, high, medium, and low,
   (iii) trigger conditions comprising keyword lists and regular expression patterns, and
   (iv) validation rules comprising required values and numerical thresholds.

**Claim 7.** The method of Claim 1, wherein the causality chains of step (e)(ii) comprise relationships including REVEALED, PROPOSED, ADDRESSES, and RELATES_TO, enabling reconstruction of decision rationale from historical cases.

**Claim 8.** The method of Claim 1, wherein the reasoning chain of step (g) comprises, for each step:
   (i) a step description,
   (ii) a source type indicator selected from GRAPH, POLICY, and INFERENCE,
   (iii) a node identifier linking to the knowledge graph, and
   (iv) an evidence snippet quoted from the source.

**Claim 9.** The system of Claim 2, wherein the policy evaluation engine is further configured to sort activated policies by priority level and inject policy requirements into language model generation context in priority order.

**Claim 10.** The system of Claim 2, wherein the safety-critical risk detection mechanism employs a similarity threshold of at least 0.75 to prevent false positive risk detections.

**Claim 11.** The system of Claim 2, further comprising an ambiguity detection module configured to:
   (i) analyze retrieval results for attribute variance across multiple matching entities,
   (ii) identify a differentiating attribute based on variance analysis, and
   (iii) generate a clarification question targeting the identified differentiating attribute.

**Claim 12.** The method of Claim 3, wherein the confidence indicators of step (g) comprise:
   (i) EXACT, indicating direct keyword match with similarity above 0.95,
   (ii) HIGH, indicating semantic match with similarity between 0.85 and 0.95, and
   (iii) SEMANTIC, indicating conceptual match with similarity between 0.70 and 0.85.

**Claim 13.** The method of Claim 3, wherein the mandatory citation requirements of step (h) comprise instructions in a language model system prompt specifying that verified sources must appear in the first content segment of any generated response.

**Claim 14.** The method of Claim 1, further comprising:
   (h) detecting when retrieved results contain competitor product mappings in the knowledge graph; and
   (i) when competitor mappings are detected, forcing generation of a comparison response and blocking clarification requests.

**Claim 15.** The method of Claim 1, further comprising:
   (h) detecting material-environment specification mismatches by comparing requested material corrosion classes against environment requirements; and
   (i) when mismatches are detected, injecting warning content into the generated response while permitting continued generation.

---

## ABSTRACT

A constraint-enforced knowledge graph system for controlling large language model (LLM) generation through policy-driven reasoning and expert-verified knowledge sources. The system maintains a dual-representation knowledge graph combining symbolic relationships with vector embeddings. A policy evaluation engine activates domain-specific policies based on query analysis and validates constraints before permitting LLM generation. A safety-critical risk detection mechanism employing two-level filtering blocks generation entirely when hazardous configurations are detected, rather than merely providing warnings. An expert verification pipeline provides formal workflows for knowledge source attestation, rule confirmation, and confidence scoring. The system produces deterministic reasoning chains with complete source attribution, enabling forensic audit of any generated recommendation. The architecture is domain-agnostic, enabling deployment across industries through configuration changes without code modification.

---

## INVENTOR INFORMATION

[To be completed]

---

## PRIORITY CLAIM

[To be completed if claiming priority from provisional application]

---

## DOCUMENT HISTORY

- Draft Version: 1.0
- Date: January 2026
- Status: Initial Draft for Review

---

## NOTES FOR PATENT COUNSEL

### Key Differentiators from Prior Art

1. **Blocking vs Warning**: System can PREVENT generation, not just warn
2. **Two-Level Filtering**: Novel safety detection with query-context AND concept-relation validation
3. **Expert Verification Pipeline**: Formal workflow for knowledge attestation
4. **Deterministic Reasoning Chains**: Complete audit trail in every response
5. **Domain-Agnostic Architecture**: Configuration-driven, no code changes for new domains

### Recommended Search Terms for Prior Art Review

- Graph retrieval augmented generation
- Knowledge graph LLM constraint
- Safety-critical AI generation blocking
- Expert verification knowledge base
- Deterministic reasoning chain
- Policy-driven language model

### Prosecution Strategy Recommendations

1. Emphasize "blocking" mechanism in Claim 1 - this is the strongest differentiator
2. Two-level filtering is novel and specific - defend this structure
3. Expert verification pipeline (Claim 3) may be patentable independently
4. Consider divisional application for the configuration-driven architecture
