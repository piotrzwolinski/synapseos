"use client";

import { useState, useRef, useEffect, forwardRef, useImperativeHandle } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Send,
  Loader2,
  Bot,
  User,
  Sparkles,
  Copy,
  Check,
  FlaskConical,
  Brain,
  ChevronDown,
  ChevronRight,
  Code,
  Network,
  Timer,
  Cpu,
  ArrowRight,
  Database,
  Lock,
  Scale,
  Download,
  ThumbsUp,
  ThumbsDown,
  MessageSquare,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";
import { apiUrl, authFetch, getSessionId, resetSessionId, getSessionGraphState, clearSessionGraph, type SessionGraphState, evaluateResponse, type JudgeEvalResult, type JudgeSingleResult, submitExpertReview, saveJudgeResults } from "@/lib/api";
import { getUserRole } from "@/lib/auth";
import SessionGraphViewer from "./session-graph-viewer";
import { Widget, BotResponse } from "./chat-widgets";
import { WidgetList } from "./chat-widgets";
import { ThreadInspectorSheet } from "./thread-inspector-sheet";
import {
  ReasoningChain,
  ReasoningStepData,
  ReferenceDetail,
  ExplainableResponseData,
  PolicyWarning,
  VerifiedBadge,
  // Deep Explainability components
  ThinkingTimeline,
  ExplainableChatBubble,
  ProductCardComponent,
  ExpertModeToggle,
  DeepExplainableResponseData,
  ReasoningSummaryStep,
  ContentSegment,
  ProductCard,
  // Autonomous Guardian - Risk Detection
  RiskDetectedBanner,
  ComplianceBadge,
  StatusBadges,
  // Clarification Mode
  ClarificationCard,
  // Detail Panel
  DetailPanel,
  SelectedDetail,
} from "./reasoning-chain";

interface DiagnosticsData {
  model?: string;
  llm_time_s?: number;
  total_time_s?: number;
  history_turns?: number;
  variant_count?: number;
  material_count?: number;
  graph_paths_count?: number;
}

const JUDGE_DIM_LABELS: Record<string, string> = {
  correctness: "COR", completeness: "COM", safety: "SAF",
  tone: "TON", reasoning_quality: "REA", constraint_adherence: "CON",
};

const PROVIDER_LABELS: Record<string, string> = { gemini: "Gemini", openai: "GPT-5.2", anthropic: "Claude" };

function recColor(rec: string) {
  return rec === "PASS"       ? "bg-emerald-50 dark:bg-emerald-900/30 border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-400 hover:bg-emerald-100 dark:hover:bg-emerald-900/50" :
         rec === "BORDERLINE" ? "bg-amber-50 dark:bg-amber-900/30 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-400 hover:bg-amber-100 dark:hover:bg-amber-900/50" :
         rec === "FAIL"       ? "bg-red-50 dark:bg-red-900/30 border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/50" :
                                "bg-slate-50 dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700";
}

function recBadgeColor(rec: string) {
  return rec === "PASS" ? "bg-emerald-200 dark:bg-emerald-800 text-emerald-800 dark:text-emerald-200" :
         rec === "BORDERLINE" ? "bg-amber-200 dark:bg-amber-800 text-amber-800 dark:text-amber-200" :
         rec === "FAIL" ? "bg-red-200 dark:bg-red-800 text-red-800 dark:text-red-200" :
         "bg-slate-200 dark:bg-slate-700 text-slate-800 dark:text-slate-200";
}

function JudgeBadge({
  result,
  loading,
  judgeReviews,
  onJudgeReview,
}: {
  result?: JudgeEvalResult;
  loading?: boolean;
  judgeReviews?: Record<string, "thumbs_up" | "thumbs_down">;
  onJudgeReview?: (provider: string, score: "thumbs_up" | "thumbs_down") => void;
}) {
  const [expanded, setExpanded] = useState(false);

  if (loading) {
    return (
      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-violet-50 border border-violet-100 text-[11px] text-violet-500">
        <Loader2 className="w-3 h-3 animate-spin" />
        Judging...
      </div>
    );
  }

  if (!result) return null;

  // Collect non-ERROR provider results
  const providers = (["gemini", "openai", "anthropic"] as const).filter(
    (k) => result[k] && result[k].recommendation !== "ERROR"
  );

  if (providers.length === 0) return null;

  return (
    <div className="mt-1">
      <div className="inline-flex items-center gap-1.5 flex-wrap">
        {providers.map((prov) => {
          const r = result[prov];
          const review = judgeReviews?.[prov];
          return (
            <button
              key={prov}
              onClick={() => setExpanded(!expanded)}
              className={cn(
                "inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium transition-colors border cursor-pointer",
                recColor(r.recommendation)
              )}
            >
              <Scale className="w-3 h-3" />
              <span className="opacity-60">{PROVIDER_LABELS[prov]}</span>
              {r.overall_score.toFixed(1)}/5
              <span className={cn("px-1.5 py-0.5 rounded text-[10px] font-bold", recBadgeColor(r.recommendation))}>
                {r.recommendation}
              </span>
              {review && (
                review === "thumbs_up"
                  ? <ThumbsUp className="w-3 h-3 text-emerald-600 ml-0.5" />
                  : <ThumbsDown className="w-3 h-3 text-red-600 ml-0.5" />
              )}
            </button>
          );
        })}
        <button onClick={() => setExpanded(!expanded)} className="text-slate-400 hover:text-slate-600 cursor-pointer">
          {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        </button>
      </div>
      {expanded && (
        <div className="mt-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3 text-xs space-y-3 max-w-xl">
          {providers.map((prov) => {
            const r = result[prov];
            const u = r.usage;
            const review = judgeReviews?.[prov];
            return (
              <div key={prov}>
                <div className="flex items-center justify-between mb-1">
                  <p className="font-semibold text-slate-700">{PROVIDER_LABELS[prov]}</p>
                  <div className="flex items-center gap-1.5">
                    {u && u.duration_s != null && (
                      <span className="text-[10px] text-slate-400 font-mono">{u.duration_s}s</span>
                    )}
                    {/* Per-judge thumbs up/down */}
                    {onJudgeReview && (
                      <div className="flex items-center gap-0.5 ml-1">
                        <button
                          onClick={(e) => { e.stopPropagation(); onJudgeReview(prov, "thumbs_up"); }}
                          className={cn(
                            "p-1 rounded transition-colors",
                            review === "thumbs_up"
                              ? "bg-emerald-100 text-emerald-600"
                              : "text-slate-300 hover:text-emerald-500 hover:bg-emerald-50"
                          )}
                        >
                          <ThumbsUp className="w-3 h-3" />
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); onJudgeReview(prov, "thumbs_down"); }}
                          className={cn(
                            "p-1 rounded transition-colors",
                            review === "thumbs_down"
                              ? "bg-red-100 text-red-600"
                              : "text-slate-300 hover:text-red-500 hover:bg-red-50"
                          )}
                        >
                          <ThumbsDown className="w-3 h-3" />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
                <p className="text-slate-600 leading-relaxed mb-1.5">{r.explanation}</p>
                <div className="flex flex-wrap gap-1.5 mb-1.5">
                  {Object.entries(r.scores).map(([dim, s]) => (
                    <span
                      key={dim}
                      className={cn(
                        "px-1.5 py-0.5 rounded text-[10px] font-medium",
                        s >= 4 ? "bg-emerald-100 text-emerald-700"
                          : s >= 3 ? "bg-amber-100 text-amber-700"
                          : "bg-red-100 text-red-700"
                      )}
                    >
                      {JUDGE_DIM_LABELS[dim] || dim}:{s}
                    </span>
                  ))}
                </div>
                {r.pdf_citations && r.pdf_citations.length > 0 && (
                  <div className="mt-1.5 border-t border-slate-100 pt-1.5">
                    <p className="text-[10px] font-semibold text-slate-500 mb-0.5">PDF Citations</p>
                    <ul className="list-disc list-inside text-[10px] text-slate-500 space-y-0.5">
                      {r.pdf_citations.map((c, i) => <li key={i}>{c}</li>)}
                    </ul>
                  </div>
                )}
                {u && (u.prompt_tokens || u.output_tokens) && (
                  <div className="flex items-center gap-2 text-[10px] text-slate-400 font-mono border-t border-slate-100 pt-1">
                    <span>in:{(u.prompt_tokens || 0).toLocaleString()}</span>
                    {u.cached_tokens ? (
                      <span className="text-violet-400">cached:{u.cached_tokens.toLocaleString()} ({Math.round((u.cached_tokens / (u.prompt_tokens || 1)) * 100)}%)</span>
                    ) : null}
                    <span>out:{(u.output_tokens || 0).toLocaleString()}</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

interface Message {
  role: "user" | "assistant";
  content: string;
  widgets?: Widget[];
  // Mode tracking
  chatMode?: "graphrag" | "llm-driven" | "graph-reasoning" | "neuro-symbolic";
  // Dev mode metadata
  graphPaths?: string[];
  promptPreview?: string;
  diagnostics?: DiagnosticsData;
  // Deep Explainable mode metadata (new format)
  deepExplainableData?: DeepExplainableResponseData;
  // Legacy Explainable mode metadata
  explainableData?: {
    reasoning_chain: ReasoningStepData[];
    references: Record<string, ReferenceDetail>;
    confidence_level: "high" | "medium" | "low";
    policy_warnings: string[];
    graph_facts_count: number;
    llm_inferences_count: number;
  };
  // LLM-as-a-Judge auto-evaluation
  judgeResult?: JudgeEvalResult;
  judgeLoading?: boolean;
  judgeMsgId?: string;
  // Per-judge expert reviews (keyed by provider)
  judgeReviews?: Record<string, "thumbs_up" | "thumbs_down">;
}

export interface ChatHandle {
  clearChat: () => void;
  testWidgets: () => void;
}

interface ChatProps {
  devMode?: boolean;
  sampleQuestions?: Record<string, string[]>;
  externalQuestion?: string;
  autoSubmit?: boolean;
  onQuestionConsumed?: () => void;
  explainableMode?: boolean;
  expertMode?: boolean;
  onExpertModeChange?: (value: boolean) => void;
  chatMode?: "graphrag" | "llm-driven" | "graph-reasoning" | "neuro-symbolic";
}

// Reasoning step types
interface ReasoningStep {
  id: string;
  label: string;
  icon: string;
  status: "pending" | "active" | "done" | "error";
  detail?: string;
  data?: {
    concepts?: string[];
    projects?: string[];
    citations?: string[];
    actions?: string[];
    similar_cases?: string[];
    graph_paths?: string[];
    total_results?: number;
  };
}

const GRAPHRAG_REASONING_STEPS: ReasoningStep[] = [
  { id: "intent", label: "Analyzing project context", icon: "🔍", status: "pending" },
  { id: "embed", label: "Loading product catalog from Graph", icon: "📦", status: "pending" },
  { id: "vector", label: "Reviewing Project Ledger", icon: "📋", status: "pending" },
  { id: "products", label: "Matching product specs", icon: "📦", status: "pending" },
  { id: "graph", label: "Guardian: Verifying compliance", icon: "🛡️", status: "pending" },
  { id: "thinking", label: "Senior Engineer: Synthesizing", icon: "👔", status: "pending" },
];

const LLM_REASONING_STEPS: ReasoningStep[] = [
  { id: "intent", label: "Analyzing query intent", icon: "🔍", status: "pending" },
  { id: "embed", label: "Loading catalog context", icon: "📦", status: "pending" },
  { id: "vector", label: "Reviewing conversation history", icon: "📋", status: "pending" },
  { id: "thinking", label: "LLM generating response", icon: "🤖", status: "pending" },
];

// Graph Reasoning and Neuro-Symbolic use dynamic steps from SSE - these are just placeholders
const GRAPH_REASONING_PLACEHOLDER: ReasoningStep[] = [
  { id: "init", label: "Initializing graph reasoning engine", icon: "🔗", status: "pending" },
];

const INITIAL_REASONING_STEPS = GRAPHRAG_REASONING_STEPS;

function getStepsForMode(mode: string): ReasoningStep[] {
  switch (mode) {
    case "llm-driven": return LLM_REASONING_STEPS;
    case "graphrag": return GRAPHRAG_REASONING_STEPS;
    case "graph-reasoning":
    case "neuro-symbolic":
      return GRAPH_REASONING_PLACEHOLDER;
    default: return GRAPHRAG_REASONING_STEPS;
  }
}

// Category info for dev mode questions
const QUESTION_CATEGORIES: Record<string, {
  label: string;
  icon: React.ReactNode;
  gradient: string;
  hoverGradient: string;
  textColor: string;
  bgColor: string;
  borderColor: string;
}> = {
  knittel: {
    label: "Knittel Project",
    icon: <span className="text-sm">🔧</span>,
    gradient: "from-blue-500 to-cyan-500",
    hoverGradient: "hover:from-blue-600 hover:to-cyan-600",
    textColor: "text-blue-700",
    bgColor: "bg-blue-50",
    borderColor: "border-blue-200",
  },
  huddinge: {
    label: "Huddinge Hospital",
    icon: <span className="text-sm">🏥</span>,
    gradient: "from-emerald-500 to-teal-500",
    hoverGradient: "hover:from-emerald-600 hover:to-teal-600",
    textColor: "text-emerald-700",
    bgColor: "bg-emerald-50",
    borderColor: "border-emerald-200",
  },
  nordic: {
    label: "Nordic Furniture",
    icon: <span className="text-sm">⚠️</span>,
    gradient: "from-amber-500 to-orange-500",
    hoverGradient: "hover:from-amber-600 hover:to-orange-600",
    textColor: "text-amber-700",
    bgColor: "bg-amber-50",
    borderColor: "border-amber-200",
  },
  catalog: {
    label: "Filter Catalog",
    icon: <span className="text-sm">📄</span>,
    gradient: "from-violet-500 to-purple-500",
    hoverGradient: "hover:from-violet-600 hover:to-purple-600",
    textColor: "text-violet-700",
    bgColor: "bg-violet-50",
    borderColor: "border-violet-200",
  },
  housing: {
    label: "Housing Selection",
    icon: <span className="text-sm">🏗️</span>,
    gradient: "from-rose-500 to-pink-500",
    hoverGradient: "hover:from-rose-600 hover:to-pink-600",
    textColor: "text-rose-700",
    bgColor: "bg-rose-50",
    borderColor: "border-rose-200",
  },
  maritime: {
    label: "Maritime / Offshore",
    icon: <span className="text-sm">⚓</span>,
    gradient: "from-sky-500 to-cyan-500",
    hoverGradient: "hover:from-sky-600 hover:to-cyan-600",
    textColor: "text-sky-700",
    bgColor: "bg-sky-50",
    borderColor: "border-sky-200",
  },
  guardian: {
    label: "Guardian Tests",
    icon: <span className="text-sm">🛡️</span>,
    gradient: "from-red-500 to-orange-500",
    hoverGradient: "hover:from-red-600 hover:to-orange-600",
    textColor: "text-red-700",
    bgColor: "bg-red-50",
    borderColor: "border-red-200",
  },
};

// Dev Mode Questions Component with beautiful collapsible dropdowns
function DevModeQuestions({
  sampleQuestions,
  onSelectQuestion,
}: {
  sampleQuestions: Record<string, string[]>;
  onSelectQuestion: (question: string) => void;
}) {
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);

  const toggleCategory = (key: string) => {
    setExpandedCategory(expandedCategory === key ? null : key);
  };

  return (
    <div className="mb-3 space-y-1.5">
      <div className="flex items-center gap-2 px-1 mb-2">
        <FlaskConical className="w-3.5 h-3.5 text-amber-600" />
        <span className="text-xs font-semibold text-amber-700">Test Questions</span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {Object.entries(sampleQuestions).map(([key, questions]) => {
          const category = QUESTION_CATEGORIES[key] || {
            label: key,
            icon: <span className="text-sm">📋</span>,
            gradient: "from-slate-500 to-slate-600",
            hoverGradient: "hover:from-slate-600 hover:to-slate-700",
            textColor: "text-slate-700",
            bgColor: "bg-slate-50",
            borderColor: "border-slate-200",
          };
          const isExpanded = expandedCategory === key;

          return (
            <div
              key={key}
              className={cn(
                "rounded-xl border overflow-hidden transition-all duration-300",
                isExpanded ? "col-span-2" : "col-span-1",
                category.borderColor,
                category.bgColor
              )}
            >
              {/* Header Button */}
              <button
                onClick={() => toggleCategory(key)}
                className={cn(
                  "w-full flex items-center justify-between px-3 py-2 transition-all",
                  isExpanded
                    ? `bg-gradient-to-r ${category.gradient} text-white`
                    : `${category.bgColor} ${category.textColor} hover:brightness-95`
                )}
              >
                <div className="flex items-center gap-2">
                  {category.icon}
                  <span className="text-xs font-semibold">{category.label}</span>
                  <span className={cn(
                    "px-1.5 py-0.5 rounded-full text-[10px] font-medium",
                    isExpanded ? "bg-white/20 text-white" : "bg-white/80 " + category.textColor
                  )}>
                    {questions.length}
                  </span>
                </div>
                <ChevronDown
                  className={cn(
                    "w-4 h-4 transition-transform duration-200",
                    isExpanded ? "rotate-180" : ""
                  )}
                />
              </button>

              {/* Expandable Questions List */}
              <div
                className={cn(
                  "overflow-hidden transition-all duration-300 ease-in-out",
                  isExpanded ? "max-h-[300px] opacity-100" : "max-h-0 opacity-0"
                )}
              >
                <div className="p-2 space-y-1 max-h-[280px] overflow-y-auto">
                  {questions.map((question, idx) => (
                    <button
                      key={idx}
                      onClick={() => {
                        onSelectQuestion(question);
                        setExpandedCategory(null);
                      }}
                      className={cn(
                        "w-full text-left px-3 py-2 rounded-lg text-xs transition-all",
                        "bg-white/60 hover:bg-white border",
                        category.borderColor,
                        category.textColor,
                        "hover:shadow-sm"
                      )}
                    >
                      <div className="flex items-start gap-2">
                        <span className="text-[10px] font-mono text-slate-400 mt-0.5">
                          {String(idx + 1).padStart(2, '0')}
                        </span>
                        <span className="leading-relaxed">{question}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Dev Mode Panel for showing graph paths and prompt
function DevModePanel({ graphPaths, promptPreview }: { graphPaths?: string[]; promptPreview?: string }) {
  const [showPaths, setShowPaths] = useState(false);
  const [showPrompt, setShowPrompt] = useState(false);
  const [copied, setCopied] = useState(false);

  const copyPrompt = async () => {
    if (promptPreview) {
      await navigator.clipboard.writeText(promptPreview);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="flex items-center gap-2 pt-2">
      {graphPaths && graphPaths.length > 0 && (
        <div className="relative">
          <button
            onClick={() => setShowPaths(!showPaths)}
            className={cn(
              "flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors",
              showPaths
                ? "bg-violet-100 text-violet-700"
                : "bg-slate-100 text-slate-500 hover:bg-violet-50 hover:text-violet-600"
            )}
          >
            {showPaths ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            Graph Paths ({graphPaths.length})
          </button>
          {showPaths && (
            <div className="absolute left-0 top-full mt-1 z-10 w-[400px] max-h-[300px] overflow-auto bg-white border border-violet-200 rounded-lg shadow-lg p-2 space-y-1">
              {graphPaths.map((path, i) => (
                <div key={i} className="px-2 py-1.5 bg-violet-50 border border-violet-100 rounded text-[10px] text-violet-800 font-mono leading-relaxed">
                  {path}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {promptPreview && (
        <div className="relative">
          <button
            onClick={() => setShowPrompt(!showPrompt)}
            className={cn(
              "flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors",
              showPrompt
                ? "bg-slate-700 text-white"
                : "bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-700"
            )}
          >
            <Code className="w-3 h-3" />
            Prompt
          </button>
          {showPrompt && (
            <div className="absolute left-0 top-full mt-1 z-10 w-[600px] max-h-[500px] overflow-auto bg-slate-800 border border-slate-600 rounded-lg shadow-lg">
              <div className="sticky top-0 flex items-center justify-between px-3 py-2 bg-slate-700 border-b border-slate-600">
                <span className="text-[10px] text-slate-400 font-medium">Full Prompt to AI</span>
                <button
                  onClick={copyPrompt}
                  className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium bg-slate-600 hover:bg-slate-500 text-slate-200 transition-colors"
                >
                  {copied ? (
                    <>
                      <Check className="w-3 h-3 text-green-400" />
                      Copied!
                    </>
                  ) : (
                    <>
                      <Copy className="w-3 h-3" />
                      Copy
                    </>
                  )}
                </button>
              </div>
              <pre className="p-3 text-[10px] text-slate-300 whitespace-pre-wrap font-mono leading-relaxed">
                {promptPreview}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// LLM Mode: Prompt & Diagnostics Panel (always shown for llm-driven mode)
function LlmDiagnosticsPanel({ promptPreview, diagnostics }: { promptPreview?: string; diagnostics?: DiagnosticsData }) {
  const [showPrompt, setShowPrompt] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!promptPreview && !diagnostics) return null;

  const copyPrompt = async () => {
    if (promptPreview) {
      await navigator.clipboard.writeText(promptPreview);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="mt-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-gradient-to-br from-slate-50 to-blue-50/30 dark:from-slate-800 dark:to-blue-900/20 overflow-hidden">
      {/* Header with diagnostics summary */}
      <div className="flex items-center justify-between px-3 py-2 bg-white/60 dark:bg-slate-800/60 border-b border-slate-100 dark:border-slate-700">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-md bg-blue-100 dark:bg-blue-900/40 flex items-center justify-center">
            <Cpu className="w-3 h-3 text-blue-600 dark:text-blue-400" />
          </div>
          <span className="text-[11px] font-semibold text-slate-700 dark:text-slate-300">LLM Diagnostics</span>
        </div>
        {diagnostics && (
          <div className="flex items-center gap-3 text-[10px] text-slate-500 dark:text-slate-400">
            {diagnostics.model && (
              <span className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 font-mono">{diagnostics.model}</span>
            )}
            {diagnostics.llm_time_s != null && (
              <span className="flex items-center gap-1">
                <Timer className="w-3 h-3" />
                LLM: {diagnostics.llm_time_s}s
              </span>
            )}
            {diagnostics.total_time_s != null && (
              <span className="flex items-center gap-1">
                Total: {diagnostics.total_time_s}s
              </span>
            )}
          </div>
        )}
      </div>

      {/* Diagnostics details */}
      {diagnostics && (
        <div className="px-3 py-2 flex flex-wrap gap-3 text-[10px] border-b border-slate-100/50 dark:border-slate-700/50">
          {diagnostics.history_turns != null && (
            <div className="flex items-center gap-1.5 text-slate-600 dark:text-slate-400">
              <span className="font-medium text-slate-500 dark:text-slate-400">History:</span>
              <span>{diagnostics.history_turns} turns</span>
            </div>
          )}
          {diagnostics.variant_count != null && (
            <div className="flex items-center gap-1.5 text-slate-600 dark:text-slate-400">
              <span className="font-medium text-slate-500 dark:text-slate-400">Variants loaded:</span>
              <span>{diagnostics.variant_count}</span>
            </div>
          )}
        </div>
      )}

      {/* Prompt toggle */}
      {promptPreview && (
        <div>
          <button
            onClick={() => setShowPrompt(!showPrompt)}
            className={cn(
              "w-full flex items-center justify-between px-3 py-2 text-[11px] font-medium transition-colors",
              showPrompt
                ? "bg-slate-700 text-white"
                : "text-slate-600 hover:bg-slate-100"
            )}
          >
            <div className="flex items-center gap-1.5">
              <Code className="w-3 h-3" />
              Full Prompt to LLM
            </div>
            <div className="flex items-center gap-2">
              {showPrompt && (
                <button
                  onClick={(e) => { e.stopPropagation(); copyPrompt(); }}
                  className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-slate-600 hover:bg-slate-500 text-slate-200 transition-colors"
                >
                  {copied ? <><Check className="w-3 h-3 text-green-400" /> Copied!</> : <><Copy className="w-3 h-3" /> Copy</>}
                </button>
              )}
              {showPrompt ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            </div>
          </button>
          {showPrompt && (
            <div className="max-h-[400px] overflow-auto bg-slate-800">
              <pre className="p-3 text-[10px] text-slate-300 whitespace-pre-wrap font-mono leading-relaxed">
                {promptPreview}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// GraphRAG Mode: Graph Traversal Panel (always shown for graphrag mode)
function GraphTraversalPanel({ graphPaths, diagnostics, promptPreview }: { graphPaths?: string[]; diagnostics?: DiagnosticsData; promptPreview?: string }) {
  const [expanded, setExpanded] = useState(false);
  const [showPrompt, setShowPrompt] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!graphPaths || graphPaths.length === 0) return null;

  return (
    <div className="mt-3 rounded-xl border border-violet-200 bg-gradient-to-br from-violet-50/50 to-blue-50/30 overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-2 hover:bg-violet-50/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-md bg-violet-100 flex items-center justify-center">
            <Network className="w-3 h-3 text-violet-600" />
          </div>
          <span className="text-[11px] font-semibold text-slate-700">Graph Traversal</span>
          <span className="px-1.5 py-0.5 rounded-full bg-violet-100 text-violet-700 text-[10px] font-medium">
            {graphPaths.length} paths
          </span>
        </div>
        <div className="flex items-center gap-3">
          {diagnostics && (
            <div className="flex items-center gap-3 text-[10px] text-slate-500">
              {diagnostics.model && (
                <span className="px-1.5 py-0.5 rounded bg-slate-100 font-mono">{diagnostics.model}</span>
              )}
              {diagnostics.total_time_s != null && (
                <span className="flex items-center gap-1">
                  <Timer className="w-3 h-3" />
                  {diagnostics.total_time_s}s
                </span>
              )}
            </div>
          )}
          {expanded ? <ChevronDown className="w-3 h-3 text-slate-400" /> : <ChevronRight className="w-3 h-3 text-slate-400" />}
        </div>
      </button>

      {/* Expanded paths */}
      {expanded && (
        <div className="px-3 pb-3 space-y-1.5 border-t border-violet-100">
          <div className="pt-2" />
          {graphPaths.map((path, i) => {
            // Parse path like "ProductFamily(GDB) → ProductVariant[23 variants]"
            const parts = path.split(" → ");
            return (
              <div key={i} className="flex items-start gap-2 group">
                <div className="flex-shrink-0 mt-1 w-4 h-4 rounded-full bg-violet-100 flex items-center justify-center">
                  <span className="text-[8px] text-violet-600 font-bold">{i + 1}</span>
                </div>
                <div className="flex-1 flex flex-wrap items-center gap-1 text-[10px] font-mono leading-relaxed">
                  {parts.map((part, j) => {
                    // Highlight node names in parentheses
                    const isNode = part.includes("(") || part.includes("[");
                    return (
                      <span key={j} className="flex items-center gap-1">
                        {j > 0 && <ArrowRight className="w-3 h-3 text-violet-400 flex-shrink-0" />}
                        <span className={cn(
                          "px-1.5 py-0.5 rounded",
                          isNode
                            ? "bg-violet-100 text-violet-800 border border-violet-200"
                            : "text-slate-600"
                        )}>
                          {part}
                        </span>
                      </span>
                    );
                  })}
                </div>
              </div>
            );
          })}

          {/* Summary stats */}
          {diagnostics && (
            <div className="mt-2 pt-2 border-t border-violet-100 flex flex-wrap gap-3 text-[10px] text-slate-500">
              {diagnostics.variant_count != null && (
                <span><Database className="w-3 h-3 inline mr-1" />{diagnostics.variant_count} variants loaded</span>
              )}
              {diagnostics.material_count != null && (
                <span>{diagnostics.material_count} materials</span>
              )}
              {diagnostics.graph_paths_count != null && (
                <span>{diagnostics.graph_paths_count} graph paths traversed</span>
              )}
            </div>
          )}

          {/* Prompt preview (collapsible) */}
          {promptPreview && (
            <div className="mt-2 pt-2 border-t border-violet-100">
              <button
                onClick={() => setShowPrompt(!showPrompt)}
                className={cn(
                  "flex items-center gap-1.5 text-[10px] font-medium transition-colors",
                  showPrompt ? "text-slate-700" : "text-slate-500 hover:text-slate-700"
                )}
              >
                <Code className="w-3 h-3" />
                {showPrompt ? "Hide" : "Show"} LLM Prompt
                {showPrompt ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
              </button>
              {showPrompt && (
                <div className="mt-1.5 rounded-lg overflow-hidden bg-slate-800">
                  <div className="flex items-center justify-between px-3 py-1.5 bg-slate-700 border-b border-slate-600">
                    <span className="text-[10px] text-slate-400">Full Prompt</span>
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(promptPreview);
                        setCopied(true);
                        setTimeout(() => setCopied(false), 2000);
                      }}
                      className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-slate-600 hover:bg-slate-500 text-slate-200"
                    >
                      {copied ? <><Check className="w-3 h-3 text-green-400" /> Copied!</> : <><Copy className="w-3 h-3" /> Copy</>}
                    </button>
                  </div>
                  <pre className="p-3 text-[10px] text-slate-300 whitespace-pre-wrap font-mono leading-relaxed max-h-[300px] overflow-auto">
                    {promptPreview}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export const Chat = forwardRef<ChatHandle, ChatProps>(function Chat(
  { devMode, sampleQuestions, externalQuestion, autoSubmit, onQuestionConsumed, explainableMode = false, expertMode = true, onExpertModeChange, chatMode = "graphrag" },
  ref
) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [reasoningSteps, setReasoningSteps] = useState<ReasoningStep[]>(INITIAL_REASONING_STEPS);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [inspectorProject, setInspectorProject] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<SelectedDetail | null>(null);
  const [selectedDetailIdx, setSelectedDetailIdx] = useState<number | null>(null);
  // Track confirmed inferences (for Active Learning)
  const [confirmedInferences, setConfirmedInferences] = useState<Set<number>>(new Set());
  // Track original query for clarification follow-ups
  const [pendingClarificationContext, setPendingClarificationContext] = useState<{
    originalQuery: string;
    missingAttribute: string;
  } | null>(null);
  // Track locked context for multi-turn persistence (material, project, filter depths)
  const [lockedContext, setLockedContext] = useState<{
    material?: string;
    project?: string;
    filter_depths?: number[];
    dimension_mappings?: Array<{ width: number; height: number; depth?: number }>;
  } | null>(null);
  // Track full technical state for comprehensive multi-turn persistence
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [technicalState, setTechnicalState] = useState<Record<string, any> | null>(null);
  const [sessionGraphState, setSessionGraphState] = useState<SessionGraphState | null>(null);
  const [showSessionGraph, setShowSessionGraph] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Expose methods to parent via ref
  useImperativeHandle(ref, () => ({
    clearChat,
    testWidgets,
  }));

  // Parse a message content that might be JSON with summary/widgets
  const parseMessageContent = (content: string): { text: string; widgets?: Widget[] } => {
    try {
      const trimmed = content.trim();
      if (trimmed.startsWith("{")) {
        const parsed = JSON.parse(trimmed);
        return {
          text: parsed.summary || parsed.text_summary || content,
          widgets: parsed.widgets,
        };
      }
    } catch {
      // Not JSON, return as-is
    }
    return { text: content };
  };

  useEffect(() => {
    const loadHistory = async () => {
      try {
        const response = await fetch(apiUrl(`/chat/history?session_id=${getSessionId()}`), authFetch());
        if (response.ok) {
          const data = await response.json();
          // Parse assistant messages that might contain JSON
          const parsedMessages = data.messages.map((msg: Message) => {
            if (msg.role === "assistant" && !msg.widgets) {
              const parsed = parseMessageContent(msg.content);
              return {
                ...msg,
                content: parsed.text,
                widgets: parsed.widgets,
              };
            }
            return msg;
          });
          setMessages(parsedMessages);
        }
      } catch (error) {
        console.error("Failed to load chat history:", error);
      }
    };
    loadHistory();
  }, []);

  // Handle external question injection (from dev mode or URL ?q= param)
  const autoSubmitFiredRef = useRef(false);
  useEffect(() => {
    if (externalQuestion && externalQuestion.trim()) {
      setInput(externalQuestion);
      onQuestionConsumed?.();
      if (autoSubmit && !autoSubmitFiredRef.current) {
        autoSubmitFiredRef.current = true;
        // Delay to let state settle after history load
        setTimeout(() => sendMessage(externalQuestion), 300);
      } else {
        inputRef.current?.focus();
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [externalQuestion, onQuestionConsumed, autoSubmit]);

  useEffect(() => {
    // Delay scroll to ensure DOM has updated with new content
    const timer = setTimeout(() => {
      if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    }, 100);
    return () => clearTimeout(timer);
  }, [messages]);

  // Animate reasoning steps during loading (deep-explainable is non-streaming)
  useEffect(() => {
    const modeSteps = getStepsForMode(chatMode);
    if (!isLoading) {
      setReasoningSteps(modeSteps);
      return;
    }

    // For graph-reasoning and neuro-symbolic, steps are dynamically pushed from SSE
    if (chatMode === "graph-reasoning" || chatMode === "neuro-symbolic") {
      setReasoningSteps(modeSteps);
      return;
    }

    setReasoningSteps(modeSteps);
    const stepIds = modeSteps.map(s => s.id);
    let current = 0;

    // Activate first step immediately
    setReasoningSteps(prev =>
      prev.map((s, i) => ({ ...s, status: i === 0 ? "active" : "pending" }))
    );

    const interval = setInterval(() => {
      current++;
      if (current >= stepIds.length) {
        // All done except last stays active (waiting for response)
        setReasoningSteps(prev =>
          prev.map((s, i) => ({
            ...s,
            status: i < stepIds.length - 1 ? "done" : "active"
          }))
        );
        clearInterval(interval);
        return;
      }
      setReasoningSteps(prev =>
        prev.map((s, i) => ({
          ...s,
          status: i < current ? "done" : i === current ? "active" : "pending"
        }))
      );
    }, 800);

    return () => clearInterval(interval);
  }, [isLoading, chatMode]);

  // Send a clarification response - displays short value in chat, sends full context to backend
  const sendClarificationResponse = async (displayValue: string, fullContext: string) => {
    if (isLoading) return;

    // Build query with locked context for multi-turn persistence
    let queryWithContext = fullContext;
    if (lockedContext) {
      const contextParts: string[] = [];
      if (lockedContext.material) {
        contextParts.push(`material=${lockedContext.material}`);
      }
      if (lockedContext.project) {
        contextParts.push(`project=${lockedContext.project}`);
      }
      if (lockedContext.filter_depths && lockedContext.filter_depths.length > 0) {
        contextParts.push(`filter_depths=${lockedContext.filter_depths.join(',')}`);
      }
      // BUGFIX: Include dimension_mappings in locked context
      if (lockedContext.dimension_mappings && lockedContext.dimension_mappings.length > 0) {
        const dimStr = lockedContext.dimension_mappings
          .map(d => `${d.width}x${d.height}${d.depth ? 'x' + d.depth : ''}`)
          .join(',');
        contextParts.push(`dimensions=${dimStr}`);
      }
      if (contextParts.length > 0) {
        queryWithContext = `${fullContext} [LOCKED: ${contextParts.join('; ')}]`;
      }
    }
    // BUGFIX: Send full technical state for complete cumulative tracking
    if (technicalState && Object.keys(technicalState).length > 0) {
      queryWithContext = `${queryWithContext} [STATE: ${JSON.stringify(technicalState)}]`;
    }

    // Display the short value in chat (what user sees)
    setMessages((prev) => [...prev, { role: "user", content: displayValue }]);
    setIsLoading(true);

    // Scroll to bottom after adding message
    setTimeout(() => {
      if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    }, 50);
    setReasoningSteps(INITIAL_REASONING_STEPS);
    setSelectedDetail(null);
    setSelectedDetailIdx(null);
    setPendingClarificationContext(null);

    try {
      // Send the full context to backend (what LLM reads)
      const response = await fetch(apiUrl("/consult/deep-explainable"), authFetch({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: queryWithContext }),
      }));

      if (!response.ok) throw new Error("Failed to get response");

      const data: DeepExplainableResponseData = await response.json();

      const contentText = data.content_segments && Array.isArray(data.content_segments)
        ? data.content_segments.map(seg => seg.text).join("")
        : "Response received.";

      // If this is another clarification, store context (unlikely but handle it)
      if (data.clarification_needed && data.clarification) {
        setPendingClarificationContext({
          originalQuery: fullContext,
          missingAttribute: data.clarification.missing_info || "the required parameter",
        });
      }

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: contentText,
          chatMode,
          deepExplainableData: data,
        },
      ]);

      // Scroll to bottom after assistant response
      setTimeout(() => {
        if (scrollRef.current) {
          scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
      }, 100);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "An unknown error occurred";
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `⚠️ **Error:** ${errorMessage}\n\nPlease try again.`,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const sendMessage = async (overrideMessage?: string | React.MouseEvent) => {
    // Guard: ignore MouseEvent from onClick={sendMessage} handlers
    const override = typeof overrideMessage === "string" ? overrideMessage : undefined;
    const userMessage = override || input.trim();
    if (!userMessage || isLoading) return;

    // Store the original query for potential clarification follow-up
    const lastQueryForClarification = userMessage;

    // Build query with locked context for multi-turn persistence
    let queryWithContext = userMessage;
    if (lockedContext) {
      const contextParts: string[] = [];
      if (lockedContext.material) {
        contextParts.push(`material=${lockedContext.material}`);
      }
      if (lockedContext.project) {
        contextParts.push(`project=${lockedContext.project}`);
      }
      if (lockedContext.filter_depths && lockedContext.filter_depths.length > 0) {
        contextParts.push(`filter_depths=${lockedContext.filter_depths.join(',')}`);
      }
      // BUGFIX: Include dimension_mappings in locked context
      if (lockedContext.dimension_mappings && lockedContext.dimension_mappings.length > 0) {
        const dimStr = lockedContext.dimension_mappings
          .map(d => `${d.width}x${d.height}${d.depth ? 'x' + d.depth : ''}`)
          .join(',');
        contextParts.push(`dimensions=${dimStr}`);
      }
      if (contextParts.length > 0) {
        queryWithContext = `${userMessage} [LOCKED: ${contextParts.join('; ')}]`;
      }
    }
    // BUGFIX: Send full technical state for complete cumulative tracking
    if (technicalState && Object.keys(technicalState).length > 0) {
      queryWithContext = `${queryWithContext} [STATE: ${JSON.stringify(technicalState)}]`;
    }

    if (!override) {
      setInput("");
    }
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setIsLoading(true);
    setReasoningSteps(INITIAL_REASONING_STEPS);
    // Clear selected detail when sending new message
    setSelectedDetail(null);
    setSelectedDetailIdx(null);
    // Clear pending clarification context when sending new message
    // (will be set again if response is a clarification)
    setPendingClarificationContext(null);

    // Reset textarea height
    if (!override && inputRef.current) {
      inputRef.current.style.height = "auto";
    }

    try {
      // Graph Reasoning and Neuro-Symbolic use the consult endpoints with SSE inference chain
      const useGraphEngine = chatMode === "graph-reasoning" || chatMode === "neuro-symbolic" || explainableMode;
      console.log(`%c[MODE ROUTING] chatMode="${chatMode}" | explainableMode=${explainableMode} | useGraphEngine=${useGraphEngine}`, 'color: #ff6600; font-weight: bold; font-size: 14px');
      if (useGraphEngine) {
        // Use streaming endpoint for real-time inference chain
        const token = localStorage.getItem("mh_auth_token");
        const streamUrl = chatMode === "neuro-symbolic" ? "/consult/universal/stream" : "/consult/deep-explainable/stream";
        console.log(`%c[MODE ROUTING] → Graph engine endpoint: ${streamUrl}`, 'color: #ff6600; font-weight: bold; font-size: 14px');
        const response = await fetch(apiUrl(streamUrl), {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { "Authorization": `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ query: queryWithContext, session_id: getSessionId() }),
        });

        if (!response.ok) throw new Error("Failed to get response");

        // Process SSE stream
        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        let data: DeepExplainableResponseData | null = null;
        const dynamicSteps: ReasoningStep[] = [];
        let capturedGraphReport: Record<string, unknown> = {};

        if (reader) {
          let buffer = "";
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";

            for (const line of lines) {
              if (line.startsWith("data: ")) {
                try {
                  const event = JSON.parse(line.slice(6));

                  if (event.type === "inference") {
                    // Update reasoning steps dynamically with real discoveries
                    const existingIdx = dynamicSteps.findIndex(s => s.id === event.step);
                    const newStep: ReasoningStep = {
                      id: event.step,
                      label: event.detail,  // Human-readable message with emoji
                      icon: event.detail?.charAt(0) || "🔍",
                      status: event.status === "done" ? "done" : event.status === "warning" ? "done" : "active",
                      data: event.data,  // Keep structured data for potential UI rendering
                    };

                    if (existingIdx >= 0) {
                      dynamicSteps[existingIdx] = newStep;
                    } else {
                      dynamicSteps.push(newStep);
                    }

                    setReasoningSteps([...dynamicSteps]);
                    console.log(`🔗 Inference: ${event.detail}`);

                  } else if (event.type === "complete") {
                    // Final response received
                    data = event.response;
                    capturedGraphReport = event.graph_report || {};
                    console.log("✅ Stream complete", event.timings);

                    // Extract and persist locked context for multi-turn persistence
                    if (event.locked_context && Object.keys(event.locked_context).length > 0) {
                      console.log("🔒 Locked context received:", event.locked_context);
                      setLockedContext(prev => ({
                        ...prev,
                        ...event.locked_context
                      }));
                    }

                    // Extract and persist full technical state if available
                    if (event.technical_state && Object.keys(event.technical_state).length > 0) {
                      console.log("📋 Technical state received:", event.technical_state);
                      setTechnicalState(event.technical_state);
                    }

                    // Mark all steps as done
                    setReasoningSteps(dynamicSteps.map(s => ({ ...s, status: "done" as const })));
                  } else if (event.type === "session_state" && event.data) {
                    // Layer 4: Update session graph state from graph-reasoning SSE
                    setSessionGraphState(event.data);
                    console.log("📊 [SESSION GRAPH] Updated from graph-reasoning SSE:", event.data.tag_count, "tags");
                  } else if (event.type === "error") {
                    console.error("Stream error:", event.detail);
                  }
                } catch (e) {
                  console.warn("Failed to parse SSE event:", line, e);
                }
              }
            }
          }
        }

        // Fallback if no streaming data received
        if (!data) {
          data = { content_segments: [{ text: "No response received", type: "GENERAL" }] } as DeepExplainableResponseData;
        }

        // Build content from segments for display (with safety check)
        const contentText = data.content_segments && Array.isArray(data.content_segments)
          ? data.content_segments.map(seg => seg.text).join("")
          : "Response received.";

        // Validate that we have proper data structure
        if (!data.content_segments || !Array.isArray(data.content_segments)) {
          console.error("Invalid response structure:", data);
        }

        // If this is a clarification response, store the context for follow-up
        if (data.clarification_needed && data.clarification) {
          setPendingClarificationContext({
            originalQuery: lastQueryForClarification,
            missingAttribute: data.clarification.missing_info || "the required parameter",
          });
        }

        // Generate a unique ID for this message so the judge callback can find it
        const judgeMsgId = `judge-${Date.now()}`;
        const isExpertRole = true;
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: contentText,
            chatMode,
            deepExplainableData: data,
            judgeLoading: isExpertRole,
            judgeMsgId,
          },
        ]);

        // Fire LLM judge in background (non-blocking) — expert role only
        if (isExpertRole) {
          // Build conversation history: all prior messages + current response
          const conversationHistory = messages
            .filter((m) => m.chatMode === "graph-reasoning" || m.role === "user")
            .map((m) => ({
              role: m.role as string,
              content: m.content,
              product_card: m.deepExplainableData?.product_card || null,
              product_cards: m.deepExplainableData?.product_cards || null,
              clarification_needed: m.deepExplainableData?.clarification_needed || false,
              status_badges: m.deepExplainableData?.status_badges || null,
            }));
          // Append the current user message + this assistant response
          conversationHistory.push({ role: "user", content: userMessage, product_card: null, product_cards: null, clarification_needed: false, status_badges: null });
          conversationHistory.push({
            role: "assistant",
            content: contentText,
            product_card: data?.product_card || null,
            product_cards: data?.product_cards || null,
            clarification_needed: data?.clarification_needed || false,
            status_badges: data?.status_badges || null,
          });

          const judgeResponseData = {
            conversation_history: conversationHistory,
            content_text: contentText,
            product_card: data?.product_card || null,
            product_cards: data?.product_cards || null,
            clarification_needed: data?.clarification_needed || false,
            graph_report: capturedGraphReport,
            inference_steps: dynamicSteps.map(s => ({
              step: s.id,
              detail: s.label,
              status: s.status,
            })),
          };
          // Calculate turn number for this assistant response
          const currentTurnNumber = messages.filter(m => m.role === "assistant").length + 1;
          evaluateResponse(userMessage, judgeResponseData)
            .then((judgeResult) => {
              setMessages((prev) =>
                prev.map((m) =>
                  m.judgeMsgId === judgeMsgId ? { ...m, judgeResult, judgeLoading: false } : m
                )
              );
              // Persist judge results to Neo4j (non-blocking)
              saveJudgeResults(getSessionId(), currentTurnNumber, judgeResult as unknown as Record<string, unknown>)
                .catch((err) => console.warn("Failed to persist judge results:", err));
            })
            .catch((err) => {
              console.warn("Judge evaluation failed:", err);
              setMessages((prev) =>
                prev.map((m) =>
                  m.judgeMsgId === judgeMsgId ? { ...m, judgeLoading: false } : m
                )
              );
            });
        }
      } else {
        // Use streaming endpoint based on chat mode
        const streamEndpoint = chatMode === "llm-driven" ? "/chat/llm-driven/stream" : "/chat/stream";
        console.log(`%c[MODE ROUTING] → Chat endpoint: ${streamEndpoint}`, 'color: #0088ff; font-weight: bold; font-size: 14px');
        const response = await fetch(apiUrl(streamEndpoint), authFetch({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: userMessage, session_id: getSessionId() }),
        }));

        if (!response.ok) throw new Error("Failed to get response");

        const reader = response.body?.getReader();
        const decoder = new TextDecoder();

        if (!reader) throw new Error("No response body");

        let finalResponse = "";
        let capturedPrompt = "";
        let capturedPaths: string[] = [];
        let capturedDiagnostics: DiagnosticsData = {};

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value);
          const lines = chunk.split("\n");

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6));

                if (data.step === "complete" && data.response) {
                  finalResponse = data.response;
                  console.log("✅ Response complete - timing summary above ^");
                  console.log("📦 Raw response:", finalResponse);
                  console.log("📦 Response type:", typeof finalResponse);
                  console.log("📦 Starts with {:", finalResponse.trim().startsWith("{"));
                } else if (data.step === "session_state" && data.data) {
                  // Layer 4: Update session graph state from SSE
                  setSessionGraphState(data.data);
                  console.log("📊 [SESSION GRAPH] Updated from SSE:", data.data.tag_count, "tags");
                } else if (data.step === "error") {
                  // Handle API errors (rate limits, etc.)
                  throw new Error(data.detail || "An error occurred while generating response");
                } else if (data.step === "prompt" && data.prompt_preview) {
                  // Capture the prompt preview for the message
                  capturedPrompt = data.prompt_preview;
                } else if (data.step === "diagnostics" && data.data) {
                  // Capture diagnostics data
                  capturedDiagnostics = data.data;
                } else if (data.step && data.status) {
                  // Capture graph paths from graph step
                  if (data.step === "graph" && data.data?.graph_paths) {
                    capturedPaths = data.data.graph_paths;
                  }
                  // Log timing to console - ALWAYS log step updates
                  console.log(`[SSE] ${data.step}: ${data.status} - ${data.detail || 'no detail'}`);
                  // Update reasoning steps with real data
                  setReasoningSteps((prev) =>
                    prev.map((step) =>
                      step.id === data.step
                        ? { ...step, status: data.status, detail: data.detail, data: data.data }
                        : step
                    )
                  );
                }
              } catch {
                // Ignore parse errors for incomplete chunks
              }
            }
          }
        }

        // Parse the final response
        let textContent = finalResponse;
        let widgets: Widget[] | undefined;

        // Check for empty response
        if (!finalResponse || finalResponse.trim() === "") {
          throw new Error("No response received from the AI. Please try again.");
        }

        try {
          const trimmed = finalResponse.trim();
          console.log("🔍 Parsing response, starts with {:", trimmed.startsWith("{"));
          if (trimmed.startsWith("{")) {
            const parsed = JSON.parse(trimmed);
            console.log("✅ JSON parsed successfully");
            console.log("📋 Summary:", parsed.summary || parsed.text_summary || "(none)");
            console.log("🧩 Widgets:", parsed.widgets?.length || 0, "widgets");
            console.log("🧩 Widget types:", parsed.widgets?.map((w: Widget) => w.type));
            textContent = parsed.summary || parsed.text_summary || finalResponse;
            widgets = parsed.widgets;
          } else {
            console.log("⚠️ Response is NOT JSON, using as plain text");
            console.log("📄 First 200 chars:", trimmed.substring(0, 200));
          }
        } catch (parseError) {
          // Not JSON, use as plain text
          console.error("❌ JSON parse failed:", parseError);
          console.log("📄 Raw response (first 500 chars):", finalResponse.substring(0, 500));
        }

        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: textContent,
            widgets,
            chatMode,
            graphPaths: capturedPaths.length > 0 ? capturedPaths : undefined,
            promptPreview: capturedPrompt || undefined,
            diagnostics: Object.keys(capturedDiagnostics).length > 0 ? capturedDiagnostics : undefined,
          },
        ]);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "An unknown error occurred";
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `⚠️ **Error:** ${errorMessage}\n\nPlease try again or switch to a different model.`,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const clearChat = async () => {
    try {
      await fetch(apiUrl("/chat/clear"), authFetch({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: getSessionId() }),
      }));
      setMessages([]);
      // Clear locked context, technical state, and session graph
      setLockedContext(null);
      setTechnicalState(null);
      setSessionGraphState(null);
      // Generate a fresh session ID so no stale Layer 4 state can leak
      resetSessionId();
      console.log("🔓 Session fully reset (state + ID)");
    } catch (error) {
      console.error("Failed to clear chat:", error);
    }
  };

  const copyMessage = async (content: string, index: number) => {
    await navigator.clipboard.writeText(content);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const exportConversation = () => {
    if (messages.length === 0) return;

    const exported = {
      session_id: getSessionId(),
      exported_at: new Date().toISOString(),
      chat_mode: chatMode,
      session_graph: sessionGraphState || null,
      locked_context: lockedContext || null,
      technical_state: technicalState || null,
      turns: messages.map((msg, idx) => {
        const turn: Record<string, unknown> = {
          turn: idx + 1,
          role: msg.role,
          content: msg.content,
          chat_mode: msg.chatMode || null,
        };

        // Assistant-specific data
        if (msg.role === "assistant") {
          // Deep Explainable data (reasoning steps, product cards, etc.)
          if (msg.deepExplainableData) {
            const d = msg.deepExplainableData;
            turn.reasoning_steps = d.reasoning_summary?.map(s => ({
              step: s.step, icon: s.icon, description: s.description,
            })) || [];
            turn.status_badges = d.status_badges || [];
            turn.product_card = d.product_card || null;
            turn.product_cards = d.product_cards || [];
            turn.clarification = d.clarification || null;
            turn.clarification_needed = d.clarification_needed || false;
            turn.risk_detected = d.risk_detected || false;
            turn.risk_severity = d.risk_severity || null;
            turn.confidence_level = d.confidence_level;
            turn.graph_facts_count = d.graph_facts_count;
            turn.inference_count = d.inference_count;
            turn.timings = d.timings || null;
          }

          // Judge evaluations (all 3 models)
          if (msg.judgeResult) {
            const jr = msg.judgeResult;
            turn.judge = {} as Record<string, unknown>;
            for (const prov of ["gemini", "openai", "anthropic"] as const) {
              const r = jr[prov];
              if (r && r.recommendation !== "ERROR") {
                (turn.judge as Record<string, unknown>)[prov] = {
                  overall_score: r.overall_score,
                  recommendation: r.recommendation,
                  scores: r.scores,
                  explanation: r.explanation,
                  dimension_explanations: r.dimension_explanations,
                  strengths: r.strengths,
                  weaknesses: r.weaknesses,
                  pdf_citations: r.pdf_citations || [],
                  usage: r.usage || null,
                };
              }
            }
          }

          // Widgets (action proposals, safety guards, etc.)
          if (msg.widgets && msg.widgets.length > 0) {
            turn.widgets = msg.widgets;
          }
        }

        return turn;
      }),
    };

    const blob = new Blob([JSON.stringify(exported, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `conversation-${new Date().toISOString().slice(0, 19).replace(/:/g, "-")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Test function to inject mock widget response
  const testWidgets = () => {
    const mockResponse: BotResponse = {
      summary: "Critical safety risk detected. Standard polyester filters are not acceptable for milk powder applications due to ATEX explosion risk.",
      widgets: [
        {
          type: "safety_guard",
          data: {
            title: "BLOCK: Explosion Risk (ATEX)",
            severity: "critical",
            risk_description: "Milk powder is an explosive material. Standard polyester filters can generate electrostatic charges leading to explosion in hazardous zones.",
            compliance_items: [
              "ATEX zone requires certified antistatic filters",
              "EN 60079 standard for Ex zone equipment",
              "Compliance documentation required for all components",
              "Safety audit before installation"
            ],
            recommendation: "Use antistatic filters with ATEX certification (e.g., AF-3000 series) instead of standard polyester. Contact the technical department for proper configuration selection.",
            acknowledge_label: "I understand the risk and want to continue"
          }
        },
        {
          type: "action_proposal",
          data: {
            title: "Recommended ATEX Configuration",
            product_name: "AF-3200 ATEX Antistatic Filter",
            specs: [
              "Material: Antistatic polyester with carbon fiber",
              "Certificate: ATEX II 2D Ex tb IIIC T135°C Db",
              "Surface resistance: < 10⁹ Ω",
              "Grounding system: Integrated"
            ],
            price_impact: "+45% vs standard configuration",
            is_locked: true
          }
        },
        {
          type: "technical_card",
          data: {
            title: "Custom Flange Adapter",
            reasoning: {
              project_ref: "Knittel Glasbearbeitungs",
              constraint: "Welded/Fixed Intake Grid",
              author: "Milad Alzaghari",
              confidence_level: "High"
            },
            properties: [
              { label: "Interface", value: "DIN 2633 (PN16)" },
              { label: "Diameter", value: "DN 400" },
              { label: "Material", value: "Galvanized Steel" },
              { label: "Install Time", value: "2 Hours", is_estimate: true },
              { label: "Bypass Type", value: "External Pipe" }
            ],
            actions: [
              { label: "Copy Spec", action_id: "copy", variant: "outline" },
              { label: "Add to Quote", action_id: "add", variant: "primary" }
            ]
          }
        }
      ]
    };

    setMessages((prev) => [
      ...prev,
      { role: "user", content: "A food industry client is looking for the cheapest polyester filters for milk powder dust collection. Please prepare a quote." },
      { role: "assistant", content: mockResponse.summary || "", widgets: mockResponse.widgets }
    ]);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    // Auto-resize textarea to fit content (max 300px)
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 300) + "px";
  };

  // Handler for Deep Dive / Source Inspection
  const handleProjectClick = (projectName: string) => {
    setInspectorProject(projectName);
    setInspectorOpen(true);
  };

  // Component to render markdown with [[REF:ID]] verification badges
  const VerifiedMarkdownRenderer = ({
    content,
    references,
  }: {
    content: string;
    references: Record<string, ReferenceDetail>;
  }) => {
    // Split by [[REF:...]] markers and render
    const parts = content.split(/(\[\[REF:[^\]]+\]\])/g);

    // Simple markdown parsing for bold, lists, etc.
    const parseSimpleMarkdown = (text: string) => {
      // Bold
      let parsed = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
      // Line breaks for lists
      parsed = parsed.replace(/^- /gm, '• ');
      return parsed;
    };

    return (
      <div className="text-sm text-slate-700 leading-relaxed">
        {parts.map((part, idx) => {
          const match = part.match(/\[\[REF:([^\]]+)\]\]/);
          if (match) {
            const refId = match[1];
            const reference = references[refId];
            return <VerifiedBadge key={idx} refId={refId} reference={reference} />;
          }
          // Render text with simple markdown parsing
          return (
            <span
              key={idx}
              dangerouslySetInnerHTML={{ __html: parseSimpleMarkdown(part) }}
            />
          );
        })}
      </div>
    );
  };

  // Handler for selecting a detail from the chat
  const handleSelectDetail = (detail: SelectedDetail, idx: number) => {
    // Toggle off if clicking the same item
    if (selectedDetailIdx === idx) {
      setSelectedDetail(null);
      setSelectedDetailIdx(null);
    } else {
      setSelectedDetail(detail);
      setSelectedDetailIdx(idx);
    }
  };

  const handleCloseDetail = () => {
    setSelectedDetail(null);
    setSelectedDetailIdx(null);
  };

  // Handler for confirming an inference as a learned rule (Active Learning)
  const handleConfirmInference = async (inferenceLogic: string, contextText: string) => {
    try {
      const response = await fetch(apiUrl("/api/learn_rule"), authFetch({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          trigger_text: contextText,
          rule_text: inferenceLogic,
          context: `Confirmed from chat conversation`,
          confirmed_by: "expert"
        }),
      }));

      if (!response.ok) {
        throw new Error("Failed to save rule");
      }

      const result = await response.json();
      console.log("Rule learned:", result);

      // Mark this inference as confirmed
      if (selectedDetailIdx !== null) {
        setConfirmedInferences(prev => {
          const newSet = new Set(Array.from(prev));
          newSet.add(selectedDetailIdx);
          return newSet;
        });
      }

      // Show success feedback (could use a toast library)
      // For now, the UI will update to show the confirmed state

    } catch (error) {
      console.error("Failed to confirm inference:", error);
      // Could show an error toast here
    }
  };

  // Per-judge expert review submission
  const handleJudgeReview = async (msgIndex: number, provider: string, score: "thumbs_up" | "thumbs_down") => {
    // Optimistically update UI
    setMessages((prev) =>
      prev.map((m, i) => {
        if (i !== msgIndex) return m;
        const reviews = { ...(m.judgeReviews || {}) };
        reviews[provider] = score;
        return { ...m, judgeReviews: reviews };
      })
    );
    // Calculate turn number from message index (count assistant messages up to and including this one)
    const turnNumber = messages.slice(0, msgIndex + 1).filter(m => m.role === "assistant").length;
    try {
      await submitExpertReview(getSessionId(), {
        comment: "",
        overall_score: score,
        provider,
        turn_number: turnNumber,
      });
    } catch (err) {
      console.error("Failed to submit judge review:", err);
      // Revert on failure
      setMessages((prev) =>
        prev.map((m, i) => {
          if (i !== msgIndex) return m;
          const reviews = { ...(m.judgeReviews || {}) };
          delete reviews[provider];
          return { ...m, judgeReviews: reviews };
        })
      );
    }
  };

  return (
    <div className="flex gap-4">
      {/* Main Chat Panel */}
      <div className={cn(
        "bg-white dark:bg-slate-900 rounded-2xl shadow-xl shadow-slate-200/50 dark:shadow-slate-900/50 border border-slate-200/60 dark:border-slate-700/60 overflow-hidden transition-all duration-300",
        explainableMode && expertMode ? "flex-1" : "w-full"
      )}>
      {/* Messages */}
      <ScrollArea className="h-[calc(100vh-280px)]" ref={scrollRef}>
        <div className="p-6 space-y-6">
          {messages.length === 0 && (
            <div className="text-center py-16">
              <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-blue-100 to-violet-100 dark:from-blue-900/50 dark:to-violet-900/50 flex items-center justify-center">
                <Bot className="w-8 h-8 text-blue-600 dark:text-blue-400" />
              </div>
              <h3 className="font-semibold text-slate-900 dark:text-slate-100 mb-2">
                How can I help you today?
              </h3>
              <p className="text-sm text-slate-500 dark:text-slate-400 max-w-md mx-auto mb-4">
                Ask me about past engineering cases, product recommendations, or
                technical decisions from our knowledge base.
              </p>
              <button
                onClick={() => { setInput("I need a GDB housing, size 600x600, Galvanized FZ, airflow 2500 m\u00B3/h."); inputRef.current?.focus(); }}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm text-slate-600 dark:text-slate-400 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl hover:bg-blue-50 dark:hover:bg-blue-900/30 hover:border-blue-300 dark:hover:border-blue-700 hover:text-blue-700 dark:hover:text-blue-400 transition-all shadow-sm"
              >
                <MessageSquare className="w-3.5 h-3.5" />
                I need a GDB housing, size 600x600, Galvanized FZ, airflow 2500 m&sup3;/h.
              </button>
              {/* Explainable mode hint */}
              {explainableMode && (
                <div className="mt-4 inline-flex items-center gap-2 px-3 py-1.5 bg-emerald-50 border border-emerald-200 rounded-full">
                  <span className="text-xs text-emerald-700">
                    <strong>Explainable Mode ON</strong> - Click underlined text to see sources
                  </span>
                </div>
              )}
            </div>
          )}

          {messages.map((message, index) => (
            <div
              key={index}
              className={cn(
                "flex gap-4 animate-fade-in",
                message.role === "user" ? "flex-row-reverse" : ""
              )}
            >
              {/* Avatar */}
              <div
                className={cn(
                  "flex-shrink-0 w-9 h-9 rounded-xl flex items-center justify-center",
                  message.role === "user"
                    ? "bg-gradient-to-br from-blue-600 to-blue-700"
                    : "bg-gradient-to-br from-slate-100 to-slate-200 dark:from-slate-700 dark:to-slate-800"
                )}
              >
                {message.role === "user" ? (
                  <User className="w-4 h-4 text-white" />
                ) : (
                  <Bot className="w-4 h-4 text-slate-600 dark:text-slate-300" />
                )}
              </div>

              {/* Message Content */}
              <div
                className={cn(
                  "flex-1 max-w-[85%]",
                  message.role === "user" ? "flex justify-end" : ""
                )}
              >
                <div className="space-y-3">
                  {/* ========== 0. STATUS BADGES (Resolved states at very top) ========== */}
                  {message.role === "assistant" && message.deepExplainableData?.status_badges && message.deepExplainableData.status_badges.length > 0 && (
                    <StatusBadges badges={message.deepExplainableData.status_badges} />
                  )}
                  {/* Fallback: show compliance badge if risk_resolved but no status_badges */}
                  {message.role === "assistant" && message.deepExplainableData?.risk_resolved && !message.deepExplainableData?.risk_detected && (!message.deepExplainableData?.status_badges || message.deepExplainableData.status_badges.length === 0) && (
                    <ComplianceBadge />
                  )}

                  {/* ========== 1. REASONING TIMELINE (Collapsible) ========== */}
                  {message.role === "assistant" && message.deepExplainableData && (
                    <ThinkingTimeline
                      steps={message.deepExplainableData.reasoning_summary}
                      defaultCollapsed={true}
                    />
                  )}

                  {/* ========== 2. ACTIVE RISK ALERT (After timeline, before content) ========== */}
                  {message.role === "assistant" && message.deepExplainableData?.risk_detected && (
                    <RiskDetectedBanner
                      warnings={message.deepExplainableData.policy_warnings}
                      severity={message.deepExplainableData.risk_severity}
                    />
                  )}

                  {/* Legacy Explainable Mode: Reasoning Chain */}
                  {message.role === "assistant" && message.explainableData && !message.deepExplainableData && (
                    <ReasoningChain
                      chain={message.explainableData.reasoning_chain}
                      graphCount={message.explainableData.graph_facts_count}
                      llmCount={message.explainableData.llm_inferences_count}
                      defaultCollapsed={false}
                    />
                  )}

                  {/* ========== 2. TEXT CONTENT (The Explanation) ========== */}
                  <div
                    className={cn(
                      "relative group",
                      message.role === "user"
                        ? "rounded-2xl px-4 py-3 bg-gradient-to-br from-blue-600 to-blue-700 text-white"
                        : message.deepExplainableData
                          ? "rounded-xl px-4 py-3 bg-slate-50/80 dark:bg-slate-800/80"
                          : "rounded-2xl px-4 py-3 bg-slate-50 dark:bg-slate-800 border border-slate-100 dark:border-slate-700"
                    )}
                  >
                    {message.role === "assistant" ? (
                      <div className={cn(
                        message.deepExplainableData
                          ? "" // No prose wrapper for clean look
                          : "prose-chat"
                      )}>
                        {(message.deepExplainableData?.content_segments?.length ?? 0) > 0 ? (
                          // Deep Explainable: Clean, Perplexity-style render
                          <ExplainableChatBubble
                            segments={message.deepExplainableData!.content_segments}
                            expertMode={false}
                            selectedDetailIdx={selectedDetailIdx}
                            onSelectDetail={handleSelectDetail}
                            onConfirmInference={handleConfirmInference}
                            confirmedInferences={confirmedInferences}
                          />
                        ) : message.explainableData ? (
                          // Legacy: Render with [[REF:ID]] markers
                          <VerifiedMarkdownRenderer
                            content={message.content}
                            references={message.explainableData.references}
                          />
                        ) : (
                          <ReactMarkdown>{message.content}</ReactMarkdown>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm whitespace-pre-wrap">
                        {message.content}
                      </p>
                    )}
                  </div>

                  {/* ========== 3. INTERACTIVE WIDGET (Action - directly after text) ========== */}
                  {/* Clarification Form */}
                  {message.role === "assistant" && message.deepExplainableData?.clarification_needed && message.deepExplainableData?.clarification && (
                    <div className="mt-3">
                      <ClarificationCard
                        clarification={message.deepExplainableData.clarification}
                        onOptionSelect={(value, description) => {
                          const displayValue = description ? `${value} (${description})` : value;
                          // Route through streaming endpoint (sendMessage) for graph-reasoning/neuro-symbolic
                          // to ensure state management, airflow extraction, and session persistence
                          const useStreaming = chatMode === "graph-reasoning" || chatMode === "neuro-symbolic";
                          if (useStreaming) {
                            sendMessage(displayValue);
                          } else if (pendingClarificationContext) {
                            const fullContext = `${pendingClarificationContext.originalQuery}. Context Update: ${pendingClarificationContext.missingAttribute} is ${value}.`;
                            sendClarificationResponse(displayValue, fullContext);
                          } else {
                            setInput(value);
                          }
                        }}
                      />
                    </div>
                  )}

                  {/* Product Card(s) — supports multi-card assembly output */}
                  {message.role === "assistant" &&
                   !message.deepExplainableData?.clarification_needed &&
                   (message.deepExplainableData?.product_cards?.length || message.deepExplainableData?.product_card) && (
                    <div className="mt-3 space-y-3">
                      {(message.deepExplainableData.product_cards && message.deepExplainableData.product_cards.length > 0)
                        ? message.deepExplainableData.product_cards.map((card, i) => (
                            <ProductCardComponent
                              key={i}
                              card={card}
                              riskSeverity={
                                // Multi-card assembly = risk is resolved by the assembly itself
                                message.deepExplainableData!.product_cards!.length > 1
                                  ? undefined
                                  : message.deepExplainableData!.risk_severity
                              }
                              onAction={(action) => console.log("Action:", action, card.title)}
                            />
                          ))
                        : message.deepExplainableData?.product_card && (
                            <ProductCardComponent
                              card={message.deepExplainableData.product_card}
                              riskSeverity={message.deepExplainableData.risk_severity}
                              onAction={(action) => console.log("Action:", action)}
                            />
                          )
                      }
                    </div>
                  )}

                  {/* Deep Explainable Mode: Policy Warnings (only if not risk_detected to avoid duplication) */}
                  {message.role === "assistant" &&
                   message.deepExplainableData &&
                   !message.deepExplainableData.risk_detected &&
                   message.deepExplainableData.policy_warnings &&
                   message.deepExplainableData.policy_warnings.length > 0 && (
                    <div className="space-y-2">
                      {message.deepExplainableData.policy_warnings.filter(w => w && w !== "null" && w !== "None").map((warning, idx) => (
                        <PolicyWarning key={idx} warning={warning} />
                      ))}
                    </div>
                  )}

                  {/* Legacy Explainable Mode: Policy Warnings */}
                  {message.role === "assistant" && !message.deepExplainableData && message.explainableData && message.explainableData.policy_warnings && message.explainableData.policy_warnings.length > 0 && (
                    <div className="space-y-2">
                      {message.explainableData.policy_warnings.filter(w => w && w !== "null" && w !== "None").map((warning, idx) => (
                        <PolicyWarning key={idx} warning={warning} />
                      ))}
                    </div>
                  )}

                  {/* Render widgets for assistant messages */}
                  {message.role === "assistant" && message.widgets && (
                    <WidgetList widgets={message.widgets} onProjectClick={handleProjectClick} />
                  )}

                  {/* ========== JUDGE VERDICT (Auto, Graph Reasoning only) ========== */}
                  {message.role === "assistant" && message.chatMode === "graph-reasoning" && (message.judgeLoading || message.judgeResult) && (
                    <JudgeBadge
                      result={message.judgeResult}
                      loading={message.judgeLoading}
                      judgeReviews={message.judgeReviews}
                      onJudgeReview={(provider, score) => handleJudgeReview(index, provider, score)}
                    />
                  )}

                  {/* Mode-specific panels (always shown) */}
                  {message.role === "assistant" && message.chatMode === "llm-driven" && (
                    <LlmDiagnosticsPanel
                      promptPreview={message.promptPreview}
                      diagnostics={message.diagnostics}
                    />
                  )}
                  {message.role === "assistant" && message.chatMode === "graphrag" && message.graphPaths && (
                    <GraphTraversalPanel
                      graphPaths={message.graphPaths}
                      diagnostics={message.diagnostics}
                      promptPreview={message.promptPreview}
                    />
                  )}

                  {/* Dev Mode: Graph Paths & Prompt fallback (for messages without chatMode) */}
                  {devMode && message.role === "assistant" && !message.chatMode && (message.graphPaths || message.promptPreview) && (
                    <DevModePanel
                      graphPaths={message.graphPaths}
                      promptPreview={message.promptPreview}
                    />
                  )}

                </div>
              </div>
            </div>
          ))}

          {/* Reasoning indicator */}
          {isLoading && (
            <div className="flex gap-4 animate-fade-in">
              <div className="flex-shrink-0 w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
                <Brain className="w-4 h-4 text-white animate-pulse" />
              </div>
              <div className="bg-gradient-to-br from-slate-50 to-blue-50/30 dark:from-slate-800 dark:to-blue-900/20 border border-blue-100/50 dark:border-blue-800/50 rounded-2xl px-4 py-3 min-w-[320px] max-w-[420px]">
                <div className="text-xs font-medium text-blue-600 dark:text-blue-400 mb-3 flex items-center gap-1.5">
                  {chatMode === "llm-driven" && <><Cpu className="w-3 h-3" /> LLM Processing...</>}
                  {chatMode === "graphrag" && <><Database className="w-3 h-3" /> LLM + Graph Data Analysis...</>}
                  {chatMode === "graph-reasoning" && <><Network className="w-3 h-3" /> Graph Reasoning Engine...</>}
                  {chatMode === "neuro-symbolic" && <><Brain className="w-3 h-3" /> Neuro-Symbolic Reasoning...</>}
                </div>
                <div className="space-y-3">
                  {reasoningSteps.map((step) => (
                    <div key={step.id} className="flex items-start gap-2">
                      <span className="w-4 h-4 flex items-center justify-center flex-shrink-0 mt-0.5">
                        {step.status === "done" ? (
                          <span className="text-emerald-500 text-sm">✓</span>
                        ) : step.status === "active" ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />
                        ) : (
                          <span className="w-1.5 h-1.5 rounded-full bg-slate-300 dark:bg-slate-600" />
                        )}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div
                          className={cn(
                            "text-sm transition-all duration-300",
                            step.status === "active" && "text-blue-700 dark:text-blue-400 font-medium",
                            step.status === "done" && "text-slate-700 dark:text-slate-300",
                            step.status === "pending" && "text-slate-400 dark:text-slate-500"
                          )}
                        >
                          {step.label}
                        </div>
                        {/* Show concepts found */}
                        {step.status === "done" && step.data?.concepts && step.data.concepts.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {step.data.concepts.map((concept, i) => (
                              <span key={i} className="px-1.5 py-0.5 bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400 rounded text-[10px] font-medium">
                                {concept}
                              </span>
                            ))}
                          </div>
                        )}
                        {/* Show actions/findings */}
                        {step.status === "done" && step.data?.actions && step.data.actions.length > 0 && (
                          <div className="mt-1.5 space-y-1">
                            {step.data.actions.slice(0, 2).map((action, i) => (
                              <div key={i} className="text-[11px] text-slate-600 dark:text-slate-400 flex items-start gap-1">
                                <span className="text-slate-400 dark:text-slate-500">→</span>
                                <span>{action}</span>
                              </div>
                            ))}
                          </div>
                        )}
                        {/* Show citation as key evidence */}
                        {step.status === "done" && step.data?.citations && step.data.citations.length > 0 && (
                          <div className="mt-1.5 px-2 py-1.5 bg-amber-50 dark:bg-amber-900/20 border-l-2 border-amber-400 dark:border-amber-600 rounded text-[11px] text-amber-800 dark:text-amber-300 italic">
                            &quot;{step.data.citations[0]}&quot;
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
                {/* Total time summary when all steps done */}
                {reasoningSteps.every(s => s.status === "done") && (
                  <div className="mt-3 pt-2 border-t border-slate-200/50 dark:border-slate-700/50 flex items-center justify-between text-[10px] text-slate-500 dark:text-slate-400">
                    <span>Total pipeline time</span>
                    <span className="font-mono">
                      {(() => {
                        // Extract times from detail strings like "Vector ready (0.5s)"
                        let total = 0;
                        reasoningSteps.forEach(s => {
                          const match = s.detail?.match(/\((\d+\.?\d*)s\)/);
                          if (match) total += parseFloat(match[1]);
                        });
                        return total > 0 ? `${total.toFixed(1)}s` : "—";
                      })()}
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Session Graph Panel (collapsible) */}
      {showSessionGraph && sessionGraphState && (
        <div className="border-t border-cyan-200 bg-gradient-to-b from-slate-900 to-slate-950">
          <SessionGraphViewer
            sessionState={sessionGraphState}
            height={320}
            onRefresh={async () => {
              const state = await getSessionGraphState();
              if (state) setSessionGraphState(state);
            }}
          />
        </div>
      )}

      {/* Input */}
      <div className="p-4 border-t border-slate-100 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50">
        {/* Dev Mode: Sample Questions - Collapsible Dropdowns */}
        {devMode && sampleQuestions && (
          <DevModeQuestions
            sampleQuestions={sampleQuestions}
            onSelectQuestion={(q) => setInput(q)}
          />
        )}
        {/* Session Graph Toggle + Context indicators hidden for clean UI */}
        <div className="flex gap-3 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder="Ask about past cases, products, or decisions..."
            rows={1}
            className="flex-1 px-4 py-3 text-sm bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl resize-none focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 dark:focus:border-blue-500 placeholder:text-slate-400 dark:placeholder:text-slate-500 dark:text-slate-100"
            disabled={isLoading}
          />
          {messages.length > 0 && (
            <Button
              onClick={exportConversation}
              variant="outline"
              className="h-[42px] w-[42px] p-0 flex-shrink-0 rounded-xl border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 hover:border-slate-300 dark:hover:border-slate-600"
              title="Export conversation (JSON)"
            >
              <Download className="w-4 h-4 text-slate-500 dark:text-slate-400" />
            </Button>
          )}
          <Button
            onClick={sendMessage}
            disabled={isLoading || !input.trim()}
            className="h-[42px] w-[42px] p-0 flex-shrink-0 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 shadow-lg shadow-blue-500/25 rounded-xl"
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </Button>
        </div>
        <p className="mt-2 text-[10px] text-center text-slate-400 dark:text-slate-500">
          Press Enter to send, Shift+Enter for new line
        </p>
      </div>

      {/* Thread Inspector Sheet for Deep Dive */}
      <ThreadInspectorSheet
        isOpen={inspectorOpen}
        onClose={() => setInspectorOpen(false)}
        projectName={inspectorProject}
      />
      </div>

      {/* Detail Panel - Right Side (only in explainable + expert mode) */}
      {explainableMode && expertMode && (
        <div className="w-[320px] flex-shrink-0 bg-white dark:bg-slate-900 rounded-2xl shadow-xl shadow-slate-200/50 dark:shadow-slate-900/50 border border-slate-200/60 dark:border-slate-700/60 overflow-hidden">
          <DetailPanel
            detail={selectedDetail}
            onClose={handleCloseDetail}
            onConfirmInference={handleConfirmInference}
            isConfirmed={selectedDetailIdx !== null && confirmedInferences.has(selectedDetailIdx)}
          />
        </div>
      )}
    </div>
  );
});
