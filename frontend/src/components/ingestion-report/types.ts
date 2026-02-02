export interface PlaybookRule {
  trigger: string;
  constraint: string;
  outcome: string;
  status: 'active' | 'review';
}

export interface Simulation {
  user_query: string;
  before_response: string;
  after_response: string;
}

export interface Expert {
  name: string;
  role: string;
  contribution: string;
}

export interface IngestionInsight {
  playbook_rule: PlaybookRule;
  simulation: Simulation;
  expert: Expert;
}

// Timeline event from extraction
export interface TimelineEvent {
  step: number;
  sender: string;
  sender_email?: string;
  date: string;
  time?: string;
  summary: string;
  logic_type: string | null;
  logic_description?: string;
  citation?: string;
  local_concepts?: string[];
}

// Extraction result from API
export interface ExtractionResult {
  project: string;
  timeline: TimelineEvent[];
  concepts: string[];
  causality: [number, string, number][];
}

/**
 * Transform extraction result into display-friendly insight
 */
export function buildInsightFromExtraction(extraction: ExtractionResult): IngestionInsight | null {
  const timeline = extraction.timeline;

  if (!timeline || timeline.length === 0) {
    return null;
  }

  // Find key events by logic type
  const symptoms = timeline.filter(e => e.logic_type === 'Symptom');
  const constraints = timeline.filter(e => e.logic_type === 'Constraint');
  const blockers = timeline.filter(e => e.logic_type === 'Blocker');
  const workarounds = timeline.filter(e => e.logic_type === 'Workaround');
  const standards = timeline.filter(e => e.logic_type === 'Standard');
  const productMappings = timeline.filter(e => e.logic_type === 'ProductMapping');
  const commercials = timeline.filter(e => e.logic_type === 'Commercial');

  // Build the trigger (problem/symptom)
  let trigger = "No initial problem identified";
  if (symptoms.length > 0) {
    trigger = symptoms[0].logic_description || symptoms[0].summary;
  } else if (timeline[0]?.summary) {
    trigger = timeline[0].summary;
  }

  // Build the constraint (limitation discovered)
  let constraint = "No constraints identified";
  if (constraints.length > 0) {
    constraint = constraints[0].logic_description || constraints[0].summary;
  } else if (blockers.length > 0) {
    constraint = blockers[0].logic_description || blockers[0].summary;
  }

  // Build the outcome (solution/action taken)
  let outcome = "No resolution recorded";
  if (workarounds.length > 0) {
    outcome = workarounds[0].logic_description || workarounds[0].summary;
  } else if (productMappings.length > 0) {
    outcome = productMappings[0].logic_description || productMappings[0].summary;
  } else if (commercials.length > 0) {
    // Commercial data is valuable - include the exact numbers
    outcome = commercials[0].logic_description || commercials[0].summary;
  } else if (standards.length > 0) {
    outcome = standards[0].logic_description || standards[0].summary;
  }

  // Find the expert (person who proposed the solution)
  let expertName = "Unknown";
  let expertRole = "Sales Engineer";
  let expertContribution = outcome;

  const solutionEvent = workarounds[0] || productMappings[0] || commercials[0] || standards[0];
  if (solutionEvent) {
    expertName = solutionEvent.sender;
    expertContribution = solutionEvent.logic_description || solutionEvent.summary;
  }

  // Build simulation based on actual content
  const concepts = extraction.concepts || [];
  const conceptsStr = concepts.slice(0, 3).join(", ");

  const userQuery = constraints.length > 0
    ? `Customer has a situation involving: ${conceptsStr || trigger}`
    : `Question about ${conceptsStr || extraction.project}`;

  const beforeResponse = `I don't have specific information about this scenario. Let me check our general catalog...`;

  const afterResponse = outcome !== "No resolution recorded"
    ? `Based on ${extraction.project}: ${outcome}`
    : `Now aware of ${extraction.project} case with ${timeline.length} documented events.`;

  return {
    playbook_rule: {
      trigger: truncate(trigger, 80),
      constraint: truncate(constraint, 80),
      outcome: truncate(outcome, 80),
      status: 'active',
    },
    simulation: {
      user_query: truncate(userQuery, 100),
      before_response: beforeResponse,
      after_response: truncate(afterResponse, 200),
    },
    expert: {
      name: expertName,
      role: expertRole,
      contribution: truncate(expertContribution, 80),
    },
  };
}

function truncate(str: string, maxLen: number): string {
  if (str.length <= maxLen) return str;
  return str.substring(0, maxLen - 3) + "...";
}
