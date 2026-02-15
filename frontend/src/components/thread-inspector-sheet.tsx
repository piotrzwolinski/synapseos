"use client";

import { useState, useEffect } from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Loader2,
  Mail,
  AlertTriangle,
  CheckCircle2,
  Quote,
  User,
  Clock,
  FileText,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiUrl, authFetch } from "@/lib/api";

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
  sender: string;
  sender_email?: string;
  summary: string;
  logic_node: LogicNode | null;
}

interface TimelineData {
  project: string;
  customer?: string;
  timeline: TimelineEvent[];
}

interface ThreadInspectorSheetProps {
  isOpen: boolean;
  onClose: () => void;
  projectName: string | null;
}

export function ThreadInspectorSheet({
  isOpen,
  onClose,
  projectName,
}: ThreadInspectorSheetProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<TimelineData | null>(null);

  useEffect(() => {
    if (isOpen && projectName) {
      fetchTimeline(projectName);
    }
  }, [isOpen, projectName]);

  const fetchTimeline = async (name: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        apiUrl(`/knowledge/timeline?project_name=${encodeURIComponent(name)}`),
        authFetch()
      );
      if (!response.ok) {
        if (response.status === 404) {
          throw new Error("Project not found in knowledge base");
        }
        throw new Error("Failed to fetch timeline");
      }
      const result = await response.json();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const getLogicTypeStyle = (type: string) => {
    switch (type) {
      case "Symptom":
        return {
          bg: "bg-red-50 dark:bg-red-900/20",
          border: "border-red-300 dark:border-red-800",
          text: "text-red-700 dark:text-red-400",
          icon: "text-red-500",
        };
      case "Constraint":
        return {
          bg: "bg-amber-50 dark:bg-amber-900/20",
          border: "border-amber-300 dark:border-amber-800",
          text: "text-amber-700 dark:text-amber-400",
          icon: "text-amber-500",
        };
      case "Blocker":
        return {
          bg: "bg-orange-50 dark:bg-orange-900/20",
          border: "border-orange-300 dark:border-orange-800",
          text: "text-orange-700 dark:text-orange-400",
          icon: "text-orange-500",
        };
      case "Standard":
        return {
          bg: "bg-blue-50 dark:bg-blue-900/20",
          border: "border-blue-300 dark:border-blue-800",
          text: "text-blue-700 dark:text-blue-400",
          icon: "text-blue-500",
        };
      case "Workaround":
        return {
          bg: "bg-emerald-50 dark:bg-emerald-900/20",
          border: "border-emerald-300 dark:border-emerald-800",
          text: "text-emerald-700 dark:text-emerald-400",
          icon: "text-emerald-500",
        };
      default:
        return {
          bg: "bg-slate-50 dark:bg-slate-800",
          border: "border-slate-200 dark:border-slate-700",
          text: "text-slate-600 dark:text-slate-400",
          icon: "text-slate-400",
        };
    }
  };

  const getLogicIcon = (nodeType: string, type: string) => {
    if (nodeType === "Observation") {
      return <AlertTriangle className="w-3.5 h-3.5" />;
    }
    return <CheckCircle2 className="w-3.5 h-3.5" />;
  };

  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-xl p-0">
        <SheetHeader className="p-6 pb-4 border-b border-slate-100 dark:border-slate-700">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center">
              <FileText className="w-5 h-5 text-white" />
            </div>
            <div>
              <SheetTitle className="text-lg">Source Inspection</SheetTitle>
              <SheetDescription className="text-xs">
                {projectName || "Loading..."}
              </SheetDescription>
            </div>
          </div>
        </SheetHeader>

        <ScrollArea className="h-[calc(100vh-120px)]">
          <div className="p-6">
            {/* Loading State */}
            {loading && (
              <div className="flex flex-col items-center justify-center py-16">
                <Loader2 className="w-8 h-8 animate-spin text-blue-600 mb-3" />
                <p className="text-sm text-slate-500">Loading email thread...</p>
              </div>
            )}

            {/* Error State */}
            {error && (
              <div className="p-4 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
                <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
              </div>
            )}

            {/* Timeline */}
            {!loading && !error && data && (
              <div className="space-y-4">
                {/* Project Header */}
                <div className="p-4 rounded-xl bg-gradient-to-br from-slate-50 to-blue-50 dark:from-slate-800 dark:to-blue-900/20 border border-slate-200 dark:border-slate-700">
                  <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">
                    Project Reference
                  </p>
                  <p className="font-semibold text-slate-900 dark:text-slate-100">{data.project}</p>
                  {data.customer && (
                    <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
                      Customer: {data.customer}
                    </p>
                  )}
                </div>

                {/* Timeline Events */}
                <div className="space-y-3">
                  <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                    Email Thread ({data.timeline.length} messages)
                  </p>

                  {data.timeline.map((event, index) => {
                    const hasLogic = event.logic_node !== null;
                    const logicStyle = hasLogic
                      ? getLogicTypeStyle(event.logic_node!.type)
                      : null;

                    return (
                      <div
                        key={index}
                        className={cn(
                          "relative p-4 rounded-xl border-2 transition-all",
                          hasLogic
                            ? `${logicStyle!.bg} ${logicStyle!.border}`
                            : "bg-white dark:bg-slate-800 border-slate-100 dark:border-slate-700 hover:border-slate-200 dark:hover:border-slate-600"
                        )}
                      >
                        {/* Step indicator */}
                        <div className="absolute -left-3 top-4 w-6 h-6 rounded-full bg-gradient-to-br from-blue-600 to-violet-600 text-white flex items-center justify-center text-xs font-bold shadow-md">
                          {event.step}
                        </div>

                        {/* Email Header */}
                        <div className="ml-4">
                          <div className="flex items-center gap-2 text-xs text-slate-500 mb-2">
                            <User className="w-3 h-3" />
                            <span className="font-medium text-slate-700 dark:text-slate-300">
                              {event.sender}
                            </span>
                            {(event.date || event.time) && (
                              <>
                                <span>•</span>
                                <Clock className="w-3 h-3" />
                                <span>
                                  {event.date}
                                  {event.time && ` ${event.time}`}
                                </span>
                              </>
                            )}
                          </div>

                          {/* Email Summary */}
                          <div className="flex items-start gap-2 mb-2">
                            <Mail className="w-4 h-4 text-slate-400 flex-shrink-0 mt-0.5" />
                            <p className="text-sm text-slate-700 dark:text-slate-300">
                              {event.summary}
                            </p>
                          </div>

                          {/* Logic Node (if present) */}
                          {hasLogic && (
                            <div className="mt-3 pt-3 border-t border-slate-200/50 dark:border-slate-700/50">
                              {/* Logic Tag */}
                              <div className="flex items-center gap-2 mb-2">
                                <span
                                  className={cn(
                                    "inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-semibold",
                                    logicStyle!.bg,
                                    logicStyle!.text,
                                    "border",
                                    logicStyle!.border
                                  )}
                                >
                                  {getLogicIcon(
                                    event.logic_node!.node_type,
                                    event.logic_node!.type
                                  )}
                                  {event.logic_node!.type}
                                </span>
                                <span className="text-xs text-slate-500">
                                  {event.logic_node!.node_type === "Observation"
                                    ? "Problem Detected"
                                    : "Solution Proposed"}
                                </span>
                              </div>

                              {/* Logic Description */}
                              <p className="text-sm text-slate-700 dark:text-slate-300 mb-2">
                                {event.logic_node!.description}
                              </p>

                              {/* Citation (Source Evidence) */}
                              {event.logic_node!.citation && (
                                <div className="mt-2 pl-3 py-2 border-l-4 border-slate-300 dark:border-slate-600 bg-white/50 dark:bg-slate-700/50 rounded-r-lg">
                                  <div className="flex items-start gap-2">
                                    <Quote className="w-3 h-3 text-slate-400 flex-shrink-0 mt-0.5" />
                                    <p className="text-xs text-slate-500 dark:text-slate-400 italic leading-relaxed">
                                      "{event.logic_node!.citation}"
                                    </p>
                                  </div>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Empty State */}
                {data.timeline.length === 0 && (
                  <div className="text-center py-12">
                    <Mail className="w-12 h-12 mx-auto text-slate-300 mb-3" />
                    <p className="text-sm text-slate-500">
                      No email thread found for this project
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
