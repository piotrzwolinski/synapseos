"use client";

import { useState, useRef, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Play,
  Check,
  X,
  ChevronRight,
  ChevronDown,
  Loader2,
  Sparkles,
  MessageSquare,
  Merge,
  AlertCircle,
  CheckCircle2,
  RotateCcw,
} from "lucide-react";
import { apiUrl, authFetch } from "@/lib/api";

// ─── Types ──────────────────────────────────────────────────────

interface Assertion {
  name: string;
  check: string;
  condition: string;
  expected: string;
  category: string;
}

interface ProposedTest {
  id: string;
  name: string;
  description: string;
  category: string;
  query: string;
  pdf_reference?: string;
  assertions: Assertion[];
  consensus_score: number;
  proposed_by: string;
  critique_notes?: string;
}

interface ProviderStatus {
  name: string;
  label: string;
  phase: string;
  status: "idle" | "active" | "complete" | "error";
  testCount: number;
  duration: number;
  error?: string;
}

interface DebateSummary {
  total_tests: number;
  high_consensus: number;
  categories: string[];
  providers_used: string[];
  duration_s: number;
}

interface ProviderKeyStatus {
  provider: string;
  label: string;
  configured: boolean;
  masked_key: string | null;
}

type WizardStep = "configure" | "debate" | "review";

// ─── Category colors ────────────────────────────────────────────

const CATEGORY_COLORS: Record<string, string> = {
  env: "bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400",
  assembly: "bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-500",
  atex: "bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400",
  sizing: "bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-500",
  material: "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400",
  positive: "bg-teal-100 dark:bg-teal-900/30 text-teal-700 dark:text-teal-400",
  clarification: "bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400",
};

const PROVIDER_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  openai: { bg: "bg-green-50 dark:bg-green-900/20", text: "text-green-700 dark:text-green-400", border: "border-green-200 dark:border-green-800" },
  gemini: { bg: "bg-green-50 dark:bg-green-900/20", text: "text-green-800 dark:text-green-500", border: "border-green-200 dark:border-green-800" },
  anthropic: { bg: "bg-orange-50 dark:bg-orange-900/20", text: "text-orange-700 dark:text-orange-400", border: "border-orange-200 dark:border-orange-800" },
};

// ─── Component ──────────────────────────────────────────────────

export function TestGenerator() {
  // Wizard state
  const [step, setStep] = useState<WizardStep>("configure");

  // Configure state
  const [providerKeys, setProviderKeys] = useState<ProviderKeyStatus[]>([]);
  const [selectedProviders, setSelectedProviders] = useState<Set<string>>(new Set());
  const [targetCount, setTargetCount] = useState(15);
  const [categoryFocus, setCategoryFocus] = useState<string>("");

  // Debate state
  const [debatePhase, setDebatePhase] = useState<string>("idle");
  const [providerStatuses, setProviderStatuses] = useState<Record<string, ProviderStatus>>({});
  const [debateLog, setDebateLog] = useState<{ type: string; provider?: string; message: string; time: number }[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Review state
  const [finalTests, setFinalTests] = useState<ProposedTest[]>([]);
  const [selectedTests, setSelectedTests] = useState<Set<string>>(new Set());
  const [expandedTest, setExpandedTest] = useState<string | null>(null);
  const [summary, setSummary] = useState<DebateSummary | null>(null);
  const [approving, setApproving] = useState(false);
  const [approveResult, setApproveResult] = useState<{ added: number; total: number } | null>(null);

  // Error state
  const [error, setError] = useState<string | null>(null);

  const logRef = useRef<HTMLDivElement>(null);

  // ─── Effects ────────────────────────────────────────────────────

  useEffect(() => {
    fetchProviderKeys();
  }, []);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [debateLog]);

  // ─── API calls ──────────────────────────────────────────────────

  const fetchProviderKeys = async () => {
    try {
      const res = await fetch(apiUrl("/config/api-keys"), authFetch());
      const data: ProviderKeyStatus[] = await res.json();
      setProviderKeys(data);
      const configured = new Set(data.filter((k) => k.configured).map((k) => k.provider));
      setSelectedProviders(configured);
    } catch {
      console.error("Failed to fetch provider keys");
    }
  };

  // ─── Debate streaming ──────────────────────────────────────────

  const startDebate = async () => {
    if (selectedProviders.size === 0) return;

    setStep("debate");
    setIsStreaming(true);
    setError(null);
    setDebateLog([]);
    setDebatePhase("starting");
    setProviderStatuses({});
    setFinalTests([]);
    setSummary(null);

    const formData = new FormData();
    formData.append(
      "config",
      JSON.stringify({
        selected_providers: Array.from(selectedProviders),
        target_test_count: targetCount,
        category_focus: categoryFocus || undefined,
      })
    );

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(apiUrl("/test-generator/debate/stream"), {
        ...authFetch({ method: "POST", body: formData }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || `HTTP ${res.status}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
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
              handleDebateEvent(event);
            } catch {
              // Skip malformed events
            }
          }
        }
      }
    } catch (e: any) {
      if (e.name !== "AbortError") {
        setError(e.message);
        addLog("error", undefined, `Debate failed: ${e.message}`);
      }
    } finally {
      setIsStreaming(false);
      abortRef.current = null;
    }
  };

  const handleDebateEvent = (event: any) => {
    const now = Date.now();

    switch (event.type) {
      case "debate_start":
        setDebatePhase("generation");
        addLog("system", undefined, `Debate started with ${event.providers?.length} providers`);
        break;

      case "phase":
        setDebatePhase(event.phase);
        if (event.status === "started") {
          addLog("system", undefined, `${phaseLabel(event.phase)} started${event.description ? `: ${event.description}` : ""}`);
        } else if (event.status === "complete") {
          addLog("system", undefined, `${phaseLabel(event.phase)} complete${event.data?.total_proposals ? ` (${event.data.total_proposals} proposals)` : ""}`);
        } else if (event.status === "skipped") {
          addLog("system", undefined, `${phaseLabel(event.phase)} skipped: ${event.description}`);
        }
        break;

      case "provider_progress":
        setProviderStatuses((prev) => ({
          ...prev,
          [event.provider]: {
            ...prev[event.provider],
            name: event.provider,
            label: providerLabel(event.provider),
            phase: event.phase,
            status: event.status,
            testCount: event.data?.test_count ?? prev[event.provider]?.testCount ?? 0,
            duration: event.data?.duration_s ?? prev[event.provider]?.duration ?? 0,
          },
        }));
        break;

      case "proposal":
        addLog("proposal", event.provider, `Proposed ${event.test_count} test cases (${event.duration_s}s)`);
        setProviderStatuses((prev) => ({
          ...prev,
          [event.provider]: {
            ...prev[event.provider],
            name: event.provider,
            label: providerLabel(event.provider),
            phase: "generation",
            status: "complete",
            testCount: event.test_count,
            duration: event.duration_s,
          },
        }));
        break;

      case "critique":
        addLog(
          "critique",
          event.critic,
          `Reviewed ${event.critiques_count} tests (avg score: ${event.average_score}/5), proposed ${event.missing_tests_proposed} new gaps`
        );
        break;

      case "provider_error":
        addLog("error", event.provider, `Error in ${event.phase}: ${event.error}`);
        setProviderStatuses((prev) => ({
          ...prev,
          [event.provider]: {
            ...prev[event.provider],
            name: event.provider,
            label: providerLabel(event.provider),
            phase: event.phase,
            status: "error",
            testCount: prev[event.provider]?.testCount ?? 0,
            duration: prev[event.provider]?.duration ?? 0,
            error: event.error,
          },
        }));
        break;

      case "result":
        setFinalTests(event.tests || []);
        setSummary(event.summary || null);
        // Auto-select high consensus tests
        const highConsensus = new Set<string>(
          (event.tests || [])
            .filter((t: ProposedTest) => (t.consensus_score ?? 0) >= 0.7)
            .map((t: ProposedTest) => t.id)
        );
        setSelectedTests(highConsensus);
        addLog("system", undefined, `Synthesis complete: ${event.tests?.length} final tests (${event.summary?.high_consensus} high consensus)`);
        break;

      case "debate_complete":
        setDebatePhase("complete");
        setStep("review");
        addLog("system", undefined, `Debate finished in ${event.duration_s}s`);
        break;

      case "error":
        setError(event.detail);
        addLog("error", undefined, event.detail);
        break;
    }
  };

  const addLog = (type: string, provider: string | undefined, message: string) => {
    setDebateLog((prev) => [...prev, { type, provider, message, time: Date.now() }]);
  };

  // ─── Approve ────────────────────────────────────────────────────

  const approveSelected = async () => {
    const tests = finalTests.filter((t) => selectedTests.has(t.id));
    if (tests.length === 0) return;

    setApproving(true);
    try {
      const res = await fetch(
        apiUrl("/test-generator/approve"),
        authFetch({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tests }),
        })
      );
      const data = await res.json();
      setApproveResult(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setApproving(false);
    }
  };

  // ─── Helpers ────────────────────────────────────────────────────

  const phaseLabel = (phase: string) => {
    switch (phase) {
      case "generation": return "Round 1: Generation";
      case "critique": return "Round 2: Critique";
      case "synthesis": return "Round 3: Synthesis";
      default: return phase;
    }
  };

  const providerLabel = (name: string) => {
    switch (name) {
      case "openai": return "GPT-5.2";
      case "gemini": return "Gemini";
      case "anthropic": return "Claude";
      default: return name;
    }
  };

  const toggleTest = (id: string) => {
    setSelectedTests((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAllHighConsensus = () => {
    const ids = finalTests.filter((t) => (t.consensus_score ?? 0) >= 0.7).map((t) => t.id);
    setSelectedTests(new Set(ids));
  };

  const scoreColor = (score: number) => {
    if (score >= 0.8) return "text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/30";
    if (score >= 0.5) return "text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/30";
    return "text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30";
  };

  // ─── Wizard Steps ───────────────────────────────────────────────

  const steps: { key: WizardStep; label: string; icon: React.ReactNode }[] = [
    { key: "configure", label: "Configure", icon: <Sparkles className="w-4 h-4" /> },
    { key: "debate", label: "Debate", icon: <MessageSquare className="w-4 h-4" /> },
    { key: "review", label: "Review", icon: <Check className="w-4 h-4" /> },
  ];

  const canProceed = () => {
    switch (step) {
      case "configure": return selectedProviders.size > 0;
      default: return false;
    }
  };

  // ─── Render ─────────────────────────────────────────────────────

  return (
    <div className="h-full flex flex-col">
      {/* Wizard Progress Bar */}
      <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-700 bg-white/50 dark:bg-slate-800/50">
        <div className="flex items-center gap-2">
          {steps.map((s, i) => (
            <div key={s.key} className="flex items-center">
              {i > 0 && <ChevronRight className="w-4 h-4 text-slate-300 mx-1" />}
              <button
                onClick={() => {
                  // Allow going back but not forward past current
                  const currentIdx = steps.findIndex((st) => st.key === step);
                  const targetIdx = i;
                  if (targetIdx <= currentIdx) setStep(s.key);
                }}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                  step === s.key
                    ? "bg-green-100 dark:bg-green-950/30 text-green-800 dark:text-green-500"
                    : steps.findIndex((st) => st.key === step) > i
                    ? "bg-green-50 dark:bg-green-900/30 text-green-600 dark:text-green-400"
                    : "bg-slate-50 dark:bg-slate-800 text-slate-400"
                }`}
              >
                {s.icon}
                {s.label}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="p-6 max-w-5xl mx-auto space-y-6">
          {error && (
            <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-red-500" />
              <span className="text-sm text-red-700 dark:text-red-400">{error}</span>
              <button onClick={() => setError(null)} className="ml-auto">
                <X className="w-4 h-4 text-red-400" />
              </button>
            </div>
          )}

          {/* ═══ Step 1: Configure ═══ */}
          {step === "configure" && (
            <div className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-200">Configure Debate</h2>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                  Select which LLMs participate in the debate. Each will analyze the product catalog PDF and independently propose test cases.
                </p>
              </div>

              {/* Provider selection */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">LLM Participants</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {providerKeys.map((pk) => {
                    const colors = PROVIDER_COLORS[pk.provider] || PROVIDER_COLORS.openai;
                    return (
                      <div
                        key={pk.provider}
                        className={`flex items-center justify-between p-3 rounded-lg border ${
                          pk.configured ? colors.border : "border-slate-200"
                        } ${pk.configured ? colors.bg : "bg-slate-50 dark:bg-slate-800 opacity-60"}`}
                      >
                        <div className="flex items-center gap-3">
                          <input
                            type="checkbox"
                            checked={selectedProviders.has(pk.provider)}
                            disabled={!pk.configured}
                            onChange={() => {
                              setSelectedProviders((prev) => {
                                const next = new Set(prev);
                                if (next.has(pk.provider)) next.delete(pk.provider);
                                else next.add(pk.provider);
                                return next;
                              });
                            }}
                            className="w-4 h-4 accent-green-700"
                          />
                          <div>
                            <span className={`text-sm font-medium ${pk.configured ? colors.text : "text-slate-400"}`}>
                              {pk.label}
                            </span>
                            {pk.configured ? (
                              <Badge className="ml-2 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 text-xs border-0">Ready</Badge>
                            ) : (
                              <Badge className="ml-2 bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400 text-xs border-0">No env var</Badge>
                            )}
                          </div>
                        </div>
                        {pk.masked_key && (
                          <span className="text-xs font-mono text-slate-400">{pk.masked_key}</span>
                        )}
                      </div>
                    );
                  })}
                  {providerKeys.filter((k) => k.configured).length === 0 && (
                    <p className="text-sm text-amber-600 dark:text-amber-400 p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg">
                      No API keys detected. Set environment variables: <code className="font-mono text-xs bg-amber-100 dark:bg-amber-900/40 px-1 rounded">OPENAI_API_KEY</code>, <code className="font-mono text-xs bg-amber-100 dark:bg-amber-900/40 px-1 rounded">ANTHROPIC_API_KEY</code>, <code className="font-mono text-xs bg-amber-100 dark:bg-amber-900/40 px-1 rounded">GEMINI_API_KEY</code>
                    </p>
                  )}
                </CardContent>
              </Card>

              {/* Options */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Options</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <label className="text-sm font-medium text-slate-700 dark:text-slate-300 block mb-1">
                      Target test count: {targetCount}
                    </label>
                    <input
                      type="range"
                      min={5}
                      max={30}
                      value={targetCount}
                      onChange={(e) => setTargetCount(Number(e.target.value))}
                      className="w-full accent-green-700"
                    />
                    <div className="flex justify-between text-xs text-slate-400">
                      <span>5</span>
                      <span>30</span>
                    </div>
                  </div>
                  <div>
                    <label className="text-sm font-medium text-slate-700 dark:text-slate-300 block mb-1">
                      Category focus (optional)
                    </label>
                    <div className="flex flex-wrap gap-2">
                      {["", "env", "assembly", "sizing", "material", "atex", "positive", "clarification"].map((cat) => (
                        <button
                          key={cat}
                          onClick={() => setCategoryFocus(cat)}
                          className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                            categoryFocus === cat
                              ? "bg-green-700 text-white"
                              : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700"
                          }`}
                        >
                          {cat || "All categories"}
                        </button>
                      ))}
                    </div>
                  </div>
                </CardContent>
              </Card>

              <div className="flex justify-end">
                <button
                  onClick={startDebate}
                  disabled={selectedProviders.size === 0}
                  className="px-6 py-2 rounded-lg bg-green-700 text-white font-medium text-sm hover:bg-green-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
                >
                  <Play className="w-4 h-4" />
                  Start Debate ({selectedProviders.size} LLMs)
                </button>
              </div>
            </div>
          )}

          {/* ═══ Step 3: Debate (Live Stream) ═══ */}
          {step === "debate" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-200">Multi-LLM Debate</h2>
                  <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                    {isStreaming ? "Debate in progress..." : "Debate complete"}
                  </p>
                </div>
                {isStreaming && (
                  <button
                    onClick={() => abortRef.current?.abort()}
                    className="px-3 py-1.5 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm font-medium hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
                  >
                    Stop
                  </button>
                )}
              </div>

              {/* Phase indicator */}
              <div className="flex items-center gap-4">
                {["generation", "critique", "synthesis"].map((phase, i) => (
                  <div key={phase} className="flex items-center gap-2">
                    {i > 0 && <div className="w-8 h-px bg-slate-300 dark:bg-slate-600" />}
                    <div
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium ${
                        debatePhase === phase
                          ? "bg-green-100 dark:bg-green-950/30 text-green-800 dark:text-green-500 ring-2 ring-green-300 dark:ring-green-700"
                          : debatePhase === "complete" || steps.findIndex((s) => s.key === "debate") < ["generation", "critique", "synthesis"].indexOf(debatePhase)
                          ? "bg-green-50 dark:bg-green-900/30 text-green-600 dark:text-green-400"
                          : "bg-slate-100 dark:bg-slate-800 text-slate-400"
                      }`}
                    >
                      {phase === "generation" && <Sparkles className="w-3 h-3" />}
                      {phase === "critique" && <MessageSquare className="w-3 h-3" />}
                      {phase === "synthesis" && <Merge className="w-3 h-3" />}
                      {phaseLabel(phase)}
                    </div>
                  </div>
                ))}
              </div>

              {/* Provider cards */}
              <div className="grid grid-cols-3 gap-3">
                {Object.values(providerStatuses).map((ps) => {
                  const colors = PROVIDER_COLORS[ps.name] || PROVIDER_COLORS.openai;
                  return (
                    <Card key={ps.name} className={`${colors.border} border`}>
                      <CardContent className="p-4">
                        <div className="flex items-center justify-between mb-2">
                          <span className={`text-sm font-semibold ${colors.text}`}>{ps.label}</span>
                          {ps.status === "active" && <Loader2 className="w-4 h-4 animate-spin text-green-600" />}
                          {ps.status === "complete" && <CheckCircle2 className="w-4 h-4 text-green-500" />}
                          {ps.status === "error" && <AlertCircle className="w-4 h-4 text-red-500" />}
                        </div>
                        <div className="text-xs text-slate-500 dark:text-slate-400">
                          {ps.status === "active" && `${ps.phase}...`}
                          {ps.status === "complete" && `${ps.testCount} tests (${ps.duration}s)`}
                          {ps.status === "error" && <span className="text-red-500">{ps.error}</span>}
                          {ps.status === "idle" && "Waiting..."}
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>

              {/* Event log */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Debate Timeline</CardTitle>
                </CardHeader>
                <CardContent>
                  <div ref={logRef} className="max-h-80 overflow-y-auto space-y-1.5">
                    {debateLog.map((entry, i) => {
                      const provColors = entry.provider ? PROVIDER_COLORS[entry.provider] : null;
                      return (
                        <div key={i} className="flex items-start gap-2 text-xs">
                          <span className="text-slate-400 font-mono w-16 flex-shrink-0">
                            {new Date(entry.time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                          </span>
                          {entry.provider && (
                            <Badge className={`text-[10px] ${provColors?.bg || ""} ${provColors?.text || ""} border-0 flex-shrink-0`}>
                              {providerLabel(entry.provider)}
                            </Badge>
                          )}
                          <span className={`${entry.type === "error" ? "text-red-600 dark:text-red-400" : "text-slate-700 dark:text-slate-300"}`}>
                            {entry.message}
                          </span>
                        </div>
                      );
                    })}
                    {isStreaming && (
                      <div className="flex items-center gap-2 text-xs text-green-600">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        <span>Streaming...</span>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Auto-advance to review when done */}
              {debatePhase === "complete" && finalTests.length > 0 && (
                <div className="flex justify-end">
                  <button
                    onClick={() => setStep("review")}
                    className="px-4 py-2 rounded-lg bg-green-700 text-white font-medium text-sm hover:bg-green-800 transition-colors"
                  >
                    Review {finalTests.length} Test Cases
                  </button>
                </div>
              )}
            </div>
          )}

          {/* ═══ Step 4: Review & Approve ═══ */}
          {step === "review" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-200">Review Generated Tests</h2>
                  <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                    {selectedTests.size} of {finalTests.length} selected
                    {summary && ` | ${summary.high_consensus} high consensus | ${summary.duration_s}s total`}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={selectAllHighConsensus}
                    className="px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 text-xs font-medium hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
                  >
                    Select High Consensus (&ge;0.7)
                  </button>
                  <button
                    onClick={() => setStep("debate")}
                    className="px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 text-xs font-medium hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors flex items-center gap-1"
                  >
                    <RotateCcw className="w-3 h-3" />
                    Back to Debate
                  </button>
                </div>
              </div>

              {approveResult && (
                <div className="p-3 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-green-500" />
                  <span className="text-sm text-green-700 dark:text-green-400">
                    Added {approveResult.added} test(s) to the suite ({approveResult.total} total generated tests)
                  </span>
                </div>
              )}

              {/* Test list */}
              <div className="space-y-2">
                {finalTests.map((test) => (
                  <Card
                    key={test.id}
                    className={`cursor-pointer transition-all ${
                      selectedTests.has(test.id) ? "ring-2 ring-green-300 border-green-200" : ""
                    }`}
                  >
                    <div
                      className="p-4"
                      onClick={() => setExpandedTest(expandedTest === test.id ? null : test.id)}
                    >
                      <div className="flex items-center gap-3">
                        <input
                          type="checkbox"
                          checked={selectedTests.has(test.id)}
                          onChange={(e) => { e.stopPropagation(); toggleTest(test.id); }}
                          className="w-4 h-4 accent-green-700 flex-shrink-0"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-mono font-medium text-slate-800 dark:text-slate-200 truncate">
                              {test.name}
                            </span>
                            <Badge className={`text-[10px] border-0 ${CATEGORY_COLORS[test.category] || "bg-slate-100 text-slate-600"}`}>
                              {test.category}
                            </Badge>
                            <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${scoreColor(test.consensus_score)}`}>
                              {(test.consensus_score ?? 0).toFixed(2)}
                            </span>
                            {test.proposed_by && (
                              <span className="text-[10px] text-slate-400">
                                by {providerLabel(test.proposed_by)}
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 truncate">
                            {test.description}
                          </p>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <Badge variant="outline" className="text-[10px]">
                            {test.assertions?.length || 0} assertions
                          </Badge>
                          {expandedTest === test.id ? (
                            <ChevronDown className="w-4 h-4 text-slate-400" />
                          ) : (
                            <ChevronRight className="w-4 h-4 text-slate-400" />
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Expanded detail */}
                    {expandedTest === test.id && (
                      <div className="px-4 pb-4 border-t border-slate-100 dark:border-slate-700 pt-3 space-y-3">
                        <div>
                          <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide mb-1">Query</p>
                          <p className="text-sm text-slate-800 dark:text-slate-200 bg-slate-50 dark:bg-slate-800 p-2 rounded">{test.query}</p>
                        </div>
                        {test.pdf_reference && (
                          <div>
                            <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide mb-1">PDF Reference</p>
                            <p className="text-xs text-slate-600 dark:text-slate-400">{test.pdf_reference}</p>
                          </div>
                        )}
                        {test.critique_notes && (
                          <div>
                            <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide mb-1">Critique Notes</p>
                            <p className="text-xs text-slate-600 dark:text-slate-400 italic">{test.critique_notes}</p>
                          </div>
                        )}
                        <div>
                          <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide mb-1">Assertions</p>
                          <div className="space-y-1">
                            {test.assertions?.map((a, i) => (
                              <div key={i} className="flex items-center gap-2 text-xs p-1.5 bg-slate-50 dark:bg-slate-800 rounded">
                                <Badge variant="outline" className="text-[10px]">{a.category}</Badge>
                                <span className="font-mono text-slate-700 dark:text-slate-300">{a.name}</span>
                                <span className="text-slate-400">
                                  {a.check} {a.condition} {a.expected ? `"${a.expected.slice(0, 50)}${a.expected.length > 50 ? "..." : ""}"` : ""}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </Card>
                ))}
              </div>

              {finalTests.length === 0 && (
                <div className="text-center py-12 text-slate-400">
                  <Sparkles className="w-8 h-8 mx-auto mb-2" />
                  <p className="text-sm">No test cases generated yet. Run a debate first.</p>
                </div>
              )}

              {/* Approve button */}
              {finalTests.length > 0 && !approveResult && (
                <div className="flex justify-end pt-4 border-t border-slate-200 dark:border-slate-700">
                  <button
                    onClick={approveSelected}
                    disabled={selectedTests.size === 0 || approving}
                    className="px-6 py-2.5 rounded-lg bg-green-600 text-white font-medium text-sm hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
                  >
                    {approving ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <CheckCircle2 className="w-4 h-4" />
                    )}
                    Approve {selectedTests.size} Test{selectedTests.size !== 1 ? "s" : ""} to Suite
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
