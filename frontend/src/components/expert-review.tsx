"use client";

import { useState, useEffect, useCallback } from "react";
import {
  ThumbsUp,
  ThumbsDown,
  MessageSquare,
  Search,
  Loader2,
  User,
  Bot,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  XCircle,
  Clock,
  Filter,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import {
  getExpertConversations,
  getExpertConversation,
  getExpertReviewsSummary,
  type ConversationSummary,
  type ConversationDetail,
  type ExpertReviewData,
  type JudgeSingleResult,
} from "@/lib/api";

const JUDGE_DIMENSIONS = [
  "correctness",
  "completeness",
  "safety",
  "tone",
  "reasoning_quality",
  "constraint_adherence",
] as const;

function formatTimestamp(ts: number | null): string {
  if (!ts) return "—";
  const d = new Date(ts);
  return d.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ScoreBadge({ score }: { score: string | null }) {
  if (!score) {
    return (
      <Badge variant="outline" className="text-slate-400 border-slate-200 dark:border-slate-700">
        Not reviewed
      </Badge>
    );
  }
  if (score === "thumbs_up") {
    return (
      <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-800">
        <ThumbsUp className="w-3 h-3 mr-1" />
        Approved
      </Badge>
    );
  }
  return (
    <Badge className="bg-red-100 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800">
      <ThumbsDown className="w-3 h-3 mr-1" />
      Rejected
    </Badge>
  );
}

function JudgeScoresPanel({
  judges,
}: {
  judges: Record<string, JudgeSingleResult>;
}) {
  const judgeNames = Object.keys(judges);
  if (judgeNames.length === 0) return null;

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
        Judge Evaluations
      </h4>
      <div className="grid gap-3">
        {judgeNames.map((name) => {
          const j = judges[name];
          if (!j) return null;
          const recColor =
            j.recommendation === "PASS"
              ? "text-emerald-600"
              : j.recommendation === "FAIL"
                ? "text-red-600"
                : "text-amber-600";
          return (
            <Card key={name} className="border-slate-200 dark:border-slate-700">
              <CardContent className="p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium capitalize">
                    {name}
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold">
                      {j.overall_score?.toFixed(1)}
                    </span>
                    <span className={cn("text-xs font-semibold", recColor)}>
                      {j.recommendation}
                    </span>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-1 text-xs">
                  {JUDGE_DIMENSIONS.map((dim) => (
                    <div
                      key={dim}
                      className="flex justify-between px-1 py-0.5 bg-slate-50 dark:bg-slate-700 rounded"
                    >
                      <span className="text-slate-500 dark:text-slate-400 truncate">
                        {dim.replace("_", " ")}
                      </span>
                      <span className="font-medium ml-1">
                        {j.scores?.[dim] ?? "—"}
                      </span>
                    </div>
                  ))}
                </div>
                {j.explanation && (
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-2 line-clamp-2">
                    {j.explanation}
                  </p>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function ExistingReviews({ reviews }: { reviews: ExpertReviewData[] }) {
  if (reviews.length === 0) return null;

  return (
    <div className="space-y-2 border-t border-slate-200 dark:border-slate-700 pt-4">
      <h4 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
        Previous Reviews ({reviews.length})
      </h4>
      {reviews.map((r) => (
        <div
          key={r.id}
          className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-100 dark:border-slate-700 space-y-1"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
                {r.reviewer}
              </span>
              <ScoreBadge score={r.overall_score} />
              {r.provider && (
                <Badge variant="outline" className="text-[10px] px-1.5 py-0 capitalize">
                  {r.provider}
                </Badge>
              )}
              {r.turn_number != null && (
                <span className="text-[10px] text-slate-400">T{r.turn_number}</span>
              )}
            </div>
            <span className="text-xs text-slate-400">
              {formatTimestamp(r.created_at)}
            </span>
          </div>
          {r.comment && (
            <p className="text-sm text-slate-600 dark:text-slate-400">{r.comment}</p>
          )}
        </div>
      ))}
    </div>
  );
}

export function ExpertReview() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterStatus, setFilterStatus] = useState<
    "all" | "reviewed" | "unreviewed"
  >("all");

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [stats, setStats] = useState<{
    total: number;
    positive: number;
    negative: number;
  } | null>(null);

  const PAGE_SIZE = 30;

  const loadConversations = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getExpertConversations(PAGE_SIZE, page * PAGE_SIZE);
      setConversations(data.conversations);
      setTotal(data.total);
    } catch (err) {
      console.error("Failed to load conversations:", err);
    } finally {
      setLoading(false);
    }
  }, [page]);

  const loadStats = useCallback(async () => {
    try {
      const data = await getExpertReviewsSummary();
      setStats(data);
    } catch {
      // non-fatal
    }
  }, []);

  useEffect(() => {
    loadConversations();
    loadStats();
  }, [loadConversations, loadStats]);

  const loadDetail = async (sessionId: string) => {
    setSelectedId(sessionId);
    setDetailLoading(true);
    try {
      const data = await getExpertConversation(sessionId);
      setDetail(data);
    } catch (err) {
      console.error("Failed to load conversation:", err);
    } finally {
      setDetailLoading(false);
    }
  };

  // Client-side filtering
  const filtered = conversations.filter((c) => {
    if (filterStatus === "reviewed" && !c.has_review) return false;
    if (filterStatus === "unreviewed" && c.has_review) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        c.session_id.toLowerCase().includes(q) ||
        (c.project_name || "").toLowerCase().includes(q) ||
        (c.detected_family || "").toLowerCase().includes(q) ||
        (c.locked_material || "").toLowerCase().includes(q)
      );
    }
    return true;
  });

  const totalPages = Math.ceil(total / PAGE_SIZE);
  return (
    <div className="flex h-[calc(100vh-140px)] gap-4">
      {/* LEFT PANEL: Conversation List */}
      <div className="w-[380px] flex-shrink-0 flex flex-col">
        {/* Stats bar */}
        {stats && (
          <div className="flex items-center gap-3 mb-3 px-1">
            <div className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
              <MessageSquare className="w-3.5 h-3.5" />
              <span>{total} conversations</span>
            </div>
            <div className="flex items-center gap-1 text-xs text-emerald-600">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>{stats.positive}</span>
            </div>
            <div className="flex items-center gap-1 text-xs text-red-600">
              <XCircle className="w-3.5 h-3.5" />
              <span>{stats.negative}</span>
            </div>
            <div className="flex items-center gap-1 text-xs text-slate-400">
              <Clock className="w-3.5 h-3.5" />
              <span>{total - stats.total} pending</span>
            </div>
          </div>
        )}

        {/* Search + Filter */}
        <div className="flex gap-2 mb-3">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search..."
              className="pl-8 h-8 text-sm"
            />
          </div>
          <Button
            size="sm"
            variant={filterStatus !== "all" ? "default" : "outline"}
            className="h-8 px-2"
            onClick={() => {
              const next =
                filterStatus === "all"
                  ? "unreviewed"
                  : filterStatus === "unreviewed"
                    ? "reviewed"
                    : "all";
              setFilterStatus(next);
            }}
          >
            <Filter className="w-3.5 h-3.5 mr-1" />
            <span className="text-xs capitalize">{filterStatus}</span>
          </Button>
        </div>

        {/* Conversation list */}
        <ScrollArea className="flex-1 -mx-1 px-1">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
            </div>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-12">
              No conversations found
            </p>
          ) : (
            <div className="space-y-1.5">
              {filtered.map((c) => (
                <button
                  key={c.session_id}
                  onClick={() => loadDetail(c.session_id)}
                  className={cn(
                    "w-full text-left p-3 rounded-lg border transition-colors",
                    selectedId === c.session_id
                      ? "bg-blue-50 border-blue-200 dark:bg-blue-900/30 dark:border-blue-800"
                      : "bg-white border-slate-100 hover:border-slate-200 hover:bg-slate-50 dark:bg-slate-800 dark:border-slate-700 dark:hover:border-slate-600 dark:hover:bg-slate-700/50"
                  )}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-mono text-slate-400 truncate max-w-[160px]">
                      {c.session_id.slice(0, 12)}...
                    </span>
                    <ScoreBadge score={c.review_score} />
                  </div>
                  <div className="flex items-center gap-2 mb-1">
                    {c.detected_family && (
                      <Badge
                        variant="outline"
                        className="text-xs px-1.5 py-0"
                      >
                        {c.detected_family}
                      </Badge>
                    )}
                    {c.locked_material && (
                      <Badge
                        variant="outline"
                        className="text-xs px-1.5 py-0"
                      >
                        {c.locked_material}
                      </Badge>
                    )}
                    {c.project_name && (
                      <span className="text-xs text-slate-500 truncate">
                        {c.project_name}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center justify-between text-xs text-slate-400">
                    <span>{c.turn_count} turns</span>
                    <span>{formatTimestamp(c.last_activity)}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </ScrollArea>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-100 dark:border-slate-700">
            <Button
              size="sm"
              variant="ghost"
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <span className="text-xs text-slate-400">
              Page {page + 1} of {totalPages}
            </span>
            <Button
              size="sm"
              variant="ghost"
              disabled={page >= totalPages - 1}
              onClick={() => setPage((p) => p + 1)}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        )}
      </div>

      {/* RIGHT PANEL: Conversation Detail */}
      <div className="flex-1 flex flex-col min-w-0">
        {!selectedId ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center text-slate-400">
              <MessageSquare className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p className="text-sm">Select a conversation to review</p>
            </div>
          </div>
        ) : detailLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
          </div>
        ) : detail ? (
          <div className="flex-1 flex gap-4 min-h-0">
            {/* Conversation turns */}
            <div className="flex-1 flex flex-col min-w-0">
              <div className="flex items-center gap-2 mb-3">
                <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                  Conversation
                </h3>
                {detail.detected_family && (
                  <Badge variant="outline">{detail.detected_family}</Badge>
                )}
                {detail.locked_material && (
                  <Badge variant="outline">{detail.locked_material}</Badge>
                )}
                <span className="text-xs text-slate-400 ml-auto">
                  {detail.turns.length} turns
                </span>
              </div>
              <ScrollArea className="flex-1">
                <div className="space-y-3 pr-4">
                  {detail.turns.map((turn) => {
                    const isUser = turn.role === "user";
                    // Parse judge results for this turn
                    let turnJudges: Record<string, JudgeSingleResult> | null = null;
                    if (!isUser && turn.judge_results) {
                      try {
                        turnJudges = JSON.parse(turn.judge_results);
                      } catch { /* ignore */ }
                    }
                    // Find per-judge reviews for this turn
                    const turnReviews = detail.reviews.filter(
                      (r) => r.turn_number === turn.turn_number && r.provider
                    );
                    const reviewByProvider: Record<string, string> = {};
                    for (const r of turnReviews) {
                      if (r.provider) reviewByProvider[r.provider] = r.overall_score;
                    }

                    return (
                      <div key={turn.id || turn.turn_number}>
                        <div
                          className={cn(
                            "flex gap-2",
                            isUser ? "justify-end" : "justify-start"
                          )}
                        >
                          {!isUser && (
                            <div className="w-7 h-7 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                              <Bot className="w-4 h-4 text-blue-600" />
                            </div>
                          )}
                          <div
                            className={cn(
                              "max-w-[85%] rounded-lg px-3 py-2 text-sm",
                              isUser
                                ? "bg-blue-600 text-white"
                                : "bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300"
                            )}
                          >
                            <p className="whitespace-pre-wrap break-words">
                              {turn.message}
                            </p>
                          </div>
                          {isUser && (
                            <div className="w-7 h-7 rounded-full bg-slate-200 dark:bg-slate-700 flex items-center justify-center flex-shrink-0 mt-0.5">
                              <User className="w-4 h-4 text-slate-600 dark:text-slate-400" />
                            </div>
                          )}
                        </div>
                        {/* Inline judge results for assistant turns */}
                        {turnJudges && (
                          <div className="ml-9 mt-1.5 mb-1">
                            <div className="inline-flex items-center gap-1.5 flex-wrap">
                              {(["gemini", "openai", "anthropic"] as const)
                                .filter((p) => turnJudges![p] && turnJudges![p].recommendation !== "ERROR")
                                .map((prov) => {
                                  const j = turnJudges![prov];
                                  const review = reviewByProvider[prov];
                                  const recCls =
                                    j.recommendation === "PASS"
                                      ? "bg-emerald-50 border-emerald-200 text-emerald-700 dark:bg-emerald-900/30 dark:border-emerald-800 dark:text-emerald-400"
                                      : j.recommendation === "FAIL"
                                        ? "bg-red-50 border-red-200 text-red-700 dark:bg-red-900/30 dark:border-red-800 dark:text-red-400"
                                        : "bg-amber-50 border-amber-200 text-amber-700 dark:bg-amber-900/30 dark:border-amber-800 dark:text-amber-400";
                                  const badgeCls =
                                    j.recommendation === "PASS"
                                      ? "bg-emerald-200 text-emerald-800"
                                      : j.recommendation === "FAIL"
                                        ? "bg-red-200 text-red-800"
                                        : "bg-amber-200 text-amber-800";
                                  return (
                                    <span
                                      key={prov}
                                      className={cn(
                                        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium border",
                                        recCls
                                      )}
                                    >
                                      <span className="opacity-60 capitalize">{prov}</span>
                                      {j.overall_score?.toFixed(1)}/5
                                      <span className={cn("px-1 py-0 rounded text-[9px] font-bold", badgeCls)}>
                                        {j.recommendation}
                                      </span>
                                      {review && (
                                        review === "thumbs_up"
                                          ? <ThumbsUp className="w-2.5 h-2.5 text-emerald-600" />
                                          : <ThumbsDown className="w-2.5 h-2.5 text-red-600" />
                                      )}
                                    </span>
                                  );
                                })}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </ScrollArea>
            </div>

            {/* Review sidebar */}
            <div className="w-[300px] flex-shrink-0 flex flex-col min-h-0">
              <ScrollArea className="flex-1">
                <div className="space-y-4 pr-2">
                  {/* Session-level judge scores (from static file) */}
                  {detail.judge_results && (
                    <JudgeScoresPanel judges={detail.judge_results} />
                  )}

                  {/* Existing reviews */}
                  <ExistingReviews reviews={detail.reviews} />
                </div>
              </ScrollArea>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
