// Widget Types for Generative UI

export type WidgetType = 'diagnostic_checklist' | 'reference_case' | 'action_proposal' | 'safety_guard' | 'technical_card' | 'comparison_card';

// Data structures for each widget type
export interface DiagnosticChecklistData {
  title: string;
  items: (string | { id?: string; text?: string })[];
  email_button_label?: string;  // Optional - LLM may provide clarification_data instead
  clarification_data?: {
    parameter?: string;
    options?: Array<{ value: string; description: string }>;
  };
}

export interface ReferenceCaseData {
  project_name: string;
  symptom: string;
  root_cause: string;
  solution: string;
  link_label: string;
}

export interface ActionReasoningData {
  source_project?: string;
  trigger_event?: string;
  author?: string;
  confidence?: string;
}

export interface ActionProposalData {
  title: string;
  product_name: string;
  specs: string[];
  price_impact: string;
  is_locked: boolean;
  reasoning?: ActionReasoningData;
}

export interface SafetyGuardData {
  title: string;
  severity: 'warning' | 'critical';
  risk_description: string;
  compliance_items: string[];
  recommendation: string;
  acknowledge_label: string;
}

// Technical Card types (Generic Datasheet)
export interface TechProperty {
  label: string;
  value: string | number;
  unit?: string;
  is_estimate?: boolean;
}

export interface TechReasoningContext {
  project_ref: string;
  constraint: string;
  author: string;
  confidence_level: 'High' | 'Medium' | 'Low';
}

export interface TechCardAction {
  label: string;
  action_id: string;
  variant: 'primary' | 'outline';
}

export interface TechnicalCardData {
  title: string;
  properties: TechProperty[];
  reasoning?: TechReasoningContext;  // Optional - not always provided by LLM
  actions?: TechCardAction[];  // Optional - not always provided by LLM
}

// Comparison Card types (Competitor-to-Product Mapping)
export interface ComparisonCardData {
  title: string;
  match_type: 'direct' | 'similar' | 'partial';
  competitor: {
    name: string;
    manufacturer?: string;
  };
  our_product: {
    name: string;
    sku?: string;
    price?: string;
  };
  historical_proof?: {
    project_ref: string;
    context: string;
  };
  technical_notes?: string;
  confidence: 'High' | 'Medium';
  actions?: TechCardAction[];
}

// Widget wrapper type
export interface Widget {
  type: WidgetType;
  data: DiagnosticChecklistData | ReferenceCaseData | ActionProposalData | SafetyGuardData | TechnicalCardData | ComparisonCardData;
}

// Full bot response structure
export interface BotResponse {
  summary?: string;
  text_summary?: string;  // Legacy support
  widgets: Widget[];
}

// Type guards for widget data
export function isDiagnosticChecklist(data: Widget['data']): data is DiagnosticChecklistData {
  return 'items' in data && 'email_button_label' in data;
}

export function isReferenceCase(data: Widget['data']): data is ReferenceCaseData {
  return 'project_name' in data && 'root_cause' in data;
}

export function isActionProposal(data: Widget['data']): data is ActionProposalData {
  return 'product_name' in data && 'is_locked' in data;
}

export function isSafetyGuard(data: Widget['data']): data is SafetyGuardData {
  return 'severity' in data && 'compliance_items' in data;
}

export function isTechnicalCard(data: Widget['data']): data is TechnicalCardData {
  return 'properties' in data && 'title' in data;
}

export function isComparisonCard(data: Widget['data']): data is ComparisonCardData {
  return 'match_type' in data && 'competitor' in data && 'our_product' in data;
}
