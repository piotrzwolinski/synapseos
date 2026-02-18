"use client";

import { useState, useRef, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Play,
  Check,
  X,
  Loader2,
  AlertTriangle,
  AlertCircle,
  CheckCircle2,
  Info,
  ChevronRight,
  Download,
  Search,
  RotateCcw,
  Shield,
  Eye,
} from "lucide-react";
import { apiUrl, authFetch } from "@/lib/api";
import type { GraphAuditFinding, GraphAuditReport, GraphAuditReportMeta } from "@/lib/api";
import { cn } from "@/lib/utils";

// ─── Types ──────────────────────────────────────────────────────

interface ProviderKeyStatus {
  provider: string;
  label: string;
  configured: boolean;
  masked_key: string | null;
}

interface ProviderStatus {
  name: string;
  label: string;
  phase: string;
  status: "idle" | "active" | "complete" | "error";
  findingsCount: number;
  overallScore: number;
  duration: number;
  error?: string;
}

interface AuditSummary {
  total_findings: number;
  overall_score: number;
  confidence: number;
  severity_breakdown: Record<string, number>;
  providers_used: string[];
  critiques_completed: string[];
  synthesizer: string;
  duration_s: number;
  report_file: string;
}

type WizardStep = "configure" | "debate" | "results";

// ─── Constants ──────────────────────────────────────────────────

const SEVERITY_CONFIG: Record<string, { color: string; icon: React.ComponentType<{ className?: string }>; order: number }> = {
  CRITICAL: { color: "bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 border-red-200 dark:border-red-800", icon: X, order: 0 },
  MAJOR: { color: "bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400 border-orange-200 dark:border-orange-800", icon: AlertTriangle, order: 1 },
  MINOR: { color: "bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400 border-yellow-200 dark:border-yellow-800", icon: AlertCircle, order: 2 },
  INFO: { color: "bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-500 border-green-200 dark:border-green-800", icon: Info, order: 3 },
};

const PROVIDER_LABELS: Record<string, string> = {
  gemini_pro: "Gemini 3 Pro",
  openai: "GPT-5.2",
  anthropic_opus: "Claude Opus 4.6",
};

const PROVIDER_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  openai: { bg: "bg-green-50 dark:bg-green-900/30", text: "text-green-700 dark:text-green-400", border: "border-green-200 dark:border-green-800" },
  gemini_pro: { bg: "bg-green-50 dark:bg-green-900/30", text: "text-green-800 dark:text-green-500", border: "border-green-200 dark:border-green-800" },
  anthropic_opus: { bg: "bg-orange-50 dark:bg-orange-900/30", text: "text-orange-700 dark:text-orange-400", border: "border-orange-200 dark:border-orange-800" },
};

const PHASE_LABELS: Record<string, string> = {
  audit: "Round 1: Independent Audit",
  critique: "Round 2: Cross-Critique",
  synthesis: "Round 3: Consensus Synthesis",
};

// ─── Component ──────────────────────────────────────────────────

export function GraphAudit() {
  // Wizard state
  const [step, setStep] = useState<WizardStep>("configure");

  // Configure state
  const [providerKeys, setProviderKeys] = useState<ProviderKeyStatus[]>([]);
  const [selectedProviders, setSelectedProviders] = useState<Set<string>>(new Set());

  // Debate state
  const [debatePhase, setDebatePhase] = useState<string>("idle");
  const [providerStatuses, setProviderStatuses] = useState<Record<string, ProviderStatus>>({});
  const [debateLog, setDebateLog] = useState<{ type: string; provider?: string; message: string; time: number }[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Results state
  const [report, setReport] = useState<GraphAuditReport | null>(null);
  const [summary, setSummary] = useState<AuditSummary | null>(null);
  const [selectedFinding, setSelectedFinding] = useState<GraphAuditFinding | null>(null);
  const [severityFilter, setSeverityFilter] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // Previous reports
  const [previousReports, setPreviousReports] = useState<GraphAuditReportMeta[]>([]);

  // Error state
  const [error, setError] = useState<string | null>(null);

  const logRef = useRef<HTMLDivElement>(null);

  // ─── Effects ────────────────────────────────────────────────────

  useEffect(() => {
    fetchProviderKeys();
    fetchPreviousReports();
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
      // Map standard providers to audit providers
      const auditMap: Record<string, string> = { gemini: "gemini_pro", openai: "openai", anthropic: "anthropic_opus" };
      const configured = new Set<string>();
      for (const k of data) {
        if (k.configured && auditMap[k.provider]) {
          configured.add(auditMap[k.provider]);
        }
      }
      setSelectedProviders(configured);
    } catch {
      console.error("Failed to fetch provider keys");
    }
  };

  const fetchPreviousReports = async () => {
    try {
      const res = await fetch(apiUrl("/graph-audit/results/list"), authFetch());
      if (res.ok) {
        const data = await res.json();
        setPreviousReports(data);
      }
    } catch {
      // Non-fatal
    }
  };

  // ─── Debate streaming ──────────────────────────────────────────

  const addLog = (type: string, provider: string | undefined, message: string) => {
    setDebateLog((prev) => [...prev, { type, provider, message, time: Date.now() }]);
  };

  const startAudit = async () => {
    if (selectedProviders.size === 0) return;

    setStep("debate");
    setIsStreaming(true);
    setError(null);
    setDebateLog([]);
    setDebatePhase("starting");
    setProviderStatuses({});
    setReport(null);
    setSummary(null);
    setSelectedFinding(null);

    const formData = new FormData();
    formData.append(
      "config",
      JSON.stringify({
        selected_providers: Array.from(selectedProviders),
        audit_scope: "full",
      })
    );

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(apiUrl("/graph-audit/debate/stream"), {
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
              handleAuditEvent(event);
            } catch {
              // Skip malformed events
            }
          }
        }
      }
    } catch (e: unknown) {
      const err = e as Error;
      if (err.name !== "AbortError") {
        setError(err.message);
        addLog("error", undefined, `Audit failed: ${err.message}`);
      }
    } finally {
      setIsStreaming(false);
      abortRef.current = null;
    }
  };

  const handleAuditEvent = (event: Record<string, unknown>) => {
    switch (event.type) {
      case "audit_start":
        setDebatePhase("audit");
        addLog("system", undefined, `Audit debate started with ${(event.providers as string[])?.length} providers`);
        break;

      case "phase": {
        const phase = event.phase as string;
        setDebatePhase(phase);
        if (event.status === "started") {
          addLog("system", undefined, `${PHASE_LABELS[phase] || phase} started`);
        } else if (event.status === "complete") {
          const data = event.data as Record<string, unknown> | undefined;
          addLog("system", undefined, `${PHASE_LABELS[phase] || phase} complete${data?.total_findings ? ` (${data.total_findings} findings)` : ""}`);
        } else if (event.status === "skipped") {
          addLog("system", undefined, `${PHASE_LABELS[phase] || phase} skipped: ${event.description}`);
        }
        break;
      }

      case "provider_progress": {
        const provName = event.provider as string;
        const data = event.data as Record<string, unknown> | undefined;
        setProviderStatuses((prev) => ({
          ...prev,
          [provName]: {
            ...prev[provName],
            name: provName,
            label: PROVIDER_LABELS[provName] || provName,
            phase: event.phase as string,
            status: event.status as "idle" | "active" | "complete" | "error",
            findingsCount: (data?.findings_count as number) ?? prev[provName]?.findingsCount ?? 0,
            overallScore: (data?.overall_score as number) ?? prev[provName]?.overallScore ?? 0,
            duration: (data?.duration_s as number) ?? prev[provName]?.duration ?? 0,
          },
        }));
        break;
      }

      case "audit_finding": {
        const provName = event.provider as string;
        addLog("finding", provName, `Found ${event.findings_count} findings (score: ${event.overall_score}/100, ${event.duration_s}s)`);
        break;
      }

      case "critique_result":
        addLog("critique", event.critic as string, `Confirmed ${event.confirmed_count}, challenged ${event.challenged_count}, added ${event.new_count} new (${event.duration_s}s)`);
        break;

      case "provider_error":
        addLog("error", event.provider as string, `Error in ${event.phase}: ${event.error}`);
        setProviderStatuses((prev) => ({
          ...prev,
          [event.provider as string]: {
            ...prev[event.provider as string],
            name: event.provider as string,
            label: PROVIDER_LABELS[event.provider as string] || (event.provider as string),
            phase: event.phase as string,
            status: "error",
            findingsCount: 0,
            overallScore: 0,
            duration: 0,
            error: event.error as string,
          },
        }));
        break;

      case "result": {
        const reportData = event.report as GraphAuditReport;
        const summaryData = event.summary as AuditSummary;
        setReport(reportData);
        setSummary(summaryData);
        setStep("results");
        addLog("system", undefined, `Consensus report ready: ${summaryData.total_findings} findings, score ${summaryData.overall_score}/100`);
        break;
      }

      case "audit_complete":
        addLog("system", undefined, `Audit complete in ${event.duration_s}s`);
        fetchPreviousReports();
        break;

      case "error":
        setError(event.detail as string);
        addLog("error", undefined, event.detail as string);
        break;
    }
  };

  const stopAudit = () => {
    abortRef.current?.abort();
    setIsStreaming(false);
  };

  // ─── Filtering ──────────────────────────────────────────────────

  const filteredFindings = (report?.findings || []).filter((f) => {
    if (severityFilter && f.severity !== severityFilter) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        f.description.toLowerCase().includes(q) ||
        f.product_family.toLowerCase().includes(q) ||
        f.category.toLowerCase().includes(q)
      );
    }
    return true;
  });

  // ─── Score color ────────────────────────────────────────────────

  const scoreColor = (score: number) => {
    if (score >= 80) return "text-emerald-600 dark:text-emerald-400";
    if (score >= 60) return "text-yellow-600 dark:text-yellow-400";
    return "text-red-600 dark:text-red-400";
  };

  const scoreBg = (score: number) => {
    if (score >= 80) return "bg-emerald-50 dark:bg-emerald-900/30 border-emerald-200 dark:border-emerald-800";
    if (score >= 60) return "bg-yellow-50 dark:bg-yellow-900/30 border-yellow-200 dark:border-yellow-800";
    return "bg-red-50 dark:bg-red-900/30 border-red-200 dark:border-red-800";
  };

  // ─── Render ─────────────────────────────────────────────────────

  return (
    <div className="h-full flex flex-col gap-4">
      {/* Step indicator */}
      <div className="flex items-center gap-2 text-sm">
        {(["configure", "debate", "results"] as WizardStep[]).map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            {i > 0 && <ChevronRight className="w-4 h-4 text-slate-300 dark:text-slate-600" />}
            <button
              onClick={() => {
                if (s === "configure" && !isStreaming) setStep(s);
                if (s === "results" && report) setStep(s);
              }}
              className={cn(
                "px-3 py-1.5 rounded-lg font-medium transition-colors",
                step === s
                  ? "bg-green-700 text-white"
                  : s === "configure" || (s === "results" && report)
                    ? "text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700/50 cursor-pointer"
                    : "text-slate-300 dark:text-slate-600 cursor-default"
              )}
            >
              {s === "configure" && "1. Configure"}
              {s === "debate" && "2. Debate"}
              {s === "results" && "3. Results"}
            </button>
          </div>
        ))}
      </div>

      {/* ── STEP 1: Configure ─────────────────────────────────────── */}
      {step === "configure" && (
        <div className="space-y-6">
          <Card>
            <CardContent className="p-6 space-y-4">
              <h3 className="font-semibold text-slate-900 dark:text-slate-100">Select LLM Auditors</h3>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Choose which LLMs will independently audit the knowledge graph against the product catalog PDF.
                All three run in parallel, then cross-critique each other, and finally synthesize a consensus report.
              </p>

              <div className="grid grid-cols-3 gap-3">
                {[
                  { id: "gemini_pro", key: "gemini" },
                  { id: "openai", key: "openai" },
                  { id: "anthropic_opus", key: "anthropic" },
                ].map(({ id, key }) => {
                  const keyInfo = providerKeys.find((k) => k.provider === key);
                  const configured = keyInfo?.configured ?? false;
                  const selected = selectedProviders.has(id);
                  const colors = PROVIDER_COLORS[id] || { bg: "bg-slate-50 dark:bg-slate-800", text: "text-slate-700 dark:text-slate-300", border: "border-slate-200 dark:border-slate-700" };

                  return (
                    <button
                      key={id}
                      onClick={() => {
                        if (!configured) return;
                        const next = new Set(selectedProviders);
                        if (next.has(id)) next.delete(id);
                        else next.add(id);
                        setSelectedProviders(next);
                      }}
                      disabled={!configured}
                      className={cn(
                        "p-4 rounded-xl border-2 transition-all text-left",
                        !configured && "opacity-40 cursor-not-allowed",
                        configured && selected && `${colors.bg} ${colors.border}`,
                        configured && !selected && "border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600"
                      )}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className={cn("font-semibold text-sm", selected ? colors.text : "text-slate-700 dark:text-slate-300")}>
                          {PROVIDER_LABELS[id]}
                        </span>
                        {selected && <Check className={cn("w-4 h-4", colors.text)} />}
                      </div>
                      <div className="text-xs text-slate-500 dark:text-slate-400">
                        {configured ? (
                          <span className="flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                            API key configured
                          </span>
                        ) : (
                          <span className="flex items-center gap-1">
                            <X className="w-3 h-3 text-red-400" />
                            Not configured
                          </span>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>

              <button
                onClick={startAudit}
                disabled={selectedProviders.size === 0}
                className={cn(
                  "w-full py-3 rounded-xl font-semibold text-white transition-all flex items-center justify-center gap-2",
                  selectedProviders.size > 0
                    ? "bg-green-700 hover:bg-green-800 shadow-lg shadow-green-600/25"
                    : "bg-slate-300 dark:bg-slate-700 cursor-not-allowed"
                )}
              >
                <Shield className="w-5 h-5" />
                Start Graph Audit ({selectedProviders.size} auditor{selectedProviders.size !== 1 ? "s" : ""})
              </button>
            </CardContent>
          </Card>

          {/* Previous reports */}
          {previousReports.length > 0 && (
            <Card>
              <CardContent className="p-6 space-y-3">
                <h3 className="font-semibold text-slate-900 dark:text-slate-100">Previous Audit Reports</h3>
                <div className="space-y-2">
                  {previousReports.slice(0, 5).map((r) => (
                    <button
                      key={r.filename}
                      onClick={async () => {
                        try {
                          const res = await fetch(apiUrl("/graph-audit/results"), authFetch());
                          if (res.ok) {
                            const data = await res.json();
                            setReport(data.final_report);
                            setSummary({
                              total_findings: data.final_report?.total_findings || 0,
                              overall_score: data.final_report?.overall_score || 0,
                              confidence: data.final_report?.confidence || 0,
                              severity_breakdown: {},
                              providers_used: data.meta?.providers || [],
                              critiques_completed: [],
                              synthesizer: data.meta?.synthesizer || "",
                              duration_s: data.meta?.duration_s || 0,
                              report_file: r.filename,
                            });
                            setStep("results");
                          }
                        } catch { /* non-fatal */ }
                      }}
                      className="w-full p-3 rounded-lg border border-slate-200 dark:border-slate-700 hover:border-green-300 dark:hover:border-green-700 hover:bg-green-50/50 dark:hover:bg-green-900/20 transition-all flex items-center justify-between text-left"
                    >
                      <div>
                        <div className="text-sm font-medium text-slate-700 dark:text-slate-300">
                          Score: <span className={scoreColor(r.overall_score)}>{r.overall_score}/100</span>
                          {" "}&middot;{" "}
                          {r.total_findings} findings
                        </div>
                        <div className="text-xs text-slate-400 mt-0.5">
                          {r.timestamp ? new Date(r.timestamp).toLocaleString() : r.filename}
                          {" "}&middot;{" "}
                          {r.providers.map(p => PROVIDER_LABELS[p] || p).join(", ")}
                          {" "}&middot;{" "}
                          {r.duration_s}s
                        </div>
                      </div>
                      <Eye className="w-4 h-4 text-slate-400" />
                    </button>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* ── STEP 2: Debate (live SSE) ─────────────────────────────── */}
      {step === "debate" && (
        <div className="space-y-4 flex-1 flex flex-col">
          {/* Phase progress */}
          <div className="flex items-center gap-1">
            {["audit", "critique", "synthesis"].map((phase, i) => {
              const isCurrent = debatePhase === phase;
              const isPast = ["audit", "critique", "synthesis"].indexOf(debatePhase) > i;
              return (
                <div key={phase} className="flex items-center gap-1 flex-1">
                  <div
                    className={cn(
                      "flex-1 h-2 rounded-full transition-colors",
                      isPast && "bg-emerald-400",
                      isCurrent && "bg-green-500 animate-pulse",
                      !isPast && !isCurrent && "bg-slate-200 dark:bg-slate-700"
                    )}
                  />
                  <span className={cn(
                    "text-xs font-medium whitespace-nowrap",
                    isCurrent ? "text-green-700 dark:text-green-500" : isPast ? "text-emerald-600 dark:text-emerald-400" : "text-slate-400"
                  )}>
                    {PHASE_LABELS[phase]?.replace(/Round \d: /, "") || phase}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Provider status cards */}
          <div className="grid grid-cols-3 gap-3">
            {Array.from(selectedProviders).map((name) => {
              const ps = providerStatuses[name];
              const colors = PROVIDER_COLORS[name] || { bg: "bg-slate-50 dark:bg-slate-800", text: "text-slate-700 dark:text-slate-300", border: "border-slate-200 dark:border-slate-700" };
              return (
                <div
                  key={name}
                  className={cn(
                    "p-3 rounded-xl border transition-all",
                    ps?.status === "active" && `${colors.bg} ${colors.border} border-2`,
                    ps?.status === "complete" && "bg-emerald-50 dark:bg-emerald-900/30 border-emerald-200 dark:border-emerald-800",
                    ps?.status === "error" && "bg-red-50 dark:bg-red-900/30 border-red-200 dark:border-red-800",
                    (!ps || ps.status === "idle") && "border-slate-200 dark:border-slate-700"
                  )}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium text-sm">{PROVIDER_LABELS[name] || name}</span>
                    {ps?.status === "active" && <Loader2 className="w-4 h-4 text-green-600 animate-spin" />}
                    {ps?.status === "complete" && <Check className="w-4 h-4 text-emerald-500" />}
                    {ps?.status === "error" && <X className="w-4 h-4 text-red-500" />}
                  </div>
                  <div className="text-xs text-slate-500 dark:text-slate-400">
                    {ps?.status === "active" && `${ps.phase}...`}
                    {ps?.status === "complete" && `${ps.findingsCount} findings, ${ps.duration}s`}
                    {ps?.status === "error" && (ps.error || "Failed")}
                    {(!ps || ps.status === "idle") && "Waiting..."}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Event log */}
          <div
            ref={logRef}
            className="flex-1 min-h-[300px] max-h-[500px] overflow-y-auto rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 p-4 space-y-1.5 font-mono text-xs"
          >
            {debateLog.map((log, i) => (
              <div key={i} className="flex gap-2">
                <span className="text-slate-400 shrink-0">
                  {new Date(log.time).toLocaleTimeString()}
                </span>
                {log.provider && (
                  <Badge variant="outline" className="text-[10px] py-0 px-1.5 shrink-0">
                    {PROVIDER_LABELS[log.provider] || log.provider}
                  </Badge>
                )}
                <span className={cn(
                  log.type === "error" && "text-red-600 dark:text-red-400",
                  log.type === "system" && "text-slate-600 dark:text-slate-400",
                  log.type === "finding" && "text-green-700 dark:text-green-500",
                  log.type === "critique" && "text-green-700 dark:text-green-500",
                )}>
                  {log.message}
                </span>
              </div>
            ))}
            {isStreaming && (
              <div className="flex items-center gap-2 text-green-600 pt-2">
                <Loader2 className="w-3 h-3 animate-spin" />
                <span>Processing...</span>
              </div>
            )}
          </div>

          {/* Controls */}
          <div className="flex gap-2">
            {isStreaming && (
              <button
                onClick={stopAudit}
                className="px-4 py-2 rounded-lg bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 text-sm font-medium hover:bg-red-200 dark:hover:bg-red-900/50 transition-colors"
              >
                Stop Audit
              </button>
            )}
            {!isStreaming && !report && (
              <button
                onClick={() => setStep("configure")}
                className="px-4 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 text-sm font-medium hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors flex items-center gap-1.5"
              >
                <RotateCcw className="w-4 h-4" />
                Back to Configure
              </button>
            )}
          </div>

          {error && (
            <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-400">
              {error}
            </div>
          )}
        </div>
      )}

      {/* ── STEP 3: Results ───────────────────────────────────────── */}
      {step === "results" && report && (
        <div className="flex-1 flex flex-col gap-4">
          {/* Top summary bar */}
          <div className="flex items-center gap-4 flex-wrap">
            {/* Overall score */}
            <div className={cn("px-4 py-2 rounded-xl border font-bold text-2xl", scoreBg(report.overall_score))}>
              <span className={scoreColor(report.overall_score)}>{report.overall_score}</span>
              <span className="text-sm font-normal text-slate-400">/100</span>
            </div>

            {/* Confidence */}
            {report.confidence > 0 && (
              <div className="text-sm text-slate-500 dark:text-slate-400">
                Confidence: <span className="font-semibold text-slate-700 dark:text-slate-300">{Math.round(report.confidence * 100)}%</span>
              </div>
            )}

            {/* Severity breakdown */}
            <div className="flex gap-1.5">
              {(["CRITICAL", "MAJOR", "MINOR", "INFO"] as const).map((sev) => {
                const count = report.findings.filter((f) => f.severity === sev).length;
                if (count === 0) return null;
                const cfg = SEVERITY_CONFIG[sev];
                return (
                  <button
                    key={sev}
                    onClick={() => setSeverityFilter(severityFilter === sev ? null : sev)}
                    className={cn(
                      "px-2.5 py-1 rounded-lg border text-xs font-medium transition-all",
                      cfg.color,
                      severityFilter === sev && "ring-2 ring-offset-1 ring-green-500"
                    )}
                  >
                    {count} {sev.toLowerCase()}
                  </button>
                );
              })}
            </div>

            {/* Duration & providers */}
            {summary && (
              <div className="ml-auto text-xs text-slate-400">
                {summary.providers_used.map(p => PROVIDER_LABELS[p] || p).join(" + ")}
                {" "}&middot;{" "}
                {summary.duration_s}s
              </div>
            )}

            {/* Download */}
            <button
              onClick={() => {
                const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = `graph_audit_report.json`;
                a.click();
                URL.revokeObjectURL(url);
              }}
              className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors"
              title="Download report"
            >
              <Download className="w-4 h-4" />
            </button>

            {/* New audit */}
            <button
              onClick={() => setStep("configure")}
              className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors"
              title="Run new audit"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          </div>

          {/* Two-panel layout */}
          <div className="flex-1 flex gap-4 min-h-0">
            {/* Left panel: Finding list */}
            <div className="w-[380px] flex flex-col gap-2 shrink-0">
              {/* Search */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search findings..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm focus:outline-none focus:border-green-400"
                />
              </div>

              {/* Finding list */}
              <div className="flex-1 overflow-y-auto space-y-1.5 pr-1">
                {filteredFindings.length === 0 && (
                  <div className="text-center py-8 text-sm text-slate-400">
                    No findings match your filters
                  </div>
                )}
                {filteredFindings.map((finding) => {
                  const sevCfg = SEVERITY_CONFIG[finding.severity] || SEVERITY_CONFIG.INFO;
                  const SevIcon = sevCfg.icon;
                  const isSelected = selectedFinding?.id === finding.id;
                  return (
                    <button
                      key={finding.id}
                      onClick={() => setSelectedFinding(finding)}
                      className={cn(
                        "w-full p-3 rounded-lg border text-left transition-all",
                        isSelected
                          ? "border-green-400 dark:border-green-700 bg-green-50 dark:bg-green-900/30 ring-1 ring-green-200 dark:ring-green-800"
                          : "border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-700/50"
                      )}
                    >
                      <div className="flex items-start gap-2">
                        <SevIcon className={cn("w-4 h-4 mt-0.5 shrink-0",
                          finding.severity === "CRITICAL" && "text-red-500",
                          finding.severity === "MAJOR" && "text-orange-500",
                          finding.severity === "MINOR" && "text-yellow-500",
                          finding.severity === "INFO" && "text-green-600",
                        )} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5 mb-0.5">
                            <Badge variant="outline" className={cn("text-[10px] py-0 px-1.5", sevCfg.color)}>
                              {finding.severity}
                            </Badge>
                            <span className="text-[10px] text-slate-400 truncate">
                              {finding.category.replace(/_/g, " ")}
                            </span>
                          </div>
                          <p className="text-xs text-slate-700 dark:text-slate-300 line-clamp-2">
                            {finding.description}
                          </p>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-[10px] text-slate-400">{finding.product_family}</span>
                            {finding.confidence > 0 && (
                              <span className="text-[10px] text-slate-400">
                                {Math.round(finding.confidence * 100)}% confidence
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>

              <div className="text-xs text-slate-400 text-center py-1">
                {filteredFindings.length} of {report.findings.length} findings
              </div>
            </div>

            {/* Right panel: Finding detail */}
            <div className="flex-1 min-w-0">
              {!selectedFinding ? (
                <div className="h-full flex items-center justify-center text-slate-400">
                  <div className="text-center">
                    <Shield className="w-12 h-12 mx-auto mb-3 text-slate-300 dark:text-slate-600" />
                    <p className="font-medium">Select a finding to view details</p>
                    <p className="text-sm mt-1">Click any finding on the left panel</p>
                  </div>
                </div>
              ) : (
                <div className="h-full overflow-y-auto space-y-4 pr-2">
                  {/* Header */}
                  <div className="flex items-center gap-2">
                    <Badge className={cn("text-xs", SEVERITY_CONFIG[selectedFinding.severity]?.color)}>
                      {selectedFinding.severity}
                    </Badge>
                    <Badge variant="outline" className="text-xs">
                      {selectedFinding.category.replace(/_/g, " ")}
                    </Badge>
                    <Badge variant="outline" className="text-xs">
                      {selectedFinding.product_family}
                    </Badge>
                    {selectedFinding.confidence > 0 && (
                      <span className="text-xs text-slate-500 dark:text-slate-400 ml-auto">
                        Confidence: {Math.round(selectedFinding.confidence * 100)}%
                      </span>
                    )}
                  </div>

                  {/* Description */}
                  <div>
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-1">Description</h4>
                    <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">{selectedFinding.description}</p>
                  </div>

                  {/* PDF vs Graph comparison */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-900/30 border border-emerald-200 dark:border-emerald-800">
                      <h5 className="text-xs font-semibold text-emerald-700 dark:text-emerald-400 mb-1 flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" />
                        PDF Says (Ground Truth)
                      </h5>
                      <p className="text-sm text-emerald-900 dark:text-emerald-200">{selectedFinding.pdf_says}</p>
                    </div>
                    <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800">
                      <h5 className="text-xs font-semibold text-red-700 dark:text-red-400 mb-1 flex items-center gap-1">
                        <AlertCircle className="w-3 h-3" />
                        Graph Says (Current)
                      </h5>
                      <p className="text-sm text-red-900 dark:text-red-200">{selectedFinding.graph_says}</p>
                    </div>
                  </div>

                  {/* Recommendation */}
                  <div className="p-3 rounded-lg bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800">
                    <h5 className="text-xs font-semibold text-green-800 dark:text-green-500 mb-1">Recommendation</h5>
                    <p className="text-sm text-green-900 dark:text-green-200">{selectedFinding.recommendation}</p>
                  </div>

                  {/* Consensus */}
                  {(selectedFinding.agreed_by?.length > 0 || selectedFinding.challenged_by?.length > 0) && (
                    <div>
                      <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-2">Consensus</h4>
                      <div className="flex gap-2 flex-wrap">
                        {selectedFinding.agreed_by?.map((p) => (
                          <Badge key={p} className="bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 text-xs">
                            <Check className="w-3 h-3 mr-1" />
                            {PROVIDER_LABELS[p] || p}
                          </Badge>
                        ))}
                        {selectedFinding.challenged_by?.map((p) => (
                          <Badge key={p} className="bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 text-xs">
                            <X className="w-3 h-3 mr-1" />
                            {PROVIDER_LABELS[p] || p}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Summary & recommendations at bottom */}
          {report.summary && (
            <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700">
              <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-1">Executive Summary</h4>
              <p className="text-sm text-slate-600 dark:text-slate-400 whitespace-pre-line">{report.summary}</p>
            </div>
          )}

          {report.recommendations && report.recommendations.length > 0 && (
            <div className="p-4 rounded-xl bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800">
              <h4 className="text-sm font-semibold text-amber-800 dark:text-amber-300 mb-2">Priority Actions</h4>
              <ul className="space-y-1">
                {report.recommendations.map((rec, i) => (
                  <li key={i} className="text-sm text-amber-700 dark:text-amber-400 flex items-start gap-2">
                    <span className="font-semibold text-amber-500 dark:text-amber-500 shrink-0">{i + 1}.</span>
                    {rec}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
