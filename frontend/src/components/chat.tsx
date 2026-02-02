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
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";
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
  ConfidenceIndicator,
  DeepExplainableResponseData,
  ReasoningSummaryStep,
  ContentSegment,
  ProductCard,
  // Autonomous Guardian - Risk Detection
  RiskDetectedBanner,
  ComplianceBadge,
  // Clarification Mode
  ClarificationCard,
  // Detail Panel
  DetailPanel,
  SelectedDetail,
} from "./reasoning-chain";

interface Message {
  role: "user" | "assistant";
  content: string;
  widgets?: Widget[];
  // Dev mode metadata
  graphPaths?: string[];
  promptPreview?: string;
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
  onQuestionConsumed?: () => void;
  explainableMode?: boolean;
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

const INITIAL_REASONING_STEPS: ReasoningStep[] = [
  { id: "embed", label: "Generating embedding", icon: "🔍", status: "pending" },
  { id: "search", label: "Searching knowledge graph", icon: "📊", status: "pending" },
  { id: "projects", label: "Finding related projects", icon: "🏷️", status: "pending" },
  { id: "context", label: "Building context", icon: "📄", status: "pending" },
  { id: "thinking", label: "AI Reasoning", icon: "🤖", status: "pending" },
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

export const Chat = forwardRef<ChatHandle, ChatProps>(function Chat(
  { devMode, sampleQuestions, externalQuestion, onQuestionConsumed, explainableMode = false, expertMode = true, onExpertModeChange },
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
        const response = await fetch("http://localhost:8000/chat/history");
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

  // Handle external question injection (from dev mode)
  useEffect(() => {
    if (externalQuestion && externalQuestion.trim()) {
      setInput(externalQuestion);
      onQuestionConsumed?.();
      // Focus the input
      inputRef.current?.focus();
    }
  }, [externalQuestion, onQuestionConsumed]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Animate reasoning steps during loading (deep-explainable is non-streaming)
  useEffect(() => {
    if (!isLoading) {
      setReasoningSteps(INITIAL_REASONING_STEPS);
      return;
    }

    const stepIds = INITIAL_REASONING_STEPS.map(s => s.id);
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
  }, [isLoading]);

  // Send a clarification response - displays short value in chat, sends full context to backend
  const sendClarificationResponse = async (displayValue: string, fullContext: string) => {
    if (isLoading) return;

    // Display the short value in chat (what user sees)
    setMessages((prev) => [...prev, { role: "user", content: displayValue }]);
    setIsLoading(true);
    setReasoningSteps(INITIAL_REASONING_STEPS);
    setSelectedDetail(null);
    setSelectedDetailIdx(null);
    setPendingClarificationContext(null);

    try {
      // Send the full context to backend (what LLM reads)
      const response = await fetch("http://localhost:8000/consult/deep-explainable", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: fullContext }),
      });

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

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    // Store the original query for potential clarification follow-up
    const lastQueryForClarification = userMessage;

    setInput("");
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
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
    }

    try {
      // Use Deep Explainable endpoint if enabled, otherwise use streaming
      if (explainableMode) {
        const response = await fetch("http://localhost:8000/consult/deep-explainable", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: userMessage }),
        });

        if (!response.ok) throw new Error("Failed to get response");

        const data: DeepExplainableResponseData = await response.json();

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
      } else {
        // Use streaming endpoint
        const response = await fetch("http://localhost:8000/chat/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: userMessage }),
        });

        if (!response.ok) throw new Error("Failed to get response");

        const reader = response.body?.getReader();
        const decoder = new TextDecoder();

        if (!reader) throw new Error("No response body");

        let finalResponse = "";
        let capturedPrompt = "";
        let capturedPaths: string[] = [];

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
                } else if (data.step === "error") {
                  // Handle API errors (rate limits, etc.)
                  throw new Error(data.detail || "An error occurred while generating response");
                } else if (data.step === "prompt" && data.prompt_preview) {
                  // Capture the prompt preview for the message
                  capturedPrompt = data.prompt_preview;
                } else if (data.step && data.status) {
                  // Capture graph paths from context step
                  if (data.step === "context" && data.data?.graph_paths) {
                    capturedPaths = data.data.graph_paths;
                  }
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
          if (trimmed.startsWith("{")) {
            const parsed = JSON.parse(trimmed);
            textContent = parsed.summary || parsed.text_summary || finalResponse;
            widgets = parsed.widgets;
          }
        } catch {
          // Not JSON, use as plain text
        }

        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: textContent,
            widgets,
            graphPaths: capturedPaths.length > 0 ? capturedPaths : undefined,
            promptPreview: capturedPrompt || undefined,
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
      await fetch("http://localhost:8000/chat/clear", { method: "POST" });
      setMessages([]);
    } catch (error) {
      console.error("Failed to clear chat:", error);
    }
  };

  const copyMessage = async (content: string, index: number) => {
    await navigator.clipboard.writeText(content);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
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
    // Auto-resize textarea
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
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
      const response = await fetch("http://localhost:8000/api/learn_rule", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          trigger_text: contextText,
          rule_text: inferenceLogic,
          context: `Confirmed from chat conversation`,
          confirmed_by: "expert"
        }),
      });

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

  return (
    <div className="flex gap-4">
      {/* Main Chat Panel */}
      <div className={cn(
        "bg-white rounded-2xl shadow-xl shadow-slate-200/50 border border-slate-200/60 overflow-hidden transition-all duration-300",
        explainableMode && expertMode ? "flex-1" : "w-full"
      )}>
      {/* Messages */}
      <ScrollArea className="h-[calc(100vh-280px)]" ref={scrollRef}>
        <div className="p-6 space-y-6">
          {messages.length === 0 && (
            <div className="text-center py-16">
              <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-blue-100 to-violet-100 flex items-center justify-center">
                <Bot className="w-8 h-8 text-blue-600" />
              </div>
              <h3 className="font-semibold text-slate-900 mb-2">
                How can I help you today?
              </h3>
              <p className="text-sm text-slate-500 max-w-md mx-auto">
                Ask me about past engineering cases, product recommendations, or
                technical decisions from our knowledge base.
              </p>
              {/* Explainable mode hint */}
              {explainableMode && (
                <div className="mt-4 inline-flex items-center gap-2 px-3 py-1.5 bg-emerald-50 border border-emerald-200 rounded-full">
                  <span className="text-xs text-emerald-700">
                    <strong>Explainable Mode ON</strong> - Click underlined text to see sources
                  </span>
                </div>
              )}
              <div className="mt-6 flex flex-wrap justify-center gap-2">
                {[
                  "I received a request from Airteam for the Huddinge Hospital project. They want standard GDB housings in Zinc (FZ) because they are budget-constrained. They didn't specify the airflow, but stated it's a standard office unit. Please help me preparing a quote.",
                ].map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => setInput(suggestion)}
                    className="px-4 py-2 text-sm rounded-full bg-slate-100 text-slate-600 hover:bg-blue-50 hover:text-blue-700 transition-colors"
                  >
                    {suggestion}
                  </button>
                ))}
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
                    ? "bg-gradient-to-br from-blue-600 to-blue-700"
                    : "bg-gradient-to-br from-slate-100 to-slate-200"
                )}
              >
                {message.role === "user" ? (
                  <User className="w-4 h-4 text-white" />
                ) : (
                  <Bot className="w-4 h-4 text-slate-600" />
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
                  {/* ========== 1. REASONING TIMELINE (Top, Collapsible) ========== */}
                  {message.role === "assistant" && message.deepExplainableData && (
                    <ThinkingTimeline
                      steps={message.deepExplainableData.reasoning_summary}
                      defaultCollapsed={true}
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
                          ? "rounded-xl px-4 py-3 bg-slate-50/80" // Subtle background for text bubble
                          : "rounded-2xl px-4 py-3 bg-slate-50 border border-slate-100"
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
                            expertMode={expertMode}
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

                  {/* ========== 3. RISK ALERT or COMPLIANCE BADGE ========== */}
                  {message.role === "assistant" && message.deepExplainableData?.risk_detected && (
                    <div className="mt-2">
                      <RiskDetectedBanner
                        warnings={message.deepExplainableData.policy_warnings}
                        severity={message.deepExplainableData.risk_severity}
                      />
                    </div>
                  )}
                  {message.role === "assistant" && message.deepExplainableData?.risk_resolved && !message.deepExplainableData?.risk_detected && (
                    <ComplianceBadge />
                  )}

                  {/* ========== 4. INTERACTIVE WIDGET (Action - Bottom) ========== */}
                  {/* Clarification Form */}
                  {message.role === "assistant" && message.deepExplainableData?.clarification_needed && message.deepExplainableData?.clarification && (
                    <div className="mt-3">
                      <ClarificationCard
                        clarification={message.deepExplainableData.clarification}
                        onOptionSelect={(value, description) => {
                          if (pendingClarificationContext) {
                            const displayValue = description ? `${value} (${description})` : value;
                            const fullContext = `${pendingClarificationContext.originalQuery}. Context Update: ${pendingClarificationContext.missingAttribute} is ${value}.`;
                            sendClarificationResponse(displayValue, fullContext);
                          } else {
                            setInput(value);
                          }
                        }}
                      />
                    </div>
                  )}

                  {/* Product Card */}
                  {message.role === "assistant" &&
                   message.deepExplainableData?.product_card &&
                   !message.deepExplainableData?.clarification_needed && (
                    <div className="mt-3">
                      <ProductCardComponent
                        card={message.deepExplainableData.product_card}
                        riskSeverity={message.deepExplainableData.risk_severity}
                        onAction={(action) => console.log("Action:", action)}
                      />
                    </div>
                  )}

                  {/* Deep Explainable Mode: Confidence & Stats - hide when clarification needed */}
                  {message.role === "assistant" &&
                   message.deepExplainableData &&
                   !message.deepExplainableData?.clarification_needed && (
                    <ConfidenceIndicator
                      level={message.deepExplainableData.confidence_level}
                      graphFacts={message.deepExplainableData.graph_facts_count}
                      inferences={message.deepExplainableData.inference_count}
                    />
                  )}

                  {/* Deep Explainable Mode: Policy Warnings (only if not risk_detected to avoid duplication) */}
                  {message.role === "assistant" &&
                   message.deepExplainableData &&
                   !message.deepExplainableData.risk_detected &&
                   message.deepExplainableData.policy_warnings &&
                   message.deepExplainableData.policy_warnings.length > 0 && (
                    <div className="space-y-2">
                      {message.deepExplainableData.policy_warnings.map((warning, idx) => (
                        <PolicyWarning key={idx} warning={warning} />
                      ))}
                    </div>
                  )}

                  {/* Legacy Explainable Mode: Policy Warnings */}
                  {message.role === "assistant" && !message.deepExplainableData && message.explainableData && message.explainableData.policy_warnings && message.explainableData.policy_warnings.length > 0 && (
                    <div className="space-y-2">
                      {message.explainableData.policy_warnings.map((warning, idx) => (
                        <PolicyWarning key={idx} warning={warning} />
                      ))}
                    </div>
                  )}

                  {/* Legacy Explainable Mode: Confidence Indicator */}
                  {message.role === "assistant" && !message.deepExplainableData && message.explainableData && (
                    <ConfidenceIndicator
                      level={message.explainableData.confidence_level}
                      graphFacts={message.explainableData.graph_facts_count}
                      inferences={message.explainableData.llm_inferences_count}
                    />
                  )}

                  {/* Render widgets for assistant messages */}
                  {message.role === "assistant" && message.widgets && (
                    <WidgetList widgets={message.widgets} onProjectClick={handleProjectClick} />
                  )}

                  {/* Dev Mode: Graph Paths & Prompt (shown after response) */}
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
              <div className="flex-shrink-0 w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
                <Brain className="w-4 h-4 text-white animate-pulse" />
              </div>
              <div className="bg-gradient-to-br from-slate-50 to-blue-50/30 border border-blue-100/50 rounded-2xl px-4 py-3 min-w-[320px] max-w-[420px]">
                <div className="text-xs font-medium text-blue-600 mb-3 flex items-center gap-1.5">
                  <Sparkles className="w-3 h-3" />
                  Searching knowledge base...
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
                          <span className="w-1.5 h-1.5 rounded-full bg-slate-300" />
                        )}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div
                          className={cn(
                            "text-sm transition-all duration-300",
                            step.status === "active" && "text-blue-700 font-medium",
                            step.status === "done" && "text-slate-700",
                            step.status === "pending" && "text-slate-400"
                          )}
                        >
                          {step.detail || step.label}
                        </div>
                        {/* Show concepts found */}
                        {step.status === "done" && step.data?.concepts && step.data.concepts.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {step.data.concepts.map((concept, i) => (
                              <span key={i} className="px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded text-[10px] font-medium">
                                {concept}
                              </span>
                            ))}
                          </div>
                        )}
                        {/* Show actions/findings */}
                        {step.status === "done" && step.data?.actions && step.data.actions.length > 0 && (
                          <div className="mt-1.5 space-y-1">
                            {step.data.actions.slice(0, 2).map((action, i) => (
                              <div key={i} className="text-[11px] text-slate-600 flex items-start gap-1">
                                <span className="text-slate-400">→</span>
                                <span>{action}</span>
                              </div>
                            ))}
                          </div>
                        )}
                        {/* Show citation as key evidence */}
                        {step.status === "done" && step.data?.citations && step.data.citations.length > 0 && (
                          <div className="mt-1.5 px-2 py-1.5 bg-amber-50 border-l-2 border-amber-400 rounded text-[11px] text-amber-800 italic">
                            &quot;{step.data.citations[0]}&quot;
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="p-4 border-t border-slate-100 bg-slate-50/50">
        {/* Dev Mode: Sample Questions - Collapsible Dropdowns */}
        {devMode && sampleQuestions && (
          <DevModeQuestions
            sampleQuestions={sampleQuestions}
            onSelectQuestion={(q) => setInput(q)}
          />
        )}
        <div className="flex items-end gap-3">
          <div className="flex-1 relative">
            <textarea
              ref={inputRef}
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              placeholder="Ask about past cases, products, or decisions..."
              rows={1}
              className="w-full px-4 py-3 pr-12 text-sm bg-white border border-slate-200 rounded-xl resize-none focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 placeholder:text-slate-400"
              disabled={isLoading}
            />
          </div>
          <Button
            onClick={sendMessage}
            disabled={isLoading || !input.trim()}
            className="h-[46px] px-4 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 shadow-lg shadow-blue-500/25 rounded-xl"
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </Button>
        </div>
        <p className="mt-2 text-[10px] text-center text-slate-400">
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
        <div className="w-[320px] flex-shrink-0 bg-white rounded-2xl shadow-xl shadow-slate-200/50 border border-slate-200/60 overflow-hidden">
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
