"use client";

import { useState, useEffect, useMemo } from "react";
import { authFetch, apiUrl } from "@/lib/api";
import {
  BarChart3, Clock, CheckCircle2, XCircle, AlertTriangle,
  ChevronDown, ChevronUp, ArrowUpDown, RefreshCw, Loader2,
  FileText, Brain, Sparkles, Eye, TrendingUp,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DimensionScores {
  correctness?: number;
  completeness?: number;
  safety?: number;
  tone?: number;
  reasoning_quality?: number;
  constraint_adherence?: number;
}

interface JudgeResult {
  overall: number;
  recommendation: string;
  scores: DimensionScores;
  explanation: string;
  weaknesses: string[];
  strengths: string[];
  pdf_citations: string[];
  dimension_explanations: Record<string, string>;
}

interface TestResult {
  name: string;
  query: string;
  duration_s: number;
  error: string | null;
  total_turns: number;
  last_judged_turn: number;
  judges: Record<string, JudgeResult>;
}

interface BatchSummary {
  batch_id: string;
  test_count: number;
  results: TestResult[];
}

interface BatchListItem {
  id: string;
  timestamp: number;
  test_count: number;
  judged_count: number;
  judge_avgs: Record<string, number>;
  overall_avg: number;
  dimension_avgs: Record<string, number>;
  pass_count: number;
  fail_count: number;
}

type SortKey = "name" | "avg" | "gemini" | "openai" | "anthropic" | "duration" | "turns";
type SortDir = "asc" | "desc";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getJudgeScore(test: TestResult, provider: string): number {
  return test.judges[provider]?.overall ?? 0;
}

function getAvgScore(test: TestResult): number {
  const vals = Object.values(test.judges).map(j => j.overall).filter(v => v > 0);
  return vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
}

function recBadge(rec: string) {
  if (rec === "PASS") return <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400">PASS</span>;
  if (rec === "FAIL") return <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400">FAIL</span>;
  if (rec === "BORDERLINE") return <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400">BORDER</span>;
  return <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500">N/A</span>;
}

function scoreColor(score: number): string {
  if (score >= 4.0) return "text-emerald-600 dark:text-emerald-400";
  if (score >= 3.0) return "text-amber-600 dark:text-amber-400";
  if (score > 0) return "text-red-600 dark:text-red-400";
  return "text-gray-400";
}

function scoreBg(score: number): string {
  if (score >= 4.0) return "bg-emerald-50 dark:bg-emerald-900/20";
  if (score >= 3.0) return "bg-amber-50 dark:bg-amber-900/20";
  if (score > 0) return "bg-red-50 dark:bg-red-900/20";
  return "bg-gray-50 dark:bg-gray-800/50";
}

function dimLabel(key: string): string {
  const map: Record<string, string> = {
    correctness: "COR", completeness: "COM", safety: "SAF",
    tone: "TON", reasoning_quality: "REA", constraint_adherence: "CON",
  };
  return map[key] || key.slice(0, 3).toUpperCase();
}

function formatTs(ts: number): string {
  return new Date(ts * 1000).toLocaleString("en-GB", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

function formatTsShort(ts: number): string {
  return new Date(ts * 1000).toLocaleString("en-GB", {
    day: "2-digit", month: "short",
    hour: "2-digit", minute: "2-digit",
  });
}

// ---------------------------------------------------------------------------
// Cross-batch trend chart (SVG)
// ---------------------------------------------------------------------------

const CHART_COLORS = {
  gemini: "#5B8C3E",   // violet
  openai: "#34d399",   // emerald
  anthropic: "#f59e0b", // amber
  overall: "#7CB356",  // blue
};

function TrendChart({ batches, selectedBatch, onSelect }: {
  batches: BatchListItem[];
  selectedBatch: string | null;
  onSelect: (id: string) => void;
}) {
  // Only show batches with judge data, sorted chronologically
  const data = useMemo(() =>
    [...batches]
      .filter(b => b.judged_count > 0 && b.test_count >= 5)
      .sort((a, b) => a.timestamp - b.timestamp),
    [batches]
  );

  if (data.length < 2) return null;

  const W = 700, H = 200;
  const PAD = { top: 20, right: 20, bottom: 30, left: 40 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const minY = 1, maxY = 5;
  const yScale = (v: number) => PAD.top + plotH - ((v - minY) / (maxY - minY)) * plotH;
  const xScale = (i: number) => PAD.left + (i / (data.length - 1)) * plotW;

  const makePath = (key: string) => {
    const points = data.map((b, i) => {
      const v = key === "overall" ? b.overall_avg : (b.judge_avgs[key] || 0);
      return `${i === 0 ? "M" : "L"}${xScale(i).toFixed(1)},${yScale(v).toFixed(1)}`;
    });
    return points.join(" ");
  };

  const yTicks = [1, 2, 3, 4, 5];
  const lines = [
    { key: "gemini", label: "Gemini" },
    { key: "openai", label: "GPT-5.2" },
    { key: "anthropic", label: "Claude" },
    { key: "overall", label: "3-Avg" },
  ];

  return (
    <div className="bg-white dark:bg-slate-800/60 rounded-xl border border-slate-200/60 dark:border-slate-700/60 p-4 mb-6">
      <div className="flex items-center gap-2 mb-3">
        <TrendingUp className="w-4 h-4 text-green-600" />
        <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">Score Trend Across Batches</span>
        <span className="text-xs text-slate-400">({data.length} runs)</span>
      </div>

      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[700px] h-auto">
          {/* Grid lines */}
          {yTicks.map(y => (
            <g key={y}>
              <line x1={PAD.left} x2={W - PAD.right} y1={yScale(y)} y2={yScale(y)}
                stroke="currentColor" className="text-slate-200 dark:text-slate-700" strokeWidth={0.5} />
              <text x={PAD.left - 6} y={yScale(y) + 4} textAnchor="end"
                className="fill-slate-400 dark:fill-slate-500" fontSize={10}>{y}</text>
            </g>
          ))}

          {/* X axis labels */}
          {data.map((b, i) => (
            <text key={b.id} x={xScale(i)} y={H - 5} textAnchor="middle"
              className="fill-slate-400 dark:fill-slate-500" fontSize={9}>
              {formatTsShort(b.timestamp)}
            </text>
          ))}

          {/* Lines */}
          {lines.map(({ key }) => (
            <path key={key} d={makePath(key)} fill="none"
              stroke={CHART_COLORS[key as keyof typeof CHART_COLORS]}
              strokeWidth={key === "overall" ? 2.5 : 1.5}
              strokeDasharray={key === "overall" ? "6 3" : "none"}
              opacity={key === "overall" ? 0.8 : 0.9} />
          ))}

          {/* Data points */}
          {data.map((b, i) => (
            <g key={b.id}>
              {lines.map(({ key }) => {
                const v = key === "overall" ? b.overall_avg : (b.judge_avgs[key] || 0);
                if (v <= 0) return null;
                return (
                  <circle key={key} cx={xScale(i)} cy={yScale(v)} r={b.id === selectedBatch ? 5 : 3}
                    fill={CHART_COLORS[key as keyof typeof CHART_COLORS]}
                    stroke={b.id === selectedBatch ? "white" : "none"} strokeWidth={1.5}
                    className="cursor-pointer" onClick={() => onSelect(b.id)}>
                    <title>{`${key}: ${v.toFixed(2)} — ${formatTsShort(b.timestamp)}`}</title>
                  </circle>
                );
              })}
            </g>
          ))}
        </svg>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-2 justify-center">
        {lines.map(({ key, label }) => (
          <div key={key} className="flex items-center gap-1.5">
            <div className="w-3 h-0.5 rounded" style={{ background: CHART_COLORS[key as keyof typeof CHART_COLORS] }} />
            <span className="text-[10px] text-slate-500 dark:text-slate-400">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Cross-batch overview table
// ---------------------------------------------------------------------------

function BatchOverviewTable({ batches, selectedBatch, onSelect }: {
  batches: BatchListItem[];
  selectedBatch: string | null;
  onSelect: (id: string) => void;
}) {
  const data = useMemo(() =>
    [...batches]
      .filter(b => b.judged_count > 0 && b.test_count >= 5)
      .sort((a, b) => b.timestamp - a.timestamp),
    [batches]
  );

  if (data.length === 0) return null;

  return (
    <div className="bg-white dark:bg-slate-800/60 rounded-xl border border-slate-200/60 dark:border-slate-700/60 overflow-hidden mb-6">
      <div className="px-4 py-3 border-b border-slate-200/60 dark:border-slate-700/60 bg-slate-50 dark:bg-slate-800/80">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">All Batch Runs</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200/60 dark:border-slate-700/60">
              <th className="text-left px-4 py-2 text-[11px] font-semibold uppercase text-slate-500 dark:text-slate-400">Date</th>
              <th className="text-center px-3 py-2 text-[11px] font-semibold uppercase text-slate-500 dark:text-slate-400">Tests</th>
              <th className="text-center px-3 py-2 text-[11px] font-semibold uppercase text-slate-500 dark:text-slate-400">3-Avg</th>
              <th className="text-center px-3 py-2 text-[11px] font-semibold uppercase text-slate-500 dark:text-slate-400">Gemini</th>
              <th className="text-center px-3 py-2 text-[11px] font-semibold uppercase text-slate-500 dark:text-slate-400">GPT</th>
              <th className="text-center px-3 py-2 text-[11px] font-semibold uppercase text-slate-500 dark:text-slate-400">Claude</th>
              <th className="text-center px-3 py-2 text-[11px] font-semibold uppercase text-slate-500 dark:text-slate-400">Pass</th>
              <th className="text-center px-3 py-2 text-[11px] font-semibold uppercase text-slate-500 dark:text-slate-400">Fail</th>
              <th className="text-center px-3 py-2 text-[11px] font-semibold uppercase text-slate-500 dark:text-slate-400">COR</th>
              <th className="text-center px-3 py-2 text-[11px] font-semibold uppercase text-slate-500 dark:text-slate-400">SAF</th>
              <th className="text-center px-3 py-2 text-[11px] font-semibold uppercase text-slate-500 dark:text-slate-400">COM</th>
              <th className="text-center px-3 py-2 text-[11px] font-semibold uppercase text-slate-500 dark:text-slate-400">CON</th>
            </tr>
          </thead>
          <tbody>
            {data.map(b => {
              const isSelected = b.id === selectedBatch;
              return (
                <tr key={b.id}
                  onClick={() => onSelect(b.id)}
                  className={cn(
                    "border-b border-slate-100 dark:border-slate-800 cursor-pointer transition-colors",
                    isSelected ? "bg-green-50/60 dark:bg-green-900/15" : "hover:bg-slate-50 dark:hover:bg-slate-800/40"
                  )}>
                  <td className="px-4 py-2">
                    <span className={cn("text-xs", isSelected ? "font-bold text-green-700 dark:text-green-500" : "text-slate-600 dark:text-slate-300")}>
                      {formatTs(b.timestamp)}
                    </span>
                  </td>
                  <td className="text-center px-3 py-2 text-xs text-slate-500">{b.judged_count}/{b.test_count}</td>
                  <td className={cn("text-center px-3 py-2 text-xs font-bold", scoreColor(b.overall_avg))}>{b.overall_avg.toFixed(2)}</td>
                  <td className={cn("text-center px-3 py-2 text-xs font-semibold", scoreColor(b.judge_avgs.gemini || 0))}>{(b.judge_avgs.gemini || 0).toFixed(2)}</td>
                  <td className={cn("text-center px-3 py-2 text-xs font-semibold", scoreColor(b.judge_avgs.openai || 0))}>{(b.judge_avgs.openai || 0).toFixed(2)}</td>
                  <td className={cn("text-center px-3 py-2 text-xs font-semibold", scoreColor(b.judge_avgs.anthropic || 0))}>{(b.judge_avgs.anthropic || 0).toFixed(2)}</td>
                  <td className="text-center px-3 py-2 text-xs text-emerald-600 dark:text-emerald-400 font-medium">{b.pass_count}</td>
                  <td className="text-center px-3 py-2 text-xs text-red-600 dark:text-red-400 font-medium">{b.fail_count}</td>
                  <td className={cn("text-center px-3 py-2 text-xs", scoreColor(b.dimension_avgs.correctness || 0))}>{(b.dimension_avgs.correctness || 0).toFixed(1)}</td>
                  <td className={cn("text-center px-3 py-2 text-xs", scoreColor(b.dimension_avgs.safety || 0))}>{(b.dimension_avgs.safety || 0).toFixed(1)}</td>
                  <td className={cn("text-center px-3 py-2 text-xs", scoreColor(b.dimension_avgs.completeness || 0))}>{(b.dimension_avgs.completeness || 0).toFixed(1)}</td>
                  <td className={cn("text-center px-3 py-2 text-xs", scoreColor(b.dimension_avgs.constraint_adherence || 0))}>{(b.dimension_avgs.constraint_adherence || 0).toFixed(1)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stats Bar
// ---------------------------------------------------------------------------

function StatsBar({ results }: { results: TestResult[] }) {
  const totalTests = results.length;
  const withScores = results.filter(r => Object.keys(r.judges).length > 0);

  const avgByJudge = (provider: string) => {
    const vals = withScores.map(r => getJudgeScore(r, provider)).filter(v => v > 0);
    return vals.length > 0 ? (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2) : "-";
  };

  const overallAvg = () => {
    const vals = withScores.map(r => getAvgScore(r)).filter(v => v > 0);
    return vals.length > 0 ? (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2) : "-";
  };

  const passCount = withScores.filter(r => {
    const avg = getAvgScore(r);
    return avg >= 3.5;
  }).length;

  const failCount = withScores.filter(r => {
    const recs = Object.values(r.judges).map(j => j.recommendation);
    return recs.includes("FAIL");
  }).length;

  const dimAvgs: Record<string, number> = {};
  const dimKeys = ["correctness", "completeness", "safety", "tone", "reasoning_quality", "constraint_adherence"];
  for (const dim of dimKeys) {
    const vals: number[] = [];
    for (const r of withScores) {
      for (const j of Object.values(r.judges)) {
        const v = j.scores[dim as keyof DimensionScores];
        if (v && v > 0) vals.push(v);
      }
    }
    dimAvgs[dim] = vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 mb-6">
      <div className="bg-white dark:bg-slate-800/60 rounded-xl p-4 border border-slate-200/60 dark:border-slate-700/60">
        <div className="text-xs text-slate-500 dark:text-slate-400 mb-1">Tests</div>
        <div className="text-2xl font-bold text-slate-900 dark:text-slate-100">{totalTests}</div>
      </div>
      <div className="bg-white dark:bg-slate-800/60 rounded-xl p-4 border border-slate-200/60 dark:border-slate-700/60">
        <div className="text-xs text-slate-500 dark:text-slate-400 mb-1">3-Judge Avg</div>
        <div className={cn("text-2xl font-bold", scoreColor(parseFloat(overallAvg()) || 0))}>{overallAvg()}</div>
      </div>
      <div className="bg-white dark:bg-slate-800/60 rounded-xl p-4 border border-slate-200/60 dark:border-slate-700/60">
        <div className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400 mb-1"><Sparkles className="w-3 h-3" /> Gemini</div>
        <div className={cn("text-2xl font-bold", scoreColor(parseFloat(avgByJudge("gemini")) || 0))}>{avgByJudge("gemini")}</div>
      </div>
      <div className="bg-white dark:bg-slate-800/60 rounded-xl p-4 border border-slate-200/60 dark:border-slate-700/60">
        <div className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400 mb-1"><Brain className="w-3 h-3" /> GPT-5.2</div>
        <div className={cn("text-2xl font-bold", scoreColor(parseFloat(avgByJudge("openai")) || 0))}>{avgByJudge("openai")}</div>
      </div>
      <div className="bg-white dark:bg-slate-800/60 rounded-xl p-4 border border-slate-200/60 dark:border-slate-700/60">
        <div className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400 mb-1"><Eye className="w-3 h-3" /> Claude</div>
        <div className={cn("text-2xl font-bold", scoreColor(parseFloat(avgByJudge("anthropic")) || 0))}>{avgByJudge("anthropic")}</div>
      </div>
      <div className="bg-white dark:bg-slate-800/60 rounded-xl p-4 border border-emerald-200/60 dark:border-emerald-800/40">
        <div className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400 mb-1"><CheckCircle2 className="w-3 h-3" /> Pass</div>
        <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">{passCount}</div>
      </div>
      <div className="bg-white dark:bg-slate-800/60 rounded-xl p-4 border border-red-200/60 dark:border-red-800/40">
        <div className="flex items-center gap-1 text-xs text-red-600 dark:text-red-400 mb-1"><XCircle className="w-3 h-3" /> Fail</div>
        <div className="text-2xl font-bold text-red-600 dark:text-red-400">{failCount}</div>
      </div>

      {/* Dimension averages bar */}
      <div className="col-span-2 md:col-span-4 lg:col-span-7 bg-white dark:bg-slate-800/60 rounded-xl p-4 border border-slate-200/60 dark:border-slate-700/60">
        <div className="text-xs text-slate-500 dark:text-slate-400 mb-3 font-medium">Dimension Averages (all judges combined)</div>
        <div className="grid grid-cols-6 gap-3">
          {dimKeys.map(dim => (
            <div key={dim} className="text-center">
              <div className={cn("text-lg font-bold", scoreColor(dimAvgs[dim]))}>{dimAvgs[dim].toFixed(1)}</div>
              <div className="text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-wider">{dimLabel(dim)}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Expanded Test Row
// ---------------------------------------------------------------------------

function TestDetailPanel({ test }: { test: TestResult }) {
  const providers = ["gemini", "openai", "anthropic"];
  const providerLabels: Record<string, string> = { gemini: "Gemini", openai: "GPT-5.2", anthropic: "Claude" };
  const dimKeys = ["correctness", "completeness", "safety", "tone", "reasoning_quality", "constraint_adherence"];

  return (
    <div className="bg-slate-50 dark:bg-slate-800/30 border-t border-slate-200/60 dark:border-slate-700/60 p-4">
      <div className="mb-3">
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Query:</span>
        <p className="text-sm text-slate-700 dark:text-slate-300 mt-1">{test.query}</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {providers.map(p => {
          const j = test.judges[p];
          if (!j) return (
            <div key={p} className="rounded-lg border border-slate-200 dark:border-slate-700 p-3 opacity-50">
              <div className="text-sm font-medium text-slate-500">{providerLabels[p]}</div>
              <div className="text-xs text-slate-400 mt-1">No result</div>
            </div>
          );
          return (
            <div key={p} className={cn("rounded-lg border p-3", scoreBg(j.overall), "border-slate-200 dark:border-slate-700")}>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">{providerLabels[p]}</span>
                <div className="flex items-center gap-2">
                  <span className={cn("text-lg font-bold", scoreColor(j.overall))}>{j.overall.toFixed(1)}</span>
                  {recBadge(j.recommendation)}
                </div>
              </div>

              {/* Dimension scores */}
              <div className="grid grid-cols-6 gap-1 mb-3">
                {dimKeys.map(dim => {
                  const v = j.scores[dim as keyof DimensionScores] ?? 0;
                  return (
                    <div key={dim} className="text-center">
                      <div className={cn("text-sm font-bold", scoreColor(v))}>{v || "-"}</div>
                      <div className="text-[9px] text-slate-400 uppercase">{dimLabel(dim)}</div>
                    </div>
                  );
                })}
              </div>

              {/* Explanation */}
              <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed mb-2">{j.explanation}</p>

              {/* Weaknesses */}
              {j.weaknesses.length > 0 && (
                <div className="mt-2">
                  <div className="text-[10px] font-semibold text-red-600 dark:text-red-400 uppercase mb-1">Weaknesses</div>
                  <ul className="text-xs text-slate-600 dark:text-slate-400 space-y-0.5">
                    {j.weaknesses.map((w, i) => <li key={i} className="flex gap-1"><span className="text-red-400 flex-shrink-0">-</span> {w}</li>)}
                  </ul>
                </div>
              )}

              {/* Strengths */}
              {j.strengths.length > 0 && (
                <div className="mt-2">
                  <div className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 uppercase mb-1">Strengths</div>
                  <ul className="text-xs text-slate-600 dark:text-slate-400 space-y-0.5">
                    {j.strengths.map((s, i) => <li key={i} className="flex gap-1"><span className="text-emerald-400 flex-shrink-0">+</span> {s}</li>)}
                  </ul>
                </div>
              )}

              {/* PDF Citations */}
              {j.pdf_citations.length > 0 && (
                <div className="mt-2">
                  <div className="text-[10px] font-semibold text-green-700 dark:text-green-500 uppercase mb-1">PDF Citations</div>
                  <ul className="text-xs text-slate-500 dark:text-slate-500 space-y-0.5">
                    {j.pdf_citations.map((c, i) => <li key={i}>{c}</li>)}
                  </ul>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function BatchResults() {
  const [batches, setBatches] = useState<BatchListItem[]>([]);
  const [selectedBatch, setSelectedBatch] = useState<string | null>(null);
  const [batchData, setBatchData] = useState<BatchSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingBatch, setLoadingBatch] = useState(false);
  const [expandedTest, setExpandedTest] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("avg");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [filterRec, setFilterRec] = useState<string>("all");

  // Load batch list
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(apiUrl("/test-lab/batches"), authFetch());
        if (res.ok) {
          const data = await res.json();
          setBatches(data);
          if (data.length > 0) {
            setSelectedBatch(data[0].id);
          }
        }
      } catch (e) {
        console.error("Failed to load batches", e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // Load batch data when selected
  useEffect(() => {
    if (!selectedBatch) return;
    (async () => {
      setLoadingBatch(true);
      try {
        const res = await fetch(apiUrl(`/test-lab/batches/${selectedBatch}`), authFetch());
        if (res.ok) {
          setBatchData(await res.json());
        }
      } catch (e) {
        console.error("Failed to load batch data", e);
      } finally {
        setLoadingBatch(false);
      }
    })();
  }, [selectedBatch]);

  // Sorted + filtered results
  const sortedResults = useMemo(() => {
    if (!batchData) return [];
    let items = [...batchData.results];

    // Filter
    if (filterRec !== "all") {
      items = items.filter(r => {
        const recs = Object.values(r.judges).map(j => j.recommendation);
        if (filterRec === "PASS") return recs.every(rc => rc === "PASS") && recs.length > 0;
        if (filterRec === "FAIL") return recs.includes("FAIL");
        if (filterRec === "BORDERLINE") return recs.includes("BORDERLINE") && !recs.includes("FAIL");
        return true;
      });
    }

    // Sort
    items.sort((a, b) => {
      let va = 0, vb = 0;
      switch (sortKey) {
        case "name": return sortDir === "asc" ? a.name.localeCompare(b.name) : b.name.localeCompare(a.name);
        case "avg": va = getAvgScore(a); vb = getAvgScore(b); break;
        case "gemini": va = getJudgeScore(a, "gemini"); vb = getJudgeScore(b, "gemini"); break;
        case "openai": va = getJudgeScore(a, "openai"); vb = getJudgeScore(b, "openai"); break;
        case "anthropic": va = getJudgeScore(a, "anthropic"); vb = getJudgeScore(b, "anthropic"); break;
        case "duration": va = a.duration_s; vb = b.duration_s; break;
        case "turns": va = a.total_turns; vb = b.total_turns; break;
      }
      return sortDir === "asc" ? va - vb : vb - va;
    });

    return items;
  }, [batchData, sortKey, sortDir, filterRec]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(d => d === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir(key === "name" ? "asc" : "desc");
    }
  };

  const handleRefresh = async () => {
    setLoading(true);
    try {
      const res = await fetch(apiUrl("/test-lab/batches"), authFetch());
      if (res.ok) {
        const data = await res.json();
        setBatches(data);
        if (data.length > 0 && !selectedBatch) {
          setSelectedBatch(data[0].id);
        }
        // Reload current batch
        if (selectedBatch) {
          const bres = await fetch(apiUrl(`/test-lab/batches/${selectedBatch}`), authFetch());
          if (bres.ok) setBatchData(await bres.json());
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const SortHeader = ({ label, sortKeyVal, className }: { label: string; sortKeyVal: SortKey; className?: string }) => (
    <button
      onClick={() => handleSort(sortKeyVal)}
      className={cn("flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200", className)}
    >
      {label}
      {sortKey === sortKeyVal ? (sortDir === "asc" ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />) : <ArrowUpDown className="w-3 h-3 opacity-30" />}
    </button>
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-green-600" />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-[1400px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Batch Test Results</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            3-LLM judge evaluation across all test questions
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Batch selector */}
          <select
            value={selectedBatch || ""}
            onChange={e => setSelectedBatch(e.target.value)}
            className="text-sm border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300"
          >
            {batches.map(b => (
              <option key={b.id} value={b.id}>
                {formatTs(b.timestamp)} ({b.test_count} tests)
              </option>
            ))}
          </select>
          <button onClick={handleRefresh} className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
            <RefreshCw className={cn("w-4 h-4 text-slate-500", loading && "animate-spin")} />
          </button>
        </div>
      </div>

      {/* Cross-batch overview */}
      <TrendChart batches={batches} selectedBatch={selectedBatch} onSelect={setSelectedBatch} />
      <BatchOverviewTable batches={batches} selectedBatch={selectedBatch} onSelect={setSelectedBatch} />

      {/* Selected batch detail */}
      {loadingBatch ? (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-8 h-8 animate-spin text-green-600" />
        </div>
      ) : batchData ? (
        <>
          <StatsBar results={batchData.results} />

          {/* Filter bar */}
          <div className="flex items-center gap-2 mb-4">
            <span className="text-xs text-slate-500 dark:text-slate-400">Filter:</span>
            {["all", "PASS", "BORDERLINE", "FAIL"].map(f => (
              <button
                key={f}
                onClick={() => setFilterRec(f)}
                className={cn(
                  "px-3 py-1 rounded-full text-xs font-medium transition-colors",
                  filterRec === f
                    ? "bg-green-700 text-white"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700"
                )}
              >
                {f === "all" ? `All (${batchData.results.length})` : f}
              </button>
            ))}
          </div>

          {/* Results table */}
          <div className="bg-white dark:bg-slate-800/60 rounded-xl border border-slate-200/60 dark:border-slate-700/60 overflow-hidden">
            {/* Table header */}
            <div className="grid grid-cols-[1fr_80px_80px_80px_80px_60px_50px] gap-2 px-4 py-3 border-b border-slate-200/60 dark:border-slate-700/60 bg-slate-50 dark:bg-slate-800/80">
              <SortHeader label="Test Name" sortKeyVal="name" />
              <SortHeader label="3-Avg" sortKeyVal="avg" className="justify-center" />
              <SortHeader label="Gemini" sortKeyVal="gemini" className="justify-center" />
              <SortHeader label="GPT" sortKeyVal="openai" className="justify-center" />
              <SortHeader label="Claude" sortKeyVal="anthropic" className="justify-center" />
              <SortHeader label="Time" sortKeyVal="duration" className="justify-center" />
              <SortHeader label="T" sortKeyVal="turns" className="justify-center" />
            </div>

            {/* Rows */}
            {sortedResults.map(test => {
              const avg = getAvgScore(test);
              const isExpanded = expandedTest === test.name;
              return (
                <div key={test.name}>
                  <div
                    onClick={() => setExpandedTest(isExpanded ? null : test.name)}
                    className={cn(
                      "grid grid-cols-[1fr_80px_80px_80px_80px_60px_50px] gap-2 px-4 py-2.5 cursor-pointer transition-colors border-b border-slate-100 dark:border-slate-800",
                      isExpanded ? "bg-green-50/50 dark:bg-green-900/10" : "hover:bg-slate-50 dark:hover:bg-slate-800/40"
                    )}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      {isExpanded ? <ChevronUp className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" /> : <ChevronDown className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />}
                      <span className="text-sm text-slate-700 dark:text-slate-300 truncate font-medium">{test.name}</span>
                      {test.error && <AlertTriangle className="w-3.5 h-3.5 text-red-500 flex-shrink-0" />}
                    </div>
                    <div className={cn("text-center text-sm font-bold", scoreColor(avg))}>{avg > 0 ? avg.toFixed(2) : "-"}</div>
                    {["gemini", "openai", "anthropic"].map(p => {
                      const s = getJudgeScore(test, p);
                      const j = test.judges[p];
                      return (
                        <div key={p} className="flex items-center justify-center gap-1">
                          <span className={cn("text-sm font-semibold", scoreColor(s))}>{s > 0 ? s.toFixed(1) : "-"}</span>
                          {j && recBadge(j.recommendation)}
                        </div>
                      );
                    })}
                    <div className="text-center text-xs text-slate-500 dark:text-slate-400 flex items-center justify-center">
                      {test.duration_s > 0 ? `${test.duration_s.toFixed(0)}s` : "-"}
                    </div>
                    <div className="text-center text-xs text-slate-500 dark:text-slate-400 flex items-center justify-center">
                      {test.total_turns}
                    </div>
                  </div>

                  {isExpanded && <TestDetailPanel test={test} />}
                </div>
              );
            })}
          </div>

          <div className="mt-3 text-xs text-slate-400 dark:text-slate-500 text-center">
            {sortedResults.length} of {batchData.results.length} tests shown
          </div>
        </>
      ) : (
        <div className="text-center py-12 text-slate-500 dark:text-slate-400">
          <BarChart3 className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>No batch results found. Run the test suite first.</p>
        </div>
      )}
    </div>
  );
}
