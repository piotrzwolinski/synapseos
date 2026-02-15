"use client";

import { useState, useEffect, useReducer, useCallback, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Loader2,
  BookOpen,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Pencil,
  ExternalLink,
  Clock,
  Activity,
  TrendingUp,
  AlertTriangle,
  Lightbulb,
  Database,
  FileText,
  Settings,
  Quote,
  ChevronDown,
  ChevronRight,
  Users,
  BarChart3,
  Sparkles,
  X,
  Zap,
  Link2,
  Tag,
  Search,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiUrl, authFetch } from "@/lib/api";

// ─── Types ───────────────────────────────────────────────────

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

interface Expert {
  expert_name: string;
  expert_email: string | null;
  source_count: number;
  top_sources: { source: string; type: string; usage_count: number }[];
}

interface KnowledgeStats {
  pending: number;
  verified: number;
  rejected: number;
  total_candidates: number;
  total_sources: number;
  total_projects: number;
}

type RefineryView = "feed" | "library" | "experts";
type CardAnimation = "none" | "exit-left" | "exit-right" | "exit-up" | "enter";

interface RefineryState {
  view: RefineryView;
  candidates: KnowledgeCandidate[];
  verifiedSources: VerifiedSource[];
  experts: Expert[];
  stats: KnowledgeStats | null;
  currentIndex: number;
  cardAnimation: CardAnimation;
  editMode: boolean;
  editedLogic: string;
  loading: boolean;
  error: string | null;
  processingAction: boolean;
  sessionReviewed: number;
  sessionGoal: number;
  verifyModalOpen: boolean;
  verifyAction: "create_new" | "map_to_existing";
  verifiedName: string;
  description: string;
  selectedSourceId: string;
  citationExpanded: boolean;
  searchQuery: string;
  pendingActionType: "verify" | "reject" | null;
}

type RefineryAction =
  | { type: "SET_CANDIDATES"; candidates: KnowledgeCandidate[] }
  | { type: "SET_VERIFIED_SOURCES"; sources: VerifiedSource[] }
  | { type: "SET_EXPERTS"; experts: Expert[] }
  | { type: "SET_STATS"; stats: KnowledgeStats }
  | { type: "SET_LOADING"; loading: boolean }
  | { type: "SET_ERROR"; error: string | null }
  | { type: "SET_VIEW"; view: RefineryView }
  | { type: "SET_ANIMATION"; animation: CardAnimation }
  | { type: "START_VERIFY" }
  | { type: "START_REJECT" }
  | { type: "ADVANCE_CARD" }
  | { type: "NEXT_CARD" }
  | { type: "PREV_CARD" }
  | { type: "ENTER_EDIT" }
  | { type: "CANCEL_EDIT" }
  | { type: "SET_EDITED_LOGIC"; text: string }
  | { type: "SET_PROCESSING"; processing: boolean }
  | { type: "OPEN_VERIFY_MODAL" }
  | { type: "CLOSE_VERIFY_MODAL" }
  | { type: "SET_VERIFY_ACTION"; action: "create_new" | "map_to_existing" }
  | { type: "SET_VERIFIED_NAME"; name: string }
  | { type: "SET_DESCRIPTION"; desc: string }
  | { type: "SET_SELECTED_SOURCE_ID"; id: string }
  | { type: "TOGGLE_CITATION" }
  | { type: "SET_SEARCH"; query: string };

const initialState: RefineryState = {
  view: "feed",
  candidates: [],
  verifiedSources: [],
  experts: [],
  stats: null,
  currentIndex: 0,
  cardAnimation: "none",
  editMode: false,
  editedLogic: "",
  loading: true,
  error: null,
  processingAction: false,
  sessionReviewed: 0,
  sessionGoal: 5,
  verifyModalOpen: false,
  verifyAction: "create_new",
  verifiedName: "",
  description: "",
  selectedSourceId: "",
  citationExpanded: false,
  searchQuery: "",
  pendingActionType: null,
};

function refineryReducer(state: RefineryState, action: RefineryAction): RefineryState {
  switch (action.type) {
    case "SET_CANDIDATES":
      return {
        ...state,
        candidates: action.candidates,
        sessionGoal: Math.max(5, Math.min(10, action.candidates.length)),
        currentIndex: state.currentIndex >= action.candidates.length ? 0 : state.currentIndex,
      };
    case "SET_VERIFIED_SOURCES":
      return { ...state, verifiedSources: action.sources };
    case "SET_EXPERTS":
      return { ...state, experts: action.experts };
    case "SET_STATS":
      return { ...state, stats: action.stats };
    case "SET_LOADING":
      return { ...state, loading: action.loading };
    case "SET_ERROR":
      return { ...state, error: action.error };
    case "SET_VIEW":
      return { ...state, view: action.view, searchQuery: "" };
    case "SET_ANIMATION":
      return { ...state, cardAnimation: action.animation };
    case "START_VERIFY":
      return { ...state, cardAnimation: "exit-right", pendingActionType: "verify" };
    case "START_REJECT":
      return { ...state, cardAnimation: "exit-left", pendingActionType: "reject" };
    case "ADVANCE_CARD": {
      const newCandidates = [...state.candidates];
      newCandidates.splice(state.currentIndex, 1);
      const newIndex = state.currentIndex >= newCandidates.length ? 0 : state.currentIndex;
      return {
        ...state,
        candidates: newCandidates,
        currentIndex: newIndex,
        cardAnimation: newCandidates.length > 0 ? "enter" : "none",
        sessionReviewed: state.sessionReviewed + 1,
        editMode: false,
        editedLogic: "",
        citationExpanded: false,
        pendingActionType: null,
      };
    }
    case "NEXT_CARD":
      if (state.candidates.length <= 1) return state;
      return {
        ...state,
        currentIndex: (state.currentIndex + 1) % state.candidates.length,
        cardAnimation: "enter",
        editMode: false,
        editedLogic: "",
        citationExpanded: false,
      };
    case "PREV_CARD":
      if (state.candidates.length <= 1) return state;
      return {
        ...state,
        currentIndex: (state.currentIndex - 1 + state.candidates.length) % state.candidates.length,
        cardAnimation: "enter",
        editMode: false,
        editedLogic: "",
        citationExpanded: false,
      };
    case "ENTER_EDIT": {
      const c = state.candidates[state.currentIndex];
      return { ...state, editMode: true, editedLogic: c?.inference_logic || "" };
    }
    case "CANCEL_EDIT":
      return { ...state, editMode: false, editedLogic: "" };
    case "SET_EDITED_LOGIC":
      return { ...state, editedLogic: action.text };
    case "SET_PROCESSING":
      return { ...state, processingAction: action.processing };
    case "OPEN_VERIFY_MODAL": {
      const c = state.candidates[state.currentIndex];
      return {
        ...state,
        verifyModalOpen: true,
        verifyAction: "create_new",
        verifiedName: c?.raw_name || "",
        description: state.editedLogic || c?.inference_logic || "",
        selectedSourceId: "",
      };
    }
    case "CLOSE_VERIFY_MODAL":
      return { ...state, verifyModalOpen: false };
    case "SET_VERIFY_ACTION":
      return { ...state, verifyAction: action.action };
    case "SET_VERIFIED_NAME":
      return { ...state, verifiedName: action.name };
    case "SET_DESCRIPTION":
      return { ...state, description: action.desc };
    case "SET_SELECTED_SOURCE_ID":
      return { ...state, selectedSourceId: action.id };
    case "TOGGLE_CITATION":
      return { ...state, citationExpanded: !state.citationExpanded };
    case "SET_SEARCH":
      return { ...state, searchQuery: action.query };
    default:
      return state;
  }
}

// ─── Helpers ─────────────────────────────────────────────────

interface LogicSegment {
  text: string;
  editable: boolean;
  type: "label" | "quote" | "data" | "text";
}

function parseInferenceLogic(logic: string): LogicSegment[] {
  const segments: LogicSegment[] = [];
  const regex = /'([^']+)'|"([^"]+)"|\(([^)]+)\)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(logic)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ text: logic.slice(lastIndex, match.index), editable: false, type: "text" });
    }
    if (match[1] || match[2]) {
      segments.push({ text: match[1] || match[2], editable: true, type: "quote" });
    } else if (match[3]) {
      segments.push({ text: match[3], editable: true, type: "data" });
    }
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < logic.length) {
    segments.push({ text: logic.slice(lastIndex), editable: false, type: "text" });
  }
  if (!segments.some((s) => s.editable)) {
    return [{ text: logic, editable: true, type: "text" }];
  }
  return segments;
}

function reassembleLogic(segments: LogicSegment[]): string {
  return segments
    .map((s) => {
      if (!s.editable) return s.text;
      if (s.type === "quote") return `'${s.text}'`;
      if (s.type === "data") return `(${s.text})`;
      return s.text;
    })
    .join("");
}

function relativeTime(dateStr: string): string {
  if (!dateStr) return "";
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHrs = Math.floor(diffMins / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  const diffDays = Math.floor(diffHrs / 24);
  if (diffDays < 30) return `${diffDays}d ago`;
  return `${Math.floor(diffDays / 30)}mo ago`;
}

function getTypeIcon(type: string) {
  switch (type) {
    case "Failure Mode": return <AlertTriangle className="w-4 h-4" />;
    case "Engineering Requirement": return <Zap className="w-4 h-4" />;
    case "Validation Check": return <Settings className="w-4 h-4" />;
    case "Physical Limit": return <BarChart3 className="w-4 h-4" />;
    case "Assembly Requirement": return <Link2 className="w-4 h-4" />;
    case "Performance Rating": return <TrendingUp className="w-4 h-4" />;
    case "Software": return <Settings className="w-4 h-4" />;
    case "Data": return <Database className="w-4 h-4" />;
    case "Manual": return <FileText className="w-4 h-4" />;
    case "Process": return <Settings className="w-4 h-4" />;
    default: return <Lightbulb className="w-4 h-4" />;
  }
}

function getTypeColor(type: string) {
  switch (type) {
    case "Failure Mode": return "bg-red-50 text-red-700 border-red-200 dark:bg-red-950 dark:text-red-300 dark:border-red-800";
    case "Engineering Requirement": return "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800";
    case "Validation Check": return "bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-950 dark:text-violet-300 dark:border-violet-800";
    case "Physical Limit": return "bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-950 dark:text-orange-300 dark:border-orange-800";
    case "Assembly Requirement": return "bg-cyan-50 text-cyan-700 border-cyan-200 dark:bg-cyan-950 dark:text-cyan-300 dark:border-cyan-800";
    case "Performance Rating": return "bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-950 dark:text-indigo-300 dark:border-indigo-800";
    case "Software": return "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950 dark:text-blue-300 dark:border-blue-800";
    case "Data": return "bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-950 dark:text-purple-300 dark:border-purple-800";
    case "Manual": return "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800";
    case "Process": return "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:border-emerald-800";
    default: return "bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700";
  }
}

function isGraphRule(id: string): boolean {
  // Graph rule IDs are property-based strings like "GATE_ATEX_ZONE" or "DEP_KITCHEN_CARBON"
  // Neo4j elementIds contain colons like "4:abc:123"
  return !id.includes(":");
}

function getReviewedRuleIds(): string[] {
  try {
    return JSON.parse(localStorage.getItem("reviewed_rules") || "[]");
  } catch {
    return [];
  }
}

function markRuleReviewed(id: string) {
  const reviewed = getReviewedRuleIds();
  if (!reviewed.includes(id)) {
    reviewed.push(id);
    localStorage.setItem("reviewed_rules", JSON.stringify(reviewed));
  }
}

const ANIMATION_CLASS: Record<CardAnimation, string> = {
  none: "",
  "exit-left": "animate-card-exit-left",
  "exit-right": "animate-card-exit-right",
  "exit-up": "animate-card-exit-up",
  enter: "animate-card-enter",
};

// ─── Subcomponents ───────────────────────────────────────────

function ProgressTracker({
  reviewed,
  goal,
  stats,
}: {
  reviewed: number;
  goal: number;
  stats: KnowledgeStats | null;
}) {
  const pct = Math.min(100, Math.round((reviewed / goal) * 100));
  const goalReached = reviewed >= goal;

  return (
    <div className="px-6 py-5">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-lg shadow-violet-500/20">
          <Sparkles className="w-5 h-5 text-white" />
        </div>
        <div>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            {stats && stats.pending > 0 ? (
              <>You have <strong className="text-slate-900 dark:text-slate-100">{stats.pending}</strong> discoveries awaiting review</>
            ) : (
              "No pending discoveries right now"
            )}
          </p>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
            {goalReached ? (
              <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> Session goal reached!
              </span>
            ) : (
              `Today's progress`
            )}
          </span>
          <span className={cn("text-xs font-bold", goalReached ? "text-emerald-600 dark:text-emerald-400" : "text-violet-600 dark:text-violet-400")}>
            {reviewed}/{goal}
          </span>
        </div>
        <div className="h-2 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-700 ease-out",
              goalReached
                ? "bg-gradient-to-r from-emerald-400 to-emerald-500"
                : "bg-gradient-to-r from-violet-500 to-purple-500"
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-3 gap-3">
          <div className="p-2.5 rounded-lg bg-amber-50 dark:bg-amber-950 border border-amber-100 dark:border-amber-800 text-center">
            <span className="text-lg font-bold text-amber-700 dark:text-amber-300">{stats.pending}</span>
            <p className="text-[10px] text-amber-600 dark:text-amber-400 font-medium">Pending</p>
          </div>
          <div className="p-2.5 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-100 dark:border-emerald-800 text-center">
            <span className="text-lg font-bold text-emerald-700 dark:text-emerald-300">{stats.total_sources}</span>
            <p className="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium">Verified</p>
          </div>
          <div className="p-2.5 rounded-lg bg-violet-50 dark:bg-violet-950 border border-violet-100 dark:border-violet-800 text-center">
            <span className="text-lg font-bold text-violet-700 dark:text-violet-300">
              {stats.total_sources + stats.pending > 0
                ? Math.round((stats.total_sources / (stats.total_sources + stats.pending)) * 100)
                : 0}%
            </span>
            <p className="text-[10px] text-violet-600 dark:text-violet-400 font-medium">Coverage</p>
          </div>
        </div>
      )}
    </div>
  );
}

function MadLibsEditor({
  logic,
  editMode,
  onChangeLogic,
}: {
  logic: string;
  editMode: boolean;
  onChangeLogic: (text: string) => void;
}) {
  const segments = parseInferenceLogic(logic);
  const [localSegments, setLocalSegments] = useState(segments);

  useEffect(() => {
    setLocalSegments(parseInferenceLogic(logic));
  }, [logic]);

  // Fallback: single textarea if nothing is parseable as inline editable
  const hasSingleFallback = localSegments.length === 1 && localSegments[0].type === "text" && localSegments[0].editable;

  if (editMode && hasSingleFallback) {
    return (
      <textarea
        value={localSegments[0].text}
        onChange={(e) => {
          const updated = [{ ...localSegments[0], text: e.target.value }];
          setLocalSegments(updated);
          onChangeLogic(reassembleLogic(updated));
        }}
        rows={3}
        className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800 border border-violet-300 dark:border-violet-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500 resize-none leading-relaxed dark:text-slate-200"
      />
    );
  }

  return (
    <div className="text-sm leading-relaxed text-slate-700 dark:text-slate-300">
      {localSegments.map((seg, i) => {
        if (!seg.editable) {
          return <span key={i}>{seg.text}</span>;
        }

        if (editMode) {
          return (
            <InlineInput
              key={i}
              value={seg.text}
              onChange={(val) => {
                const updated = [...localSegments];
                updated[i] = { ...seg, text: val };
                setLocalSegments(updated);
                onChangeLogic(reassembleLogic(updated));
              }}
            />
          );
        }

        return (
          <span
            key={i}
            className={cn(
              "px-1 py-0.5 rounded font-medium",
              seg.type === "quote"
                ? "bg-violet-100 text-violet-800 dark:bg-violet-900 dark:text-violet-300"
                : "bg-blue-50 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
            )}
          >
            {seg.type === "quote" ? `'${seg.text}'` : `(${seg.text})`}
          </span>
        );
      })}
    </div>
  );
}

function InlineInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const spanRef = useRef<HTMLSpanElement>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    if (spanRef.current) {
      setWidth(spanRef.current.scrollWidth + 12);
    }
  }, [value]);

  return (
    <span className="relative inline-block">
      <span
        ref={spanRef}
        className="invisible absolute whitespace-pre text-sm font-medium"
        aria-hidden
      >
        {value || " "}
      </span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="border-b-2 border-violet-500 bg-violet-50 dark:bg-violet-900 outline-none text-violet-900 dark:text-violet-200 font-medium text-sm px-1 py-0.5 rounded-t"
        style={{ width: Math.max(40, width) }}
      />
    </span>
  );
}

function ImpactBadge({ candidate }: { candidate: KnowledgeCandidate }) {
  const projects = (candidate.projects || []).filter(Boolean);
  const eventCount = (candidate.events || []).length;

  return (
    <div className="flex items-center flex-wrap gap-3 text-xs text-slate-400 dark:text-slate-500">
      {projects.length > 0 && (
        <span className="flex items-center gap-1">
          <ExternalLink className="w-3 h-3" />
          {projects.length > 1 ? `Found in ${projects.length} projects` : projects[0]}
        </span>
      )}
      {eventCount > 0 && (
        <span className="flex items-center gap-1">
          <Activity className="w-3 h-3" />
          {eventCount} related event{eventCount !== 1 ? "s" : ""}
        </span>
      )}
      {candidate.created_at && (
        <span className="flex items-center gap-1">
          <Clock className="w-3 h-3" />
          {relativeTime(candidate.created_at)}
        </span>
      )}
      {projects.length > 1 && (
        <span className="flex items-center gap-1 text-violet-500 dark:text-violet-400 font-medium">
          <TrendingUp className="w-3 h-3" />
          Cross-project pattern
        </span>
      )}
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────

export function KnowledgeRefinery() {
  const [state, dispatch] = useReducer(refineryReducer, initialState);

  // ── Data fetching ──

  const fetchCandidates = useCallback(async () => {
    try {
      const response = await fetch(apiUrl("/knowledge/candidates?status=pending"), authFetch());
      if (!response.ok) throw new Error("Failed to fetch candidates");
      const data = await response.json();
      // Filter out graph rules that the user already reviewed (stored in localStorage)
      const reviewedIds = getReviewedRuleIds();
      const candidates = (data.candidates || []).filter(
        (c: KnowledgeCandidate) => !isGraphRule(c.id) || !reviewedIds.includes(c.id)
      );
      dispatch({ type: "SET_CANDIDATES", candidates });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: err instanceof Error ? err.message : "Failed to load" });
    }
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const response = await fetch(apiUrl("/knowledge/stats"), authFetch());
      if (response.ok) {
        const data = await response.json();
        dispatch({ type: "SET_STATS", stats: data });
      }
    } catch {
      // Stats are optional
    }
  }, []);

  const fetchLibrary = useCallback(async () => {
    try {
      const response = await fetch(apiUrl("/knowledge/library"), authFetch());
      if (!response.ok) throw new Error("Failed to fetch library");
      const data = await response.json();
      dispatch({ type: "SET_VERIFIED_SOURCES", sources: data.sources || [] });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: err instanceof Error ? err.message : "Failed to load" });
    }
  }, []);

  const fetchExperts = useCallback(async () => {
    try {
      const response = await fetch(apiUrl("/knowledge/experts"), authFetch());
      if (!response.ok) throw new Error("Failed to fetch experts");
      const data = await response.json();
      dispatch({ type: "SET_EXPERTS", experts: data.experts || [] });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: err instanceof Error ? err.message : "Failed to load" });
    }
  }, []);

  useEffect(() => {
    const load = async () => {
      dispatch({ type: "SET_LOADING", loading: true });
      await Promise.all([fetchCandidates(), fetchStats(), fetchLibrary()]);
      dispatch({ type: "SET_LOADING", loading: false });
    };
    load();
  }, [fetchCandidates, fetchStats, fetchLibrary]);

  useEffect(() => {
    if (state.view === "experts" && state.experts.length === 0) {
      dispatch({ type: "SET_LOADING", loading: true });
      fetchExperts().finally(() => dispatch({ type: "SET_LOADING", loading: false }));
    }
  }, [state.view, state.experts.length, fetchExperts]);

  // ── Actions ──

  const currentCandidate = state.candidates[state.currentIndex] || null;

  const processAction = useCallback(
    async (actionType: "verify" | "reject") => {
      if (!currentCandidate) return;
      dispatch({ type: "SET_PROCESSING", processing: true });
      try {
        if (isGraphRule(currentCandidate.id)) {
          // Graph-derived rules: track review state in localStorage
          markRuleReviewed(currentCandidate.id);
        } else if (actionType === "reject") {
          // KnowledgeCandidate nodes: persist rejection via backend
          await fetch(
            apiUrl("/knowledge/verify"),
            authFetch({
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ candidate_id: currentCandidate.id, action: "reject" }),
            })
          );
        }
        // For verify, we open the modal instead
      } catch (err) {
        console.error("Action failed:", err);
      } finally {
        dispatch({ type: "SET_PROCESSING", processing: false });
      }
    },
    [currentCandidate]
  );

  const handleAnimationEnd = useCallback(() => {
    if (state.cardAnimation === "exit-left") {
      // Reject
      processAction("reject").then(() => {
        dispatch({ type: "ADVANCE_CARD" });
        fetchStats();
      });
    } else if (state.cardAnimation === "exit-right") {
      // Verify - open modal
      dispatch({ type: "SET_ANIMATION", animation: "none" });
      dispatch({ type: "OPEN_VERIFY_MODAL" });
    } else if (state.cardAnimation === "exit-up") {
      dispatch({ type: "ADVANCE_CARD" });
      fetchStats();
    } else if (state.cardAnimation === "enter") {
      dispatch({ type: "SET_ANIMATION", animation: "none" });
    }
  }, [state.cardAnimation, processAction, fetchStats]);

  const handleVerify = useCallback(() => {
    if (!currentCandidate || state.processingAction || state.cardAnimation !== "none") return;
    dispatch({ type: "START_VERIFY" });
  }, [currentCandidate, state.processingAction, state.cardAnimation]);

  const handleReject = useCallback(() => {
    if (!currentCandidate || state.processingAction || state.cardAnimation !== "none") return;
    dispatch({ type: "START_REJECT" });
  }, [currentCandidate, state.processingAction, state.cardAnimation]);

  const submitVerification = useCallback(async () => {
    if (!currentCandidate) return;
    dispatch({ type: "SET_PROCESSING", processing: true });
    try {
      if (isGraphRule(currentCandidate.id)) {
        // Graph-derived rules: just mark as reviewed in localStorage
        markRuleReviewed(currentCandidate.id);
      } else {
        // KnowledgeCandidate nodes: persist via backend
        const body: Record<string, string> = {
          candidate_id: currentCandidate.id,
          action: state.verifyAction,
        };
        if (state.verifyAction === "create_new") {
          body.verified_name = state.verifiedName;
          body.description = state.description;
        } else {
          body.existing_source_id = state.selectedSourceId;
        }

        const response = await fetch(
          apiUrl("/knowledge/verify"),
          authFetch({
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          })
        );
        if (!response.ok) throw new Error("Verification failed");
      }

      dispatch({ type: "CLOSE_VERIFY_MODAL" });
      dispatch({ type: "ADVANCE_CARD" });
      fetchStats();
      fetchLibrary();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to verify");
    } finally {
      dispatch({ type: "SET_PROCESSING", processing: false });
    }
  }, [currentCandidate, state.verifyAction, state.verifiedName, state.description, state.selectedSourceId, fetchStats, fetchLibrary]);

  // ── Keyboard shortcuts ──

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) return;
      if (state.verifyModalOpen) return;
      if (state.cardAnimation !== "none") return;
      if (state.view !== "feed") return;

      switch (e.key) {
        case "y":
        case "Y":
          e.preventDefault();
          handleVerify();
          break;
        case "Enter":
          e.preventDefault();
          handleVerify();
          break;
        case "n":
        case "N":
        case "Delete":
          e.preventDefault();
          handleReject();
          break;
        case "e":
        case "E":
          e.preventDefault();
          if (!state.editMode) dispatch({ type: "ENTER_EDIT" });
          break;
        case "Escape":
          if (state.editMode) dispatch({ type: "CANCEL_EDIT" });
          break;
        case "ArrowRight":
          e.preventDefault();
          dispatch({ type: "NEXT_CARD" });
          break;
        case "ArrowLeft":
          e.preventDefault();
          dispatch({ type: "PREV_CARD" });
          break;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [state.view, state.editMode, state.verifyModalOpen, state.cardAnimation, handleVerify, handleReject]);

  // ── Filtered data for library/experts ──

  const filteredSources = state.verifiedSources.filter(
    (s) =>
      s.name.toLowerCase().includes(state.searchQuery.toLowerCase()) ||
      (s.description && s.description.toLowerCase().includes(state.searchQuery.toLowerCase()))
  );

  const filteredExperts = state.experts.filter(
    (e) =>
      e.expert_name.toLowerCase().includes(state.searchQuery.toLowerCase()) ||
      e.top_sources.some((s) => s.source.toLowerCase().includes(state.searchQuery.toLowerCase()))
  );

  // ── Render ──

  return (
    <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl shadow-slate-200/50 dark:shadow-slate-900/50 border border-slate-200/60 dark:border-slate-700/60 overflow-hidden h-full flex flex-col">
      {/* Header */}
      <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-700 bg-gradient-to-r from-slate-50 to-white dark:from-slate-800 dark:to-slate-900">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-lg shadow-violet-500/20">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-900 dark:text-slate-100">Knowledge Refinery</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {state.view === "feed" && `${state.candidates.length} candidates in queue`}
                {state.view === "library" && `${state.verifiedSources.length} verified sources`}
                {state.view === "experts" && `${state.experts.length} subject matter experts`}
              </p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={async () => {
              dispatch({ type: "SET_LOADING", loading: true });
              if (state.view === "feed") {
                await Promise.all([fetchCandidates(), fetchStats()]);
              } else if (state.view === "library") {
                await fetchLibrary();
              } else {
                await fetchExperts();
              }
              dispatch({ type: "SET_LOADING", loading: false });
            }}
            disabled={state.loading}
            className="text-slate-500 dark:text-slate-400"
          >
            <RefreshCw className={cn("w-4 h-4", state.loading && "animate-spin")} />
          </Button>
        </div>

        {/* View Tabs */}
        <div className="flex gap-2">
          {([
            { id: "feed" as const, label: "Review Queue", icon: Sparkles },
            { id: "library" as const, label: "Knowledge Library", icon: BookOpen },
            { id: "experts" as const, label: "SME Directory", icon: Users },
          ]).map((tab) => (
            <Button
              key={tab.id}
              variant={state.view === tab.id ? "default" : "ghost"}
              size="sm"
              onClick={() => dispatch({ type: "SET_VIEW", view: tab.id })}
              className={cn(
                state.view === tab.id
                  ? "bg-violet-600 hover:bg-violet-700"
                  : "hover:bg-violet-50 dark:hover:bg-violet-900/50"
              )}
            >
              <tab.icon className="w-4 h-4 mr-2" />
              {tab.label}
            </Button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {state.loading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="w-8 h-8 animate-spin text-violet-600" />
          </div>
        ) : state.error ? (
          <div className="flex flex-col items-center justify-center h-full p-6">
            <AlertTriangle className="w-12 h-12 text-red-400 mb-4" />
            <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">{state.error}</p>
            <Button
              onClick={async () => {
                dispatch({ type: "SET_ERROR", error: null });
                dispatch({ type: "SET_LOADING", loading: true });
                await Promise.all([fetchCandidates(), fetchStats()]);
                dispatch({ type: "SET_LOADING", loading: false });
              }}
              variant="outline"
            >
              Try Again
            </Button>
          </div>
        ) : state.view === "feed" ? (
          /* ═══ Feed View ═══ */
          <div className="h-full flex flex-col">
            <ProgressTracker
              reviewed={state.sessionReviewed}
              goal={state.sessionGoal}
              stats={state.stats}
            />

            {state.candidates.length === 0 ? (
              /* Empty state */
              <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
                <CheckCircle2 className="w-16 h-16 text-emerald-400 mb-4" />
                <h4 className="font-semibold text-slate-700 dark:text-slate-300 mb-2">All caught up!</h4>
                <p className="text-sm text-slate-400 dark:text-slate-500">
                  {state.sessionReviewed > 0
                    ? `You reviewed ${state.sessionReviewed} item${state.sessionReviewed !== 1 ? "s" : ""} this session.`
                    : "No pending discoveries to review."}
                </p>
              </div>
            ) : (
              /* Card area */
              <div className="flex-1 flex items-start justify-center px-6 pb-6 overflow-auto">
                <div className="w-full max-w-2xl">
                  {/* Card counter */}
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-xs text-slate-400 dark:text-slate-500">
                      Card {state.currentIndex + 1} of {state.candidates.length}
                    </span>
                    {state.candidates.length > 1 && (
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => dispatch({ type: "PREV_CARD" })}
                          className="h-7 w-7 p-0 text-slate-400"
                          disabled={state.cardAnimation !== "none"}
                        >
                          <ChevronRight className="w-4 h-4 rotate-180" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => dispatch({ type: "NEXT_CARD" })}
                          className="h-7 w-7 p-0 text-slate-400"
                          disabled={state.cardAnimation !== "none"}
                        >
                          <ChevronRight className="w-4 h-4" />
                        </Button>
                      </div>
                    )}
                  </div>

                  {/* The Logic Card */}
                  {currentCandidate && (
                    <div
                      className={cn(
                        "rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-lg shadow-slate-200/50 dark:shadow-slate-900/50 overflow-hidden",
                        ANIMATION_CLASS[state.cardAnimation]
                      )}
                      onAnimationEnd={handleAnimationEnd}
                    >
                      {/* Card header */}
                      <div className="px-6 pt-6 pb-4">
                        <div className="flex items-start gap-3 mb-4">
                          <span
                            className={cn(
                              "flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border shrink-0",
                              getTypeColor(currentCandidate.type)
                            )}
                          >
                            {getTypeIcon(currentCandidate.type)}
                            {currentCandidate.type}
                          </span>
                          <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100 leading-tight">
                            {currentCandidate.raw_name}
                          </h3>
                        </div>

                        {/* Source pills */}
                        {currentCandidate.projects?.filter(Boolean).length > 0 && (
                          <div className="flex items-center gap-2 flex-wrap mb-4">
                            {currentCandidate.projects.filter(Boolean).map((p, i) => (
                              <span
                                key={i}
                                className="text-xs px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-600"
                              >
                                {p}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* AI interpretation */}
                      <div className="px-6 pb-4">
                        <div className="p-4 rounded-xl bg-gradient-to-br from-violet-50/80 to-purple-50/40 dark:from-violet-950/50 dark:to-purple-950/30 border border-violet-100 dark:border-violet-800">
                          <p className="text-xs font-semibold text-violet-600 dark:text-violet-400 mb-2 flex items-center gap-1.5">
                            <Sparkles className="w-3.5 h-3.5" />
                            Engineering Assessment
                            {state.editMode && (
                              <Badge variant="warning" className="ml-2 text-[10px]">Editing</Badge>
                            )}
                          </p>
                          <MadLibsEditor
                            logic={state.editMode ? state.editedLogic : currentCandidate.inference_logic}
                            editMode={state.editMode}
                            onChangeLogic={(text) => dispatch({ type: "SET_EDITED_LOGIC", text })}
                          />
                        </div>
                      </div>

                      {/* Citation */}
                      {currentCandidate.citation && (
                        <div className="px-6 pb-4">
                          <button
                            onClick={() => dispatch({ type: "TOGGLE_CITATION" })}
                            className="flex items-center gap-1.5 text-xs text-violet-600 dark:text-violet-400 hover:text-violet-800 dark:hover:text-violet-300 transition-colors"
                          >
                            {state.citationExpanded ? (
                              <ChevronDown className="w-3 h-3" />
                            ) : (
                              <ChevronRight className="w-3 h-3" />
                            )}
                            <Quote className="w-3 h-3" />
                            Source citation
                          </button>
                          {state.citationExpanded && (
                            <div className="mt-2 pl-3 py-2 border-l-4 border-violet-200 dark:border-violet-700 bg-violet-50/50 dark:bg-violet-950/30 rounded-r-lg animate-fade-in">
                              <p className="text-xs text-slate-600 dark:text-slate-400 italic leading-relaxed">
                                &ldquo;{currentCandidate.citation}&rdquo;
                              </p>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Impact */}
                      <div className="px-6 pb-4">
                        <ImpactBadge candidate={currentCandidate} />
                      </div>

                      {/* Actions */}
                      <div className="px-6 pb-5 border-t border-slate-100 dark:border-slate-700 pt-4">
                        {state.editMode ? (
                          <div className="flex gap-3">
                            <Button
                              onClick={() => {
                                dispatch({ type: "CANCEL_EDIT" });
                              }}
                              variant="outline"
                              className="flex-1"
                            >
                              <X className="w-4 h-4 mr-2" />
                              Cancel
                            </Button>
                            <Button
                              onClick={() => {
                                // Save edit then verify
                                dispatch({ type: "START_VERIFY" });
                              }}
                              className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white"
                            >
                              <CheckCircle2 className="w-4 h-4 mr-2" />
                              Save & Verify
                            </Button>
                          </div>
                        ) : (
                          <div className="flex gap-3">
                            <Button
                              onClick={handleReject}
                              variant="outline"
                              className="flex-1 text-red-600 dark:text-red-400 border-red-200 dark:border-red-800 hover:bg-red-50 dark:hover:bg-red-950 hover:border-red-300 dark:hover:border-red-700"
                              disabled={state.processingAction || state.cardAnimation !== "none"}
                            >
                              <XCircle className="w-4 h-4 mr-2" />
                              Reject
                            </Button>
                            <Button
                              onClick={() => dispatch({ type: "ENTER_EDIT" })}
                              variant="outline"
                              className="flex-1 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-700/50"
                              disabled={state.processingAction || state.cardAnimation !== "none"}
                            >
                              <Pencil className="w-4 h-4 mr-2" />
                              Edit
                            </Button>
                            <Button
                              onClick={handleVerify}
                              className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white"
                              disabled={state.processingAction || state.cardAnimation !== "none"}
                            >
                              <CheckCircle2 className="w-4 h-4 mr-2" />
                              Verify
                            </Button>
                          </div>
                        )}

                        {/* Keyboard hints */}
                        {!state.editMode && (
                          <div className="flex items-center justify-center gap-4 text-[10px] text-slate-400 dark:text-slate-500 mt-3">
                            <span><kbd className="px-1.5 py-0.5 bg-slate-100 dark:bg-slate-700 rounded font-mono">Y</kbd> Verify</span>
                            <span><kbd className="px-1.5 py-0.5 bg-slate-100 dark:bg-slate-700 rounded font-mono">E</kbd> Edit</span>
                            <span><kbd className="px-1.5 py-0.5 bg-slate-100 dark:bg-slate-700 rounded font-mono">N</kbd> Reject</span>
                            <span><kbd className="px-1.5 py-0.5 bg-slate-100 dark:bg-slate-700 rounded font-mono">&larr;&rarr;</kbd> Nav</span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : state.view === "library" ? (
          /* ═══ Library View ═══ */
          <div className="h-full flex flex-col">
            {/* Search */}
            <div className="p-4 border-b border-slate-100 dark:border-slate-700">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 dark:text-slate-500" />
                <input
                  type="text"
                  value={state.searchQuery}
                  onChange={(e) => dispatch({ type: "SET_SEARCH", query: e.target.value })}
                  placeholder="Search verified sources..."
                  className="w-full pl-10 pr-4 py-2 text-sm bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500 dark:text-slate-200 dark:placeholder-slate-500"
                />
              </div>
            </div>

            {filteredSources.length === 0 ? (
              <div className="flex flex-col items-center justify-center flex-1 p-6 text-center">
                <BookOpen className="w-16 h-16 text-slate-300 dark:text-slate-600 mb-4" />
                <h4 className="font-medium text-slate-600 dark:text-slate-400 mb-2">Library is empty</h4>
                <p className="text-sm text-slate-400 dark:text-slate-500">
                  {state.searchQuery ? "No sources match your search" : "Verify discoveries to build your knowledge library"}
                </p>
              </div>
            ) : (
              <ScrollArea className="flex-1">
                <div className="p-4 space-y-3">
                  {filteredSources.map((source) => (
                    <div
                      key={source.id}
                      className="p-4 rounded-xl border border-slate-200 bg-white hover:border-violet-300 transition-all"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-2">
                            <span className={cn("flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium border", getTypeColor(source.type))}>
                              {getTypeIcon(source.type)}
                              {source.type}
                            </span>
                            <h4 className="font-semibold text-slate-900">{source.name}</h4>
                          </div>
                          {source.description && (
                            <p className="text-sm text-slate-600 mb-2">{source.description}</p>
                          )}
                          {source.aliases?.length > 0 && (
                            <div className="flex items-center gap-2 flex-wrap mb-2">
                              <Link2 className="w-3 h-3 text-slate-400" />
                              {source.aliases.map((alias, i) => (
                                <span key={i} className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                                  {alias}
                                </span>
                              ))}
                            </div>
                          )}
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
            )}
          </div>
        ) : (
          /* ═══ Experts View ═══ */
          <div className="h-full flex flex-col">
            <div className="p-4 border-b border-slate-100">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="text"
                  value={state.searchQuery}
                  onChange={(e) => dispatch({ type: "SET_SEARCH", query: e.target.value })}
                  placeholder="Search experts..."
                  className="w-full pl-10 pr-4 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500"
                />
              </div>
            </div>

            {filteredExperts.length === 0 ? (
              <div className="flex flex-col items-center justify-center flex-1 p-6 text-center">
                <Users className="w-16 h-16 text-slate-300 mb-4" />
                <h4 className="font-medium text-slate-600 mb-2">No expert data yet</h4>
                <p className="text-sm text-slate-400">
                  {state.searchQuery ? "No experts match your search" : "Verify knowledge discoveries to build the SME directory"}
                </p>
              </div>
            ) : (
              <ScrollArea className="flex-1">
                <div className="p-4 space-y-3">
                  {filteredExperts.map((expert) => (
                    <div
                      key={expert.expert_name}
                      className="p-4 rounded-xl border border-slate-200 bg-white hover:border-violet-300 transition-all"
                    >
                      <div className="flex items-start gap-4">
                        <div className="w-12 h-12 rounded-full bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center text-white font-bold text-lg shadow-lg">
                          {expert.expert_name.charAt(0).toUpperCase()}
                        </div>
                        <div className="flex-1 min-w-0">
                          <h4 className="font-semibold text-slate-900">{expert.expert_name}</h4>
                          {expert.expert_email && (
                            <p className="text-xs text-slate-400">{expert.expert_email}</p>
                          )}
                          <div className="flex items-center gap-1 text-xs text-violet-600 mt-1">
                            <BookOpen className="w-3 h-3" />
                            Expert in {expert.source_count} verified source{expert.source_count !== 1 ? "s" : ""}
                          </div>
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
            )}
          </div>
        )}
      </div>

      {/* ═══ Verify Modal ═══ */}
      {state.verifyModalOpen && currentCandidate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden animate-fade-in">
            <div className="p-6 border-b border-slate-100">
              <h3 className="font-semibold text-lg text-slate-900">Verify Discovery</h3>
              <p className="text-sm text-slate-500 mt-1">
                Verifying: <strong>{currentCandidate.raw_name}</strong>
              </p>
            </div>

            <div className="p-6 space-y-4">
              <div className="flex gap-2">
                <Button
                  variant={state.verifyAction === "create_new" ? "default" : "outline"}
                  size="sm"
                  onClick={() => dispatch({ type: "SET_VERIFY_ACTION", action: "create_new" })}
                  className={cn(state.verifyAction === "create_new" && "bg-violet-600 hover:bg-violet-700")}
                >
                  <CheckCircle2 className="w-4 h-4 mr-2" />
                  Create New
                </Button>
                <Button
                  variant={state.verifyAction === "map_to_existing" ? "default" : "outline"}
                  size="sm"
                  onClick={() => dispatch({ type: "SET_VERIFY_ACTION", action: "map_to_existing" })}
                  className={cn(state.verifyAction === "map_to_existing" && "bg-violet-600 hover:bg-violet-700")}
                >
                  <Link2 className="w-4 h-4 mr-2" />
                  Map to Existing
                </Button>
              </div>

              {state.verifyAction === "create_new" ? (
                <>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Canonical Name</label>
                    <input
                      type="text"
                      value={state.verifiedName}
                      onChange={(e) => dispatch({ type: "SET_VERIFIED_NAME", name: e.target.value })}
                      className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500"
                      placeholder="e.g., HABE Calculation Tool"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Description</label>
                    <textarea
                      value={state.description}
                      onChange={(e) => dispatch({ type: "SET_DESCRIPTION", desc: e.target.value })}
                      rows={3}
                      className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500 resize-none"
                      placeholder="What is this tool/data source used for?"
                    />
                  </div>
                </>
              ) : (
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Select Existing Source</label>
                  <select
                    value={state.selectedSourceId}
                    onChange={(e) => dispatch({ type: "SET_SELECTED_SOURCE_ID", id: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500"
                  >
                    <option value="">-- Select a source --</option>
                    {state.verifiedSources.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name} ({s.type})
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-slate-400 mt-2">
                    This will create an alias: &ldquo;{currentCandidate.raw_name}&rdquo; &rarr; selected source
                  </p>
                </div>
              )}
            </div>

            <div className="p-6 border-t border-slate-100 flex gap-3 justify-end">
              <Button
                variant="outline"
                onClick={() => dispatch({ type: "CLOSE_VERIFY_MODAL" })}
              >
                Cancel
              </Button>
              <Button
                onClick={submitVerification}
                disabled={
                  state.processingAction ||
                  (state.verifyAction === "create_new" && !state.verifiedName) ||
                  (state.verifyAction === "map_to_existing" && !state.selectedSourceId)
                }
                className="bg-emerald-600 hover:bg-emerald-700 text-white"
              >
                {state.processingAction ? (
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
