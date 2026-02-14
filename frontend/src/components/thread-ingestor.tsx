"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Loader2,
  CheckCircle2,
  AlertCircle,
  Mail,
  Users,
  Send,
  Trash2,
  FileJson,
  Copy,
  Check,
  X,
  ArrowRight,
  Zap,
  Eye,
  GitBranch,
  Quote,
  ChevronDown,
  ChevronRight,
  FileText,
  Lightbulb,
  Database,
  Settings,
  BookOpen,
  Link2,
  XCircle,
} from "lucide-react";
import {
  LogicRuleCard,
  ImpactSimulator,
  ExpertAttribution,
  buildInsightFromExtraction,
} from "./ingestion-report";
import { cn } from "@/lib/utils";
import { apiUrl, authFetch } from "@/lib/api";

interface TimelineEvent {
  step: number;
  sender: string;
  sender_email?: string;
  date: string;
  time?: string;
  summary: string;
  logic_type: string | null;
  logic_description?: string;
  citation?: string;
}

interface KnowledgeCandidate {
  id: string;
  raw_name: string;
  type: string;
  inference_logic: string;
  citation?: string;
  status: string;
}

interface IngestResult {
  message: string;
  counts: {
    project: string;
    persons: number;
    events: number;
    concepts: number;
    observations: number;
    actions: number;
    relationships: number;
    knowledge_candidates?: number;
  };
  extracted: {
    project: string;
    timeline: TimelineEvent[];
    concepts: string[];
    causality: [number, string, number][];
    knowledge_candidates?: KnowledgeCandidate[];
  };
}

type UploadState = "idle" | "uploading" | "success" | "error";

interface GraphData {
  nodes: Array<{
    id: string;
    label: string;
    name: string;
    properties: Record<string, unknown>;
  }>;
  relationships: Array<{
    id: string;
    type: string;
    source: string;
    target: string;
    properties: Record<string, unknown>;
  }>;
}

interface SampleCase {
  name: string;
  text: string;
}

interface ThreadIngestorProps {
  devMode?: boolean;
  sampleCases?: Record<string, SampleCase>;
  pendingSampleText?: string | null;
  onSampleTextConsumed?: () => void;
}

export function ThreadIngestor({ devMode, sampleCases, pendingSampleText, onSampleTextConsumed }: ThreadIngestorProps) {
  const [threadText, setThreadText] = useState("");
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [result, setResult] = useState<IngestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);
  const [showExport, setShowExport] = useState(false);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [loadingGraph, setLoadingGraph] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showAuditLog, setShowAuditLog] = useState(false);
  const [showDiscoveries, setShowDiscoveries] = useState(true);
  const [processingCandidate, setProcessingCandidate] = useState<string | null>(null);
  const [expandedCandidate, setExpandedCandidate] = useState<string | null>(null);
  const [verifiedSources, setVerifiedSources] = useState<Array<{id: string; name: string; type: string}>>([]);
  const [showMapModal, setShowMapModal] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState<KnowledgeCandidate | null>(null);
  const [mapAction, setMapAction] = useState<"create_new" | "map_to_existing">("create_new");
  const [verifiedName, setVerifiedName] = useState("");
  const [description, setDescription] = useState("");
  const [selectedSourceId, setSelectedSourceId] = useState("");

  // Handle external sample text injection (from dev mode)
  useEffect(() => {
    if (pendingSampleText && pendingSampleText.trim()) {
      setThreadText(pendingSampleText);
      onSampleTextConsumed?.();
    }
  }, [pendingSampleText, onSampleTextConsumed]);

  const fetchGraphData = async () => {
    setLoadingGraph(true);
    try {
      const response = await fetch(apiUrl("/graph/data"), authFetch());
      if (!response.ok) throw new Error("Failed to fetch graph");
      const data = await response.json();
      setGraphData(data);
      setShowExport(true);
    } catch (err) {
      alert("Failed to fetch graph data");
    } finally {
      setLoadingGraph(false);
    }
  };

  const formatGraphAsText = (data: GraphData): string => {
    const lines: string[] = [];
    lines.push("// ==========================================");
    lines.push("// GRAPH EXPORT");
    lines.push(`// Nodes: ${data.nodes.length}`);
    lines.push(`// Relationships: ${data.relationships.length}`);
    lines.push("// ==========================================\n");

    const nodesByLabel: Record<string, typeof data.nodes> = {};
    data.nodes.forEach((node) => {
      if (!nodesByLabel[node.label]) nodesByLabel[node.label] = [];
      nodesByLabel[node.label].push(node);
    });

    lines.push("// NODES\n");
    Object.entries(nodesByLabel).forEach(([label, nodes]) => {
      lines.push(`// --- ${label} (${nodes.length}) ---`);
      nodes.forEach((node) => {
        const props = { ...node.properties };
        delete props.embedding;
        const propsStr = Object.entries(props)
          .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
          .join(", ");
        lines.push(`(:${label} {${propsStr}})`);
      });
      lines.push("");
    });

    lines.push("// RELATIONSHIPS\n");
    const relsByType: Record<string, typeof data.relationships> = {};
    data.relationships.forEach((rel) => {
      if (!relsByType[rel.type]) relsByType[rel.type] = [];
      relsByType[rel.type].push(rel);
    });

    const nodeNames: Record<string, string> = {};
    data.nodes.forEach((node) => {
      nodeNames[node.id] = node.name || node.id;
    });

    Object.entries(relsByType).forEach(([type, rels]) => {
      lines.push(`// --- ${type} (${rels.length}) ---`);
      rels.forEach((rel) => {
        const sourceName = nodeNames[rel.source] || rel.source;
        const targetName = nodeNames[rel.target] || rel.target;
        lines.push(`(${sourceName})-[:${type}]->(${targetName})`);
      });
      lines.push("");
    });

    return lines.join("\n");
  };

  const copyToClipboard = async () => {
    if (!graphData) return;
    const text = formatGraphAsText(graphData);
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const clearGraph = async () => {
    if (!confirm("Are you sure you want to clear all graph data?")) return;
    setClearing(true);
    try {
      const response = await fetch(apiUrl("/graph/clear"), authFetch({
        method: "DELETE",
      }));
      if (!response.ok) throw new Error("Failed to clear graph");
      alert("Graph cleared successfully");
    } catch (err) {
      alert("Failed to clear graph");
    } finally {
      setClearing(false);
    }
  };

  const handleSubmit = async () => {
    if (!threadText.trim()) return;
    setUploadState("uploading");
    setError(null);

    try {
      const response = await fetch(apiUrl("/ingest/thread/text"), authFetch({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: threadText }),
      }));

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to process thread");
      }

      const data: IngestResult = await response.json();
      setResult(data);
      setUploadState("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Processing failed");
      setUploadState("error");
    }
  };

  const reset = () => {
    setThreadText("");
    setUploadState("idle");
    setResult(null);
    setError(null);
  };

  // Fetch verified sources for mapping dropdown
  const fetchVerifiedSources = async () => {
    try {
      const response = await fetch(apiUrl("/knowledge/library"), authFetch());
      if (response.ok) {
        const data = await response.json();
        setVerifiedSources(data.sources || []);
      }
    } catch {
      // Silently fail - sources just won't be available for mapping
    }
  };

  // Reject a candidate (dismiss)
  const rejectCandidate = async (candidateId: string) => {
    setProcessingCandidate(candidateId);
    try {
      const response = await fetch(apiUrl("/knowledge/verify"), authFetch({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          candidate_id: candidateId,
          action: "reject",
        }),
      }));
      if (!response.ok) throw new Error("Failed to reject");
      // Update local state to remove the candidate
      if (result?.extracted.knowledge_candidates) {
        const updated = result.extracted.knowledge_candidates.filter(c => c.id !== candidateId);
        setResult({
          ...result,
          extracted: { ...result.extracted, knowledge_candidates: updated }
        });
      }
    } catch {
      alert("Failed to dismiss discovery");
    } finally {
      setProcessingCandidate(null);
    }
  };

  // Open verification modal
  const openMapModal = async (candidate: KnowledgeCandidate) => {
    setSelectedCandidate(candidate);
    setVerifiedName(candidate.raw_name);
    setDescription(candidate.inference_logic);
    setMapAction("create_new");
    setSelectedSourceId("");
    await fetchVerifiedSources();
    setShowMapModal(true);
  };

  // Submit verification
  const submitVerification = async () => {
    if (!selectedCandidate) return;
    setProcessingCandidate(selectedCandidate.id);
    try {
      const body: Record<string, string> = {
        candidate_id: selectedCandidate.id,
        action: mapAction,
      };
      if (mapAction === "create_new") {
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
      if (!response.ok) throw new Error("Failed to verify");
      // Update local state
      if (result?.extracted.knowledge_candidates) {
        const updated = result.extracted.knowledge_candidates.filter(c => c.id !== selectedCandidate.id);
        setResult({
          ...result,
          extracted: { ...result.extracted, knowledge_candidates: updated }
        });
      }
      setShowMapModal(false);
      setSelectedCandidate(null);
    } catch {
      alert("Failed to verify discovery");
    } finally {
      setProcessingCandidate(null);
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case "Software": return <Settings className="w-3.5 h-3.5" />;
      case "Data": return <Database className="w-3.5 h-3.5" />;
      case "Manual": return <BookOpen className="w-3.5 h-3.5" />;
      case "Process": return <Settings className="w-3.5 h-3.5" />;
      default: return <Lightbulb className="w-3.5 h-3.5" />;
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case "Software": return "bg-blue-50 text-blue-700 border-blue-200";
      case "Data": return "bg-purple-50 text-purple-700 border-purple-200";
      case "Manual": return "bg-amber-50 text-amber-700 border-amber-200";
      case "Process": return "bg-emerald-50 text-emerald-700 border-emerald-200";
      default: return "bg-slate-50 text-slate-600 border-slate-200";
    }
  };

  const getLogicTypeStyle = (type: string | null) => {
    switch (type) {
      case "Symptom":
        return "bg-red-50 text-red-700 border-red-200";
      case "Constraint":
        return "bg-amber-50 text-amber-700 border-amber-200";
      case "Blocker":
        return "bg-orange-50 text-orange-700 border-orange-200";
      case "Standard":
        return "bg-blue-50 text-blue-700 border-blue-200";
      case "Workaround":
        return "bg-emerald-50 text-emerald-700 border-emerald-200";
      case "ProductMapping":
        return "bg-indigo-50 text-indigo-700 border-indigo-200";
      case "Commercial":
        return "bg-green-50 text-green-700 border-green-200";
      default:
        return "bg-slate-50 text-slate-600 border-slate-200";
    }
  };

  return (
    <div className="bg-white rounded-2xl shadow-xl shadow-slate-200/50 border border-slate-200/60 overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-gradient-to-r from-slate-50 to-white">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-lg shadow-violet-500/20">
            <Mail className="w-5 h-5 text-white" />
          </div>
          <div>
            <h3 className="font-semibold text-slate-900">Data Ingestion</h3>
            <p className="text-xs text-slate-500">
              Process email threads into knowledge
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={fetchGraphData}
            disabled={loadingGraph}
            className="text-slate-500 hover:text-slate-700"
          >
            {loadingGraph ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <FileJson className="h-4 w-4" />
            )}
            <span className="ml-1.5 text-xs">Export</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={clearGraph}
            disabled={clearing}
            className="text-red-500 hover:text-red-700 hover:bg-red-50"
          >
            {clearing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>

      <div className="p-6">
        {/* Export View */}
        {showExport && graphData && (
          <div className="space-y-4 animate-fade-in">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <GitBranch className="w-4 h-4 text-violet-600" />
                <span className="text-sm font-medium text-slate-700">
                  Graph Export
                </span>
                <span className="text-xs text-slate-400">
                  {graphData.nodes.length} nodes, {graphData.relationships.length} relationships
                </span>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={copyToClipboard}
                  className="h-8"
                >
                  {copied ? (
                    <Check className="h-4 w-4 text-emerald-600" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowExport(false)}
                  className="h-8"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <ScrollArea className="h-80 rounded-xl border border-slate-200 bg-slate-900">
              <pre className="p-4 text-xs font-mono text-slate-300 whitespace-pre">
                {formatGraphAsText(graphData)}
              </pre>
            </ScrollArea>
          </div>
        )}

        {/* Input Area */}
        {uploadState === "idle" && !showExport && (
          <div className="space-y-4 animate-fade-in">
            {/* Dev Mode: Sample Cases */}
            {devMode && sampleCases && (
              <div className="flex items-center gap-2 p-3 rounded-xl bg-amber-50 border border-amber-200">
                <span className="text-xs font-medium text-amber-700">Load sample:</span>
                {Object.entries(sampleCases).map(([key, sample]) => (
                  <button
                    key={key}
                    onClick={() => setThreadText(sample.text)}
                    className="px-3 py-1.5 text-xs font-medium rounded-lg bg-white border border-amber-300 text-amber-700 hover:bg-amber-100 transition-colors"
                  >
                    {sample.name}
                  </button>
                ))}
              </div>
            )}
            <div className="relative">
              <textarea
                value={threadText}
                onChange={(e) => setThreadText(e.target.value)}
                placeholder="Paste the full email thread here...

Example:
From: John Smith
Date: 2024-09-05
Subject: CAD File Issue

I'm sending the CAD file...

---
From: Jane Doe
Date: 2024-09-06

The file is a dummy solid..."
                className="w-full h-64 p-4 text-sm bg-slate-50 border border-slate-200 rounded-xl resize-none focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500 focus:bg-white placeholder:text-slate-400"
              />
            </div>
            <Button
              onClick={handleSubmit}
              disabled={!threadText.trim()}
              className="w-full h-12 bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-700 hover:to-purple-700 shadow-lg shadow-violet-500/25 rounded-xl text-sm font-medium"
            >
              <Zap className="w-4 h-4 mr-2" />
              Analyze Thread
            </Button>
          </div>
        )}

        {/* Error */}
        {error && !showExport && (
          <div className="animate-fade-in">
            <div className="flex items-start gap-3 p-4 rounded-xl bg-red-50 border border-red-200">
              <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-medium text-red-800">
                  Processing Failed
                </p>
                <p className="text-sm text-red-600 mt-1">{error}</p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={reset}
                className="text-red-600 hover:text-red-800 hover:bg-red-100"
              >
                Try Again
              </Button>
            </div>
          </div>
        )}

        {/* Loading */}
        {uploadState === "uploading" && !showExport && (
          <div className="text-center py-16 animate-fade-in">
            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-violet-100 to-purple-100 flex items-center justify-center">
              <Loader2 className="w-8 h-8 animate-spin text-violet-600" />
            </div>
            <h3 className="font-semibold text-slate-900 mb-2">
              Analyzing Thread
            </h3>
            <p className="text-sm text-slate-500">
              Extracting decision chains with AI...
            </p>
          </div>
        )}

        {/* Success - Crystallized Knowledge View */}
        {uploadState === "success" && result && !showExport && (() => {
          // Build insight from actual extraction data
          const insight = buildInsightFromExtraction(result.extracted);

          return (
          <div className="space-y-6 animate-fade-in">
            {/* Success Banner */}
            <div className="flex items-center justify-between p-4 rounded-xl bg-emerald-50 border border-emerald-200">
              <div className="flex items-center gap-3">
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                <div>
                  <span className="text-sm font-medium text-emerald-800 block">
                    Knowledge Successfully Extracted
                  </span>
                  <span className="text-xs text-emerald-600">
                    {result.extracted.project}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2 text-xs text-emerald-600">
                <Mail className="w-3.5 h-3.5" />
                <span>{result.counts.events} emails processed</span>
              </div>
            </div>

            {/* HERO: Logic Rule Card - from actual extraction */}
            {insight && <LogicRuleCard rule={insight.playbook_rule} />}

            {/* Discovery Review - Forensic Knowledge Candidates */}
            {result.extracted.knowledge_candidates && result.extracted.knowledge_candidates.length > 0 && (
              <div className="border border-violet-200 rounded-xl overflow-hidden bg-violet-50/30">
                <button
                  onClick={() => setShowDiscoveries(!showDiscoveries)}
                  className="w-full px-4 py-3 flex items-center justify-between bg-gradient-to-r from-violet-100 to-purple-100 hover:from-violet-150 hover:to-purple-150 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <Lightbulb className="w-4 h-4 text-violet-600" />
                    <span className="text-sm font-semibold text-violet-800">
                      Discovered Knowledge Sources
                    </span>
                    <span className="px-2 py-0.5 rounded-full bg-violet-200 text-violet-700 text-xs font-medium">
                      {result.extracted.knowledge_candidates.length} found
                    </span>
                  </div>
                  <ChevronDown
                    className={cn(
                      "w-4 h-4 text-violet-500 transition-transform",
                      showDiscoveries && "rotate-180"
                    )}
                  />
                </button>

                {showDiscoveries && (
                  <div className="p-4 space-y-3">
                    <p className="text-xs text-violet-600 mb-3">
                      The AI detected these tools, data sources, or processes. Verify to add them to your Knowledge Library.
                    </p>
                    {result.extracted.knowledge_candidates.map((candidate) => (
                      <div
                        key={candidate.id}
                        className="p-4 rounded-xl bg-white border border-violet-100 shadow-sm"
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
                              <h4 className="font-semibold text-slate-900">
                                {candidate.raw_name}
                              </h4>
                            </div>

                            {/* Inference Logic */}
                            <div className="mb-3 p-2 bg-amber-50 rounded-lg border border-amber-100">
                              <p className="text-xs font-medium text-amber-700 mb-1">
                                Why I suggested this:
                              </p>
                              <p className="text-sm text-amber-900">{candidate.inference_logic}</p>
                            </div>

                            {/* Citation - Expandable */}
                            {candidate.citation && (
                              <div
                                className="cursor-pointer"
                                onClick={() =>
                                  setExpandedCandidate(
                                    expandedCandidate === candidate.id ? null : candidate.id
                                  )
                                }
                              >
                                <div className="flex items-center gap-1 text-xs text-violet-600 hover:text-violet-800">
                                  {expandedCandidate === candidate.id ? (
                                    <ChevronDown className="w-3 h-3" />
                                  ) : (
                                    <ChevronRight className="w-3 h-3" />
                                  )}
                                  <Quote className="w-3 h-3" />
                                  View source citation
                                </div>
                                {expandedCandidate === candidate.id && (
                                  <div className="mt-2 pl-3 py-2 border-l-4 border-violet-200 bg-violet-50 rounded-r-lg">
                                    <p className="text-xs text-slate-600 italic">
                                      &ldquo;{candidate.citation}&rdquo;
                                    </p>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>

                          {/* Actions */}
                          <div className="flex flex-col gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => openMapModal(candidate)}
                              disabled={processingCandidate === candidate.id}
                              className="text-emerald-600 border-emerald-200 hover:bg-emerald-50"
                            >
                              {processingCandidate === candidate.id ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                              ) : (
                                <CheckCircle2 className="w-4 h-4" />
                              )}
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => rejectCandidate(candidate.id)}
                              disabled={processingCandidate === candidate.id}
                              className="text-red-500 border-red-200 hover:bg-red-50"
                            >
                              <XCircle className="w-4 h-4" />
                            </Button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Impact Simulator + Expert Attribution Grid */}
            {insight && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2">
                <ImpactSimulator simulation={insight.simulation} />
              </div>
              <div className="lg:col-span-1">
                <ExpertAttribution expert={insight.expert} />
              </div>
            </div>
            )}

            {/* Audit Log / Raw Data - Collapsible */}
            <div className="border border-slate-200 rounded-xl overflow-hidden">
              <button
                onClick={() => setShowAuditLog(!showAuditLog)}
                className="w-full px-4 py-3 flex items-center justify-between bg-slate-50 hover:bg-slate-100 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-slate-500" />
                  <span className="text-sm font-medium text-slate-700">
                    Audit Log
                  </span>
                  <span className="text-xs text-slate-400">
                    ({result.extracted.timeline.length} events)
                  </span>
                </div>
                <ChevronDown
                  className={cn(
                    "w-4 h-4 text-slate-400 transition-transform",
                    showAuditLog && "rotate-180"
                  )}
                />
              </button>

              {showAuditLog && result.extracted.timeline.length > 0 && (
                <div className="border-t border-slate-200">
                  <ScrollArea className="h-64">
                    <div className="p-4 space-y-3">
                      {result.extracted.timeline.map((event, i) => (
                        <div
                          key={i}
                          className="flex gap-3 p-3 rounded-xl bg-slate-50 border border-slate-100"
                        >
                          <div className="flex-shrink-0 w-7 h-7 rounded-lg bg-gradient-to-br from-blue-600 to-violet-600 text-white flex items-center justify-center text-xs font-bold shadow-sm">
                            {event.step}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 text-xs text-slate-500 mb-1">
                              <span className="font-medium text-slate-700">
                                {event.sender}
                              </span>
                              {event.date !== "Unknown" && (
                                <>
                                  <span>•</span>
                                  <span>{event.date}{event.time && ` ${event.time}`}</span>
                                </>
                              )}
                            </div>
                            <p className="text-sm text-slate-700">{event.summary}</p>
                            {event.logic_type && (
                              <div className="mt-2 flex items-center gap-2">
                                <span
                                  className={cn(
                                    "px-2 py-0.5 rounded text-xs font-medium border",
                                    getLogicTypeStyle(event.logic_type)
                                  )}
                                >
                                  {event.logic_type}
                                </span>
                                {event.logic_description && (
                                  <span className="text-xs text-slate-500 truncate">
                                    {event.logic_description}
                                  </span>
                                )}
                              </div>
                            )}
                            {/* Citation Block - Source Evidence */}
                            {event.citation && (
                              <div className="mt-2 pl-3 py-2 border-l-4 border-slate-300 bg-white rounded-r-lg">
                                <div className="flex items-start gap-2">
                                  <Quote className="w-3 h-3 text-slate-400 flex-shrink-0 mt-0.5" />
                                  <p className="text-xs text-slate-500 italic leading-relaxed">
                                    "{event.citation}"
                                  </p>
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                </div>
              )}
            </div>

            {/* Reset Button */}
            <Button
              variant="outline"
              onClick={reset}
              className="w-full h-11 rounded-xl border-slate-200 text-slate-600 hover:bg-slate-50"
            >
              <ArrowRight className="w-4 h-4 mr-2" />
              Analyze Another Thread
            </Button>
          </div>
          );
        })()}
      </div>

      {/* Verification Modal */}
      {showMapModal && selectedCandidate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
            <div className="p-6 border-b border-slate-100">
              <h3 className="font-semibold text-lg text-slate-900">Verify Discovery</h3>
              <p className="text-sm text-slate-500 mt-1">
                Verifying: <strong>{selectedCandidate.raw_name}</strong>
              </p>
            </div>

            <div className="p-6 space-y-4">
              {/* Action Selection */}
              <div className="flex gap-2">
                <Button
                  variant={mapAction === "create_new" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setMapAction("create_new")}
                  className={cn(
                    mapAction === "create_new" && "bg-violet-600 hover:bg-violet-700"
                  )}
                >
                  <CheckCircle2 className="w-4 h-4 mr-2" />
                  Confirm as New
                </Button>
                <Button
                  variant={mapAction === "map_to_existing" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setMapAction("map_to_existing")}
                  className={cn(
                    mapAction === "map_to_existing" && "bg-violet-600 hover:bg-violet-700"
                  )}
                >
                  <Link2 className="w-4 h-4 mr-2" />
                  Map to Existing
                </Button>
              </div>

              {mapAction === "create_new" ? (
                <>
                  {/* Verified Name */}
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">
                      Canonical Name
                    </label>
                    <input
                      type="text"
                      value={verifiedName}
                      onChange={(e) => setVerifiedName(e.target.value)}
                      className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500"
                      placeholder="e.g., HABE Calculation Tool"
                    />
                  </div>

                  {/* Description */}
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">
                      Description
                    </label>
                    <textarea
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      rows={3}
                      className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500 resize-none"
                      placeholder="What is this tool/data source used for?"
                    />
                  </div>
                </>
              ) : (
                /* Map to Existing */
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Select Existing Source
                  </label>
                  <select
                    value={selectedSourceId}
                    onChange={(e) => setSelectedSourceId(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500"
                  >
                    <option value="">-- Select a source --</option>
                    {verifiedSources.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name} ({s.type})
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-slate-400 mt-2">
                    This will create an alias: &ldquo;{selectedCandidate.raw_name}&rdquo; → selected source
                  </p>
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="p-6 border-t border-slate-100 flex gap-3 justify-end">
              <Button
                variant="outline"
                onClick={() => {
                  setShowMapModal(false);
                  setSelectedCandidate(null);
                }}
              >
                Cancel
              </Button>
              <Button
                onClick={submitVerification}
                disabled={
                  processingCandidate === selectedCandidate.id ||
                  (mapAction === "create_new" && !verifiedName) ||
                  (mapAction === "map_to_existing" && !selectedSourceId)
                }
                className="bg-violet-600 hover:bg-violet-700"
              >
                {processingCandidate === selectedCandidate.id ? (
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
