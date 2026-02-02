"use client";

import { useState } from "react";
import { ChevronDown, Database, Brain, Shield, Filter, CheckCircle2, Package, AlertTriangle, FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";

// =============================================================================
// TYPES - Matching backend DeepExplainableResponse
// =============================================================================

export interface ReasoningSummaryStep {
  step: string;
  icon: string;
  description: string;
}

export interface ContentSegment {
  text: string;
  type: "GENERAL" | "INFERENCE" | "GRAPH_FACT";
  inference_logic?: string;
  source_id?: string;
  source_text?: string;
  // Rich evidence fields for GRAPH_FACT
  node_type?: string;
  evidence_snippet?: string;
  source_document?: string;
  page_number?: number;
  key_specs?: Record<string, string>;
}

export interface ProductCard {
  title: string;
  specs: Record<string, string>;
  warning?: string;
  confidence: string;
  actions: string[];
}

export interface ClarificationOption {
  value: string;
  description: string;
}

export interface ClarificationRequest {
  missing_info: string;
  why_needed: string;
  options: ClarificationOption[];
  question: string;
}

export interface DeepExplainableResponseData {
  reasoning_summary: ReasoningSummaryStep[];
  content_segments: ContentSegment[];
  product_card?: ProductCard;
  // Autonomous Guardian - Risk Detection
  risk_detected?: boolean;
  risk_severity?: "CRITICAL" | "WARNING" | "INFO" | null;
  risk_resolved?: boolean;
  // Clarification Mode
  clarification_needed?: boolean;
  clarification?: ClarificationRequest;
  query_language: string;
  confidence_level: "high" | "medium" | "low";
  policy_warnings: string[];
  graph_facts_count: number;
  inference_count: number;
}

// Type for selected detail in the side panel
export interface SelectedDetail {
  type: "source" | "inference";
  sourceId?: string;
  sourceText?: string;
  inferenceLogic?: string;
  // Rich evidence fields for source type
  nodeType?: string;
  evidenceSnippet?: string;
  sourceDocument?: string;
  pageNumber?: number;
  keySpecs?: Record<string, string>;
}

// Legacy types for backwards compatibility
export interface ReasoningStepData {
  step: string;
  source: "GRAPH" | "LLM" | "POLICY" | "FILTER";
  node_id?: string;
  confidence: "high" | "medium" | "low";
}

export interface ReferenceDetail {
  name: string;
  type: string;
  source_doc: string;
  confidence: "verified" | "inferred";
}

export interface ExplainableResponseData {
  reasoning_chain: ReasoningStepData[];
  reasoning_steps?: string[];
  final_answer_markdown: string;
  references: Record<string, ReferenceDetail>;
  query_language: string;
  confidence_level: "high" | "medium" | "low";
  policy_warnings: string[];
  graph_facts_count: number;
  llm_inferences_count: number;
}

// =============================================================================
// UI COMPONENT 1: THINKING TIMELINE
// =============================================================================

interface ThinkingTimelineProps {
  steps: ReasoningSummaryStep[];
  defaultCollapsed?: boolean;
}

export function ThinkingTimeline({ steps, defaultCollapsed = true }: ThinkingTimelineProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  if (!steps || steps.length === 0) return null;

  return (
    <div className="mb-4">
      {/* Subtle Header Button */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="group flex items-center gap-2 text-xs text-slate-500 hover:text-slate-700 transition-colors py-1"
      >
        <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-slate-100 group-hover:bg-slate-200 transition-colors">
          <Brain className="w-3 h-3 text-violet-500" />
          <span className="font-medium">AI Process</span>
          <span className="text-slate-400">·</span>
          <span>{steps.length} steps</span>
        </div>
        <ChevronDown
          className={cn(
            "w-3.5 h-3.5 text-slate-400 transition-transform",
            collapsed ? "-rotate-90" : ""
          )}
        />
      </button>

      {/* Collapsible Timeline */}
      {!collapsed && (
        <div className="mt-3 ml-1 pl-4 border-l-2 border-slate-100 space-y-3">
          {steps.map((step, idx) => (
            <div key={idx} className="relative">
              {/* Step indicator dot */}
              <div className="absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full bg-white border-2 border-slate-300" />

              {/* Content */}
              <div className="text-xs text-slate-500 font-medium uppercase tracking-wide flex items-center gap-1.5">
                <span>{step.icon}</span>
                <span>{step.step}</span>
              </div>
              <p className="mt-0.5 text-sm text-slate-600 leading-relaxed">
                {step.description}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// UI COMPONENT 2: EXPLAINABLE CHAT BUBBLE (Perplexity Style)
// =============================================================================

interface ExplainableChatBubbleProps {
  segments: ContentSegment[];
  expertMode: boolean;
  selectedDetailIdx?: number | null;
  onSelectDetail?: (detail: SelectedDetail, idx: number) => void;
  onConfirmInference?: (inferenceLogic: string, contextText: string) => Promise<void>;
  confirmedInferences?: Set<number>;  // Track which inferences have been confirmed
}

// Parse source text into structured key-value pairs
function parseSourceText(text: string): { key: string; value: string }[] {
  if (!text) return [];

  // Known field patterns to look for
  const fieldPatterns = [
    'Product:', 'Family:', 'Dimensions:', 'Cartridge Capacity:', 'Special:',
    'Adjustable Length:', 'Features:', 'Materials:', 'Length:', 'Width:',
    'Height:', 'Depth:', 'Airflow:', 'Options:', 'Insulation:', 'Type:',
    'Series:', 'Model:', 'Corrosion Class:', 'Standard Length:'
  ];

  const result: { key: string; value: string }[] = [];

  // Find each field and extract its value
  for (const pattern of fieldPatterns) {
    const patternIndex = text.indexOf(pattern);

    if (patternIndex !== -1) {
      // Find where the next field starts
      let nextFieldIndex = text.length;
      for (const nextPattern of fieldPatterns) {
        if (nextPattern === pattern) continue;
        const idx = text.indexOf(nextPattern, patternIndex + pattern.length);
        if (idx !== -1 && idx < nextFieldIndex) {
          nextFieldIndex = idx;
        }
      }

      const key = pattern.replace(':', '');
      const value = text.substring(patternIndex + pattern.length, nextFieldIndex).trim();

      if (value) {
        result.push({ key, value });
      }
    }
  }

  // If no patterns matched, return the whole text as a single entry
  if (result.length === 0 && text.trim()) {
    result.push({ key: 'Info', value: text.trim() });
  }

  return result;
}

// Source Citation Badge - Clickable chip at end of GRAPH_FACT
function SourceCitation({
  sourceId,
  sourceText,
  isSelected,
  onClick,
}: {
  sourceId?: string;
  sourceText?: string;
  isSelected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[11px] font-medium rounded cursor-pointer transition-colors ml-0.5",
        isSelected
          ? "text-white bg-emerald-600 border border-emerald-600"
          : "text-emerald-700 bg-emerald-50 border border-emerald-200 hover:bg-emerald-100"
      )}
    >
      <Database className="w-2.5 h-2.5" />
      <span>Source</span>
    </button>
  );
}

// Inference Badge - Clickable indicator for AI reasoning
function InferenceBadge({
  isSelected,
  onClick,
}: {
  isSelected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[11px] font-medium rounded cursor-pointer transition-colors ml-0.5",
        isSelected
          ? "text-white bg-amber-600 border border-amber-600"
          : "text-amber-700 bg-amber-50 border border-amber-200 hover:bg-amber-100"
      )}
    >
      <Brain className="w-2.5 h-2.5" />
      <span>AI</span>
    </button>
  );
}

// Helper to render text with inline markdown formatting (bold, newlines, bullets)
function renderFormattedText(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let key = 0;

  // Split by newlines first
  const lines = text.split('\n');

  lines.forEach((line, lineIdx) => {
    if (lineIdx > 0) {
      // Add line break between lines
      parts.push(<br key={`br-${key++}`} />);
    }

    // Handle bold text **text**
    const boldParts = line.split(/(\*\*[^*]+\*\*)/g);
    boldParts.forEach((part) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        // Bold text
        parts.push(
          <strong key={`b-${key++}`} className="font-semibold text-slate-900">
            {part.slice(2, -2)}
          </strong>
        );
      } else if (part) {
        // Check for bullet points
        if (part.startsWith('• ') || part.startsWith('- ')) {
          parts.push(
            <span key={`bullet-${key++}`} className="inline-block ml-2">
              {part}
            </span>
          );
        } else {
          parts.push(<span key={`t-${key++}`}>{part}</span>);
        }
      }
    });
  });

  return parts;
}

export function ExplainableChatBubble({
  segments,
  expertMode,
  selectedDetailIdx,
  onSelectDetail,
  onConfirmInference,
  confirmedInferences = new Set(),
}: ExplainableChatBubbleProps) {
  if (!segments || segments.length === 0) return null;

  // Check if content has complex markdown (headers, code blocks)
  const hasComplexMarkdown = segments.some(seg =>
    seg.text.includes('##') ||
    seg.text.includes('```') ||
    seg.text.includes('|') // tables
  );

  // For complex markdown without expert mode, use full ReactMarkdown
  if (hasComplexMarkdown && !expertMode) {
    const fullText = segments.map(s => s.text).join('');
    return (
      <div className="prose prose-sm prose-slate max-w-none">
        <ReactMarkdown>{fullText}</ReactMarkdown>
      </div>
    );
  }

  // Helper to add space before segment if needed
  const needsSpaceBefore = (text: string, prevText?: string): boolean => {
    if (!prevText) return false;
    const startsWithPunctuation = /^[.,;:!?)}\]'"»\n•\-]/.test(text);
    const prevEndsWithSpace = /\s$/.test(prevText);
    const prevEndsWithOpenBracket = /[(\[{«'"']$/.test(prevText);
    const prevEndsWithNewline = /\n$/.test(prevText);
    return !startsWithPunctuation && !prevEndsWithSpace && !prevEndsWithOpenBracket && !prevEndsWithNewline;
  };

  return (
    <div
      className="text-sm text-gray-800"
      style={{
        lineHeight: '1.75',        // Line height for readability
        whiteSpace: 'pre-wrap',    // Preserve newlines from backend
      }}
    >
      {segments.map((segment, idx) => {
        const isSelected = selectedDetailIdx === idx;
        const prevSegment = idx > 0 ? segments[idx - 1] : null;
        const addSpace = needsSpaceBefore(segment.text, prevSegment?.text);

        // GRAPH_FACT: Solid emerald underline - clickable text
        if (segment.type === "GRAPH_FACT" && expertMode) {
          return (
            <span key={idx}>
              {addSpace && ' '}
              <span
                onClick={() => onSelectDetail?.({
                  type: "source",
                  sourceId: segment.source_id,
                  sourceText: segment.source_text,
                  nodeType: segment.node_type,
                  evidenceSnippet: segment.evidence_snippet,
                  sourceDocument: segment.source_document,
                  pageNumber: segment.page_number,
                  keySpecs: segment.key_specs,
                }, idx)}
                className={cn(
                  "cursor-pointer transition-colors pb-0.5",
                  isSelected
                    ? "bg-emerald-100"
                    : "hover:bg-emerald-50"
                )}
                style={{
                  textDecoration: "underline",
                  textDecorationStyle: "solid",
                  textDecorationColor: isSelected ? "#059669" : "#10b981",
                  textDecorationThickness: "2px",
                  textUnderlineOffset: "4px",
                  textDecorationSkipInk: "none",
                }}
              >
                {renderFormattedText(segment.text)}
              </span>
            </span>
          );
        }

        // INFERENCE: Dashed amber underline - clickable text (green solid if confirmed)
        if (segment.type === "INFERENCE" && expertMode) {
          const isConfirmed = confirmedInferences.has(idx);

          // Get surrounding context for the rule
          const getContextText = () => {
            // Get previous GENERAL segments for context
            const contextParts: string[] = [];
            for (let i = Math.max(0, idx - 3); i < idx; i++) {
              if (segments[i]?.type === "GENERAL") {
                contextParts.push(segments[i].text.trim());
              }
            }
            return contextParts.join(" ").slice(-100) || "General context";
          };

          return (
            <span key={idx}>
              {addSpace && ' '}
              <span
                onClick={() => onSelectDetail?.({
                  type: "inference",
                  inferenceLogic: segment.inference_logic,
                }, idx)}
                className={cn(
                  "cursor-pointer transition-colors",
                  isConfirmed
                    ? "bg-emerald-50"
                    : isSelected
                      ? "bg-amber-100"
                      : "hover:bg-amber-50"
                )}
                style={{
                  textDecoration: "underline",
                  textDecorationStyle: isConfirmed ? "solid" : "dashed",
                  textDecorationColor: isConfirmed
                    ? "#10b981"
                    : isSelected
                      ? "#d97706"
                      : "#fbbf24",
                  textDecorationThickness: "2px",
                  textUnderlineOffset: "3px",
                  textDecorationSkipInk: "none",
                }}
              >
                {renderFormattedText(segment.text)}
              </span>
              {/* Confirm button - only show if not yet confirmed */}
              {!isConfirmed && onConfirmInference && segment.inference_logic && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onConfirmInference(segment.inference_logic!, getContextText());
                  }}
                  className="inline-flex items-center justify-center w-4 h-4 ml-0.5 align-baseline text-amber-500 hover:text-emerald-600 hover:bg-emerald-50 rounded transition-colors"
                  title="Confirm this inference as a rule"
                >
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </button>
              )}
              {/* Show confirmed badge */}
              {isConfirmed && (
                <span className="inline-flex items-center justify-center w-4 h-4 ml-0.5 align-baseline text-emerald-600" title="Rule confirmed">
                  <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                  </svg>
                </span>
              )}
            </span>
          );
        }

        // GENERAL or non-expert mode: Plain text with formatting
        return (
          <span key={idx}>
            {addSpace && ' '}
            {renderFormattedText(segment.text)}
          </span>
        );
      })}
    </div>
  );
}

// =============================================================================
// UI COMPONENT 3: PRODUCT CARD
// =============================================================================

interface ProductCardComponentProps {
  card: ProductCard;
  onAction?: (action: string) => void;
  riskSeverity?: "CRITICAL" | "WARNING" | "INFO" | null;
}

export function ProductCardComponent({ card, onAction, riskSeverity }: ProductCardComponentProps) {
  // Don't render if no meaningful specs
  const hasSpecs = card.specs && Object.keys(card.specs).length > 0;
  if (!hasSpecs && !card.warning) {
    return null;
  }

  const isCritical = riskSeverity === "CRITICAL";
  const isWarning = riskSeverity === "WARNING";

  return (
    <div className={cn(
      "mt-4 rounded-xl border overflow-hidden",
      isCritical
        ? "border-red-300 bg-red-50/30"
        : isWarning
          ? "border-amber-200 bg-amber-50/20"
          : "border-slate-200 bg-white"
    )}>
      {/* Header - Red for CRITICAL */}
      <div className={cn(
        "px-4 py-3 border-b",
        isCritical
          ? "bg-red-600 border-red-600"
          : isWarning
            ? "bg-amber-50 border-amber-100"
            : "border-slate-100"
      )}>
        <div className="flex items-center gap-2.5">
          <div className={cn(
            "w-8 h-8 rounded-lg flex items-center justify-center",
            isCritical
              ? "bg-red-500"
              : isWarning
                ? "bg-amber-100"
                : "bg-blue-50"
          )}>
            {isCritical ? (
              <AlertTriangle className="w-4 h-4 text-white" />
            ) : (
              <Package className={cn("w-4 h-4", isWarning ? "text-amber-600" : "text-blue-600")} />
            )}
          </div>
          <div className="flex-1">
            <h4 className={cn(
              "font-semibold",
              isCritical ? "text-white" : "text-slate-800"
            )}>
              {isCritical && "⚠️ "}{card.title}
            </h4>
            {isCritical && (
              <p className="text-xs text-red-100 mt-0.5">Not recommended for this application</p>
            )}
          </div>
          {!isCritical && card.confidence === "high" && (
            <span className="px-2 py-0.5 bg-emerald-50 text-emerald-600 text-[11px] font-medium rounded border border-emerald-100">
              Verified
            </span>
          )}
          {isCritical && (
            <span className="px-2 py-0.5 bg-red-500 text-white text-[11px] font-bold rounded">
              UNSUITABLE
            </span>
          )}
        </div>
      </div>

      {/* Specs Grid */}
      <div className="p-4">
        <div className="grid grid-cols-2 gap-x-4 gap-y-3">
          {Object.entries(card.specs).map(([key, value]) => (
            <div key={key}>
              <span className="text-[11px] text-slate-400 uppercase tracking-wide">{key}</span>
              <p className="text-sm text-slate-700 font-medium mt-0.5">{value}</p>
            </div>
          ))}
        </div>

        {/* Warning - Subtle */}
        {card.warning && (
          <div className="mt-4 flex items-start gap-2.5 px-3 py-2.5 bg-amber-50/50 border border-amber-200 rounded-lg">
            <div className="w-5 h-5 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
              <AlertTriangle className="w-3 h-3 text-amber-600" />
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">{card.warning}</p>
          </div>
        )}

        {/* Actions - Different for CRITICAL risks */}
        <div className="mt-4 flex gap-2">
          {isCritical ? (
            <>
              <button
                onClick={() => onAction?.("View Safer Alternative")}
                className="flex-1 px-4 py-2.5 rounded-lg text-sm font-semibold bg-emerald-600 text-white hover:bg-emerald-700 transition-all"
              >
                🛡️ View Safer Alternative
              </button>
              <button
                onClick={() => onAction?.("Acknowledge Risk")}
                className="px-4 py-2.5 rounded-lg text-sm font-medium bg-white text-red-600 border-2 border-red-300 hover:bg-red-50 transition-all"
              >
                I Accept Risk
              </button>
            </>
          ) : card.actions && card.actions.length > 0 ? (
            card.actions.map((action, idx) => (
              <button
                key={idx}
                onClick={() => onAction?.(action)}
                className={cn(
                  "px-4 py-2 rounded-lg text-sm font-medium transition-all",
                  idx === 0
                    ? "bg-slate-900 text-white hover:bg-slate-800"
                    : "bg-white text-slate-600 border border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                )}
              >
                {action}
              </button>
            ))
          ) : null}
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// EXPERT MODE TOGGLE
// =============================================================================

interface ExpertModeToggleProps {
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}

export function ExpertModeToggle({ enabled, onToggle }: ExpertModeToggleProps) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-slate-500">Expert Mode</span>
      <button
        onClick={() => onToggle(!enabled)}
        className={cn(
          "relative w-10 h-5 rounded-full transition-colors",
          enabled ? "bg-emerald-500" : "bg-slate-300"
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform",
            enabled ? "translate-x-5" : "translate-x-0.5"
          )}
        />
      </button>
      <span className={cn("text-xs", enabled ? "text-emerald-600" : "text-slate-400")}>
        {enabled ? "Show sources" : "Hide"}
      </span>
    </div>
  );
}

// =============================================================================
// CONFIDENCE INDICATOR
// =============================================================================

interface ConfidenceIndicatorProps {
  level: "high" | "medium" | "low";
  graphFacts: number;
  inferences: number;
}

// =============================================================================
// COMPLIANCE CONFIRMATION BADGE (Risk Resolved)
// =============================================================================

export function ComplianceBadge() {
  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-emerald-50 border border-emerald-200 rounded-lg mt-3">
      <div className="w-5 h-5 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0">
        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
      </div>
      <p className="text-xs font-medium text-emerald-700">
        Risk addressed — recommended configuration meets application requirements
      </p>
    </div>
  );
}

export function ConfidenceIndicator({ level, graphFacts, inferences }: ConfidenceIndicatorProps) {
  return (
    <div className="flex items-center flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-400 mt-4">
      {/* Graph Facts Badge */}
      {graphFacts > 0 && (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-600 border border-emerald-100">
          <Database className="w-3 h-3" />
          <span>{graphFacts} graph {graphFacts === 1 ? "fact" : "facts"}</span>
        </span>
      )}
      {/* Inferences Badge */}
      {inferences > 0 && (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-50 text-amber-600 border border-amber-100">
          <Brain className="w-3 h-3" />
          <span>{inferences} AI {inferences === 1 ? "inference" : "inferences"}</span>
        </span>
      )}
      {/* Confidence indicator - only if we have data */}
      {(graphFacts > 0 || inferences > 0) && (
        <span className="text-slate-400">
          · Confidence: <span className={cn(
            "font-medium",
            level === "high" ? "text-emerald-600" : level === "medium" ? "text-amber-600" : "text-red-500"
          )}>
            {level === "high" ? "high" : level === "medium" ? "medium" : "low"}
          </span>
        </span>
      )}
    </div>
  );
}

// =============================================================================
// POLICY WARNING
// =============================================================================

interface PolicyWarningProps {
  warning: string;
}

export function PolicyWarning({ warning }: PolicyWarningProps) {
  return (
    <div className="flex items-start gap-2.5 px-3 py-2.5 border border-amber-200 bg-amber-50/50 rounded-lg mt-3">
      <div className="w-5 h-5 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
        <AlertTriangle className="w-3 h-3 text-amber-600" />
      </div>
      <p className="text-xs text-slate-600 leading-relaxed">{warning}</p>
    </div>
  );
}

// =============================================================================
// RISK DETECTED BANNER (Autonomous Guardian) - Perplexity Style
// =============================================================================

interface RiskDetectedBannerProps {
  warnings: string[];
  severity?: "CRITICAL" | "WARNING" | "INFO" | null;
}

export function RiskDetectedBanner({ warnings, severity }: RiskDetectedBannerProps) {
  if (!warnings || warnings.length === 0) return null;

  const isCritical = severity === "CRITICAL";
  const isWarning = severity === "WARNING";

  return (
    <div className={cn(
      "mb-4 border rounded-lg px-4 py-3",
      isCritical
        ? "border-red-300 border-l-4 border-l-red-600 bg-red-50"
        : isWarning
          ? "border-amber-200 border-l-4 border-l-amber-500 bg-amber-50/50"
          : "border-red-200 border-l-4 border-l-red-500 bg-red-50/50"
    )}>
      <div className={cn(
        "flex items-start gap-2.5",
        isCritical ? "text-red-900" : isWarning ? "text-amber-800" : "text-red-800"
      )}>
        <AlertTriangle className={cn(
          "w-5 h-5 flex-shrink-0 mt-0.5",
          isCritical && "text-red-600"
        )} />
        <div className="flex-1">
          {isCritical && (
            <div className="font-bold text-red-700 mb-1 text-sm uppercase tracking-wide">
              ⛔ Critical Engineering Risk
            </div>
          )}
          <p className="text-sm leading-relaxed">{warnings.join(" ")}</p>
          {isCritical && (
            <div className="mt-3 flex gap-2">
              <button className="px-3 py-1.5 bg-red-600 text-white text-xs font-semibold rounded-md hover:bg-red-700 transition-colors">
                View Safer Alternative
              </button>
              <button className="px-3 py-1.5 bg-white text-red-700 text-xs font-semibold rounded-md border border-red-300 hover:bg-red-50 transition-colors">
                I Acknowledge the Risk
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// CLARIFICATION CARD (Missing Parameters)
// =============================================================================

interface ClarificationCardProps {
  clarification: ClarificationRequest;
  onOptionSelect?: (value: string, description: string) => void;
}

export function ClarificationCard({ clarification, onOptionSelect }: ClarificationCardProps) {
  const [showCustomInput, setShowCustomInput] = useState(false);
  const [customValue, setCustomValue] = useState("");

  const handleCustomSubmit = () => {
    if (customValue.trim()) {
      onOptionSelect?.(customValue.trim(), "Custom value");
      setCustomValue("");
      setShowCustomInput(false);
    }
  };

  return (
    <div className="border-l-2 border-blue-400 pl-4 py-2">
      {/* Question */}
      <p className="text-sm font-semibold text-slate-800 mb-0.5">{clarification.question}</p>

      {/* Subtle reason */}
      <p className="text-xs text-slate-400 mb-3">{clarification.why_needed}</p>

      {/* Horizontal Action Chips */}
      <div className="flex flex-wrap gap-2">
        {clarification.options && clarification.options.map((option, idx) => (
          <button
            key={idx}
            onClick={() => onOptionSelect?.(option.value, option.description)}
            className="px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-200 rounded-full hover:bg-blue-50 hover:border-blue-400 hover:text-blue-700 active:bg-blue-100 transition-all shadow-sm"
            title={option.description}
          >
            {option.value}
            {option.description && <span className="text-slate-400 font-normal"> · {option.description}</span>}
          </button>
        ))}

        {/* Custom Input Toggle */}
        {!showCustomInput ? (
          <button
            onClick={() => setShowCustomInput(true)}
            className="px-4 py-2 text-sm font-medium text-slate-400 bg-white border border-dashed border-slate-300 rounded-full hover:bg-slate-50 hover:border-slate-400 hover:text-slate-600 transition-all"
          >
            Other...
          </button>
        ) : (
          <div className="flex items-center gap-2 w-full mt-1">
            <input
              type="text"
              value={customValue}
              onChange={(e) => setCustomValue(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCustomSubmit()}
              placeholder="Enter value..."
              className="flex-1 px-3 py-2 text-sm border border-slate-300 rounded-full focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400"
              autoFocus
            />
            <button
              onClick={handleCustomSubmit}
              disabled={!customValue.trim()}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-full hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed transition-colors"
            >
              OK
            </button>
            <button
              onClick={() => { setShowCustomInput(false); setCustomValue(""); }}
              className="text-sm text-slate-400 hover:text-slate-600 px-1"
            >
              ✕
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// =============================================================================
// DETAIL PANEL (Right Side Panel for Source/Inference Details)
// =============================================================================

interface DetailPanelProps {
  detail: SelectedDetail | null;
  onClose: () => void;
  onConfirmInference?: (inferenceLogic: string, contextText: string) => Promise<void>;
  isConfirmed?: boolean;
}

export function DetailPanel({ detail, onClose, onConfirmInference, isConfirmed }: DetailPanelProps) {
  const parsedData = detail?.sourceText ? parseSourceText(detail.sourceText) : [];

  if (!detail) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center p-6">
        <div className="w-12 h-12 rounded-xl bg-slate-100 flex items-center justify-center mb-3">
          <Database className="w-6 h-6 text-slate-400" />
        </div>
        <h4 className="font-medium text-slate-600 mb-1">No Selection</h4>
        <p className="text-xs text-slate-400 max-w-[220px] leading-relaxed">
          Click on <span className="border-b-2 border-emerald-500 text-emerald-600">underlined text</span> to see its data source, or{" "}
          <span className="border-b-2 border-dashed border-amber-400 text-amber-600">dashed text</span> to see AI reasoning.
        </p>
      </div>
    );
  }

  if (detail.type === "source") {
    const hasKeySpecs = detail.keySpecs && Object.keys(detail.keySpecs).length > 0;
    const hasEvidence = detail.evidenceSnippet && detail.evidenceSnippet.trim().length > 0;

    return (
      <div className="h-full flex flex-col">
        {/* Header with Node Name and Type Badge */}
        <div className="flex items-center justify-between p-4 border-b border-slate-100">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <div className="w-8 h-8 rounded-lg bg-emerald-100 flex items-center justify-center flex-shrink-0">
              <Database className="w-4 h-4 text-emerald-600" />
            </div>
            <div className="min-w-0 flex-1">
              <h4 className="font-semibold text-slate-800 text-sm truncate">
                {detail.sourceId || "Data Source"}
              </h4>
              {detail.nodeType && (
                <span className="inline-flex items-center px-1.5 py-0.5 mt-0.5 text-[10px] font-medium bg-emerald-50 text-emerald-700 rounded">
                  {detail.nodeType}
                </span>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors flex-shrink-0"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4 space-y-4">
          {/* Evidence Section */}
          {hasEvidence && (
            <div>
              <span className="text-[10px] text-slate-400 font-medium uppercase tracking-wide block mb-2">
                Evidence
              </span>
              <blockquote className="px-3 py-2 bg-emerald-50/50 border-l-2 border-emerald-400 rounded-r-lg">
                <p className="text-sm text-slate-700 italic leading-relaxed">
                  "{detail.evidenceSnippet}"
                </p>
              </blockquote>
            </div>
          )}

          {/* Key Specs Section */}
          {hasKeySpecs && (
            <div>
              <span className="text-[10px] text-slate-400 font-medium uppercase tracking-wide block mb-2">
                Key Specifications
              </span>
              <div className="bg-slate-50 rounded-lg p-3 space-y-2">
                {Object.entries(detail.keySpecs!).map(([key, value]) => (
                  <div key={key} className="flex justify-between items-center">
                    <span className="text-xs text-slate-500">{key}</span>
                    <span className="text-xs font-medium text-slate-800">{value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Source Section - shows document or node info */}
          {(detail.sourceDocument || detail.sourceId) && (
            <div>
              <span className="text-[10px] text-slate-400 font-medium uppercase tracking-wide block mb-2">
                Source
              </span>
              <div className="flex items-start gap-2 bg-blue-50/50 rounded-lg p-3">
                <FileText className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
                <div className="min-w-0">
                  {detail.sourceDocument ? (
                    <>
                      <p className="text-sm text-slate-700 font-medium truncate">
                        {detail.sourceDocument}
                      </p>
                      {detail.pageNumber && (
                        <p className="text-xs text-slate-500 mt-0.5">
                          Page {detail.pageNumber}
                        </p>
                      )}
                    </>
                  ) : (
                    <>
                      <p className="text-sm text-slate-700 font-medium truncate">
                        Knowledge Graph
                      </p>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Node: {detail.sourceId}
                        {detail.nodeType && ` (${detail.nodeType})`}
                      </p>
                    </>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Fallback: Legacy parsed data or verification message */}
          {!hasEvidence && !hasKeySpecs && (
            <div className="space-y-3">
              {parsedData.length > 0 ? (
                parsedData.map((item, idx) => (
                  <div key={idx}>
                    <span className="text-[10px] text-slate-400 font-medium uppercase tracking-wide block mb-0.5">
                      {item.key}
                    </span>
                    <span className="text-sm text-slate-700">{item.value}</span>
                  </div>
                ))
              ) : (
                <div className="text-center py-4">
                  <CheckCircle2 className="w-8 h-8 text-emerald-400 mx-auto mb-2" />
                  <p className="text-sm text-slate-500">
                    Verified against Knowledge Graph
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer: Source Reference */}
        {(detail.sourceDocument || detail.sourceId) && (
          <div className="p-3 border-t border-slate-100 bg-slate-50/50">
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span>
                {detail.sourceDocument
                  ? `${detail.sourceDocument}${detail.pageNumber ? ` • p.${detail.pageNumber}` : ''}`
                  : `KG: ${detail.sourceId}${detail.nodeType ? ` (${detail.nodeType})` : ''}`
                }
              </span>
            </div>
          </div>
        )}
      </div>
    );
  }

  // Inference detail
  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <div className={cn(
            "w-8 h-8 rounded-lg flex items-center justify-center",
            isConfirmed ? "bg-emerald-100" : "bg-amber-100"
          )}>
            {isConfirmed ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            ) : (
              <Brain className="w-4 h-4 text-amber-600" />
            )}
          </div>
          <div>
            <h4 className="font-semibold text-slate-800 text-sm">
              {isConfirmed ? "Verified Rule" : "AI Inference"}
            </h4>
            <p className="text-[10px] text-slate-400">
              {isConfirmed ? "Confirmed by Expert" : "Reasoning Explanation"}
            </p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        <div className={cn(
          "p-3 border rounded-lg",
          isConfirmed
            ? "bg-emerald-50 border-emerald-100"
            : "bg-amber-50 border-amber-100"
        )}>
          <p className="text-sm text-slate-700 leading-relaxed">
            {detail.inferenceLogic || "This statement is based on AI engineering knowledge and reasoning, not directly from the knowledge graph."}
          </p>
        </div>

        {/* Confirm button - only show if not confirmed and callback exists */}
        {!isConfirmed && onConfirmInference && detail.inferenceLogic && (
          <button
            onClick={() => onConfirmInference(detail.inferenceLogic!, "Context from conversation")}
            className="mt-4 w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            <CheckCircle2 className="w-4 h-4" />
            Confirm as Verified Rule
          </button>
        )}

        {/* Confirmed badge */}
        {isConfirmed && (
          <div className="mt-4 p-3 bg-emerald-50 border border-emerald-200 rounded-lg">
            <div className="flex items-start gap-2">
              <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
              <div>
                <p className="text-sm font-medium text-emerald-800">Rule Learned!</p>
                <p className="text-xs text-emerald-600 mt-0.5">
                  This inference has been saved to the Knowledge Graph. Future queries will use this rule automatically.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Info box - only show if not confirmed */}
        {!isConfirmed && (
          <div className="mt-4 p-3 bg-slate-50 border border-slate-100 rounded-lg">
            <div className="flex items-start gap-2">
              <div className="w-5 h-5 rounded-full bg-slate-200 flex items-center justify-center flex-shrink-0 mt-0.5">
                <span className="text-[10px]">💡</span>
              </div>
              <p className="text-xs text-slate-500">
                AI inferences are derived from the model's training data and general engineering principles.
                Click "Confirm" to save this as a verified rule for future queries.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// =============================================================================
// LEGACY COMPONENTS (for backwards compatibility)
// =============================================================================

const SOURCE_CONFIG = {
  GRAPH: {
    icon: Database,
    label: "GRAPH",
    bgColor: "bg-emerald-50",
    borderColor: "border-l-emerald-500",
    iconColor: "text-emerald-600",
    badgeColor: "bg-emerald-100 text-emerald-700",
  },
  LLM: {
    icon: Brain,
    label: "LLM",
    bgColor: "bg-slate-50",
    borderColor: "border-l-slate-400",
    iconColor: "text-slate-500",
    badgeColor: "bg-slate-200 text-slate-600",
  },
  POLICY: {
    icon: Shield,
    label: "POLICY",
    bgColor: "bg-amber-50",
    borderColor: "border-l-amber-500",
    iconColor: "text-amber-600",
    badgeColor: "bg-amber-100 text-amber-700",
  },
  FILTER: {
    icon: Filter,
    label: "FILTER",
    bgColor: "bg-indigo-50",
    borderColor: "border-l-indigo-500",
    iconColor: "text-indigo-600",
    badgeColor: "bg-indigo-100 text-indigo-700",
  },
};

interface ReasoningChainProps {
  chain: ReasoningStepData[];
  graphCount: number;
  llmCount: number;
  defaultCollapsed?: boolean;
}

export function ReasoningChain({
  chain,
  graphCount,
  llmCount,
  defaultCollapsed = false,
}: ReasoningChainProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  if (!chain || chain.length === 0) return null;

  return (
    <div className="rounded-xl border border-slate-200 overflow-hidden mb-3">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center gap-2 px-3 py-2.5 bg-gradient-to-r from-slate-50 to-slate-100 hover:from-slate-100 hover:to-slate-150 transition-colors"
      >
        <Brain className="w-4 h-4 text-violet-600" />
        <span className="text-xs font-semibold text-slate-700">
          Reasoning Process ({chain.length} steps)
        </span>
        <div className="flex items-center gap-3 ml-2">
          <span className="flex items-center gap-1 text-[10px] font-medium text-emerald-600">
            <Database className="w-3 h-3" />
            {graphCount} verified
          </span>
          <span className="flex items-center gap-1 text-[10px] font-medium text-slate-500">
            <Brain className="w-3 h-3" />
            {llmCount} inferred
          </span>
        </div>
        <ChevronDown
          className={cn(
            "w-4 h-4 ml-auto text-slate-400 transition-transform",
            collapsed ? "-rotate-90" : ""
          )}
        />
      </button>

      {!collapsed && (
        <div className="p-2 space-y-1.5 bg-white">
          {chain.map((step, idx) => {
            const config = SOURCE_CONFIG[step.source] || SOURCE_CONFIG.LLM;
            const Icon = config.icon;
            const isWarning =
              step.step.toLowerCase().includes("rejected") ||
              step.step.toLowerCase().includes("insufficient") ||
              step.step.toLowerCase().includes("failed");

            return (
              <div
                key={idx}
                className={cn(
                  "flex items-start gap-2 px-3 py-2 rounded-lg border-l-[3px]",
                  isWarning ? "bg-amber-50 border-l-amber-500" : config.bgColor,
                  isWarning ? "" : config.borderColor
                )}
              >
                <Icon
                  className={cn(
                    "w-4 h-4 flex-shrink-0 mt-0.5",
                    isWarning ? "text-amber-600" : config.iconColor
                  )}
                />
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-slate-700 leading-relaxed">
                    {step.step}
                    {step.node_id && (
                      <span className="ml-1 text-slate-400 font-mono">
                        [{step.node_id}]
                      </span>
                    )}
                  </p>
                </div>
                <span
                  className={cn(
                    "px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase flex-shrink-0",
                    isWarning ? "bg-amber-100 text-amber-700" : config.badgeColor
                  )}
                >
                  {config.label}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function VerifiedBadge({ refId, reference }: { refId: string; reference?: ReferenceDetail }) {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <span
      className="relative inline-flex items-center ml-0.5"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] font-medium text-emerald-600 bg-emerald-50 border border-emerald-200 rounded cursor-pointer hover:bg-emerald-100 transition-colors">
        <CheckCircle2 className="w-2.5 h-2.5" />
      </span>
      {/* White Popover */}
      {showTooltip && reference && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 animate-popover">
          <div className="bg-white border border-slate-200 rounded-xl shadow-xl shadow-slate-200/50 p-3 min-w-[180px]">
            {/* Header */}
            <div className="flex items-center gap-1.5 pb-2 mb-2 border-b border-slate-100">
              <div className="w-5 h-5 rounded-full bg-emerald-100 flex items-center justify-center">
                <Database className="w-3 h-3 text-emerald-600" />
              </div>
              <span className="text-xs font-semibold text-emerald-700">Data Source</span>
            </div>
            {/* Content */}
            <div className="space-y-1">
              <p className="text-xs font-medium text-slate-700">{reference.name}</p>
              <p className="text-[11px] text-slate-500">{reference.type}</p>
              {reference.source_doc && (
                <p className="text-[10px] text-slate-400">{reference.source_doc}</p>
              )}
            </div>
            {/* Arrow */}
            <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-px">
              <div className="w-3 h-3 bg-white border-r border-b border-slate-200 rotate-45 -translate-y-1.5" />
            </div>
          </div>
        </div>
      )}
    </span>
  );
}
