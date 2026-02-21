"use client";

import { useState, useRef, useEffect, forwardRef, useImperativeHandle } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Send,
  Loader2,
  Bot,
  User,
  Copy,
  Check,
  FlaskConical,
  Brain,
  ChevronDown,
  ChevronRight,
  Code,
  Network,
  Download,
  MessageSquare,
  Scale,
  ThumbsUp,
  ThumbsDown,
  AlertTriangle,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";
import { apiUrl, authFetch, getSessionId, resetSessionId, getSessionGraphState, clearSessionGraph, type SessionGraphState, evaluateResponse, saveJudgeResults } from "@/lib/api";
import { getUserRole } from "@/lib/auth";
import SessionGraphViewer from "./session-graph-viewer";
import { Widget, BotResponse } from "./chat-widgets";
import { WidgetList } from "./chat-widgets";
import { ThreadInspectorSheet } from "./thread-inspector-sheet";
import {
  ReasoningChain,
  ReasoningStepData,
  ReferenceDetail,
  PolicyWarning,
  VerifiedBadge,
  // Deep Explainability components
  ThinkingTimeline,
  ExplainableChatBubble,
  ProductCardComponent,
  DeepExplainableResponseData,
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


interface Message {
  role: "user" | "assistant";
  content: string;
  widgets?: Widget[];
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
  expertMode?: boolean;
  onExpertModeChange?: (value: boolean) => void;
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

// Graph Reasoning uses dynamic steps from SSE - this is just a placeholder
const GRAPH_REASONING_PLACEHOLDER: ReasoningStep[] = [
  { id: "init", label: "Initializing graph reasoning engine", icon: "🔗", status: "pending" },
];

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
    gradient: "from-green-600 to-emerald-500",
    hoverGradient: "hover:from-green-700 hover:to-emerald-600",
    textColor: "text-green-800 dark:text-green-400",
    bgColor: "bg-green-50 dark:bg-green-900/20",
    borderColor: "border-green-200 dark:border-green-800",
  },
  huddinge: {
    label: "Huddinge Hospital",
    icon: <span className="text-sm">🏥</span>,
    gradient: "from-emerald-500 to-teal-500",
    hoverGradient: "hover:from-emerald-600 hover:to-teal-600",
    textColor: "text-emerald-700 dark:text-emerald-400",
    bgColor: "bg-emerald-50 dark:bg-emerald-900/20",
    borderColor: "border-emerald-200 dark:border-emerald-800",
  },
  nordic: {
    label: "Nordic Furniture",
    icon: <span className="text-sm">⚠️</span>,
    gradient: "from-amber-500 to-orange-500",
    hoverGradient: "hover:from-amber-600 hover:to-orange-600",
    textColor: "text-amber-700 dark:text-amber-400",
    bgColor: "bg-amber-50 dark:bg-amber-900/20",
    borderColor: "border-amber-200 dark:border-amber-800",
  },
  catalog: {
    label: "Filter Catalog",
    icon: <span className="text-sm">📄</span>,
    gradient: "from-green-600 to-green-700",
    hoverGradient: "hover:from-green-700 hover:to-green-800",
    textColor: "text-green-800 dark:text-green-400",
    bgColor: "bg-green-50 dark:bg-green-900/20",
    borderColor: "border-green-200 dark:border-green-800",
  },
  housing: {
    label: "Housing Selection",
    icon: <span className="text-sm">🏗️</span>,
    gradient: "from-rose-500 to-pink-500",
    hoverGradient: "hover:from-rose-600 hover:to-pink-600",
    textColor: "text-rose-700 dark:text-rose-400",
    bgColor: "bg-rose-50 dark:bg-rose-900/20",
    borderColor: "border-rose-200 dark:border-rose-800",
  },
  maritime: {
    label: "Maritime / Offshore",
    icon: <span className="text-sm">⚓</span>,
    gradient: "from-green-500 to-emerald-500",
    hoverGradient: "hover:from-green-600 hover:to-emerald-600",
    textColor: "text-sky-700 dark:text-sky-400",
    bgColor: "bg-sky-50 dark:bg-sky-900/20",
    borderColor: "border-sky-200 dark:border-sky-800",
  },
  guardian: {
    label: "Guardian Tests",
    icon: <span className="text-sm">🛡️</span>,
    gradient: "from-red-500 to-orange-500",
    hoverGradient: "hover:from-red-600 hover:to-orange-600",
    textColor: "text-red-700 dark:text-red-400",
    bgColor: "bg-red-50 dark:bg-red-900/20",
    borderColor: "border-red-200 dark:border-red-800",
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
        <span className="text-xs font-semibold text-amber-700 dark:text-amber-400">Test Questions</span>
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
                        "bg-white/60 dark:bg-slate-800/60 hover:bg-white dark:hover:bg-slate-700 border",
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

// Judge single result type (mirrors api.ts)
interface JudgeSingleResult {
  scores?: Record<string, number>;
  overall_score?: number;
  explanation?: string;
  recommendation?: string;
  strengths?: string[];
  weaknesses?: string[];
}

// Judge Results Panel (inline under each assistant message)
function JudgeResultsPanel({ results }: { results: Record<string, JudgeSingleResult> }) {
  const [expanded, setExpanded] = useState(false);
  const providers = Object.entries(results).filter(([, v]) => v && v.recommendation);

  if (providers.length === 0) return null;

  const recIcon = (rec: string) => {
    if (rec === "PASS") return <ThumbsUp className="w-3.5 h-3.5 text-emerald-600" />;
    if (rec === "FAIL") return <ThumbsDown className="w-3.5 h-3.5 text-red-500" />;
    return <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />;
  };

  const recColor = (rec: string) => {
    if (rec === "PASS") return "bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-400";
    if (rec === "FAIL") return "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-700 dark:text-red-400";
    return "bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-400";
  };

  const providerLabel: Record<string, string> = { gemini: "Gemini", openai: "GPT", anthropic: "Claude" };

  return (
    <div className="space-y-2">
      {/* Summary chips */}
      <div className="flex items-center gap-2 flex-wrap">
        <Scale className="w-3.5 h-3.5 text-violet-500" />
        {providers.map(([name, result]) => (
          <span
            key={name}
            className={cn(
              "inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-md border",
              recColor(result.recommendation || "")
            )}
          >
            {recIcon(result.recommendation || "")}
            {providerLabel[name] || name}: {result.overall_score?.toFixed(1)} ({result.recommendation})
          </span>
        ))}
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 ml-1"
        >
          {expanded ? "Hide details" : "Details"}
        </button>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          {providers.map(([name, result]) => (
            <div key={name} className="bg-slate-50 dark:bg-slate-800/50 rounded-lg p-3 text-xs space-y-2 border border-slate-200 dark:border-slate-700">
              <div className="font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                {recIcon(result.recommendation || "")}
                {providerLabel[name] || name}
              </div>
              {result.scores && (
                <div className="grid grid-cols-2 gap-1">
                  {Object.entries(result.scores).map(([dim, score]) => (
                    <div key={dim} className="flex justify-between">
                      <span className="text-slate-500 dark:text-slate-400 capitalize">{dim.replace(/_/g, " ")}</span>
                      <span className={cn(
                        "font-mono font-medium",
                        (score as number) >= 4 ? "text-emerald-600" : (score as number) >= 3 ? "text-amber-600" : "text-red-500"
                      )}>{String(score)}/5</span>
                    </div>
                  ))}
                </div>
              )}
              {result.explanation && (
                <p className="text-slate-600 dark:text-slate-400 leading-relaxed">{result.explanation}</p>
              )}
              {result.strengths && result.strengths.length > 0 && (
                <div>
                  <span className="text-emerald-600 font-medium">+</span>{" "}
                  {result.strengths.join("; ")}
                </div>
              )}
              {result.weaknesses && result.weaknesses.length > 0 && (
                <div>
                  <span className="text-red-500 font-medium">−</span>{" "}
                  {result.weaknesses.join("; ")}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
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
                ? "bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-400"
                : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-green-50 dark:hover:bg-green-900/20 hover:text-green-700 dark:hover:text-green-500"
            )}
          >
            {showPaths ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            Graph Paths ({graphPaths.length})
          </button>
          {showPaths && (
            <div className="absolute left-0 top-full mt-1 z-10 w-[400px] max-h-[300px] overflow-auto bg-white dark:bg-slate-800 border border-green-200 dark:border-green-800 rounded-lg shadow-lg p-2 space-y-1">
              {graphPaths.map((path, i) => (
                <div key={i} className="px-2 py-1.5 bg-green-50 dark:bg-green-900/20 border border-green-100 dark:border-green-800 rounded text-[10px] text-green-800 dark:text-green-300 font-mono leading-relaxed">
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
                : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 hover:text-slate-700 dark:hover:text-slate-300"
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

export const Chat = forwardRef<ChatHandle, ChatProps>(function Chat(
  { devMode, sampleQuestions, externalQuestion, autoSubmit, onQuestionConsumed, expertMode = true, onExpertModeChange },
  ref
) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [reasoningSteps, setReasoningSteps] = useState<ReasoningStep[]>(GRAPH_REASONING_PLACEHOLDER);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [inspectorProject, setInspectorProject] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<SelectedDetail | null>(null);
  const [selectedDetailIdx, setSelectedDetailIdx] = useState<number | null>(null);
  // Track confirmed inferences (for Active Learning)
  const [confirmedInferences, setConfirmedInferences] = useState<Set<number>>(new Set());
  // Judge evaluation state (per message index)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [judgeResults, setJudgeResults] = useState<Record<number, any>>({});
  const [judgingIndex, setJudgingIndex] = useState<number | null>(null);
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
    // Steps are dynamically pushed from SSE — just reset placeholder when not loading
    if (!isLoading) {
      setReasoningSteps(GRAPH_REASONING_PLACEHOLDER);
      return;
    }
    setReasoningSteps(GRAPH_REASONING_PLACEHOLDER);
  }, [isLoading]);

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
    setReasoningSteps(GRAPH_REASONING_PLACEHOLDER);
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
      // Always use graph reasoning streaming endpoint
      const streamUrl = "/consult/deep-explainable/stream";
      const token = localStorage.getItem("mh_auth_token");
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

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: contentText,
          deepExplainableData: data,
        },
      ]);
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

  const clearChat = async () => {
    try {
      await fetch(apiUrl(`/session/${getSessionId()}`), authFetch({
        method: "DELETE",
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
      chat_mode: "graph-reasoning",
      session_graph: sessionGraphState || null,
      locked_context: lockedContext || null,
      technical_state: technicalState || null,
      turns: messages.map((msg, idx) => {
        const turn: Record<string, unknown> = {
          turn: idx + 1,
          role: msg.role,
          content: msg.content,
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
      <div className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">
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

  // Handler: Run 3-LLM judge evaluation on an assistant response
  const handleRunJudge = async (messageIndex: number) => {
    // Find the user question (previous message)
    const userMsg = messages.slice(0, messageIndex).reverse().find(m => m.role === "user");
    const assistantMsg = messages[messageIndex];
    if (!userMsg || !assistantMsg) return;

    // Build conversation_history from all messages up to and including this response
    const conversationHistory = messages.slice(0, messageIndex + 1).map(msg => {
      const turn: Record<string, unknown> = {
        role: msg.role,
        content: msg.content,
      };
      if (msg.role === "assistant" && msg.deepExplainableData) {
        const d = msg.deepExplainableData;
        turn.product_card = d.product_card || null;
        turn.product_cards = d.product_cards || [];
        turn.status_badges = d.status_badges || [];
      }
      return turn;
    });

    // Build response_data in the shape _build_judge_prompt expects
    const d = assistantMsg.deepExplainableData;
    const responseData: Record<string, unknown> = {
      conversation_history: conversationHistory,
      content_text: assistantMsg.content,
      product_card: d?.product_card || null,
      product_cards: d?.product_cards || [],
    };

    setJudgingIndex(messageIndex);
    try {
      const result = await evaluateResponse(userMsg.content, responseData);
      setJudgeResults(prev => ({ ...prev, [messageIndex]: result }));

      // Persist to graph session
      try {
        const sessionId = getSessionId();
        const turnNumber = Math.floor(messageIndex / 2);
        await saveJudgeResults(sessionId, turnNumber, result as unknown as Record<string, unknown>);
      } catch { /* non-fatal */ }
    } catch (err) {
      console.error("Judge evaluation failed:", err);
      setJudgeResults(prev => ({ ...prev, [messageIndex]: { error: String(err) } }));
    } finally {
      setJudgingIndex(null);
    }
  };

  return (
    <div className="flex gap-4">
      {/* Main Chat Panel */}
      <div className={cn(
        "bg-white dark:bg-slate-900 rounded-2xl shadow-xl shadow-slate-200/50 dark:shadow-slate-900/50 border border-slate-200/60 dark:border-slate-700/60 overflow-hidden transition-all duration-300",
        expertMode ? "flex-1" : "w-full"
      )}>
      {/* Messages */}
      <ScrollArea className="h-[calc(100vh-280px)]" ref={scrollRef}>
        <div className="p-6 space-y-6">
          {messages.length === 0 && (
            <div className="text-center py-16">
              <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-green-100 to-green-50 dark:from-green-900/50 dark:to-green-900/50 flex items-center justify-center">
                <Bot className="w-8 h-8 text-green-700 dark:text-green-400" />
              </div>
              <h3 className="font-semibold text-slate-900 dark:text-slate-100 mb-2">
                How can I help you today?
              </h3>
              <p className="text-sm text-slate-500 dark:text-slate-400 max-w-md mx-auto mb-4">
                Ask me about past engineering cases, product recommendations, or
                technical decisions from our knowledge base.
              </p>
              <div className="flex flex-col items-center gap-2">
                <button
                  onClick={() => { setInput("I need a GDB housing, size 600x600, Galvanized FZ, airflow 2500 m\u00B3/h."); inputRef.current?.focus(); }}
                  className="inline-flex items-center gap-2 px-4 py-2 text-sm text-slate-600 dark:text-slate-400 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl hover:bg-green-50 dark:hover:bg-green-900/30 hover:border-green-300 dark:hover:border-green-700 hover:text-green-800 dark:hover:text-green-400 transition-all shadow-sm"
                >
                  <MessageSquare className="w-3.5 h-3.5" />
                  I need a GDB housing, size 600x600, Galvanized FZ, airflow 2500 m&sup3;/h.
                </button>
                <button
                  onClick={() => { setInput("Surgical ward supply air. Airflow: 3400 m\u00B3/h. Duct 600x600 mm. Can we use GDB-FZ?"); inputRef.current?.focus(); }}
                  className="inline-flex items-center gap-2 px-4 py-2 text-sm text-slate-600 dark:text-slate-400 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl hover:bg-green-50 dark:hover:bg-green-900/30 hover:border-green-300 dark:hover:border-green-700 hover:text-green-800 dark:hover:text-green-400 transition-all shadow-sm"
                >
                  <MessageSquare className="w-3.5 h-3.5" />
                  Surgical ward supply air. Airflow: 3400 m&sup3;/h. Duct 600x600 mm. Can we use GDB-FZ?
                </button>
              </div>
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
                    ? "bg-gradient-to-br from-green-700 to-green-800"
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
                        ? "rounded-2xl px-4 py-3 bg-gradient-to-br from-green-700 to-green-800 text-white"
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
                          sendMessage(displayValue);
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


                  {/* Judge Evaluation Button + Results */}
                  {message.role === "assistant" && message.deepExplainableData && (
                    <div className="flex items-center gap-2">
                      {judgingIndex === index ? (
                        <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-violet-50 dark:bg-violet-900/20 border border-violet-100 dark:border-violet-800 text-[11px] text-violet-500 dark:text-violet-400">
                          <Loader2 className="w-3 h-3 animate-spin" />
                          Judging...
                        </div>
                      ) : judgeResults[index] && !judgeResults[index].error ? (
                        <JudgeResultsPanel results={judgeResults[index]} />
                      ) : (
                        <button
                          onClick={() => handleRunJudge(index)}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:bg-violet-50 dark:hover:bg-violet-900/20 hover:border-violet-200 dark:hover:border-violet-800 hover:text-violet-600 dark:hover:text-violet-400 transition-colors"
                        >
                          <Scale className="w-3 h-3" />
                          Judge
                        </button>
                      )}
                    </div>
                  )}

                  {/* Dev Mode: Graph Paths & Prompt */}
                  {devMode && message.role === "assistant" && (message.graphPaths || message.promptPreview) && (
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
              <div className="flex-shrink-0 w-9 h-9 rounded-xl bg-gradient-to-br from-green-600 to-green-700 flex items-center justify-center shadow-lg shadow-green-600/20">
                <Brain className="w-4 h-4 text-white animate-pulse" />
              </div>
              <div className="bg-gradient-to-br from-slate-50 to-green-50/30 dark:from-slate-800 dark:to-green-900/20 border border-green-100/50 dark:border-green-800/50 rounded-2xl px-4 py-3 min-w-[320px] max-w-[420px]">
                <div className="text-xs font-medium text-green-700 dark:text-green-400 mb-3 flex items-center gap-1.5">
                  <><Network className="w-3 h-3" /> Graph Reasoning Engine...</>
                </div>
                <div className="space-y-3">
                  {reasoningSteps.map((step) => (
                    <div key={step.id} className="flex items-start gap-2">
                      <span className="w-4 h-4 flex items-center justify-center flex-shrink-0 mt-0.5">
                        {step.status === "done" ? (
                          <span className="text-emerald-500 text-sm">✓</span>
                        ) : step.status === "active" ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin text-green-600" />
                        ) : (
                          <span className="w-1.5 h-1.5 rounded-full bg-slate-300 dark:bg-slate-600" />
                        )}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div
                          className={cn(
                            "text-sm transition-all duration-300",
                            step.status === "active" && "text-green-800 dark:text-green-400 font-medium",
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
                              <span key={i} className="px-1.5 py-0.5 bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-400 rounded text-[10px] font-medium">
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
        <div className="border-t border-green-200 bg-gradient-to-b from-slate-900 to-slate-950">
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
            className="flex-1 px-4 py-3 text-sm bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl resize-none focus:outline-none focus:ring-2 focus:ring-green-600/20 focus:border-green-600 dark:focus:border-green-600 placeholder:text-slate-400 dark:placeholder:text-slate-500 dark:text-slate-100"
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
            className="h-[42px] w-[42px] p-0 flex-shrink-0 bg-gradient-to-r from-green-700 to-green-800 hover:from-green-800 hover:to-green-900 shadow-lg shadow-green-700/25 rounded-xl"
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

      {/* Detail Panel - Right Side (expert mode) */}
      {expertMode && (
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
