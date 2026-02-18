"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Loader2,
  Mail,
  Trash2,
  ChevronRight,
  Calendar,
  Users,
  Eye,
  Zap,
  Tag,
  AlertTriangle,
  RefreshCw,
  Search,
  FolderOpen,
  ArrowLeft,
  Quote,
  User,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiUrl, authFetch } from "@/lib/api";

interface ThreadSummary {
  name: string;
  customer: string | null;
  summary: string | null;
  event_count: number;
  observation_count: number;
  action_count: number;
  participants: string[];
  dates: string[];
  key_concepts: string[];
}

interface LogicNode {
  node_type: "Observation" | "Action";
  type: string;
  description: string;
  citation?: string;
}

interface TimelineEvent {
  step: number;
  date: string;
  time?: string;
  summary: string;
  sender: string;
  sender_email?: string;
  logic_node: LogicNode | null;
}

interface ThreadDetail {
  project: string;
  customer: string | null;
  timeline: TimelineEvent[];
}

export function ThreadExplorer() {
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [selectedThread, setSelectedThread] = useState<string | null>(null);
  const [threadDetail, setThreadDetail] = useState<ThreadDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Fetch all threads on mount
  useEffect(() => {
    fetchThreads();
  }, []);

  const fetchThreads = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(apiUrl("/threads"), authFetch());
      if (!response.ok) throw new Error("Failed to fetch threads");
      const data = await response.json();
      setThreads(data.threads || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load threads");
    } finally {
      setLoading(false);
    }
  };

  const fetchThreadDetail = async (projectName: string) => {
    setLoadingDetail(true);
    try {
      const response = await fetch(
        apiUrl(`/threads/${encodeURIComponent(projectName)}`),
        authFetch()
      );
      if (!response.ok) throw new Error("Failed to fetch thread details");
      const data = await response.json();
      setThreadDetail(data);
      setSelectedThread(projectName);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load thread");
    } finally {
      setLoadingDetail(false);
    }
  };

  const deleteThread = async (projectName: string) => {
    if (!confirm(`Are you sure you want to delete "${projectName}" and all its data?`)) {
      return;
    }

    setDeleting(projectName);
    try {
      const response = await fetch(
        apiUrl(`/threads/${encodeURIComponent(projectName)}`),
        authFetch({ method: "DELETE" })
      );
      if (!response.ok) throw new Error("Failed to delete thread");

      // Refresh thread list
      await fetchThreads();

      // Clear selection if the deleted thread was selected
      if (selectedThread === projectName) {
        setSelectedThread(null);
        setThreadDetail(null);
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete thread");
    } finally {
      setDeleting(null);
    }
  };

  const getLogicTypeStyle = (type: string) => {
    switch (type) {
      case "Symptom":
        return "bg-red-50 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800";
      case "Constraint":
        return "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/30 dark:text-amber-400 dark:border-amber-800";
      case "Blocker":
        return "bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-900/30 dark:text-orange-400 dark:border-orange-800";
      case "Standard":
        return "bg-green-50 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-500 dark:border-green-800";
      case "Workaround":
        return "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-800";
      case "ProductMapping":
        return "bg-green-50 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-500 dark:border-green-800";
      case "Commercial":
        return "bg-green-50 text-green-700 border-green-200 dark:bg-green-900/30 dark:text-green-400 dark:border-green-800";
      default:
        return "bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700";
    }
  };

  const filteredThreads = threads.filter((t) =>
    t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (t.customer && t.customer.toLowerCase().includes(searchQuery.toLowerCase())) ||
    t.key_concepts.some((c) => c.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const getDateRange = (dates: string[]) => {
    const validDates = dates.filter((d) => d && d !== "Unknown");
    if (validDates.length === 0) return "Unknown dates";
    if (validDates.length === 1) return validDates[0];
    return `${validDates[0]} → ${validDates[validDates.length - 1]}`;
  };

  return (
    <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl shadow-slate-200/50 dark:shadow-slate-900/50 border border-slate-200/60 dark:border-slate-700/60 overflow-hidden h-full flex flex-col">
      {/* Header */}
      <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-700 flex items-center justify-between bg-gradient-to-r from-slate-50 to-white dark:from-slate-800 dark:to-slate-800">
        <div className="flex items-center gap-3">
          {selectedThread && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSelectedThread(null);
                setThreadDetail(null);
              }}
              className="mr-2"
            >
              <ArrowLeft className="w-4 h-4" />
            </Button>
          )}
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-500/20">
            <Mail className="w-5 h-5 text-white" />
          </div>
          <div>
            <h3 className="font-semibold text-slate-900 dark:text-slate-100">
              {selectedThread || "Thread Explorer"}
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {selectedThread
                ? `${threadDetail?.timeline.length || 0} emails in thread`
                : `${threads.length} threads in knowledge base`}
            </p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={fetchThreads}
          disabled={loading}
          className="text-slate-500"
        >
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
        </Button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="w-8 h-8 animate-spin text-emerald-600" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-full p-6">
            <AlertTriangle className="w-12 h-12 text-red-400 mb-4" />
            <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">{error}</p>
            <Button onClick={fetchThreads} variant="outline">
              Try Again
            </Button>
          </div>
        ) : !selectedThread ? (
          // Thread List View
          <div className="h-full flex flex-col">
            {/* Search */}
            <div className="p-4 border-b border-slate-100 dark:border-slate-700">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search threads..."
                  className="w-full pl-10 pr-4 py-2 text-sm bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 dark:text-slate-200 dark:placeholder-slate-400"
                />
              </div>
            </div>

            {filteredThreads.length === 0 ? (
              <div className="flex flex-col items-center justify-center flex-1 p-6 text-center">
                <FolderOpen className="w-16 h-16 text-slate-300 mb-4" />
                <h4 className="font-medium text-slate-600 dark:text-slate-400 mb-2">No threads found</h4>
                <p className="text-sm text-slate-400">
                  {searchQuery
                    ? "Try a different search term"
                    : "Ingest some email threads to see them here"}
                </p>
              </div>
            ) : (
              <ScrollArea className="flex-1">
                <div className="p-4 space-y-3">
                  {filteredThreads.map((thread) => (
                    <div
                      key={thread.name}
                      className="p-4 rounded-xl border border-slate-200 dark:border-slate-700 hover:border-emerald-300 dark:hover:border-emerald-700 hover:bg-emerald-50/30 dark:hover:bg-emerald-900/20 transition-all cursor-pointer group"
                      onClick={() => fetchThreadDetail(thread.name)}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <h4 className="font-semibold text-slate-900 dark:text-slate-100 truncate">
                              {thread.name}
                            </h4>
                            {thread.customer && (
                              <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                                {thread.customer}
                              </span>
                            )}
                          </div>

                          {/* Stats Row */}
                          <div className="flex items-center gap-4 text-xs text-slate-500 dark:text-slate-400 mb-2">
                            <span className="flex items-center gap-1">
                              <Mail className="w-3 h-3" />
                              {thread.event_count} emails
                            </span>
                            <span className="flex items-center gap-1">
                              <Eye className="w-3 h-3" />
                              {thread.observation_count} observations
                            </span>
                            <span className="flex items-center gap-1">
                              <Zap className="w-3 h-3" />
                              {thread.action_count} actions
                            </span>
                          </div>

                          {/* Date Range */}
                          <div className="flex items-center gap-1 text-xs text-slate-400 mb-2">
                            <Calendar className="w-3 h-3" />
                            {getDateRange(thread.dates)}
                          </div>

                          {/* Participants */}
                          {thread.participants.length > 0 && (
                            <div className="flex items-center gap-1 text-xs text-slate-400 mb-2">
                              <Users className="w-3 h-3" />
                              {thread.participants.filter(Boolean).slice(0, 3).join(", ")}
                              {thread.participants.length > 3 && ` +${thread.participants.length - 3}`}
                            </div>
                          )}

                          {/* Key Concepts */}
                          {thread.key_concepts.length > 0 && (
                            <div className="flex items-center gap-1 flex-wrap mt-2">
                              <Tag className="w-3 h-3 text-slate-400" />
                              {thread.key_concepts.slice(0, 4).map((concept, i) => (
                                <span
                                  key={i}
                                  className="text-xs px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
                                >
                                  {concept}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>

                        {/* Actions */}
                        <div className="flex items-center gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              deleteThread(thread.name);
                            }}
                            disabled={deleting === thread.name}
                            className="text-red-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 opacity-0 group-hover:opacity-100 transition-opacity"
                          >
                            {deleting === thread.name ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <Trash2 className="w-4 h-4" />
                            )}
                          </Button>
                          <ChevronRight className="w-5 h-5 text-slate-300 group-hover:text-emerald-500 transition-colors" />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </div>
        ) : loadingDetail ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="w-8 h-8 animate-spin text-emerald-600" />
          </div>
        ) : threadDetail ? (
          // Thread Detail View
          <ScrollArea className="h-full">
            <div className="p-6 space-y-4">
              {/* Summary Card */}
              <div className="p-4 rounded-xl bg-gradient-to-br from-emerald-50 to-teal-50 dark:from-emerald-900/20 dark:to-teal-900/20 border border-emerald-200 dark:border-emerald-800">
                <h4 className="font-semibold text-emerald-900 dark:text-emerald-300 mb-2">
                  {threadDetail.project}
                </h4>
                {threadDetail.customer && (
                  <p className="text-sm text-emerald-700 dark:text-emerald-400">
                    Customer: {threadDetail.customer}
                  </p>
                )}
                <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1">
                  {threadDetail.timeline.length} emails in this thread
                </p>
              </div>

              {/* Timeline */}
              <div className="space-y-4">
                <h5 className="text-sm font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-2">
                  <Mail className="w-4 h-4" />
                  Email Timeline
                </h5>

                {threadDetail.timeline.map((event, idx) => (
                  <div
                    key={idx}
                    className="relative pl-8 pb-4 border-l-2 border-slate-200 dark:border-slate-700 last:pb-0"
                  >
                    {/* Timeline dot */}
                    <div className="absolute left-[-9px] top-0 w-4 h-4 rounded-full bg-white dark:bg-slate-800 border-2 border-emerald-500 flex items-center justify-center">
                      <span className="text-[8px] font-bold text-emerald-600">
                        {event.step}
                      </span>
                    </div>

                    {/* Event Card */}
                    <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-4 shadow-sm">
                      {/* Header */}
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <User className="w-4 h-4 text-slate-400" />
                          <span className="font-medium text-slate-800 dark:text-slate-200">
                            {event.sender}
                          </span>
                        </div>
                        <span className="text-xs text-slate-400">
                          {event.date}
                          {event.time && ` ${event.time}`}
                        </span>
                      </div>

                      {/* Summary */}
                      <p className="text-sm text-slate-600 dark:text-slate-400 mb-3">{event.summary}</p>

                      {/* Logic Node */}
                      {event.logic_node && (
                        <div className="space-y-2">
                          <div className="flex items-center gap-2">
                            <span
                              className={cn(
                                "px-2 py-0.5 rounded text-xs font-medium border",
                                getLogicTypeStyle(event.logic_node.type)
                              )}
                            >
                              {event.logic_node.node_type}: {event.logic_node.type}
                            </span>
                          </div>

                          <p className="text-sm text-slate-700 dark:text-slate-300 bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3">
                            {event.logic_node.description}
                          </p>

                          {/* Citation */}
                          {event.logic_node.citation && (
                            <div className="pl-3 py-2 border-l-4 border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700/50 rounded-r-lg">
                              <div className="flex items-start gap-2">
                                <Quote className="w-3 h-3 text-slate-400 flex-shrink-0 mt-0.5" />
                                <p className="text-xs text-slate-500 dark:text-slate-400 italic">
                                  "{event.logic_node.citation}"
                                </p>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Delete Button */}
              <div className="pt-4 border-t border-slate-200 dark:border-slate-700">
                <Button
                  variant="outline"
                  onClick={() => deleteThread(threadDetail.project)}
                  disabled={deleting === threadDetail.project}
                  className="w-full text-red-600 border-red-200 hover:bg-red-50 dark:border-red-800 dark:hover:bg-red-900/30"
                >
                  {deleting === threadDetail.project ? (
                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  ) : (
                    <Trash2 className="w-4 h-4 mr-2" />
                  )}
                  Delete Thread & All Data
                </Button>
              </div>
            </div>
          </ScrollArea>
        ) : null}
      </div>
    </div>
  );
}
