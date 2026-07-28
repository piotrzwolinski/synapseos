"use client";

import { useEffect, useState, useCallback } from "react";
import { Loader2, MessageSquare, RefreshCw, Star, Trash2, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { getUserRole, getUsername } from "@/lib/auth";
import {
  listFeedbackSessions,
  getFeedbackSessionReplay,
  listSessionComments,
  addSessionComment,
  deleteSessionComment,
  type FeedbackSessionSummary,
  type FeedbackSessionReplay,
  type UserComment,
} from "@/lib/api";
import { SessionReplay } from "./session-replay";

const PAGE_SIZE = 50;

export function FeedbackPanel() {
  const role = typeof window !== "undefined" ? getUserRole() : "admin";
  const username = typeof window !== "undefined" ? getUsername() : "";
  const isAdmin = role === "admin";

  const [sessions, setSessions] = useState<FeedbackSessionSummary[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [userFilter, setUserFilter] = useState<string>(isAdmin ? "all" : username);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [replay, setReplay] = useState<FeedbackSessionReplay | null>(null);
  const [replayLoading, setReplayLoading] = useState(false);
  const [replayError, setReplayError] = useState<string | null>(null);

  const [comments, setComments] = useState<UserComment[]>([]);
  const [commentsLoading, setCommentsLoading] = useState(false);
  const [commentDraft, setCommentDraft] = useState("");
  const [commentSubmitting, setCommentSubmitting] = useState(false);

  const reloadSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const userParam = isAdmin ? userFilter : username;
      const res = await listFeedbackSessions({
        limit: PAGE_SIZE,
        offset: 0,
        user: userParam,
      });
      setSessions(res.items);
      if (!selectedId && res.items.length > 0) {
        setSelectedId(res.items[0].session_id);
      }
    } finally {
      setSessionsLoading(false);
    }
  }, [isAdmin, userFilter, username, selectedId]);

  useEffect(() => {
    void reloadSessions();
  }, [reloadSessions]);

  useEffect(() => {
    if (!selectedId) {
      setReplay(null);
      setComments([]);
      return;
    }

    let cancelled = false;
    setReplayLoading(true);
    setReplayError(null);
    setCommentsLoading(true);

    Promise.all([
      getFeedbackSessionReplay(selectedId),
      listSessionComments(selectedId),
    ])
      .then(([replayResult, commentsResult]) => {
        if (cancelled) return;
        if (!replayResult) {
          setReplayError("Failed to load session");
          setReplay(null);
        } else {
          setReplay(replayResult);
        }
        setComments(commentsResult);
      })
      .catch((err) => {
        if (!cancelled) {
          setReplayError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setReplayLoading(false);
          setCommentsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const handleAddComment = async () => {
    if (!selectedId || !commentDraft.trim() || commentSubmitting) return;
    setCommentSubmitting(true);
    try {
      const created = await addSessionComment(selectedId, commentDraft.trim());
      if (created) {
        setComments((prev) => [...prev, created]);
        setCommentDraft("");
        // Refresh session list so the comment_count updates.
        void reloadSessions();
      }
    } finally {
      setCommentSubmitting(false);
    }
  };

  const handleDeleteComment = async (commentId: string) => {
    const ok = await deleteSessionComment(commentId);
    if (ok) {
      setComments((prev) => prev.filter((c) => c.id !== commentId));
      void reloadSessions();
    }
  };

  return (
    <div className="flex h-full min-h-[600px] bg-white dark:bg-slate-900">
      {/* LEFT — session list */}
      <aside className="w-80 border-r border-slate-200 dark:border-slate-700 flex flex-col">
        <header className="p-3 border-b border-slate-200 dark:border-slate-700 space-y-2">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
              Sessions
            </h2>
            <button
              onClick={() => void reloadSessions()}
              className="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
              title="Refresh"
              disabled={sessionsLoading}
            >
              <RefreshCw
                className={cn("w-4 h-4", sessionsLoading && "animate-spin")}
              />
            </button>
          </div>
          {isAdmin && (
            <input
              type="text"
              value={userFilter}
              onChange={(e) => setUserFilter(e.target.value || "all")}
              placeholder="Filter: all, username…"
              className="w-full text-xs px-2 py-1.5 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded focus:outline-none focus:ring-1 focus:ring-green-600"
            />
          )}
        </header>

        <ScrollArea className="flex-1">
          {sessions.length === 0 && !sessionsLoading && (
            <div className="p-4 text-xs text-slate-500 dark:text-slate-400">
              No sessions to display.
            </div>
          )}
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {sessions.map((s) => (
              <li key={s.session_id}>
                <button
                  onClick={() => setSelectedId(s.session_id)}
                  className={cn(
                    "w-full text-left px-3 py-2.5 hover:bg-slate-50 dark:hover:bg-slate-800",
                    selectedId === s.session_id &&
                      "bg-green-50 dark:bg-green-900/20 border-l-2 border-green-600"
                  )}
                >
                  <div className="text-sm text-slate-800 dark:text-slate-100 line-clamp-2">
                    {s.title || <span className="text-slate-400">(untitled)</span>}
                  </div>
                  <div className="mt-1 flex items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400">
                    <span className="flex items-center gap-1">
                      <User className="w-3 h-3" />
                      {s.user_id || "?"}
                    </span>
                    <span>·</span>
                    <span>{s.turn_count} turn{s.turn_count === 1 ? "" : "s"}</span>
                    {s.comment_count > 0 && (
                      <>
                        <span>·</span>
                        <span className="flex items-center gap-1 text-green-700 dark:text-green-400">
                          <MessageSquare className="w-3 h-3" />
                          {s.comment_count}
                        </span>
                      </>
                    )}
                    {s.rating != null && (
                      <>
                        <span>·</span>
                        <span className="flex items-center gap-0.5 text-amber-500">
                          <Star className="w-3 h-3 fill-amber-400" />
                          {s.rating}
                        </span>
                      </>
                    )}
                  </div>
                  {s.last_active && (
                    <div className="mt-0.5 text-[10px] text-slate-400">
                      {new Date(s.last_active).toLocaleString()}
                    </div>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </ScrollArea>
      </aside>

      {/* RIGHT — replay + comments */}
      <main className="flex-1 flex flex-col min-w-0">
        {!selectedId && (
          <div className="flex-1 flex items-center justify-center text-sm text-slate-500 dark:text-slate-400">
            Select a session from the list on the left.
          </div>
        )}

        {selectedId && (
          <>
            <header className="px-5 py-3 border-b border-slate-200 dark:border-slate-700">
              <h1 className="text-base font-semibold text-slate-900 dark:text-slate-100 line-clamp-1">
                {replay?.title || replay?.session_id || selectedId}
              </h1>
              <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 flex items-center gap-2">
                <span>user: {replay?.user_id || "?"}</span>
                {replay?.project?.name && (
                  <>
                    <span>·</span>
                    <span>project: {replay.project.name}</span>
                  </>
                )}
                {replay?.project?.detected_family && (
                  <>
                    <span>·</span>
                    <span>family: {replay.project.detected_family}</span>
                  </>
                )}
                {replay?.rating != null && (
                  <>
                    <span>·</span>
                    <span className="flex items-center gap-0.5 text-amber-500">
                      <Star className="w-3 h-3 fill-amber-400" />
                      {replay.rating} / 5
                    </span>
                  </>
                )}
              </div>
            </header>

            <ScrollArea className="flex-1">
              <div className="p-5 space-y-5">
                {replayLoading && (
                  <div className="flex items-center gap-2 text-sm text-slate-500">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Loading session…
                  </div>
                )}
                {replayError && (
                  <div className="text-sm text-rose-600">{replayError}</div>
                )}
                {replay && !replayLoading && <SessionReplay replay={replay} />}

                {/* Comments section */}
                <section className="mt-8 pt-5 border-t border-slate-200 dark:border-slate-700">
                  <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-3 flex items-center gap-2">
                    <MessageSquare className="w-4 h-4" />
                    Comments ({comments.length})
                  </h2>

                  {commentsLoading && (
                    <div className="text-xs text-slate-500">Loading…</div>
                  )}

                  {!commentsLoading && comments.length === 0 && (
                    <div className="text-xs text-slate-500 dark:text-slate-400">
                      No comments on this session.
                    </div>
                  )}

                  <div className="space-y-2 mb-4">
                    {comments.map((c) => (
                      <div
                        key={c.id}
                        className="rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-100 dark:border-slate-700 p-3"
                      >
                        <div className="flex items-center justify-between gap-2 text-[11px] text-slate-500 dark:text-slate-400 mb-1">
                          <span className="font-medium text-slate-700 dark:text-slate-300">
                            {c.author}
                          </span>
                          <div className="flex items-center gap-2">
                            <span>{new Date(c.created_at).toLocaleString()}</span>
                            {(isAdmin || c.author === username) && (
                              <button
                                onClick={() => handleDeleteComment(c.id)}
                                className="text-rose-500 hover:text-rose-700"
                                title="Delete comment"
                              >
                                <Trash2 className="w-3 h-3" />
                              </button>
                            )}
                          </div>
                        </div>
                        <div className="text-sm text-slate-800 dark:text-slate-200 whitespace-pre-wrap">
                          {c.text}
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="space-y-2">
                    <textarea
                      value={commentDraft}
                      onChange={(e) => setCommentDraft(e.target.value)}
                      placeholder="Add a comment about this session…"
                      rows={3}
                      maxLength={4000}
                      className="w-full px-3 py-2 text-sm bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg resize-y focus:outline-none focus:ring-2 focus:ring-green-600/20 focus:border-green-600"
                    />
                    <div className="flex justify-end">
                      <Button
                        onClick={handleAddComment}
                        disabled={commentSubmitting || !commentDraft.trim()}
                        className="bg-gradient-to-r from-green-700 to-green-800 hover:from-green-800 hover:to-green-900"
                      >
                        {commentSubmitting ? (
                          <>
                            <Loader2 className="w-4 h-4 animate-spin mr-2" />
                            Saving…
                          </>
                        ) : (
                          "Add comment"
                        )}
                      </Button>
                    </div>
                  </div>
                </section>
              </div>
            </ScrollArea>
          </>
        )}
      </main>
    </div>
  );
}
