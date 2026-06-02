"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  Loader2,
  Flag,
  CheckCircle2,
  MessageSquare,
  Filter,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import {
  synapseListFlags,
  synapseGetEpisodes,
  synapseGetReview,
  synapseStartReview,
  synapseReviewAction,
  synapseResolveFlag,
  type SynapseFlag,
  type SynapseEpisode,
  type SynapseReviewState,
} from "@/lib/api";
import ReactMarkdown from "react-markdown";

function formatDate(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function StatusBadge({ status }: { status: "open" | "resolved" }) {
  if (status === "resolved") {
    return (
      <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-800">
        <CheckCircle2 className="w-3 h-3 mr-1" />
        Resolved
      </Badge>
    );
  }
  return (
    <Badge className="bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-900/30 dark:text-amber-400 dark:border-amber-800">
      <Flag className="w-3 h-3 mr-1" />
      Open
    </Badge>
  );
}

function EpisodePair({ episode }: { episode: SynapseEpisode }) {
  return (
    <div className="space-y-1.5">
      {/* User question */}
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-xl px-3 py-2 text-sm bg-green-700 text-white">
          <p className="whitespace-pre-wrap break-words">{episode.question}</p>
        </div>
      </div>
      {/* Assistant answer */}
      <div className="flex justify-start">
        <div className="max-w-[85%] rounded-xl px-3 py-2 text-sm bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300">
          <div className="prose prose-sm max-w-none dark:prose-invert">
            <ReactMarkdown>{episode.answer}</ReactMarkdown>
          </div>
          {episode.elapsed_seconds != null && (
            <p className="text-[10px] text-slate-400 mt-1">{episode.elapsed_seconds.toFixed(1)}s</p>
          )}
        </div>
      </div>
    </div>
  );
}

function ReviewChatBubble({
  msg,
}: {
  msg: { role: "user" | "assistant"; content: string };
}) {
  const isUser = msg.role === "user";
  return (
    <div className={cn("flex gap-2", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[90%] rounded-xl px-3 py-2 text-sm",
          isUser
            ? "bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-200"
            : "bg-white border border-slate-100 text-slate-700 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-300"
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap break-words">{msg.content}</p>
        ) : (
          <div className="prose prose-sm max-w-none dark:prose-invert">
            <ReactMarkdown>{msg.content}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}

function FlagDetailPanel({ flag }: { flag: SynapseFlag }) {
  const [episodes, setEpisodes] = useState<SynapseEpisode[]>([]);
  const [episodesLoading, setEpisodesLoading] = useState(false);
  const [review, setReview] = useState<SynapseReviewState | null>(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [messageInput, setMessageInput] = useState("");
  const chatScrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setEpisodes([]);
    setReview(null);
    setEpisodesLoading(true);
    synapseGetEpisodes(flag.session_id).then((data) => {
      setEpisodes(data);
      setEpisodesLoading(false);
    });
    setReviewLoading(true);
    synapseGetReview(flag.id).then((data) => {
      if (data && data.phase !== "idle") setReview(data);
      setReviewLoading(false);
    });
  }, [flag.id, flag.session_id]);

  useEffect(() => {
    if (chatScrollRef.current) {
      chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight;
    }
  }, [review?.chatbot]);

  const handleStartReview = async () => {
    setReviewLoading(true);
    const state = await synapseStartReview(flag.id);
    setReview(state);
    setReviewLoading(false);
  };

  const handleAction = async (
    action: "accept_plan" | "reject_plan" | "confirm_edit" | "skip_edit" | "send_message",
    userText = ""
  ) => {
    setActionLoading(true);
    const state = await synapseReviewAction(flag.id, action, userText);
    if (state) setReview(state);
    setActionLoading(false);
  };

  const handleSendMessage = async () => {
    if (!messageInput.trim()) return;
    const text = messageInput;
    setMessageInput("");
    await handleAction("send_message", text);
  };

  const handleResolve = async () => {
    await synapseResolveFlag(flag.id);
    const state = await synapseGetReview(flag.id);
    if (state) setReview(state);
  };

  const reviewActive = review && review.phase !== "idle";

  return (
    <div className="flex flex-col h-full gap-4 overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 space-y-2">
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 leading-snug">
            {flag.flag_reason}
          </h3>
          <StatusBadge status={flag.status} />
        </div>
        {flag.expected_answer && (
          <p className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-800 rounded-lg px-3 py-2">
            <span className="font-medium text-slate-600 dark:text-slate-300">Expected answer: </span>
            {flag.expected_answer}
          </p>
        )}
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <span>{formatDate(flag.flagged_at)}</span>
          {flag.domain_id && (
            <Badge variant="outline" className="text-[10px] px-1.5 py-0">
              {flag.domain_id}
            </Badge>
          )}
        </div>
      </div>

      {/* Two-column scrollable area */}
      <div className="flex-1 grid grid-cols-2 gap-4 min-h-0 overflow-hidden">
        {/* LEFT: Original conversation */}
        <div className="flex flex-col min-h-0">
          <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-2 flex-shrink-0 uppercase tracking-wide">
            Original conversation
          </p>
          {episodesLoading ? (
            <div className="flex items-center justify-center flex-1">
              <Loader2 className="w-4 h-4 animate-spin text-slate-400" />
            </div>
          ) : episodes.length === 0 ? (
            <p className="text-xs text-slate-400 text-center py-4">No episodes found</p>
          ) : (
            <ScrollArea className="flex-1">
              <div className="space-y-4 pr-2">
                {episodes.map((ep) => (
                  <EpisodePair key={ep.id} episode={ep} />
                ))}
              </div>
            </ScrollArea>
          )}
        </div>

        {/* RIGHT: AI Review */}
        <div className="flex flex-col min-h-0">
          <div className="flex items-center justify-between mb-2 flex-shrink-0">
            <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
              AI Review
            </p>
            {!reviewActive && !reviewLoading && (
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                onClick={handleStartReview}
              >
                Start AI Review
              </Button>
            )}
          </div>

          {reviewLoading ? (
            <div className="flex items-center justify-center flex-1">
              <Loader2 className="w-4 h-4 animate-spin text-slate-400" />
            </div>
          ) : !reviewActive ? (
            <div className="flex-1 flex items-center justify-center text-slate-400">
              <p className="text-xs text-center">Click &quot;Start AI Review&quot; to begin</p>
            </div>
          ) : (
            <div className="flex flex-col flex-1 min-h-0 gap-2">
              {/* Chatbot history */}
              <div ref={chatScrollRef} className="flex-1 overflow-y-auto space-y-2 pr-1">
                {(review.chatbot ?? []).map((msg, i) => (
                  <ReviewChatBubble key={i} msg={msg} />
                ))}
              </div>

              {/* Status info */}
              {review.status_md && (
                <div className="text-[10px] text-slate-400 bg-slate-50 dark:bg-slate-800 rounded-lg px-2 py-1.5 flex-shrink-0">
                  <ReactMarkdown>{review.status_md}</ReactMarkdown>
                </div>
              )}

              {/* pending_edit code block */}
              {review.phase === "edit_pending" && review.pending_edit && (
                <div className="flex-shrink-0">
                  <pre className="text-[10px] bg-slate-900 text-slate-200 rounded-lg p-2 overflow-x-auto whitespace-pre-wrap">
                    {review.pending_edit}
                  </pre>
                </div>
              )}

              {/* Action buttons */}
              <div className="flex-shrink-0 space-y-2">
                {review.phase === "plan_pending" && (
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      className="flex-1 h-8 text-xs bg-emerald-600 hover:bg-emerald-700 text-white"
                      disabled={actionLoading}
                      onClick={() => handleAction("accept_plan")}
                    >
                      {actionLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : "✅ Accept plan"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="flex-1 h-8 text-xs border-red-200 text-red-600 hover:bg-red-50"
                      disabled={actionLoading}
                      onClick={() => handleAction("reject_plan")}
                    >
                      ❌ Reject plan
                    </Button>
                  </div>
                )}

                {review.phase === "edit_pending" && (
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      className="flex-1 h-8 text-xs bg-emerald-600 hover:bg-emerald-700 text-white"
                      disabled={actionLoading}
                      onClick={() => handleAction("confirm_edit")}
                    >
                      {actionLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : "✅ Confirm edit"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="flex-1 h-8 text-xs"
                      disabled={actionLoading}
                      onClick={() => handleAction("skip_edit")}
                    >
                      ⏭ Skip
                    </Button>
                  </div>
                )}

                {(review.phase === "resolved" || review.phase === "max_steps") && (
                  <Button
                    size="sm"
                    className="w-full h-8 text-xs bg-slate-700 hover:bg-slate-800 text-white"
                    disabled={actionLoading || flag.status === "resolved"}
                    onClick={handleResolve}
                  >
                    {flag.status === "resolved" ? "✓ Marked as resolved" : "Mark as resolved"}
                  </Button>
                )}

                {/* Send message — always visible when review is active */}
                <div className="flex gap-2">
                  <Input
                    value={messageInput}
                    onChange={(e) => setMessageInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        handleSendMessage();
                      }
                    }}
                    placeholder="Send a message..."
                    className="h-8 text-xs"
                    disabled={actionLoading}
                  />
                  <Button
                    size="sm"
                    className="h-8 px-3 text-xs"
                    disabled={actionLoading || !messageInput.trim()}
                    onClick={handleSendMessage}
                  >
                    {actionLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : "Send"}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function SynapseReviews() {
  const [flags, setFlags] = useState<SynapseFlag[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState<"all" | "open" | "resolved">("all");
  const [selectedFlag, setSelectedFlag] = useState<SynapseFlag | null>(null);

  const loadFlags = useCallback(async () => {
    setLoading(true);
    const status = filterStatus === "all" ? undefined : filterStatus;
    const data = await synapseListFlags(status);
    setFlags(data);
    setLoading(false);
  }, [filterStatus]);

  useEffect(() => {
    loadFlags();
  }, [loadFlags]);

  const filterLabel = filterStatus === "all" ? "All" : filterStatus === "open" ? "Open" : "Resolved";

  return (
    <div className="flex h-[calc(100vh-140px)] gap-4">
      {/* LEFT: Flag list */}
      <div className="w-80 flex-shrink-0 flex flex-col">
        <div className="flex items-center gap-2 mb-3">
          <Button
            size="sm"
            variant={filterStatus !== "all" ? "default" : "outline"}
            className="h-8 px-2"
            onClick={() =>
              setFilterStatus((prev) =>
                prev === "all" ? "open" : prev === "open" ? "resolved" : "all"
              )
            }
          >
            <Filter className="w-3.5 h-3.5 mr-1" />
            <span className="text-xs">{filterLabel}</span>
          </Button>
          <span className="text-xs text-slate-400 ml-auto">{flags.length} flags</span>
          <button
            onClick={loadFlags}
            className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-3.5 h-3.5 text-slate-400" />
          </button>
        </div>

        <ScrollArea className="flex-1 -mx-1 px-1">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
            </div>
          ) : flags.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-12">No flags found</p>
          ) : (
            <div className="space-y-1.5">
              {flags.map((f) => (
                <button
                  key={f.id}
                  onClick={() => setSelectedFlag(f)}
                  className={cn(
                    "w-full text-left p-3 rounded-xl border transition-colors",
                    selectedFlag?.id === f.id
                      ? "bg-green-50 border-green-200 dark:bg-green-900/30 dark:border-green-800"
                      : "bg-white border-slate-100 hover:border-slate-200 hover:bg-slate-50 dark:bg-slate-800 dark:border-slate-700 dark:hover:border-slate-600 dark:hover:bg-slate-700/50"
                  )}
                >
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <p className="text-xs font-medium text-slate-700 dark:text-slate-300 line-clamp-2 leading-snug">
                      {f.flag_reason}
                    </p>
                    <StatusBadge status={f.status} />
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    {f.domain_id && (
                      <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                        {f.domain_id}
                      </Badge>
                    )}
                    <span className="text-[10px] text-slate-400 ml-auto">
                      {formatDate(f.flagged_at)}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </ScrollArea>
      </div>

      {/* RIGHT: Detail panel */}
      <div className="flex-1 bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm p-5 min-w-0 overflow-hidden">
        {!selectedFlag ? (
          <div className="h-full flex items-center justify-center text-slate-400">
            <div className="text-center">
              <MessageSquare className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p className="text-sm">Select a flag to view details</p>
            </div>
          </div>
        ) : (
          <FlagDetailPanel key={selectedFlag.id} flag={selectedFlag} />
        )}
      </div>
    </div>
  );
}

export function ExpertReview() {
  return <SynapseReviews />;
}
