"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Loader2,
  BookOpen,
  CheckCircle2,
  XCircle,
  Link2,
  RefreshCw,
  Search,
  AlertTriangle,
  Lightbulb,
  Database,
  FileText,
  Settings,
  Quote,
  ChevronDown,
  ChevronRight,
  Trash2,
  Clock,
  Tag,
  ExternalLink,
  Users,
  BarChart3,
  TrendingUp,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiUrl, authFetch } from "@/lib/api";

interface KnowledgeCandidate {
  id: string;
  raw_name: string;
  type: string;
  inference_logic: string;
  citation: string;
  status: string;
  created_at: string;
  events: string[];
  projects: string[];
  verified_as: string | null;
}

interface VerifiedSource {
  id: string;
  name: string;
  type: string;
  description: string | null;
  usage_count: number;
  aliases: string[];
  created_at: string;
  top_experts?: string[];
}

interface ExpertSource {
  source: string;
  type: string;
  usage_count: number;
}

interface Expert {
  expert_name: string;
  expert_email: string | null;
  source_count: number;
  top_sources: ExpertSource[];
}

interface KnowledgeStats {
  pending: number;
  verified: number;
  rejected: number;
  total_candidates: number;
  total_sources: number;
  total_projects: number;
}

type ViewMode = "candidates" | "library" | "experts";

export function KnowledgeCenter() {
  const [viewMode, setViewMode] = useState<ViewMode>("candidates");
  const [candidates, setCandidates] = useState<KnowledgeCandidate[]>([]);
  const [verifiedSources, setVerifiedSources] = useState<VerifiedSource[]>([]);
  const [experts, setExperts] = useState<Expert[]>([]);
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [expandedCard, setExpandedCard] = useState<string | null>(null);
  const [verifyModalOpen, setVerifyModalOpen] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState<KnowledgeCandidate | null>(null);
  const [verifyAction, setVerifyAction] = useState<"create_new" | "map_to_existing">("create_new");
  const [verifiedName, setVerifiedName] = useState("");
  const [description, setDescription] = useState("");
  const [selectedSourceId, setSelectedSourceId] = useState<string>("");

  useEffect(() => {
    fetchStats();
  }, []);

  useEffect(() => {
    if (viewMode === "candidates") {
      fetchCandidates();
    } else if (viewMode === "library") {
      fetchLibrary();
    } else if (viewMode === "experts") {
      fetchExperts();
    }
  }, [viewMode]);

  const fetchStats = async () => {
    try {
      const response = await fetch(apiUrl("/knowledge/stats"), authFetch());
      if (response.ok) {
        const data = await response.json();
        setStats(data);
      }
    } catch {
      // Stats are optional, don't show error
    }
  };

  const fetchExperts = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(apiUrl("/knowledge/experts"), authFetch());
      if (!response.ok) throw new Error("Failed to fetch experts");
      const data = await response.json();
      setExperts(data.experts || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load experts");
    } finally {
      setLoading(false);
    }
  };

  const fetchCandidates = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(apiUrl("/knowledge/candidates?status=pending"), authFetch());
      if (!response.ok) throw new Error("Failed to fetch candidates");
      const data = await response.json();
      setCandidates(data.candidates || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load candidates");
    } finally {
      setLoading(false);
    }
  };

  const fetchLibrary = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(apiUrl("/knowledge/library"), authFetch());
      if (!response.ok) throw new Error("Failed to fetch library");
      const data = await response.json();
      setVerifiedSources(data.sources || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load library");
    } finally {
      setLoading(false);
    }
  };

  const rejectCandidate = async (candidateId: string) => {
    setProcessingId(candidateId);
    try {
      const response = await fetch(apiUrl("/knowledge/verify"), authFetch({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          candidate_id: candidateId,
          action: "reject",
        }),
      }));
      if (!response.ok) throw new Error("Failed to reject candidate");
      await fetchCandidates();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to reject");
    } finally {
      setProcessingId(null);
    }
  };

  const openVerifyModal = (candidate: KnowledgeCandidate) => {
    setSelectedCandidate(candidate);
    setVerifiedName(candidate.raw_name);
    setDescription(candidate.inference_logic);
    setVerifyAction("create_new");
    setSelectedSourceId("");
    setVerifyModalOpen(true);
  };

  const submitVerification = async () => {
    if (!selectedCandidate) return;

    setProcessingId(selectedCandidate.id);
    try {
      const body: Record<string, string> = {
        candidate_id: selectedCandidate.id,
        action: verifyAction,
      };

      if (verifyAction === "create_new") {
        body.verified_name = verifiedName;
        body.description = description;
      } else {
        body.existing_source_id = selectedSourceId;
      }

      const response = await fetch(apiUrl("/knowledge/verify"), authFetch({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }));
      if (!response.ok) throw new Error("Failed to verify candidate");
      await fetchCandidates();
      setVerifyModalOpen(false);
      setSelectedCandidate(null);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to verify");
    } finally {
      setProcessingId(null);
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case "Software":
        return <Settings className="w-4 h-4" />;
      case "Data":
        return <Database className="w-4 h-4" />;
      case "Manual":
        return <FileText className="w-4 h-4" />;
      case "Process":
        return <Settings className="w-4 h-4" />;
      default:
        return <Lightbulb className="w-4 h-4" />;
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case "Software":
        return "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-800";
      case "Data":
        return "bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-900/30 dark:text-purple-400 dark:border-purple-800";
      case "Manual":
        return "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/30 dark:text-amber-400 dark:border-amber-800";
      case "Process":
        return "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-800";
      default:
        return "bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700";
    }
  };

  const filteredCandidates = candidates.filter(
    (c) =>
      c.raw_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (c.inference_logic && c.inference_logic.toLowerCase().includes(searchQuery.toLowerCase())) ||
      c.type.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredExperts = experts.filter(
    (e) =>
      e.expert_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      e.top_sources.some((s) => s.source.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const filteredSources = verifiedSources.filter(
    (s) =>
      s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (s.description && s.description.toLowerCase().includes(searchQuery.toLowerCase())) ||
      s.aliases.some((a) => a.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return (
    <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl shadow-slate-200/50 dark:shadow-slate-900/50 border border-slate-200/60 dark:border-slate-700/60 overflow-hidden h-full flex flex-col">
      {/* Header */}
      <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-700 bg-gradient-to-r from-slate-50 to-white dark:from-slate-800 dark:to-slate-800">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-lg shadow-violet-500/20">
              <BookOpen className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-900 dark:text-slate-100">Knowledge Center</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {viewMode === "candidates" && `${candidates.length} pending discoveries`}
                {viewMode === "library" && `${verifiedSources.length} verified sources`}
                {viewMode === "experts" && `${experts.length} subject matter experts`}
              </p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              if (viewMode === "candidates") fetchCandidates();
              else if (viewMode === "library") fetchLibrary();
              else fetchExperts();
              fetchStats();
            }}
            disabled={loading}
            className="text-slate-500"
          >
            <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
          </Button>
        </div>

        {/* Stats Row */}
        {stats && (
          <div className="grid grid-cols-4 gap-3 mb-4">
            <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-100 dark:border-amber-800">
              <div className="flex items-center gap-2">
                <Clock className="w-4 h-4 text-amber-600" />
                <span className="text-lg font-bold text-amber-700 dark:text-amber-400">{stats.pending}</span>
              </div>
              <p className="text-xs text-amber-600 dark:text-amber-400 mt-0.5">Pending</p>
            </div>
            <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-100 dark:border-emerald-800">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                <span className="text-lg font-bold text-emerald-700 dark:text-emerald-400">{stats.total_sources}</span>
              </div>
              <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-0.5">Verified</p>
            </div>
            <div className="p-3 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800">
              <div className="flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-blue-600" />
                <span className="text-lg font-bold text-blue-700 dark:text-blue-400">{stats.total_projects}</span>
              </div>
              <p className="text-xs text-blue-600 dark:text-blue-400 mt-0.5">Projects</p>
            </div>
            <div className="p-3 rounded-lg bg-violet-50 dark:bg-violet-900/20 border border-violet-100 dark:border-violet-800">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-violet-600" />
                <span className="text-lg font-bold text-violet-700 dark:text-violet-400">
                  {stats.total_candidates > 0
                    ? Math.round((stats.total_sources / (stats.total_sources + stats.pending)) * 100)
                    : 0}%
                </span>
              </div>
              <p className="text-xs text-violet-600 dark:text-violet-400 mt-0.5">Coverage</p>
            </div>
          </div>
        )}

        {/* View Mode Tabs */}
        <div className="flex gap-2">
          <Button
            variant={viewMode === "candidates" ? "default" : "ghost"}
            size="sm"
            onClick={() => setViewMode("candidates")}
            className={cn(
              viewMode === "candidates"
                ? "bg-violet-600 hover:bg-violet-700"
                : "hover:bg-violet-50 dark:hover:bg-violet-900/20"
            )}
          >
            <Clock className="w-4 h-4 mr-2" />
            Pending Review
          </Button>
          <Button
            variant={viewMode === "library" ? "default" : "ghost"}
            size="sm"
            onClick={() => setViewMode("library")}
            className={cn(
              viewMode === "library"
                ? "bg-violet-600 hover:bg-violet-700"
                : "hover:bg-violet-50 dark:hover:bg-violet-900/20"
            )}
          >
            <BookOpen className="w-4 h-4 mr-2" />
            Knowledge Library
          </Button>
          <Button
            variant={viewMode === "experts" ? "default" : "ghost"}
            size="sm"
            onClick={() => setViewMode("experts")}
            className={cn(
              viewMode === "experts"
                ? "bg-violet-600 hover:bg-violet-700"
                : "hover:bg-violet-50 dark:hover:bg-violet-900/20"
            )}
          >
            <Users className="w-4 h-4 mr-2" />
            SME Directory
          </Button>
        </div>
      </div>

      {/* Search */}
      <div className="p-4 border-b border-slate-100 dark:border-slate-700">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={
              viewMode === "candidates"
                ? "Search discoveries..."
                : "Search verified sources..."
            }
            className="w-full pl-10 pr-4 py-2 text-sm bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500 dark:text-slate-200 dark:placeholder-slate-400"
          />
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="w-8 h-8 animate-spin text-violet-600" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-full p-6">
            <AlertTriangle className="w-12 h-12 text-red-400 mb-4" />
            <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">{error}</p>
            <Button
              onClick={() => (viewMode === "candidates" ? fetchCandidates() : fetchLibrary())}
              variant="outline"
            >
              Try Again
            </Button>
          </div>
        ) : viewMode === "candidates" ? (
          // Candidates View
          filteredCandidates.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full p-6 text-center">
              <CheckCircle2 className="w-16 h-16 text-emerald-400 mb-4" />
              <h4 className="font-medium text-slate-600 dark:text-slate-400 mb-2">All caught up!</h4>
              <p className="text-sm text-slate-400">
                {searchQuery
                  ? "No discoveries match your search"
                  : "No pending discoveries to review"}
              </p>
            </div>
          ) : (
            <ScrollArea className="h-full">
              <div className="p-4 space-y-3">
                {filteredCandidates.map((candidate) => (
                  <div
                    key={candidate.id}
                    className="p-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:border-violet-300 dark:hover:border-violet-700 transition-all"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        {/* Header */}
                        <div className="flex items-center gap-2 mb-2">
                          <span
                            className={cn(
                              "flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium border",
                              getTypeColor(candidate.type)
                            )}
                          >
                            {getTypeIcon(candidate.type)}
                            {candidate.type}
                          </span>
                          <h4 className="font-semibold text-slate-900 dark:text-slate-100 truncate">
                            {candidate.raw_name}
                          </h4>
                        </div>

                        {/* Inference Logic - Why AI suggested this */}
                        <div className="mb-3 p-2 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-100 dark:border-amber-800">
                          <p className="text-xs font-medium text-amber-700 dark:text-amber-400 mb-1">
                            Why I suggested this:
                          </p>
                          <p className="text-sm text-amber-900 dark:text-amber-300">{candidate.inference_logic}</p>
                        </div>

                        {/* Source Info */}
                        {candidate.projects && candidate.projects.length > 0 && (
                          <div className="flex items-center gap-1 text-xs text-slate-400 mb-2">
                            <ExternalLink className="w-3 h-3" />
                            Found in: {candidate.projects.filter(Boolean).join(", ")}
                          </div>
                        )}

                        {/* Citation - Expandable */}
                        <div
                          className="cursor-pointer"
                          onClick={() =>
                            setExpandedCard(
                              expandedCard === candidate.id ? null : candidate.id
                            )
                          }
                        >
                          <div className="flex items-center gap-1 text-xs text-violet-600 hover:text-violet-800">
                            {expandedCard === candidate.id ? (
                              <ChevronDown className="w-3 h-3" />
                            ) : (
                              <ChevronRight className="w-3 h-3" />
                            )}
                            <Quote className="w-3 h-3" />
                            View source citation
                          </div>
                          {expandedCard === candidate.id && (
                            <div className="mt-2 pl-3 py-2 border-l-4 border-violet-200 dark:border-violet-800 bg-violet-50 dark:bg-violet-900/20 rounded-r-lg">
                              <p className="text-xs text-slate-600 dark:text-slate-400 italic">
                                &ldquo;{candidate.citation}&rdquo;
                              </p>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex flex-col gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => openVerifyModal(candidate)}
                          disabled={processingId === candidate.id}
                          className="text-emerald-600 border-emerald-200 hover:bg-emerald-50 dark:border-emerald-800 dark:hover:bg-emerald-900/30"
                        >
                          {processingId === candidate.id ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <CheckCircle2 className="w-4 h-4" />
                          )}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => rejectCandidate(candidate.id)}
                          disabled={processingId === candidate.id}
                          className="text-red-500 border-red-200 hover:bg-red-50 dark:border-red-800 dark:hover:bg-red-900/30"
                        >
                          <XCircle className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )
        ) : viewMode === "library" ? (
          // Library View
          filteredSources.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full p-6 text-center">
              <BookOpen className="w-16 h-16 text-slate-300 mb-4" />
              <h4 className="font-medium text-slate-600 dark:text-slate-400 mb-2">Library is empty</h4>
              <p className="text-sm text-slate-400">
                {searchQuery
                  ? "No sources match your search"
                  : "Verify some discoveries to build your knowledge library"}
              </p>
            </div>
          ) : (
            <ScrollArea className="h-full">
              <div className="p-4 space-y-3">
                {filteredSources.map((source) => (
                  <div
                    key={source.id}
                    className="p-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:border-violet-300 dark:hover:border-violet-700 transition-all"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        {/* Header */}
                        <div className="flex items-center gap-2 mb-2">
                          <span
                            className={cn(
                              "flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium border",
                              getTypeColor(source.type)
                            )}
                          >
                            {getTypeIcon(source.type)}
                            {source.type}
                          </span>
                          <h4 className="font-semibold text-slate-900 dark:text-slate-100">{source.name}</h4>
                        </div>

                        {/* Description */}
                        {source.description && (
                          <p className="text-sm text-slate-600 dark:text-slate-400 mb-2">{source.description}</p>
                        )}

                        {/* Aliases */}
                        {source.aliases?.length > 0 && (
                          <div className="flex items-center gap-2 flex-wrap mb-2">
                            <Link2 className="w-3 h-3 text-slate-400" />
                            {source.aliases.map((alias, i) => (
                              <span
                                key={i}
                                className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300"
                              >
                                {alias}
                              </span>
                            ))}
                          </div>
                        )}

                        {/* Usage Stats */}
                        <div className="flex items-center gap-4 text-xs text-slate-400">
                          <span className="flex items-center gap-1">
                            <Tag className="w-3 h-3" />
                            {source.usage_count} references
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )
        ) : viewMode === "experts" ? (
          // Experts View
          filteredExperts.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full p-6 text-center">
              <Users className="w-16 h-16 text-slate-300 mb-4" />
              <h4 className="font-medium text-slate-600 dark:text-slate-400 mb-2">No expert data yet</h4>
              <p className="text-sm text-slate-400">
                {searchQuery
                  ? "No experts match your search"
                  : "Verify knowledge discoveries to build the SME directory"}
              </p>
            </div>
          ) : (
            <ScrollArea className="h-full">
              <div className="p-4 space-y-3">
                {filteredExperts.map((expert) => (
                  <div
                    key={expert.expert_name}
                    className="p-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:border-violet-300 dark:hover:border-violet-700 transition-all"
                  >
                    <div className="flex items-start gap-4">
                      {/* Avatar */}
                      <div className="w-12 h-12 rounded-full bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center text-white font-bold text-lg shadow-lg">
                        {expert.expert_name.charAt(0).toUpperCase()}
                      </div>

                      <div className="flex-1 min-w-0">
                        {/* Name */}
                        <h4 className="font-semibold text-slate-900 dark:text-slate-100">{expert.expert_name}</h4>
                        {expert.expert_email && (
                          <p className="text-xs text-slate-400">{expert.expert_email}</p>
                        )}

                        {/* Expertise Count */}
                        <div className="flex items-center gap-1 text-xs text-violet-600 mt-1">
                          <BookOpen className="w-3 h-3" />
                          Expert in {expert.source_count} verified source{expert.source_count !== 1 ? "s" : ""}
                        </div>

                        {/* Top Sources */}
                        {expert.top_sources?.length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-2">
                            {expert.top_sources.map((src, i) => (
                              <div
                                key={i}
                                className={cn(
                                  "flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium border",
                                  getTypeColor(src.type)
                                )}
                              >
                                {getTypeIcon(src.type)}
                                <span>{src.source}</span>
                                <span className="ml-1 px-1.5 py-0.5 rounded-full bg-white/50 text-[10px]">
                                  {src.usage_count}x
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )
        ) : null}
      </div>

      {/* Verification Modal */}
      {verifyModalOpen && selectedCandidate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
            <div className="p-6 border-b border-slate-100 dark:border-slate-700">
              <h3 className="font-semibold text-lg text-slate-900 dark:text-slate-100">Verify Discovery</h3>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                Verifying: <strong>{selectedCandidate.raw_name}</strong>
              </p>
            </div>

            <div className="p-6 space-y-4">
              {/* Action Selection */}
              <div className="flex gap-2">
                <Button
                  variant={verifyAction === "create_new" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setVerifyAction("create_new")}
                  className={cn(
                    verifyAction === "create_new" && "bg-violet-600 hover:bg-violet-700"
                  )}
                >
                  <CheckCircle2 className="w-4 h-4 mr-2" />
                  Create New
                </Button>
                <Button
                  variant={verifyAction === "map_to_existing" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setVerifyAction("map_to_existing")}
                  className={cn(
                    verifyAction === "map_to_existing" && "bg-violet-600 hover:bg-violet-700"
                  )}
                >
                  <Link2 className="w-4 h-4 mr-2" />
                  Map to Existing
                </Button>
              </div>

              {verifyAction === "create_new" ? (
                <>
                  {/* Verified Name */}
                  <div>
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                      Canonical Name
                    </label>
                    <input
                      type="text"
                      value={verifiedName}
                      onChange={(e) => setVerifiedName(e.target.value)}
                      className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500"
                      placeholder="e.g., HABE Calculation Tool"
                    />
                  </div>

                  {/* Description */}
                  <div>
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                      Description
                    </label>
                    <textarea
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      rows={3}
                      className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500 resize-none"
                      placeholder="What is this tool/data source used for?"
                    />
                  </div>
                </>
              ) : (
                /* Map to Existing */
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Select Existing Source
                  </label>
                  <select
                    value={selectedSourceId}
                    onChange={(e) => setSelectedSourceId(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500"
                  >
                    <option value="">-- Select a source --</option>
                    {verifiedSources.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name} ({s.type})
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-slate-400 mt-2">
                    This will create an alias relationship: &ldquo;{selectedCandidate.raw_name}&rdquo; →{" "}
                    selected source
                  </p>
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="p-6 border-t border-slate-100 dark:border-slate-700 flex gap-3 justify-end">
              <Button
                variant="outline"
                onClick={() => {
                  setVerifyModalOpen(false);
                  setSelectedCandidate(null);
                }}
              >
                Cancel
              </Button>
              <Button
                onClick={submitVerification}
                disabled={
                  processingId === selectedCandidate.id ||
                  (verifyAction === "create_new" && !verifiedName) ||
                  (verifyAction === "map_to_existing" && !selectedSourceId)
                }
                className="bg-violet-600 hover:bg-violet-700"
              >
                {processingId === selectedCandidate.id ? (
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                ) : (
                  <CheckCircle2 className="w-4 h-4 mr-2" />
                )}
                Verify
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
