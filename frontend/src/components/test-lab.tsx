"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  Search,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  FlaskConical,
  RefreshCw,
  Target,
  Cpu,
  FileText,
  Zap,
  Layers,
  Scale,
  Send,
  Play,
  Upload,
  Sparkles,
  ThumbsUp,
  ThumbsDown,
  Loader2,
  BarChart3,
  StopCircle,
  Bot,
  User,
  MessageSquare,
  ExternalLink,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { apiFetch, judgeQuestion, runBatchJudge, getJudgeResults, generateJudgeQuestions, approveJudgeQuestions } from "@/lib/api";
import ReactMarkdown from "react-markdown";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TestAssertion {
  name: string;
  check: string;
  condition: string;
  expected: string;
  actual: string;
  passed: boolean;
  message: string;
  category: string;
}

interface TestResponse {
  content_text: string;
  content_segments: Array<{ text: string; type: string; source_id?: string }>;
  product_card?: Record<string, unknown>;
  product_cards?: Record<string, unknown>[];
  clarification?: Record<string, unknown> | null;
  clarification_needed?: boolean;
  risk_detected?: boolean;
  risk_severity?: string;
  status_badges?: Array<{ type: string; text: string }>;
}

interface InferenceStep {
  step: string;
  status: string;
  detail: string;
}

interface TestResult {
  name: string;
  description: string;
  category: string;
  query: string;
  graph_dependency: string;
  pdf_reference: string;
  status: "PASS" | "FAIL" | "ERROR";
  duration_s: number;
  likely_cause: string | null;
  error_message: string | null;
  assertions: TestAssertion[];
  response: TestResponse;
  inference_steps: InferenceStep[];
  // Multi-step extensions
  steps?: StepResultData[];
  isMultiStep?: boolean;
}

interface StepResultData {
  step_index: number;
  description: string;
  status: "PASS" | "FAIL" | "ERROR";
  query: string;
  response_text: string;
  assertions_total: number;
  assertions_passed: number;
  duration_s: number;
  error_message: string;
  assertions: Array<{
    name: string; check: string; condition: string; expected: string;
    passed: boolean; actual: string; message: string; group: string;
  }>;
  failures: Array<{
    name: string; check: string; condition: string; expected: string;
    passed: boolean; actual: string; message: string; group: string;
  }>;
}

interface MultiStepData {
  timestamp: string;
  target: string;
  summary: {
    total_tests: number; passed: number; failed: number; errors: number;
    total_assertions: number; assertions_passed: number;
    assertions_failed: number; duration_s: number;
  };
  tests: Array<{
    test_name: string; status: "PASS" | "FAIL" | "ERROR"; category: string;
    total_assertions: number; total_passed: number; total_failed: number;
    duration_s: number; steps: StepResultData[];
  }>;
}

interface TestLabData {
  meta: {
    timestamp: string;
    base_url: string;
    total_tests: number;
    passed: number;
    failed: number;
    errors: number;
    duration_s: number;
    categories: Record<string, { total: number; passed: number; failed: number; errors: number }>;
  };
  tests: TestResult[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const CATEGORY_COLORS: Record<string, string> = {
  env: "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800",
  assembly: "bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-500 border-green-200 dark:border-green-800",
  atex: "bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400 border-red-200 dark:border-red-800",
  sizing: "bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-500 border-green-200 dark:border-green-800",
  material: "bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800",
  positive: "bg-teal-100 dark:bg-teal-900/40 text-teal-700 dark:text-teal-400 border-teal-200 dark:border-teal-800",
  clarif: "bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-400 border-orange-200 dark:border-orange-800",
  clarification: "bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-400 border-orange-200 dark:border-orange-800",
  environment: "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800",
  complex: "bg-pink-100 dark:bg-pink-900/40 text-pink-700 dark:text-pink-400 border-pink-200 dark:border-pink-800",
  dimension: "bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-500 border-green-200 dark:border-green-800",
  capacity: "bg-sky-100 dark:bg-sky-900/40 text-sky-700 dark:text-sky-400 border-sky-200 dark:border-sky-800",
};

function statusIcon(status: string) {
  if (status === "PASS") return <CheckCircle2 className="w-4 h-4 text-emerald-500" />;
  if (status === "FAIL") return <XCircle className="w-4 h-4 text-red-500" />;
  return <AlertTriangle className="w-4 h-4 text-amber-500" />;
}

function relativeTime(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function assertionConditionLabel(a: TestAssertion): string {
  const labels: Record<string, string> = {
    equals: `equals "${a.expected}"`,
    not_equals: `not equal to "${a.expected}"`,
    contains: `contains "${a.expected}"`,
    contains_any: `contains any of [${a.expected.split("|").join(", ")}]`,
    not_contains_any: `does NOT contain [${a.expected.split("|").join(", ")}]`,
    exists: "exists (non-empty)",
    not_exists: "does not exist",
    any_exists: "at least one path exists",
    any_contains: `any path contains [${a.expected.split("|").join(", ")}]`,
    true: "is true",
    false: "is false",
    greater_than: `> ${a.expected}`,
  };
  return labels[a.condition] || a.condition;
}

const ASSERTION_CATEGORY_COLORS: Record<string, string> = {
  detection: "bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-500 border-green-200 dark:border-green-800",
  logic: "bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-500 border-green-200 dark:border-green-800",
  output: "bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800",
  data: "bg-amber-50 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-800",
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SummaryBar({ meta }: { meta: TestLabData["meta"] }) {
  const passRate = meta.total_tests > 0 ? Math.round((meta.passed / meta.total_tests) * 100) : 0;
  return (
    <div className="flex items-center gap-3 flex-wrap">
      <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 text-sm font-medium">
        <Target className="w-3.5 h-3.5" />
        {meta.total_tests} tests
      </div>
      <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 text-sm font-medium">
        <CheckCircle2 className="w-3.5 h-3.5" />
        {meta.passed} pass
      </div>
      {meta.failed > 0 && (
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-400 text-sm font-medium">
          <XCircle className="w-3.5 h-3.5" />
          {meta.failed} fail
        </div>
      )}
      {meta.errors > 0 && (
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 text-sm font-medium">
          <AlertTriangle className="w-3.5 h-3.5" />
          {meta.errors} error
        </div>
      )}
      <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-50 dark:bg-slate-800/50 text-slate-500 dark:text-slate-400 text-sm">
        <Clock className="w-3.5 h-3.5" />
        {meta.duration_s.toFixed(0)}s
      </div>
      <div className="ml-auto flex items-center gap-1.5 text-sm font-semibold" style={{ color: passRate >= 90 ? "#059669" : passRate >= 70 ? "#d97706" : "#dc2626" }}>
        {passRate}% pass rate
      </div>
    </div>
  );
}

function InferenceTimeline({ steps }: { steps: InferenceStep[] }) {
  const [expanded, setExpanded] = useState(false);
  if (!steps.length) return null;

  return (
    <div className="mt-4">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-xs font-medium text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 transition-colors"
      >
        <Zap className="w-3.5 h-3.5" />
        {steps.length} inference steps
        {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>
      {expanded && (
        <div className="mt-2 ml-1 border-l-2 border-slate-200 dark:border-slate-700 pl-4 space-y-1.5">
          {steps.map((s, i) => (
            <div key={i} className="flex items-start gap-2 text-xs">
              <span className={cn(
                "mt-0.5 w-1.5 h-1.5 rounded-full shrink-0",
                s.status === "done" || s.status === "complete" ? "bg-emerald-400" :
                s.status === "warning" ? "bg-amber-400" : "bg-slate-300 dark:bg-slate-600"
              )} />
              <span className="font-mono text-slate-500 dark:text-slate-400">{s.step}</span>
              <span className="text-slate-600 dark:text-slate-300">{s.detail}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AssertionPanel({ assertions, defaultExpanded }: { assertions: TestAssertion[]; defaultExpanded: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());

  const toggleRow = (i: number) => {
    setExpandedRows(prev => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i); else next.add(i);
      return next;
    });
  };

  const passCount = assertions.filter(a => a.passed).length;
  const failCount = assertions.length - passCount;

  return (
    <div className="mt-4">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-xs font-medium text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 transition-colors"
      >
        <Target className="w-3.5 h-3.5" />
        {assertions.length} assertions
        <span className="text-emerald-500">{passCount} pass</span>
        {failCount > 0 && <span className="text-red-500">{failCount} fail</span>}
        {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>
      {expanded && (
        <div className="mt-2 space-y-1">
          {assertions.map((a, i) => (
            <div key={i} className={cn(
              "rounded-lg border text-xs",
              a.passed ? "border-slate-100 dark:border-slate-700 bg-white dark:bg-slate-800" : "border-red-100 dark:border-red-900/50 bg-red-50/30 dark:bg-red-900/20"
            )}>
              <button
                onClick={() => toggleRow(i)}
                className="w-full flex items-center gap-2 px-3 py-2 text-left"
              >
                {a.passed
                  ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                  : <XCircle className="w-3.5 h-3.5 text-red-500 shrink-0" />}
                <span className="font-mono text-slate-700 dark:text-slate-300">{a.name}</span>
                {a.category && (
                  <span className={cn("px-1.5 py-0.5 rounded text-[10px] font-medium border", ASSERTION_CATEGORY_COLORS[a.category] || "bg-slate-50 dark:bg-slate-800 text-slate-500 dark:text-slate-400 border-slate-200 dark:border-slate-700")}>
                    {a.category}
                  </span>
                )}
                <span className="ml-auto text-slate-400 dark:text-slate-500">
                  {expandedRows.has(i) ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                </span>
              </button>
              {expandedRows.has(i) && (
                <div className="px-3 pb-2 space-y-1 border-t border-slate-100 dark:border-slate-700 pt-2">
                  <div className="flex gap-2">
                    <span className="text-slate-400 dark:text-slate-500 w-16 shrink-0">Check:</span>
                    <span className="font-mono text-slate-600 dark:text-slate-300">{a.check}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="text-slate-400 dark:text-slate-500 w-16 shrink-0">Rule:</span>
                    <span className="text-slate-600 dark:text-slate-300">{assertionConditionLabel(a)}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="text-slate-400 dark:text-slate-500 w-16 shrink-0">Actual:</span>
                    <span className="font-mono text-slate-600 dark:text-slate-300 break-all">{a.actual.slice(0, 300)}{a.actual.length > 300 ? "..." : ""}</span>
                  </div>
                  {a.message && (
                    <div className="flex gap-2">
                      <span className="text-slate-400 dark:text-slate-500 w-16 shrink-0">Error:</span>
                      <span className="text-red-600 dark:text-red-400">{a.message}</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Multi-step helpers
// ---------------------------------------------------------------------------

function normalizeMultiStep(ms: MultiStepData): TestResult[] {
  return ms.tests.map(t => {
    // Collect all assertions from all steps for aggregate view
    const allAssertions: TestAssertion[] = t.steps.flatMap((s, si) =>
      s.assertions.map(a => ({
        name: a.name,
        check: a.check,
        condition: a.condition,
        expected: a.expected,
        actual: a.actual,
        passed: a.passed,
        message: a.message,
        category: a.group || `Step ${si + 1}`,
      }))
    );

    return {
      name: t.test_name,
      description: t.steps.map(s => s.description).filter(Boolean).join(" → "),
      category: t.category,
      query: t.steps[0]?.query || t.steps[0]?.description || "",
      graph_dependency: "",
      pdf_reference: "",
      status: t.status,
      duration_s: t.duration_s,
      likely_cause: null,
      error_message: t.steps.find(s => s.error_message)?.error_message || null,
      assertions: allAssertions,
      response: { content_text: "", content_segments: [] },
      inference_steps: [],
      steps: t.steps,
      isMultiStep: true,
    };
  });
}

function buildMergedMeta(
  singleMeta: TestLabData["meta"] | null,
  multiTests: TestResult[],
  singleTests: TestResult[],
): TestLabData["meta"] {
  const allTests = [...singleTests, ...multiTests];
  const categories: Record<string, { total: number; passed: number; failed: number; errors: number }> = {};

  // Start from single-step categories if available
  if (singleMeta?.categories) {
    for (const [cat, stats] of Object.entries(singleMeta.categories)) {
      categories[cat] = { ...stats };
    }
  }

  // Add multi-step test categories
  for (const t of multiTests) {
    if (!categories[t.category]) {
      categories[t.category] = { total: 0, passed: 0, failed: 0, errors: 0 };
    }
    categories[t.category].total += 1;
    if (t.status === "PASS") categories[t.category].passed += 1;
    else if (t.status === "FAIL") categories[t.category].failed += 1;
    else categories[t.category].errors += 1;
  }

  return {
    timestamp: singleMeta?.timestamp || new Date().toISOString(),
    base_url: singleMeta?.base_url || "",
    total_tests: allTests.length,
    passed: allTests.filter(t => t.status === "PASS").length,
    failed: allTests.filter(t => t.status === "FAIL").length,
    errors: allTests.filter(t => t.status === "ERROR").length,
    duration_s: allTests.reduce((sum, t) => sum + t.duration_s, 0),
    categories,
  };
}

// ---------------------------------------------------------------------------
// Multi-step step assertion panel (grouped by assertion group)
// ---------------------------------------------------------------------------

function StepAssertionPanel({ assertions, defaultExpanded }: {
  assertions: Array<{ name: string; check: string; condition: string; expected: string; passed: boolean; actual: string; message: string; group: string }>;
  defaultExpanded: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());

  const toggleRow = (i: number) => {
    setExpandedRows(prev => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i); else next.add(i);
      return next;
    });
  };

  const passCount = assertions.filter(a => a.passed).length;
  const failCount = assertions.length - passCount;

  // Group by assertion group
  const groups: Record<string, typeof assertions> = {};
  for (const a of assertions) {
    const g = a.group || "(ungrouped)";
    if (!groups[g]) groups[g] = [];
    groups[g].push(a);
  }

  return (
    <div className="mt-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-xs font-medium text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 transition-colors"
      >
        <Target className="w-3 h-3" />
        {assertions.length} assertions
        <span className="text-emerald-500">{passCount} pass</span>
        {failCount > 0 && <span className="text-red-500">{failCount} fail</span>}
        {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>
      {expanded && (
        <div className="mt-2 space-y-2">
          {Object.entries(groups).map(([groupName, groupAssertions]) => {
            const allPassed = groupAssertions.every(a => a.passed);
            return (
              <div key={groupName} className="space-y-1">
                <div className="flex items-center gap-1.5 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  {allPassed
                    ? <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                    : <XCircle className="w-3 h-3 text-red-500" />}
                  {groupName}
                </div>
                {groupAssertions.map((a, i) => {
                  const globalIdx = assertions.indexOf(a);
                  return (
                    <div key={i} className={cn(
                      "rounded-lg border text-xs",
                      a.passed ? "border-slate-100 dark:border-slate-700 bg-white dark:bg-slate-800" : "border-red-100 dark:border-red-900/50 bg-red-50/30 dark:bg-red-900/20"
                    )}>
                      <button
                        onClick={() => toggleRow(globalIdx)}
                        className="w-full flex items-center gap-2 px-3 py-1.5 text-left"
                      >
                        {a.passed
                          ? <CheckCircle2 className="w-3 h-3 text-emerald-500 shrink-0" />
                          : <XCircle className="w-3 h-3 text-red-500 shrink-0" />}
                        <span className="font-mono text-slate-700 dark:text-slate-300">{a.name}</span>
                        <span className="ml-auto text-slate-400 dark:text-slate-500">
                          {expandedRows.has(globalIdx) ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                        </span>
                      </button>
                      {expandedRows.has(globalIdx) && (
                        <div className="px-3 pb-2 space-y-1 border-t border-slate-100 dark:border-slate-700 pt-2">
                          <div className="flex gap-2">
                            <span className="text-slate-400 dark:text-slate-500 w-16 shrink-0">Check:</span>
                            <span className="font-mono text-slate-600 dark:text-slate-300">{a.check}</span>
                          </div>
                          <div className="flex gap-2">
                            <span className="text-slate-400 dark:text-slate-500 w-16 shrink-0">Rule:</span>
                            <span className="text-slate-600 dark:text-slate-300">
                              {assertionConditionLabel(a as unknown as TestAssertion)}
                            </span>
                          </div>
                          <div className="flex gap-2">
                            <span className="text-slate-400 dark:text-slate-500 w-16 shrink-0">Actual:</span>
                            <span className="font-mono text-slate-600 dark:text-slate-300 break-all">
                              {a.actual.slice(0, 300)}{a.actual.length > 300 ? "..." : ""}
                            </span>
                          </div>
                          {a.message && (
                            <div className="flex gap-2">
                              <span className="text-slate-400 dark:text-slate-500 w-16 shrink-0">Error:</span>
                              <span className="text-red-600 dark:text-red-400">{a.message}</span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Multi-step detail view — full chat flow with vertical timeline
// ---------------------------------------------------------------------------

function StepProgressBar({ steps }: { steps: StepResultData[] }) {
  return (
    <div className="flex items-center gap-0 w-full px-2 py-3">
      {steps.map((step, i) => (
        <div key={i} className="flex items-center flex-1 last:flex-initial">
          {/* Dot */}
          <div className="flex flex-col items-center gap-1">
            <div className={cn(
              "w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0",
              step.status === "PASS" ? "bg-emerald-500 text-white" :
              step.status === "FAIL" ? "bg-red-500 text-white" :
              "bg-amber-500 text-white"
            )}>
              {step.status === "PASS" ? "\u2713" : step.status === "FAIL" ? "\u2717" : "!"}
            </div>
            <span className="text-[9px] text-slate-500 dark:text-slate-400 whitespace-nowrap">Turn {i + 1}</span>
          </div>
          {/* Connecting line */}
          {i < steps.length - 1 && (
            <div className={cn(
              "flex-1 h-0.5 mx-1",
              step.status === "PASS" ? "bg-emerald-300 dark:bg-emerald-700" :
              step.status === "FAIL" ? "bg-red-300 dark:bg-red-700" :
              "bg-amber-300 dark:bg-amber-700"
            )} />
          )}
        </div>
      ))}
      {/* Done marker */}
      <div className="flex flex-col items-center gap-1 ml-1">
        <div className="w-5 h-5 rounded-full flex items-center justify-center bg-slate-200 dark:bg-slate-700 text-slate-500 dark:text-slate-400">
          <CheckCircle2 className="w-3 h-3" />
        </div>
        <span className="text-[9px] text-slate-400 dark:text-slate-500">Done</span>
      </div>
    </div>
  );
}

function MultiStepDetail({ test }: { test: TestResult }) {
  if (!test.steps) return null;

  const totalAssertions = test.steps.reduce((sum, s) => sum + s.assertions.length, 0);
  const passedAssertions = test.steps.reduce((sum, s) => sum + s.assertions.filter(a => a.passed).length, 0);
  const failedAssertions = totalAssertions - passedAssertions;

  return (
    <div className="space-y-4 pb-8">
      {/* Test header */}
      <div className="flex items-start gap-3">
        <div className="flex items-center gap-2">
          {statusIcon(test.status)}
          <span className={cn(
            "text-sm font-semibold",
            test.status === "PASS" ? "text-emerald-700 dark:text-emerald-400" : test.status === "FAIL" ? "text-red-700 dark:text-red-400" : "text-amber-700 dark:text-amber-400"
          )}>{test.status}</span>
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-mono font-medium text-slate-800 dark:text-slate-200">{test.name}</h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Multi-step &middot; {test.steps.length} turn{test.steps.length !== 1 ? "s" : ""} &middot; {passedAssertions}/{totalAssertions} assertions passed
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={cn("px-2 py-0.5 rounded-full text-[10px] font-medium border", CATEGORY_COLORS[test.category] || "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700")}>
            {test.category}
          </span>
          <span className="text-xs text-slate-400 dark:text-slate-500">{test.duration_s.toFixed(1)}s</span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50">
        <StepProgressBar steps={test.steps} />
      </div>

      {/* Vertical timeline with chat flow */}
      <div className="relative pl-6">
        {/* Continuous vertical line */}
        <div className="absolute left-[11px] top-0 bottom-0 w-0.5 bg-slate-200 dark:bg-slate-700" />

        {test.steps.map((step, i) => (
          <div key={i} className="relative pb-6 last:pb-0">
            {/* Timeline connector dot */}
            <div className={cn(
              "absolute left-[-13px] top-0 w-3 h-3 rounded-full border-2 border-white dark:border-slate-900 z-10",
              step.status === "PASS" ? "bg-emerald-500" :
              step.status === "FAIL" ? "bg-red-500" :
              "bg-amber-500"
            )} />

            {/* Turn header */}
            <div className="flex items-center gap-2 mb-3">
              <span className={cn(
                "text-xs font-semibold",
                step.status === "PASS" ? "text-emerald-700 dark:text-emerald-400" :
                step.status === "FAIL" ? "text-red-700 dark:text-red-400" :
                "text-amber-700 dark:text-amber-400"
              )}>
                Turn {i + 1}
              </span>
              <span className="text-[10px] text-slate-400 dark:text-slate-500">&mdash;</span>
              <span className="text-xs text-slate-600 dark:text-slate-300">{step.description || `Step ${i + 1}`}</span>
              <span className="ml-auto flex items-center gap-1.5">
                {statusIcon(step.status)}
                <span className="text-[10px] text-slate-400 dark:text-slate-500">{step.duration_s.toFixed(1)}s</span>
              </span>
            </div>

            {/* User query bubble (right-aligned, blue) */}
            {step.query ? (
              <div className="flex justify-end mb-3">
                <div className="max-w-[85%] rounded-2xl rounded-br-md px-4 py-3 bg-green-700 text-white text-sm leading-relaxed shadow-sm">
                  {step.query}
                </div>
              </div>
            ) : (
              <div className="flex justify-end mb-3">
                <div className="max-w-[85%] rounded-2xl rounded-br-md px-3 py-2 bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-500 text-xs italic">
                  (query not captured — re-run tests to populate)
                </div>
              </div>
            )}

            {/* Error message */}
            {step.status === "ERROR" && step.error_message && (
              <div className="mb-3">
                <div className="rounded-xl px-4 py-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-400">
                  <AlertTriangle className="w-4 h-4 inline mr-1" />
                  {step.error_message}
                </div>
              </div>
            )}

            {/* System response bubble (left-aligned, white) */}
            {step.response_text ? (
              <div className="flex justify-start mb-3">
                <div className="max-w-[85%] rounded-2xl rounded-bl-md px-4 py-3 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-sm shadow-sm">
                  <div className="flex items-center gap-2 mb-2">
                    <Cpu className="w-3.5 h-3.5 text-slate-500 dark:text-slate-400" />
                    <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">Response</span>
                  </div>
                  <div className="prose prose-sm prose-slate dark:prose-invert max-w-none text-slate-700 dark:text-slate-300 [&_p]:my-1 [&_ul]:my-1 [&_li]:my-0">
                    <ReactMarkdown>{step.response_text}</ReactMarkdown>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex justify-start mb-3">
                <div className="max-w-[85%] rounded-2xl rounded-bl-md px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-100 dark:border-slate-700 text-slate-400 dark:text-slate-500 text-xs italic">
                  (response not captured — re-run tests to populate)
                </div>
              </div>
            )}

            {/* Per-step assertions */}
            {step.assertions.length > 0 && (
              <StepAssertionPanel
                assertions={step.assertions}
                defaultExpanded={step.status !== "PASS"}
              />
            )}
          </div>
        ))}
      </div>

      {/* Summary card */}
      <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 p-4 space-y-2">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wide">
          <Target className="w-3.5 h-3.5" />
          Summary
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-slate-600 dark:text-slate-300">
            <span className="font-medium">{totalAssertions}</span> assertions
          </span>
          <span className="text-emerald-600 dark:text-emerald-400 font-medium">{passedAssertions} passed</span>
          {failedAssertions > 0 && (
            <span className="text-red-600 dark:text-red-400 font-medium">{failedAssertions} failed</span>
          )}
          <span className="text-slate-400 dark:text-slate-500">&middot;</span>
          <span className="text-slate-500 dark:text-slate-400">
            {test.duration_s.toFixed(1)}s across {test.steps.length} turn{test.steps.length !== 1 ? "s" : ""}
          </span>
        </div>
      </div>
    </div>
  );
}

function TestDetail({ test }: { test: TestResult }) {
  return (
    <div className="space-y-4 pb-8">
      {/* Test header */}
      <div className="flex items-start gap-3">
        <div className="flex items-center gap-2">
          {statusIcon(test.status)}
          <span className={cn(
            "text-sm font-semibold",
            test.status === "PASS" ? "text-emerald-700 dark:text-emerald-400" : test.status === "FAIL" ? "text-red-700 dark:text-red-400" : "text-amber-700 dark:text-amber-400"
          )}>{test.status}</span>
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-mono font-medium text-slate-800 dark:text-slate-200">{test.name}</h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{test.description}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={cn("px-2 py-0.5 rounded-full text-[10px] font-medium border", CATEGORY_COLORS[test.category] || "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700")}>
            {test.category}
          </span>
          <span className="text-xs text-slate-400 dark:text-slate-500">{test.duration_s.toFixed(1)}s</span>
        </div>
      </div>

      {/* User query bubble (right-aligned) */}
      <div className="flex justify-end items-end gap-1.5">
        <button
          title="Run in new chat session"
          onClick={() => window.open(`/?q=${encodeURIComponent(test.query)}`, "_blank")}
          className="shrink-0 p-1.5 rounded-lg text-slate-400 hover:text-green-700 dark:hover:text-green-500 hover:bg-green-50 dark:hover:bg-green-900/30 transition-colors"
        >
          <ExternalLink className="w-3.5 h-3.5" />
        </button>
        <div className="max-w-[85%] rounded-2xl rounded-br-md px-4 py-3 bg-green-700 text-white text-sm leading-relaxed shadow-sm">
          {test.query}
        </div>
      </div>

      {/* Expected outcome bubble */}
      <div className="flex justify-start">
        <div className="max-w-[85%] rounded-2xl rounded-bl-md px-4 py-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 text-sm shadow-sm">
          <div className="flex items-center gap-2 mb-2">
            <Target className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
            <span className="text-xs font-semibold text-amber-700 dark:text-amber-400 uppercase tracking-wide">Expected</span>
          </div>
          <div className="space-y-1">
            {test.assertions.map((a, i) => (
              <div key={i} className="flex items-start gap-2 text-xs text-amber-800 dark:text-amber-300">
                <span className="shrink-0 mt-0.5">
                  {a.passed
                    ? <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                    : <XCircle className="w-3 h-3 text-red-500" />}
                </span>
                <span>
                  <span className="font-mono font-medium">{a.name}</span>
                  {" — "}
                  <span className="text-amber-600 dark:text-amber-400">{assertionConditionLabel(a)}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* System response bubble */}
      <div className="flex justify-start">
        <div className="max-w-[85%] rounded-2xl rounded-bl-md px-4 py-3 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-sm shadow-sm">
          <div className="flex items-center gap-2 mb-2">
            <Cpu className="w-3.5 h-3.5 text-slate-500 dark:text-slate-400" />
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">System Response</span>
            {test.response.risk_detected && (
              <Badge variant="destructive" className="text-[10px] px-1.5 py-0">RISK</Badge>
            )}
            {test.response.risk_severity && test.response.risk_severity !== "NONE" && (
              <Badge variant="warning" className="text-[10px] px-1.5 py-0">{test.response.risk_severity}</Badge>
            )}
          </div>
          {test.status === "ERROR" ? (
            <div className="text-red-600 dark:text-red-400 text-sm">
              <AlertTriangle className="w-4 h-4 inline mr-1" />
              {test.error_message || "No response received"}
            </div>
          ) : test.response.content_text ? (
            <div className="prose prose-sm prose-slate dark:prose-invert max-w-none text-slate-700 dark:text-slate-300 [&_p]:my-1 [&_ul]:my-1 [&_li]:my-0">
              <ReactMarkdown>{test.response.content_text}</ReactMarkdown>
            </div>
          ) : (
            <div className="text-slate-400 dark:text-slate-500 italic text-xs">No content text in response</div>
          )}

          {/* Product card indicator */}
          {(test.response.product_card || (test.response.product_cards && test.response.product_cards.length > 0)) && (
            <div className="mt-3 pt-2 border-t border-slate-100 dark:border-slate-700">
              <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
                <FileText className="w-3 h-3" />
                {test.response.product_cards
                  ? `${test.response.product_cards.length} product card(s) returned`
                  : "Product card returned"}
              </div>
            </div>
          )}

          {/* Clarification indicator */}
          {test.response.clarification_needed && (
            <div className="mt-3 pt-2 border-t border-slate-100 dark:border-slate-700">
              <div className="flex items-center gap-1.5 text-xs text-green-700 dark:text-green-500">
                <AlertTriangle className="w-3 h-3" />
                Clarification requested
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Inference steps */}
      <InferenceTimeline steps={test.inference_steps} />

      {/* Assertion results */}
      <AssertionPanel assertions={test.assertions} defaultExpanded={test.status !== "PASS"} />

      {/* Metadata */}
      {(test.graph_dependency || test.pdf_reference || test.likely_cause) && (
        <div className="mt-4 p-3 rounded-lg bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-700 space-y-1.5 text-xs">
          {test.graph_dependency && (
            <div className="flex gap-2">
              <span className="text-slate-400 dark:text-slate-500 w-24 shrink-0">Graph nodes:</span>
              <span className="font-mono text-slate-600 dark:text-slate-300">{test.graph_dependency}</span>
            </div>
          )}
          {test.pdf_reference && (
            <div className="flex gap-2">
              <span className="text-slate-400 dark:text-slate-500 w-24 shrink-0">PDF reference:</span>
              <span className="text-slate-600 dark:text-slate-300">{test.pdf_reference}</span>
            </div>
          )}
          {test.likely_cause && (
            <div className="flex gap-2">
              <span className="text-slate-400 dark:text-slate-500 w-24 shrink-0">Likely cause:</span>
              <span className="font-mono text-red-600 dark:text-red-400">{test.likely_cause}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// LLM Judge Types & Sub-Components
// ---------------------------------------------------------------------------

interface JudgeScores {
  correctness: number;
  completeness: number;
  safety: number;
  tone: number;
  reasoning_quality: number;
  constraint_adherence: number;
}

interface JudgeResultData {
  scores: JudgeScores;
  overall_score: number;
  explanation: string;
  dimension_explanations: Record<string, string>;
  strengths: string[];
  weaknesses: string[];
  recommendation: "PASS" | "FAIL" | "BORDERLINE" | "ERROR";
}

interface JudgeBatchResult {
  question_id: string;
  question_text: string;
  description: string;
  category: string;
  judge_result: JudgeResultData;
  duration_s: number;
  status: string;
  system_response?: { content_text?: string; graph_report?: Record<string, unknown> };
}

interface JudgeBatchData {
  meta: {
    timestamp: string;
    judge_model: string;
    total_questions: number;
    avg_overall_score: number;
    score_distribution: Record<string, number>;
    category_summary: Record<string, number>;
    filter: string;
  };
  results: JudgeBatchResult[];
}

interface GeneratedQuestion {
  id: string;
  question: string;
  category: string;
  difficulty: string;
  expected_elements: string[];
  potential_failures: string[];
}

const SCORE_COLORS: Record<number, string> = {
  5: "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/30 border-emerald-200 dark:border-emerald-800",
  4: "text-green-700 dark:text-green-500 bg-green-50 dark:bg-green-900/30 border-green-200 dark:border-green-800",
  3: "text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/30 border-amber-200 dark:border-amber-800",
  2: "text-orange-600 dark:text-orange-400 bg-orange-50 dark:bg-orange-900/30 border-orange-200 dark:border-orange-800",
  1: "text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30 border-red-200 dark:border-red-800",
};

const RECOMMENDATION_COLORS: Record<string, string> = {
  PASS: "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400 border-emerald-300 dark:border-emerald-800",
  BORDERLINE: "bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400 border-amber-300 dark:border-amber-800",
  FAIL: "bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400 border-red-300 dark:border-red-800",
  ERROR: "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-300 dark:border-slate-700",
};

const DIMENSION_LABELS: Record<string, string> = {
  correctness: "Correctness",
  completeness: "Completeness",
  safety: "Safety",
  tone: "Tone",
  reasoning_quality: "Reasoning",
  constraint_adherence: "Constraints",
};

const DIMENSION_WEIGHTS: Record<string, string> = {
  correctness: "25%",
  completeness: "15%",
  safety: "25%",
  tone: "10%",
  reasoning_quality: "10%",
  constraint_adherence: "15%",
};

function ScoreCard({ dimension, score, explanation }: { dimension: string; score: number; explanation?: string }) {
  const clamped = Math.max(1, Math.min(5, Math.round(score)));
  const colorClass = SCORE_COLORS[clamped] || SCORE_COLORS[3];
  return (
    <div className={cn("rounded-lg border p-3 space-y-1.5", colorClass)}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide">
          {DIMENSION_LABELS[dimension] || dimension}
        </span>
        <span className="text-xs text-slate-400">{DIMENSION_WEIGHTS[dimension]}</span>
      </div>
      <div className="flex items-center gap-1.5">
        <span className="text-2xl font-bold">{score}</span>
        <span className="text-sm opacity-60">/5</span>
        <div className="flex gap-0.5 ml-auto">
          {[1, 2, 3, 4, 5].map(i => (
            <div
              key={i}
              className={cn(
                "w-2 h-5 rounded-sm",
                i <= clamped ? "opacity-100" : "opacity-20",
                clamped >= 4 ? "bg-current" : clamped >= 3 ? "bg-current" : "bg-current"
              )}
            />
          ))}
        </div>
      </div>
      {explanation && (
        <p className="text-[11px] opacity-80 leading-tight">{explanation}</p>
      )}
    </div>
  );
}

function JudgeResultView({ result, question, systemResponse }: {
  result: JudgeResultData;
  question: string;
  systemResponse?: string;
}) {
  const [showResponse, setShowResponse] = useState(false);

  return (
    <div className="space-y-4">
      {/* Overall score + recommendation */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="text-3xl font-bold text-slate-800 dark:text-slate-200">
            {result.overall_score.toFixed(1)}
          </span>
          <span className="text-sm text-slate-400 dark:text-slate-500">/5</span>
        </div>
        <Badge className={cn("text-sm px-3 py-1 font-semibold border", RECOMMENDATION_COLORS[result.recommendation] || RECOMMENDATION_COLORS.ERROR)}>
          {result.recommendation}
        </Badge>
      </div>

      {/* Explanation */}
      {result.explanation && (
        <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">{result.explanation}</p>
      )}

      {/* Score cards grid */}
      <div className="grid grid-cols-3 gap-3">
        {Object.entries(result.scores).map(([dim, score]) => (
          <ScoreCard
            key={dim}
            dimension={dim}
            score={score}
            explanation={result.dimension_explanations?.[dim]}
          />
        ))}
      </div>

      {/* Strengths & Weaknesses */}
      <div className="grid grid-cols-2 gap-3">
        {result.strengths?.length > 0 && (
          <div className="rounded-lg border border-emerald-200 dark:border-emerald-800 bg-emerald-50/50 dark:bg-emerald-900/20 p-3">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-700 dark:text-emerald-400 mb-2">
              <ThumbsUp className="w-3.5 h-3.5" /> Strengths
            </div>
            <ul className="space-y-1">
              {result.strengths.map((s, i) => (
                <li key={i} className="text-xs text-emerald-700 dark:text-emerald-400">{s}</li>
              ))}
            </ul>
          </div>
        )}
        {result.weaknesses?.length > 0 && (
          <div className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50/50 dark:bg-red-900/20 p-3">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-red-700 dark:text-red-400 mb-2">
              <ThumbsDown className="w-3.5 h-3.5" /> Weaknesses
            </div>
            <ul className="space-y-1">
              {result.weaknesses.map((w, i) => (
                <li key={i} className="text-xs text-red-700 dark:text-red-400">{w}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Question */}
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md px-4 py-3 bg-green-700 text-white text-sm leading-relaxed shadow-sm">
          {question}
        </div>
      </div>

      {/* System response (collapsible) */}
      {systemResponse && (
        <div>
          <button
            onClick={() => setShowResponse(!showResponse)}
            className="flex items-center gap-2 text-xs font-medium text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
          >
            <Cpu className="w-3.5 h-3.5" />
            System Response
            {showResponse ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
          {showResponse && (
            <div className="mt-2 rounded-xl px-4 py-3 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-sm">
              <div className="prose prose-sm prose-slate dark:prose-invert max-w-none">
                <ReactMarkdown>{systemResponse}</ReactMarkdown>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function JudgeTab() {
  const [mode, setMode] = useState<"realtime" | "batch" | "generate">("realtime");
  // Real-time state
  const [question, setQuestion] = useState("");
  const [judging, setJudging] = useState(false);
  const [realtimeResult, setRealtimeResult] = useState<{ result: JudgeResultData; question: string; systemResponse: string } | null>(null);
  const [statusMsg, setStatusMsg] = useState("");
  const [inferenceSteps, setInferenceSteps] = useState<Array<{ step: string; detail: string; status: string }>>([]);
  const [systemResponseText, setSystemResponseText] = useState("");
  const [phase, setPhase] = useState<"idle" | "system" | "judging" | "done">("idle");
  const stepsEndRef = useRef<HTMLDivElement>(null);
  // Batch state
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchProgress, setBatchProgress] = useState({ current: 0, total: 0 });
  const [batchResults, setBatchResults] = useState<JudgeBatchData | null>(null);
  const [batchFilter, setBatchFilter] = useState("all");
  const [expandedBatchIdx, setExpandedBatchIdx] = useState<number | null>(null);
  const [batchScoreFilter, setBatchScoreFilter] = useState<"all" | "low" | "medium" | "high">("all");
  // Generate state
  const [genFile, setGenFile] = useState<File | null>(null);
  const [genCount, setGenCount] = useState(20);
  const [generating, setGenerating] = useState(false);
  const [genQuestions, setGenQuestions] = useState<GeneratedQuestion[]>([]);
  const [selectedGenIds, setSelectedGenIds] = useState<Set<string>>(new Set());
  const [genStatus, setGenStatus] = useState("");
  // Abort controller
  const abortRef = useRef<AbortController | null>(null);

  // Auto-scroll inference steps
  useEffect(() => {
    stepsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [inferenceSteps]);

  // ---- Real-time handler ----
  const handleRealTimeJudge = useCallback(async () => {
    if (!question.trim() || judging) return;
    setJudging(true);
    setRealtimeResult(null);
    setStatusMsg("Sending question to Graph Reasoning...");
    setInferenceSteps([]);
    setSystemResponseText("");
    setPhase("system");

    try {
      const res = await judgeQuestion(question.trim());
      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response stream");
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "status") {
              setStatusMsg(event.message);
            } else if (event.type === "inference_step") {
              setInferenceSteps(prev => [...prev, {
                step: event.step || "",
                detail: event.detail || "",
                status: event.status || "",
              }]);
              setStatusMsg("");
            } else if (event.type === "system_response") {
              setSystemResponseText(event.content_text || "");
              setPhase("judging");
              setStatusMsg("Evaluating response with Gemini 3 Pro...");
            } else if (event.type === "judge_complete") {
              setRealtimeResult({
                result: event.result,
                question: event.question || question,
                systemResponse: event.result?.system_response || "",
              });
              setPhase("done");
              setStatusMsg("");
            } else if (event.type === "error") {
              setStatusMsg(`Error: ${event.detail}`);
              setPhase("idle");
            }
          } catch { /* skip malformed */ }
        }
      }
    } catch (err) {
      setStatusMsg(`Error: ${err instanceof Error ? err.message : "Unknown error"}`);
      setPhase("idle");
    } finally {
      setJudging(false);
    }
  }, [question, judging]);

  // ---- Batch handler ----
  const handleBatchRun = useCallback(async () => {
    if (batchRunning) return;
    setBatchRunning(true);
    setBatchProgress({ current: 0, total: 0 });
    setBatchResults(null);
    setExpandedBatchIdx(null);

    abortRef.current = new AbortController();

    try {
      const res = await runBatchJudge(batchFilter);
      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response stream");
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "batch_start") {
              setBatchProgress({ current: 0, total: event.total });
            } else if (event.type === "test_progress") {
              setBatchProgress({ current: event.current, total: event.total });
            } else if (event.type === "batch_complete") {
              // Load full results
              const data = await getJudgeResults();
              if (data) setBatchResults(data as JudgeBatchData);
            } else if (event.type === "error") {
              setStatusMsg(`Batch error: ${event.detail}`);
            }
          } catch { /* skip */ }
        }
      }
    } catch (err) {
      setStatusMsg(`Batch error: ${err instanceof Error ? err.message : "Unknown"}`);
    } finally {
      setBatchRunning(false);
      abortRef.current = null;
    }
  }, [batchFilter, batchRunning]);

  // Load existing results on mount
  useEffect(() => {
    if (mode === "batch" && !batchResults && !batchRunning) {
      getJudgeResults().then(data => {
        if (data) setBatchResults(data as JudgeBatchData);
      }).catch(() => {});
    }
  }, [mode, batchResults, batchRunning]);

  // ---- Generate handler ----
  const handleGenerate = useCallback(async () => {
    if (!genFile || generating) return;
    setGenerating(true);
    setGenQuestions([]);
    setSelectedGenIds(new Set());
    setGenStatus("Uploading PDF...");

    try {
      const res = await generateJudgeQuestions(genFile, { target_count: genCount });
      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response stream");
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "status") {
              setGenStatus(event.message);
            } else if (event.type === "generation_start") {
              setGenStatus(`Generating ${event.target_count} questions...`);
            } else if (event.type === "generation_complete") {
              setGenQuestions(event.questions || []);
              setGenStatus(`Generated ${event.count} questions in ${event.duration_s}s`);
            } else if (event.type === "error") {
              setGenStatus(`Error: ${event.detail}`);
            }
          } catch { /* skip */ }
        }
      }
    } catch (err) {
      setGenStatus(`Error: ${err instanceof Error ? err.message : "Unknown"}`);
    } finally {
      setGenerating(false);
    }
  }, [genFile, genCount, generating]);

  const handleApproveQuestions = useCallback(async () => {
    const selected = genQuestions.filter(q => selectedGenIds.has(q.id));
    if (selected.length === 0) return;
    try {
      const resp = await approveJudgeQuestions(selected as unknown as Record<string, unknown>[]);
      setGenStatus(`Approved ${resp.added} questions (total: ${resp.total})`);
      setSelectedGenIds(new Set());
    } catch (err) {
      setGenStatus(`Error: ${err instanceof Error ? err.message : "Unknown"}`);
    }
  }, [genQuestions, selectedGenIds]);

  // Filter batch results
  const filteredBatchResults = batchResults?.results?.filter(r => {
    const score = r.judge_result?.overall_score || 0;
    if (batchScoreFilter === "low") return score < 3;
    if (batchScoreFilter === "medium") return score >= 3 && score < 4;
    if (batchScoreFilter === "high") return score >= 4;
    return true;
  }) || [];

  return (
    <div className="flex flex-col h-full gap-4">
      {/* Mode selector */}
      <div className="flex items-center gap-2 border-b border-slate-200 dark:border-slate-700 pb-3">
        {([
          { id: "realtime" as const, label: "Real-time", icon: Send },
          { id: "batch" as const, label: "Batch", icon: Play },
          { id: "generate" as const, label: "Generate", icon: Sparkles },
        ]).map(m => (
          <button
            key={m.id}
            onClick={() => setMode(m.id)}
            className={cn(
              "flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium transition-colors",
              mode === m.id
                ? "bg-green-700 text-white"
                : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700"
            )}
          >
            <m.icon className="w-3.5 h-3.5" />
            {m.label}
          </button>
        ))}
        <div className="ml-auto text-[10px] text-slate-400 dark:text-slate-500 flex items-center gap-1">
          <Scale className="w-3 h-3" /> Judge: Gemini 3 Pro Preview
        </div>
      </div>

      {/* ============ REAL-TIME MODE ============ */}
      {mode === "realtime" && (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Input bar */}
          <div className="flex gap-2 flex-shrink-0">
            <input
              type="text"
              value={question}
              onChange={e => setQuestion(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") handleRealTimeJudge(); }}
              placeholder="Enter a question to judge (e.g., 'GDMI for hospital, RF material, 600x600, 3400 m3/h')"
              className="flex-1 px-4 py-2.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-green-600/20 focus:border-green-300 dark:focus:border-green-700 dark:placeholder:text-slate-500"
              disabled={judging}
            />
            <button
              onClick={handleRealTimeJudge}
              disabled={judging || !question.trim()}
              className={cn(
                "px-5 py-2.5 rounded-lg text-sm font-medium transition-colors flex items-center gap-2",
                judging
                  ? "bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-500 cursor-not-allowed"
                  : "bg-green-700 text-white hover:bg-green-800"
              )}
            >
              {judging ? <Loader2 className="w-4 h-4 animate-spin" /> : <Scale className="w-4 h-4" />}
              Judge
            </button>
          </div>

          {/* Chat conversation area */}
          <div className="flex-1 overflow-auto mt-4 space-y-4 px-1">

            {/* Empty state */}
            {phase === "idle" && !realtimeResult && !judging && !statusMsg && (
              <div className="flex flex-col items-center justify-center py-16 text-slate-400 gap-3">
                <Scale className="w-10 h-10 text-slate-300" />
                <p className="text-sm">Enter a question and click Judge to evaluate the system response</p>
                <p className="text-xs text-slate-400">
                  The system will send your question to Graph Reasoning, then Gemini 3 Pro will evaluate the response across 6 dimensions
                </p>
              </div>
            )}

            {/* === CHAT MESSAGE 1: User question (right-aligned) === */}
            {phase !== "idle" && (
              <div className="flex justify-end gap-2">
                <div className="max-w-[80%] rounded-2xl rounded-br-md px-4 py-3 bg-green-700 text-white text-sm leading-relaxed shadow-sm">
                  {question}
                </div>
                <div className="w-7 h-7 rounded-full bg-green-100 flex items-center justify-center flex-shrink-0 mt-1">
                  <User className="w-3.5 h-3.5 text-green-700" />
                </div>
              </div>
            )}

            {/* === CHAT MESSAGE 2: System thinking + response (left-aligned) === */}
            {phase !== "idle" && (inferenceSteps.length > 0 || phase === "system") && (
              <div className="flex gap-2">
                <div className="w-7 h-7 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center flex-shrink-0 mt-1">
                  <Bot className="w-3.5 h-3.5 text-slate-600 dark:text-slate-400" />
                </div>
                <div className="max-w-[85%] space-y-2">
                  {/* Label */}
                  <div className="text-[11px] font-medium text-slate-400 dark:text-slate-500">Graph Reasoning (SynapseOS)</div>

                  {/* Thinking steps - compact */}
                  {inferenceSteps.length > 0 && (
                    <div className="rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-100 dark:border-slate-700 px-3 py-2 space-y-1">
                      {inferenceSteps.map((s, i) => (
                        <div key={i} className="flex items-start gap-1.5 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
                          <div className={cn(
                            "mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0",
                            s.status === "done" || s.status === "complete" ? "bg-emerald-400"
                              : s.status === "warning" ? "bg-amber-400"
                              : s.status === "error" ? "bg-red-400"
                              : "bg-green-300"
                          )} />
                          <span>
                            {s.step && <span className="font-medium text-slate-600 dark:text-slate-300">{s.step}</span>}
                            {s.step && ": "}{s.detail}
                          </span>
                        </div>
                      ))}
                      {phase === "system" && (
                        <div className="flex items-center gap-1.5 text-[11px] text-slate-400 pt-0.5">
                          <Loader2 className="w-3 h-3 animate-spin" />
                          Thinking...
                        </div>
                      )}
                    </div>
                  )}

                  {/* Actual system response bubble */}
                  {(phase === "judging" || phase === "done") && (
                    <div className="rounded-2xl rounded-bl-md px-4 py-3 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm">
                      {systemResponseText ? (
                        <div className="prose prose-sm prose-slate dark:prose-invert max-w-none text-sm">
                          <ReactMarkdown>{systemResponseText.slice(0, 3000)}</ReactMarkdown>
                        </div>
                      ) : (
                        <div className="text-sm text-slate-400 dark:text-slate-500 italic">No response generated (empty content)</div>
                      )}
                    </div>
                  )}

                  {/* Still waiting for system */}
                  {phase === "system" && inferenceSteps.length === 0 && (
                    <div className="flex items-center gap-2 text-xs text-slate-400">
                      <Loader2 className="w-3 h-3 animate-spin" />
                      {statusMsg || "Connecting to Graph Reasoning..."}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* === CHAT MESSAGE 3: Judge evaluation (left-aligned, violet) === */}
            {(phase === "judging" || phase === "done") && (
              <div className="flex gap-2">
                <div className="w-7 h-7 rounded-full bg-green-100 dark:bg-green-900/40 flex items-center justify-center flex-shrink-0 mt-1">
                  <Scale className="w-3.5 h-3.5 text-green-700 dark:text-green-500" />
                </div>
                <div className="max-w-[90%] space-y-2">
                  {/* Label */}
                  <div className="text-[11px] font-medium text-green-500 dark:text-green-700">Judge (Gemini 3 Pro)</div>

                  {/* Still judging */}
                  {phase === "judging" && (
                    <div className="rounded-2xl rounded-bl-md px-4 py-3 bg-green-50 dark:bg-green-900/20 border border-green-100 dark:border-green-800">
                      <div className="flex items-center gap-2 text-sm text-green-700 dark:text-green-500">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Evaluating response across 6 dimensions...
                      </div>
                    </div>
                  )}

                  {/* Judge verdict */}
                  {realtimeResult && (
                    <div className="rounded-2xl rounded-bl-md bg-white dark:bg-slate-800 border border-green-200 dark:border-green-800 shadow-sm overflow-hidden">
                      {/* Score header */}
                      <div className={cn(
                        "px-4 py-3 flex items-center gap-3",
                        realtimeResult.result.recommendation === "PASS" ? "bg-emerald-50 dark:bg-emerald-900/20 border-b border-emerald-100 dark:border-emerald-800"
                          : realtimeResult.result.recommendation === "BORDERLINE" ? "bg-amber-50 dark:bg-amber-900/20 border-b border-amber-100 dark:border-amber-800"
                          : realtimeResult.result.recommendation === "FAIL" ? "bg-red-50 dark:bg-red-900/20 border-b border-red-100 dark:border-red-800"
                          : "bg-slate-50 dark:bg-slate-800 border-b border-slate-100 dark:border-slate-700"
                      )}>
                        <span className="text-2xl font-bold text-slate-800 dark:text-slate-200">
                          {realtimeResult.result.overall_score.toFixed(1)}
                        </span>
                        <span className="text-xs text-slate-400">/5</span>
                        <Badge className={cn(
                          "text-xs px-2.5 py-0.5 font-semibold border",
                          RECOMMENDATION_COLORS[realtimeResult.result.recommendation] || RECOMMENDATION_COLORS.ERROR
                        )}>
                          {realtimeResult.result.recommendation}
                        </Badge>
                      </div>

                      <div className="px-4 py-3 space-y-3">
                        {/* Explanation */}
                        {realtimeResult.result.explanation && (
                          <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">{realtimeResult.result.explanation}</p>
                        )}

                        {/* 6 dimension scores */}
                        <div className="grid grid-cols-3 gap-2">
                          {Object.entries(realtimeResult.result.scores).map(([dim, score]) => (
                            <ScoreCard
                              key={dim}
                              dimension={dim}
                              score={score}
                              explanation={realtimeResult.result.dimension_explanations?.[dim]}
                            />
                          ))}
                        </div>

                        {/* Strengths & Weaknesses */}
                        <div className="grid grid-cols-2 gap-2">
                          {realtimeResult.result.strengths?.length > 0 && (
                            <div className="rounded-lg border border-emerald-200 dark:border-emerald-800 bg-emerald-50/50 dark:bg-emerald-900/20 p-2.5">
                              <div className="flex items-center gap-1.5 text-[11px] font-semibold text-emerald-700 dark:text-emerald-400 mb-1.5">
                                <ThumbsUp className="w-3 h-3" /> Strengths
                              </div>
                              <ul className="space-y-0.5">
                                {realtimeResult.result.strengths.map((s, i) => (
                                  <li key={i} className="text-[11px] text-emerald-700 dark:text-emerald-400 leading-relaxed">{s}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                          {realtimeResult.result.weaknesses?.length > 0 && (
                            <div className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50/50 dark:bg-red-900/20 p-2.5">
                              <div className="flex items-center gap-1.5 text-[11px] font-semibold text-red-700 dark:text-red-400 mb-1.5">
                                <ThumbsDown className="w-3 h-3" /> Weaknesses
                              </div>
                              <ul className="space-y-0.5">
                                {realtimeResult.result.weaknesses.map((w, i) => (
                                  <li key={i} className="text-[11px] text-red-700 dark:text-red-400 leading-relaxed">{w}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            <div ref={stepsEndRef} />
          </div>
        </div>
      )}

      {/* ============ BATCH MODE ============ */}
      {mode === "batch" && (
        <div className="flex-1 overflow-auto space-y-4">
          {/* Controls */}
          <div className="flex items-center gap-3">
            <select
              value={batchFilter}
              onChange={e => setBatchFilter(e.target.value)}
              className="px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 text-sm bg-white dark:bg-slate-800 dark:text-slate-200"
              disabled={batchRunning}
            >
              <option value="all">All categories</option>
              <option value="environment">Environment</option>
              <option value="sizing">Sizing</option>
              <option value="material">Material</option>
              <option value="env">Env</option>
            </select>
            <button
              onClick={handleBatchRun}
              disabled={batchRunning}
              className={cn(
                "px-5 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2",
                batchRunning
                  ? "bg-slate-100 dark:bg-slate-800 text-slate-400 cursor-not-allowed"
                  : "bg-green-700 text-white hover:bg-green-800"
              )}
            >
              {batchRunning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              {batchRunning ? "Running..." : "Run Batch Judge"}
            </button>
            {batchRunning && (
              <div className="flex-1">
                <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
                  <span>{batchProgress.current}/{batchProgress.total} judged</span>
                  <div className="flex-1 h-2 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-green-500 rounded-full transition-all duration-300"
                      style={{ width: `${batchProgress.total > 0 ? (batchProgress.current / batchProgress.total) * 100 : 0}%` }}
                    />
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Batch results */}
          {batchResults && (
            <>
              {/* Summary cards */}
              <div className="grid grid-cols-4 gap-3">
                <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3 text-center">
                  <div className="text-2xl font-bold text-slate-800 dark:text-slate-100">{batchResults.meta.avg_overall_score.toFixed(1)}</div>
                  <div className="text-xs text-slate-500 dark:text-slate-400">Avg Score</div>
                </div>
                <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3 text-center">
                  <div className="text-2xl font-bold text-slate-800 dark:text-slate-100">{batchResults.meta.total_questions}</div>
                  <div className="text-xs text-slate-500 dark:text-slate-400">Questions</div>
                </div>
                <div className="rounded-lg border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/30 p-3 text-center">
                  <div className="text-2xl font-bold text-emerald-700 dark:text-emerald-400">
                    {batchResults.results.filter(r => r.judge_result?.recommendation === "PASS").length}
                  </div>
                  <div className="text-xs text-emerald-600 dark:text-emerald-400">Pass</div>
                </div>
                <div className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/30 p-3 text-center">
                  <div className="text-2xl font-bold text-red-700 dark:text-red-400">
                    {batchResults.results.filter(r => r.judge_result?.recommendation === "FAIL" || r.judge_result?.recommendation === "ERROR").length}
                  </div>
                  <div className="text-xs text-red-600 dark:text-red-400">Fail/Error</div>
                </div>
              </div>

              {/* Category breakdown */}
              {batchResults.meta.category_summary && Object.keys(batchResults.meta.category_summary).length > 0 && (
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="text-xs text-slate-500 dark:text-slate-400 font-medium">By category:</span>
                  {Object.entries(batchResults.meta.category_summary).map(([cat, avg]) => (
                    <span
                      key={cat}
                      className={cn(
                        "px-2.5 py-1 rounded-full text-xs font-medium border",
                        avg >= 4 ? "bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800"
                          : avg >= 3 ? "bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800"
                          : "bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-400 border-red-200 dark:border-red-800"
                      )}
                    >
                      {cat}: {avg.toFixed(1)}
                    </span>
                  ))}
                </div>
              )}

              {/* Score filter */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500 dark:text-slate-400">Filter:</span>
                {([
                  { id: "all" as const, label: "All" },
                  { id: "low" as const, label: "< 3.0" },
                  { id: "medium" as const, label: "3.0-3.9" },
                  { id: "high" as const, label: ">= 4.0" },
                ] as const).map(f => (
                  <button
                    key={f.id}
                    onClick={() => setBatchScoreFilter(f.id)}
                    className={cn(
                      "px-2.5 py-1 rounded-full text-xs font-medium border transition-colors",
                      batchScoreFilter === f.id
                        ? "bg-slate-800 dark:bg-slate-200 text-white dark:text-slate-900 border-slate-800 dark:border-slate-200"
                        : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600"
                    )}
                  >
                    {f.label} ({batchResults.results.filter(r => {
                      const s = r.judge_result?.overall_score || 0;
                      if (f.id === "low") return s < 3;
                      if (f.id === "medium") return s >= 3 && s < 4;
                      if (f.id === "high") return s >= 4;
                      return true;
                    }).length})
                  </button>
                ))}
              </div>

              {/* Results table */}
              <div className="space-y-2">
                {filteredBatchResults.map((r, idx) => {
                  const score = r.judge_result?.overall_score || 0;
                  const rec = r.judge_result?.recommendation || "ERROR";
                  const isExpanded = expandedBatchIdx === idx;
                  return (
                    <div key={r.question_id} className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 overflow-hidden">
                      <button
                        onClick={() => setExpandedBatchIdx(isExpanded ? null : idx)}
                        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors"
                      >
                        {/* Score badge */}
                        <span className={cn(
                          "w-10 h-10 rounded-lg flex items-center justify-center text-sm font-bold border",
                          score >= 4 ? "bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800"
                            : score >= 3 ? "bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800"
                            : "bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-400 border-red-200 dark:border-red-800"
                        )}>
                          {score.toFixed(1)}
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-mono text-slate-700 dark:text-slate-300 truncate">{r.question_id}</div>
                          <div className="text-[11px] text-slate-500 dark:text-slate-400 truncate">{r.question_text}</div>
                        </div>
                        <Badge className={cn("text-[10px] px-2 py-0.5 border font-medium", RECOMMENDATION_COLORS[rec])}>
                          {rec}
                        </Badge>
                        <span className={cn("px-1.5 py-0.5 rounded text-[9px] font-medium border", CATEGORY_COLORS[r.category] || "bg-slate-50 text-slate-500 border-slate-200")}>
                          {r.category}
                        </span>
                        {isExpanded ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
                      </button>
                      {isExpanded && r.judge_result && (
                        <div className="border-t border-slate-100 dark:border-slate-700 p-4">
                          <JudgeResultView
                            result={r.judge_result}
                            question={r.question_text}
                            systemResponse={r.system_response?.content_text}
                          />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {/* Empty state */}
          {!batchResults && !batchRunning && (
            <div className="flex flex-col items-center justify-center py-16 text-slate-400 dark:text-slate-500 gap-3">
              <BarChart3 className="w-10 h-10 text-slate-300 dark:text-slate-600" />
              <p className="text-sm">No judge results yet</p>
              <p className="text-xs">Click &quot;Run Batch Judge&quot; to evaluate all test cases</p>
            </div>
          )}
        </div>
      )}

      {/* ============ GENERATE MODE ============ */}
      {mode === "generate" && (
        <div className="flex-1 overflow-auto space-y-4">
          {/* PDF upload + config */}
          <div className="flex items-end gap-3">
            <div className="flex-1">
              <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">Product Catalog PDF</label>
              <div
                className={cn(
                  "border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors",
                  genFile ? "border-green-300 dark:border-green-800 bg-green-50 dark:bg-green-900/20" : "border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600 bg-white dark:bg-slate-800"
                )}
                onClick={() => document.getElementById("judge-pdf-input")?.click()}
              >
                <input
                  id="judge-pdf-input"
                  type="file"
                  accept=".pdf"
                  className="hidden"
                  onChange={e => setGenFile(e.target.files?.[0] || null)}
                />
                {genFile ? (
                  <div className="flex items-center justify-center gap-2 text-sm text-green-800 dark:text-green-500">
                    <FileText className="w-4 h-4" />
                    {genFile.name} ({(genFile.size / 1024).toFixed(0)} KB)
                  </div>
                ) : (
                  <div className="text-sm text-slate-400">
                    <Upload className="w-5 h-5 mx-auto mb-1" />
                    Click to upload PDF
                  </div>
                )}
              </div>
            </div>
            <div className="w-32">
              <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">Questions</label>
              <input
                type="number"
                value={genCount}
                onChange={e => setGenCount(Math.max(5, Math.min(50, parseInt(e.target.value) || 20)))}
                min={5}
                max={50}
                className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 text-sm bg-white dark:bg-slate-800 dark:text-slate-200"
              />
            </div>
            <button
              onClick={handleGenerate}
              disabled={!genFile || generating}
              className={cn(
                "px-5 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2",
                !genFile || generating
                  ? "bg-slate-100 dark:bg-slate-800 text-slate-400 cursor-not-allowed"
                  : "bg-green-700 text-white hover:bg-green-800"
              )}
            >
              {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              Generate
            </button>
          </div>

          {/* Status */}
          {genStatus && (
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              {generating && <Loader2 className="w-4 h-4 animate-spin" />}
              {genStatus}
            </div>
          )}

          {/* Generated questions */}
          {genQuestions.length > 0 && (
            <>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                  {genQuestions.length} questions generated
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setSelectedGenIds(new Set(genQuestions.map(q => q.id)))}
                    className="text-xs text-green-700 dark:text-green-500 hover:text-green-800 dark:hover:text-green-300"
                  >
                    Select all
                  </button>
                  <button
                    onClick={handleApproveQuestions}
                    disabled={selectedGenIds.size === 0}
                    className={cn(
                      "px-4 py-1.5 rounded-lg text-xs font-medium transition-colors",
                      selectedGenIds.size > 0
                        ? "bg-emerald-600 text-white hover:bg-emerald-700"
                        : "bg-slate-100 dark:bg-slate-800 text-slate-400 cursor-not-allowed"
                    )}
                  >
                    Approve ({selectedGenIds.size})
                  </button>
                </div>
              </div>
              <div className="space-y-2">
                {genQuestions.map(q => (
                  <div
                    key={q.id}
                    className={cn(
                      "rounded-lg border p-3 cursor-pointer transition-colors",
                      selectedGenIds.has(q.id)
                        ? "border-green-300 dark:border-green-800 bg-green-50 dark:bg-green-900/20"
                        : "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700/50"
                    )}
                    onClick={() => setSelectedGenIds(prev => {
                      const next = new Set(prev);
                      if (next.has(q.id)) next.delete(q.id); else next.add(q.id);
                      return next;
                    })}
                  >
                    <div className="flex items-start gap-3">
                      <input
                        type="checkbox"
                        checked={selectedGenIds.has(q.id)}
                        onChange={() => {}}
                        className="mt-1 rounded border-slate-300"
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-slate-700 dark:text-slate-300">{q.question}</p>
                        <div className="flex items-center gap-2 mt-1.5">
                          <span className={cn("px-1.5 py-0.5 rounded text-[10px] font-medium border", CATEGORY_COLORS[q.category] || "bg-slate-50 text-slate-500 border-slate-200")}>
                            {q.category}
                          </span>
                          <span className="text-[10px] text-slate-400 dark:text-slate-500">{q.difficulty}</span>
                        </div>
                        {q.expected_elements?.length > 0 && (
                          <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                            <span className="font-medium">Expected: </span>
                            {q.expected_elements.join(" | ")}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          {/* Empty state */}
          {genQuestions.length === 0 && !generating && (
            <div className="flex flex-col items-center justify-center py-16 text-slate-400 dark:text-slate-500 gap-3">
              <Sparkles className="w-10 h-10 text-slate-300 dark:text-slate-600" />
              <p className="text-sm">Upload a product catalog PDF to generate evaluation questions</p>
              <p className="text-xs">Gemini 3 Pro will analyze the PDF and create diverse test questions</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function TestLab() {
  const [data, setData] = useState<TestLabData | null>(null);
  const [singleTests, setSingleTests] = useState<TestResult[]>([]);
  const [multiTests, setMultiTests] = useState<TestResult[]>([]);
  const [activeTab, setActiveTab] = useState<"single" | "multi" | "judge">("single");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const detailRef = useRef<HTMLDivElement>(null);

  const fetchResults = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [singleRes, multiRes] = await Promise.allSettled([
        apiFetch("/test-lab/results"),
        apiFetch("/test-lab/multistep-results"),
      ]);

      let singleData: TestLabData | null = null;
      let fetchedMultiTests: TestResult[] = [];

      if (singleRes.status === "fulfilled" && singleRes.value.ok) {
        singleData = await singleRes.value.json();
      }
      if (multiRes.status === "fulfilled" && multiRes.value.ok) {
        const msData: MultiStepData = await multiRes.value.json();
        fetchedMultiTests = normalizeMultiStep(msData);
      }

      if (!singleData && fetchedMultiTests.length === 0) {
        throw new Error("No test results available. Run the test suite first.");
      }

      const fetchedSingleTests = singleData?.tests ?? [];
      const mergedMeta = buildMergedMeta(singleData?.meta ?? null, fetchedMultiTests, fetchedSingleTests);

      setSingleTests(fetchedSingleTests);
      setMultiTests(fetchedMultiTests);
      setData({ meta: mergedMeta, tests: [...fetchedSingleTests, ...fetchedMultiTests] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load test results");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchResults(); }, [fetchResults]);

  // Tab switch resets filters and selection
  const handleTabSwitch = useCallback((tab: "single" | "multi" | "judge") => {
    setActiveTab(tab);
    setSelectedIndex(0);
    setCategoryFilter("all");
    setStatusFilter("all");
  }, []);

  // Filter tests based on active tab
  const sourceTests = activeTab === "single" ? singleTests : multiTests;
  const filteredTests = sourceTests.filter(t => {
    if (categoryFilter !== "all" && t.category !== categoryFilter) return false;
    if (statusFilter !== "all" && t.status !== statusFilter) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return t.name.toLowerCase().includes(q)
        || t.description.toLowerCase().includes(q)
        || t.query.toLowerCase().includes(q);
    }
    return true;
  });

  const selectedTest = filteredTests[selectedIndex] ?? null;

  // Tab-specific categories
  const tabCategories = Array.from(new Set(sourceTests.map(t => t.category))).sort();

  // Keyboard navigation
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return;
      if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex(prev => Math.max(0, prev - 1));
      } else if (e.key === "ArrowRight" || e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex(prev => Math.min(filteredTests.length - 1, prev + 1));
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [filteredTests.length]);

  // Scroll detail to top on test change
  useEffect(() => {
    detailRef.current?.scrollTo(0, 0);
  }, [selectedIndex]);

  // Reset selection when filters change
  useEffect(() => {
    setSelectedIndex(0);
  }, [categoryFilter, statusFilter, searchQuery]);

  // Categories from active tab data
  const categories = tabCategories;

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center h-[500px] text-slate-400 dark:text-slate-500">
        <RefreshCw className="w-5 h-5 animate-spin mr-2" />
        Loading test results...
      </div>
    );
  }

  // Error state
  if (error || !data) {
    return (
      <div className="flex flex-col items-center justify-center h-[500px] text-slate-400 dark:text-slate-500 gap-3">
        <FlaskConical className="w-10 h-10 text-slate-300 dark:text-slate-600" />
        <p className="text-sm">{error || "No data"}</p>
        <p className="text-xs text-slate-400 dark:text-slate-500">Run: <code className="bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded">python run_tests.py all --json backend/static/test-results.json</code></p>
        <button onClick={fetchResults} className="text-xs text-green-600 hover:text-green-800 dark:text-green-500 dark:hover:text-green-300">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] gap-4">
      {/* ===== TEST RESULTS TABS ===== */}
      {<>
      {/* Summary + timestamp */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <SummaryBar meta={data.meta} />
          <div className="flex items-center gap-2 ml-4 shrink-0">
            <span className="text-xs text-slate-400">{relativeTime(data.meta.timestamp)}</span>
            <button
              onClick={fetchResults}
              className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
              title="Refresh results"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Category pills */}
          <button
            onClick={() => setCategoryFilter("all")}
            className={cn(
              "px-2.5 py-1 rounded-full text-xs font-medium border transition-colors",
              categoryFilter === "all"
                ? "bg-slate-800 dark:bg-slate-200 text-white dark:text-slate-900 border-slate-800 dark:border-slate-200"
                : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600"
            )}
          >
            All ({sourceTests.length})
          </button>
          {categories.map(cat => {
            const catCount = sourceTests.filter(t => t.category === cat).length;
            return (
              <button
                key={cat}
                onClick={() => setCategoryFilter(cat === categoryFilter ? "all" : cat)}
                className={cn(
                  "px-2.5 py-1 rounded-full text-xs font-medium border transition-colors",
                  categoryFilter === cat
                    ? "bg-slate-800 dark:bg-slate-200 text-white dark:text-slate-900 border-slate-800 dark:border-slate-200"
                    : cn("bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600", CATEGORY_COLORS[cat]?.replace("bg-", "hover:bg-") || "")
                )}
              >
                {cat} ({catCount})
              </button>
            );
          })}

          <div className="w-px h-5 bg-slate-200 dark:bg-slate-700 mx-1" />

          {/* Status filter */}
          {(["all", "PASS", "FAIL", "ERROR"] as const).map(s => (
            <button
              key={s}
              onClick={() => setStatusFilter(s === statusFilter ? "all" : s)}
              className={cn(
                "px-2.5 py-1 rounded-full text-xs font-medium border transition-colors",
                statusFilter === s
                  ? s === "PASS" ? "bg-emerald-600 text-white border-emerald-600"
                    : s === "FAIL" ? "bg-red-600 text-white border-red-600"
                    : s === "ERROR" ? "bg-amber-600 text-white border-amber-600"
                    : "bg-slate-800 dark:bg-slate-200 text-white dark:text-slate-900 border-slate-800 dark:border-slate-200"
                  : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600"
              )}
            >
              {s === "all" ? "All" : s}
            </button>
          ))}

          <div className="w-px h-5 bg-slate-200 dark:bg-slate-700 mx-1" />

          {/* Search */}
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Search tests..."
              className="w-full pl-8 pr-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-xs bg-white dark:bg-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-green-600/20 focus:border-green-300 dark:focus:border-green-700 dark:placeholder:text-slate-500"
            />
          </div>
        </div>
      </div>

      {/* Main two-panel layout */}
      <div className="flex gap-4 flex-1 min-h-0">
        {/* Left panel — test list */}
        <div className="w-[320px] shrink-0 flex flex-col bg-white dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
          <div className="flex border-b border-slate-100 dark:border-slate-700">
            <button
              onClick={() => handleTabSwitch("single")}
              className={cn(
                "flex-1 px-3 py-2 text-xs font-medium transition-colors",
                activeTab === "single"
                  ? "bg-slate-800 dark:bg-slate-200 text-white dark:text-slate-900"
                  : "text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-700 hover:text-slate-700 dark:hover:text-slate-300"
              )}
            >
              Single ({singleTests.length})
            </button>
            <button
              onClick={() => handleTabSwitch("multi")}
              className={cn(
                "flex-1 px-3 py-2 text-xs font-medium transition-colors flex items-center justify-center gap-1",
                activeTab === "multi"
                  ? "bg-slate-800 dark:bg-slate-200 text-white dark:text-slate-900"
                  : "text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-700 hover:text-slate-700 dark:hover:text-slate-300"
              )}
            >
              <Layers className="w-3 h-3" />
              Multi ({multiTests.length})
            </button>
          </div>
          <ScrollArea className="flex-1">
            <div className="p-1">
              {filteredTests.map((test, i) => (
                <button
                  key={test.name}
                  onClick={() => setSelectedIndex(i)}
                  className={cn(
                    "w-full text-left px-3 py-2.5 rounded-lg transition-colors flex items-center gap-2 group",
                    selectedIndex === i
                      ? "bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800"
                      : "hover:bg-slate-50 dark:hover:bg-slate-700/50 border border-transparent",
                    test.status === "FAIL" && selectedIndex !== i && "border-l-2 border-l-red-300",
                    test.status === "ERROR" && selectedIndex !== i && "border-l-2 border-l-amber-300",
                  )}
                >
                  {statusIcon(test.status)}
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-mono text-slate-700 dark:text-slate-300 truncate">{test.name}</div>
                    <div className="text-[10px] text-slate-400 dark:text-slate-500 truncate">{test.description}</div>
                  </div>
                  <div className="flex flex-col items-end gap-0.5 shrink-0">
                    <div className="flex items-center gap-1">
                      {test.isMultiStep && (
                        <span className="px-1.5 py-0.5 rounded text-[9px] font-medium border bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-500 border-green-200 dark:border-green-800">
                          {test.steps?.length} steps
                        </span>
                      )}
                      <span className={cn("px-1.5 py-0.5 rounded text-[9px] font-medium border", CATEGORY_COLORS[test.category] || "bg-slate-50 text-slate-500 border-slate-200")}>
                        {test.category}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-400">{test.duration_s.toFixed(1)}s</span>
                  </div>
                </button>
              ))}
              {filteredTests.length === 0 && (
                <div className="px-4 py-8 text-center text-xs text-slate-400">
                  {sourceTests.length === 0
                    ? activeTab === "multi"
                      ? <>No multi-step results. Run: <code className="bg-slate-100 dark:bg-slate-800 px-1 py-0.5 rounded">python tests/multistep/run.py all</code></>
                      : "No single-step results available"
                    : "No tests match your filters"
                  }
                </div>
              )}
            </div>
          </ScrollArea>
        </div>

        {/* Right panel — test detail */}
        <div className="flex-1 flex flex-col bg-white dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden min-w-0">
          {selectedTest ? (
            <>
              {/* Navigation bar */}
              <div className="flex items-center justify-between px-4 py-2 border-b border-slate-100 dark:border-slate-700">
                <button
                  onClick={() => setSelectedIndex(prev => Math.max(0, prev - 1))}
                  disabled={selectedIndex <= 0}
                  className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronLeft className="w-3.5 h-3.5" /> Prev
                </button>
                <span className="text-xs text-slate-400 font-medium">
                  {selectedIndex + 1} / {filteredTests.length}
                </span>
                <button
                  onClick={() => setSelectedIndex(prev => Math.min(filteredTests.length - 1, prev + 1))}
                  disabled={selectedIndex >= filteredTests.length - 1}
                  className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  Next <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="flex-1 overflow-auto" ref={detailRef}>
                <div className="p-5">
                  {selectedTest.isMultiStep
                    ? <MultiStepDetail test={selectedTest} />
                    : <TestDetail test={selectedTest} />}
                </div>
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-full text-slate-400 dark:text-slate-500 text-sm">
              Select a test from the list
            </div>
          )}
        </div>
      </div>
      </>}
    </div>
  );
}
