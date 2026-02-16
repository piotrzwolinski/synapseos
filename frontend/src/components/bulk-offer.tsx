"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Upload,
  FileSpreadsheet,
  FileText,
  Send,
  Loader2,
  Bot,
  User,
  Download,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ChevronDown,
  ChevronRight,
  HelpCircle,
  Package,
  Mail,
  Brain,
  Sparkles,
  Copy,
  Check,
  Network,
  ArrowLeftRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiUrl, authFetch } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Clarification {
  id: string;
  type: string;
  severity: string;
  message: string;
  options: { label: string; value: string; description: string }[];
  affected_rows?: number[];
  default_value?: string;
}

interface GraphTraceNode {
  type: string;
  id: string;
  detail: string;
}

interface GraphTraceRule {
  rule: string;
  description: string;
}

interface GraphTrace {
  nodes_consulted: GraphTraceNode[];
  rules_applied: GraphTraceRule[];
  reasoning_steps: string[];
}

interface RowResult {
  row_id: number;
  status: string;
  property?: string;
  unit_id?: string;
  duct?: string;
  housing?: string;
  filter_1?: string;
  filter_2?: string;
  transition?: string;
  modules_needed?: number;
  warnings?: string[];
  detail?: string;
  graph_trace?: GraphTrace;
}

interface OfferSummary {
  offer_id: string;
  total: number;
  success: number;
  errors: number;
  housing_counts: Record<string, number>;
  properties: string[];
}

interface LLMFinding {
  severity: "action_required" | "review" | "info";
  units: string[];
  message: string;
}

interface LLMAnalysis {
  summary: string;
  findings: LLMFinding[];
  // Legacy fields (backward compat)
  observations?: string[];
  risk_flags?: { severity: string; message: string }[];
  optimization_hints?: string[];
}

// Cross-reference types
interface CrossRefMapping {
  line_id: number;
  competitor: string;
  competitor_code: string;
  competitor_dims: string;
  quantity: number;
  mh_product: string;
  mh_code: string;
  mh_housing_family: string;
  confidence: number;
  match_type: string;
  dimension_note: string;
  performance_note: string;
  graph_trace?: GraphTrace;
}

type BulkOfferMode = "standard" | "cross_reference";

type MessageRole = "user" | "assistant";

interface ChatMessage {
  role: MessageRole;
  content: string;
  type?:
    | "upload"
    | "analysis"
    | "clarification_answer"
    | "generation"
    | "text"
    | "refinement"
    | "email";
  clarifications?: Clarification[];
  rowResults?: RowResult[];
  summary?: OfferSummary;
  llmAnalysis?: LLMAnalysis;
  emailDraft?: { subject: string; body: string };
  crossRefResults?: CrossRefMapping[];
  isStreaming?: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function BulkOffer() {
  const [mode, setMode] = useState<BulkOfferMode>("standard");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [offerId, setOfferId] = useState<string | null>(null);
  const [pendingClarifications, setPendingClarifications] = useState<
    Clarification[]
  >([]);
  const [clarificationAnswers, setClarificationAnswers] = useState<
    Record<string, string>
  >({});
  const [streamingResults, setStreamingResults] = useState<RowResult[]>([]);
  const [streamingProgress, setStreamingProgress] = useState<{
    current: number;
    total: number;
  } | null>(null);
  const [hasResults, setHasResults] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const dragCounterRef = useRef(0);
  const [isDragging, setIsDragging] = useState(false);
  // Store last config for re-generation after refinement
  const lastConfigRef = useRef<Record<string, unknown>>({});

  // Auto-scroll
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streamingResults]);

  // -------------------------------------------------------------------------
  // File upload + analysis
  // -------------------------------------------------------------------------

  const handleFileUpload = async (file: File) => {
    const name = file.name.toLowerCase();
    if (!name.endsWith(".xlsx") && !name.endsWith(".xls") && !name.endsWith(".pdf")) {
      addMessage("assistant", "Please upload an Excel (.xlsx) or PDF file.", "text");
      return;
    }

    setIsLoading(true);
    const isPdf = name.endsWith(".pdf");
    addMessage("user", `Uploading ${file.name}...`, "upload");

    const formData = new FormData();
    formData.append("file", file);

    try {
      // Branch endpoint based on mode
      const endpoint = mode === "cross_reference"
        ? "/offers/bulk/crossref/analyze"
        : "/offers/bulk/analyze";

      const response = await fetch(
        apiUrl(endpoint),
        authFetch({ method: "POST", body: formData })
      );

      if (!response.ok) {
        const err = await response.json();
        addMessage(
          "assistant",
          `Failed to analyze file: ${err.detail || "Unknown error"}`,
          "text"
        );
        setIsLoading(false);
        return;
      }

      const data = await response.json();
      setOfferId(data.offer_id);

      if (mode === "cross_reference") {
        // Cross-reference analysis response
        const itemCount = data.row_count || data.stats?.total_items || 0;
        const matchCount = data.stats?.matched || 0;
        const statsMsg = `Identified **${itemCount} competitor product(s)** from \`${file.name}\`\n\n**${matchCount}/${itemCount}** matched to MH equivalents`;

        const llmAnalysis: LLMAnalysis | undefined = data.llm_analysis;
        const crossRefResults: CrossRefMapping[] = (data.cross_ref_results || []).map((r: Record<string, unknown>) => ({
          line_id: r.line_id,
          competitor: r.competitor,
          competitor_code: r.competitor_code || "",
          competitor_dims: r.competitor_dims || "",
          quantity: r.quantity || 1,
          mh_product: r.mh_product || "",
          mh_code: r.mh_code || "",
          mh_housing_family: r.mh_housing_family || "",
          confidence: r.confidence || 0,
          match_type: r.match_type || "no_match",
          dimension_note: r.dimension_note || "",
          performance_note: r.performance_note || "",
          graph_trace: r.graph_trace as GraphTrace | undefined,
        }));

        if (data.clarifications && data.clarifications.length > 0) {
          setPendingClarifications(data.clarifications);
          const defaults: Record<string, string> = {};
          data.clarifications.forEach((c: Clarification) => {
            if (c.default_value) defaults[c.id] = c.default_value;
          });
          setClarificationAnswers(defaults);
        }

        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: statsMsg,
            type: "analysis",
            clarifications: data.clarifications || [],
            llmAnalysis,
            crossRefResults,
          },
        ]);

        // If no clarifications, auto-generate
        if (!data.clarifications || data.clarifications.length === 0) {
          await generateOffer(data.offer_id, {});
        }
      } else {
        // Standard analysis response
        const sourceTag = isPdf ? " (extracted via AI from PDF)" : "";
        const unitWord = data.row_count === 1 ? "unit" : "units";
        const propCount = data.stats?.property_count ?? data.properties?.length ?? "?";
        const propWord = propCount === 1 ? "property" : "properties";
        const statsMsg = `Parsed **${data.row_count} ${unitWord}** across **${propCount} ${propWord}** from \`${data.filename}\`${sourceTag}\n\nProperties: ${data.properties.join(", ")}`;

        const llmAnalysis: LLMAnalysis | undefined = data.llm_analysis;

        if (data.clarifications && data.clarifications.length > 0) {
          setPendingClarifications(data.clarifications);
          const defaults: Record<string, string> = {};
          data.clarifications.forEach((c: Clarification) => {
            if (c.default_value) defaults[c.id] = c.default_value;
          });
          setClarificationAnswers(defaults);

          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: statsMsg,
              type: "analysis",
              clarifications: data.clarifications,
              llmAnalysis: llmAnalysis,
            },
          ]);
        } else {
          addMessage("assistant", statsMsg + "\n\nNo issues found. Generating offer...", "text");
          await generateOffer(data.offer_id, {});
        }
      }
    } catch (error) {
      addMessage(
        "assistant",
        `Error: ${error instanceof Error ? error.message : "Upload failed"}`,
        "text"
      );
    }

    setIsLoading(false);
  };

  // -------------------------------------------------------------------------
  // Clarification answers → Generate
  // -------------------------------------------------------------------------

  const handleSubmitClarifications = async () => {
    if (!offerId) return;

    const config = {
      offer_id: offerId,
      material_code: clarificationAnswers["material"] || "AZ",
      housing_length: parseInt(clarificationAnswers["housing_length"] || "850"),
      filter_class: clarificationAnswers["filter_class"] || "ePM1 65%",
      product_family: "GDMI",
      overrides: {} as Record<string, Record<string, string>>,
    };

    const capAnswer = clarificationAnswers["capacity_exceeded"];
    if (capAnswer) {
      const capClarification = pendingClarifications.find(
        (c) => c.id === "capacity_exceeded"
      );
      if (capClarification?.affected_rows) {
        for (const rowId of capClarification.affected_rows) {
          config.overrides[String(rowId)] = { capacity: capAnswer };
        }
      }
    }

    const answerLines = Object.entries(clarificationAnswers)
      .filter(([k]) => !k.startsWith("capacity_exceeded_") && !k.startsWith("no_match_"))
      .map(([k, v]) => {
        const clarification = pendingClarifications.find((c) => c.id === k);
        const option = clarification?.options.find((o) => o.value === v);
        return `**${k}**: ${option?.label || v}`;
      });
    addMessage("user", answerLines.join("\n"), "clarification_answer");

    setPendingClarifications([]);
    lastConfigRef.current = config;
    await generateOffer(offerId, config);
  };

  // -------------------------------------------------------------------------
  // Generate offer (SSE streaming)
  // -------------------------------------------------------------------------

  const generateOffer = async (
    oid: string,
    config: Record<string, unknown>
  ) => {
    setIsLoading(true);
    setStreamingResults([]);
    setStreamingProgress(null);

    // Branch endpoint based on mode
    const endpoint = mode === "cross_reference"
      ? "/offers/bulk/crossref/generate/stream"
      : "/offers/bulk/generate/stream";

    const fullConfig = {
      offer_id: oid,
      material_code: "AZ",
      housing_length: 850,
      filter_class: "ePM1 65%",
      product_family: "GDMI",
      overrides: {},
      ...config,
    };

    try {
      const response = await fetch(
        apiUrl(endpoint),
        authFetch({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(fullConfig),
        })
      );

      if (!response.ok || !response.body) {
        addMessage("assistant", "Failed to start offer generation", "text");
        setIsLoading(false);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const results: RowResult[] = [];
      const crossRefMappings: CrossRefMapping[] = [];
      let summary: OfferSummary | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));

            if (event.type === "crossref_mapping") {
              crossRefMappings.push(event as CrossRefMapping);
              setStreamingProgress({
                current: crossRefMappings.length,
                total: event.total || crossRefMappings.length,
              });
            } else if (event.type === "crossref_complete") {
              // Phase 1 done, phase 2 (standard generation) starts
              setStreamingProgress(null);
            } else if (event.type === "row_result") {
              results.push(event as RowResult);
              setStreamingResults([...results]);
              setStreamingProgress({
                current: event.row,
                total: event.total,
              });
            } else if (event.type === "summary") {
              summary = event as OfferSummary;
            } else if (event.type === "error") {
              addMessage("assistant", `Error: ${event.detail}`, "text");
            }
          } catch {
            // skip malformed events
          }
        }
      }

      setStreamingProgress(null);

      const finalMsg: ChatMessage = {
        role: "assistant",
        content: summary
          ? `Offer generated: **${summary.total} units**, ${summary.success} successful, ${summary.errors} errors`
          : "Offer generation complete",
        type: "generation",
        rowResults: results,
        summary: summary || undefined,
        crossRefResults: crossRefMappings.length > 0 ? crossRefMappings : undefined,
      };
      setMessages((prev) => [...prev, finalMsg]);
      setStreamingResults([]);
      setHasResults(true);
    } catch (error) {
      addMessage(
        "assistant",
        `Generation error: ${error instanceof Error ? error.message : "Unknown"}`,
        "text"
      );
    }

    setIsLoading(false);
  };

  // -------------------------------------------------------------------------
  // Text input (LLM-powered refinement)
  // -------------------------------------------------------------------------

  const handleSendMessage = async () => {
    if (!input.trim() || isLoading) return;
    const msg = input.trim();
    setInput("");
    addMessage("user", msg, "text");

    if (!offerId) {
      addMessage("assistant", "Please upload a file first to start an offer.", "text");
      return;
    }

    setIsLoading(true);

    try {
      // Call LLM chat endpoint (branch by mode)
      const chatEndpoint = mode === "cross_reference"
        ? "/offers/bulk/crossref/chat"
        : "/offers/bulk/chat";
      const response = await fetch(
        apiUrl(chatEndpoint),
        authFetch({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ offer_id: offerId, message: msg }),
        })
      );

      if (!response.ok) {
        addMessage("assistant", "Failed to interpret your request.", "text");
        setIsLoading(false);
        return;
      }

      const result = await response.json();

      // Show interpretation
      addMessage("assistant", result.interpretation, "refinement");

      if (result.requires_regeneration && (Object.keys(result.changes || {}).length > 0 || Object.keys(result.config_changes || {}).length > 0)) {
        // Apply changes via refine endpoint
        const refinePayload: Record<string, unknown> = {
          offer_id: offerId,
          changes: result.changes || {},
        };

        // If there are config changes, update the config
        const newConfig = { ...lastConfigRef.current };
        if (result.config_changes) {
          Object.assign(newConfig, result.config_changes);
        }
        newConfig.offer_id = offerId;
        lastConfigRef.current = newConfig;

        // First apply row changes if any
        if (Object.keys(result.changes || {}).length > 0) {
          await fetch(
            apiUrl("/offers/bulk/refine/stream"),
            authFetch({
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(refinePayload),
            })
          );
        }

        // Re-generate with updated config
        await generateOffer(offerId, newConfig);
      }
    } catch (error) {
      addMessage(
        "assistant",
        `Error: ${error instanceof Error ? error.message : "Request failed"}`,
        "text"
      );
    }

    setIsLoading(false);
  };

  // -------------------------------------------------------------------------
  // Email drafting
  // -------------------------------------------------------------------------

  const handleDraftEmail = async (language: string = "sv") => {
    if (!offerId || isLoading) return;
    setIsLoading(true);

    try {
      const response = await fetch(
        apiUrl("/offers/bulk/email"),
        authFetch({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ offer_id: offerId, language }),
        })
      );

      if (!response.ok) {
        addMessage("assistant", "Failed to draft email.", "text");
        setIsLoading(false);
        return;
      }

      const result = await response.json();
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Email draft (${language === "sv" ? "Swedish" : "English"}):`,
          type: "email",
          emailDraft: result,
        },
      ]);
    } catch (error) {
      addMessage(
        "assistant",
        `Email error: ${error instanceof Error ? error.message : "Failed"}`,
        "text"
      );
    }

    setIsLoading(false);
  };

  // -------------------------------------------------------------------------
  // Export
  // -------------------------------------------------------------------------

  const handleExport = async () => {
    if (!offerId) return;
    try {
      const response = await fetch(
        apiUrl(`/offers/bulk/export?offer_id=${offerId}`),
        authFetch({})
      );
      if (!response.ok) {
        console.error("Export failed");
        return;
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `offer_${offerId}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Export error:", error);
    }
  };

  // -------------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------------

  const addMessage = (
    role: MessageRole,
    content: string,
    type?: ChatMessage["type"],
    clarifications?: Clarification[]
  ) => {
    setMessages((prev) => [
      ...prev,
      { role, content, type, clarifications },
    ]);
  };

  // -------------------------------------------------------------------------
  // Drag & drop
  // -------------------------------------------------------------------------

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    dragCounterRef.current++;
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    dragCounterRef.current--;
    if (dragCounterRef.current === 0) setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    dragCounterRef.current = 0;
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFileUpload(file);
  };

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div
      className="flex flex-col h-full bg-background"
      onDragEnter={handleDragEnter}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Drag overlay */}
      {isDragging && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm border-2 border-dashed border-violet-500 rounded-lg">
          <div className="text-center">
            <FileSpreadsheet className="w-16 h-16 text-violet-500 mx-auto mb-3" />
            <p className="text-lg font-medium text-violet-500">
              Drop Excel or PDF file here
            </p>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b bg-card">
        <Package className={cn("w-5 h-5", mode === "cross_reference" ? "text-orange-500" : "text-violet-500")} />
        <h2 className="font-semibold text-sm">Bulk Offer Creator</h2>
        {/* Mode toggle */}
        <div className="flex items-center gap-0.5 bg-muted rounded-md p-0.5">
          <button
            onClick={() => { setMode("standard"); setMessages([]); setOfferId(null); setPendingClarifications([]); setHasResults(false); }}
            className={cn(
              "px-2.5 py-1 text-xs rounded transition-colors flex items-center gap-1",
              mode === "standard"
                ? "bg-violet-600 text-white"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            <Package className="w-3 h-3" />
            Standard
          </button>
          <button
            onClick={() => { setMode("cross_reference"); setMessages([]); setOfferId(null); setPendingClarifications([]); setHasResults(false); }}
            className={cn(
              "px-2.5 py-1 text-xs rounded transition-colors flex items-center gap-1",
              mode === "cross_reference"
                ? "bg-orange-600 text-white"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            <ArrowLeftRight className="w-3 h-3" />
            Competitor X-Ref
          </button>
        </div>
        {offerId && (
          <>
            <Badge variant="outline" className="text-xs ml-auto">
              Offer: {offerId}
            </Badge>
            {hasResults && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleDraftEmail("sv")}
                disabled={isLoading}
                className="text-xs"
              >
                <Mail className="w-3.5 h-3.5 mr-1" />
                Draft Email
              </Button>
            )}
          </>
        )}
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 p-4" ref={scrollRef}>
        <div className="max-w-4xl mx-auto space-y-4">
          {messages.length === 0 && !isLoading && (
            <EmptyState onUploadClick={() => fileInputRef.current?.click()} mode={mode} />
          )}

          {messages.map((msg, idx) => (
            <MessageBubble
              key={idx}
              message={msg}
              mode={mode}
              clarificationAnswers={clarificationAnswers}
              onClarificationChange={(id, value) =>
                setClarificationAnswers((prev) => ({ ...prev, [id]: value }))
              }
              onExport={handleExport}
              onDraftEmail={handleDraftEmail}
            />
          ))}

          {/* Streaming progress */}
          {streamingResults.length > 0 && (
            <StreamingProgress
              results={streamingResults}
              progress={streamingProgress}
            />
          )}

          {/* Submit clarifications button */}
          {pendingClarifications.length > 0 && !isLoading && (
            <div className="flex justify-end">
              <Button
                onClick={handleSubmitClarifications}
                className="bg-violet-600 hover:bg-violet-700"
              >
                <Send className="w-4 h-4 mr-2" />
                Submit answers & generate offer
              </Button>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Input area */}
      <div className="border-t bg-card p-3">
        <div className="max-w-4xl mx-auto flex gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls,.pdf"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleFileUpload(file);
              e.target.value = "";
            }}
          />
          <Button
            variant="outline"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
          >
            <Upload className="w-4 h-4 mr-1" />
            Upload
          </Button>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSendMessage()}
            placeholder={
              offerId
                ? mode === "cross_reference"
                  ? 'Refine: "Change Hi-Flo match to Airpocket XL" or "Set qty to 10 for line 3"'
                  : 'Refine: "Change all 600x300 to 600x600" or "Switch material to ZM"'
                : mode === "cross_reference"
                  ? "Upload a competitor product list to start cross-referencing"
                  : "Upload an Excel or PDF file to start"
            }
            className={cn(
              "flex-1 px-3 py-1.5 text-sm border rounded-md bg-background focus:outline-none focus:ring-1",
              mode === "cross_reference" ? "focus:ring-orange-500" : "focus:ring-violet-500"
            )}
            disabled={isLoading}
          />
          <Button
            size="sm"
            onClick={handleSendMessage}
            disabled={!input.trim() || isLoading}
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </Button>
        </div>
        <div className="max-w-4xl mx-auto mt-1 text-[10px] text-muted-foreground">
          {mode === "cross_reference"
            ? "Upload competitor product lists (.xlsx, .pdf). AI identifies products and maps to MH equivalents."
            : "Supports .xlsx, .xls, and .pdf files. AI extracts data from any format."}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function EmptyState({ onUploadClick, mode }: { onUploadClick: () => void; mode: BulkOfferMode }) {
  const isXRef = mode === "cross_reference";
  const accentColor = isXRef ? "text-orange-500" : "text-violet-500";
  const btnClass = isXRef ? "bg-orange-600 hover:bg-orange-700" : "bg-violet-600 hover:bg-violet-700";

  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="relative mb-4">
        {isXRef ? (
          <ArrowLeftRight className="w-16 h-16 text-muted-foreground/30" />
        ) : (
          <FileSpreadsheet className="w-16 h-16 text-muted-foreground/30" />
        )}
        <Sparkles className={cn("w-6 h-6 absolute -top-1 -right-1", accentColor)} />
      </div>
      <h3 className="text-lg font-medium mb-2">
        {isXRef ? "Competitor Cross-Reference" : "AI-Powered Bulk Offer Creator"}
      </h3>
      <p className="text-sm text-muted-foreground mb-6 max-w-md">
        {isXRef ? (
          <>
            Upload a <strong>competitor product list</strong> (Excel, PDF, or scanned image).
            AI identifies competitor products, maps them to MH equivalents using graph + AI matching,
            and generates a complete MH offer.
          </>
        ) : (
          <>
            Upload a client order in <strong>any format</strong> (Excel or PDF). AI analyzes
            the order, asks smart questions, generates offers with full graph reasoning,
            and drafts customer emails.
          </>
        )}
      </p>
      <div className="flex gap-3">
        <Button onClick={onUploadClick} className={btnClass}>
          <Upload className="w-4 h-4 mr-2" />
          {isXRef ? "Upload Competitor List" : "Upload Excel (.xlsx)"}
        </Button>
        <Button onClick={onUploadClick} variant="outline">
          <FileText className="w-4 h-4 mr-2" />
          Upload PDF
        </Button>
      </div>
      <p className="text-xs text-muted-foreground mt-3">
        Or drag & drop anywhere on this page
      </p>
      <div className="flex gap-6 mt-8 text-xs text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <Brain className={cn("w-3.5 h-3.5", accentColor)} />
          <span>{isXRef ? "Product Matching" : "AI Analysis"}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Network className={cn("w-3.5 h-3.5", accentColor)} />
          <span>Graph Reasoning</span>
        </div>
        <div className="flex items-center gap-1.5">
          {isXRef ? (
            <ArrowLeftRight className={cn("w-3.5 h-3.5", accentColor)} />
          ) : (
            <Mail className={cn("w-3.5 h-3.5", accentColor)} />
          )}
          <span>{isXRef ? "Cross-Reference" : "Email Drafting"}</span>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({
  message,
  mode,
  clarificationAnswers,
  onClarificationChange,
  onExport,
  onDraftEmail,
}: {
  message: ChatMessage;
  mode: BulkOfferMode;
  clarificationAnswers: Record<string, string>;
  onClarificationChange: (id: string, value: string) => void;
  onExport: () => void;
  onDraftEmail: (lang: string) => void;
}) {
  const isUser = message.role === "user";
  const isXRef = mode === "cross_reference";

  return (
    <div className={cn("flex gap-3", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className={cn(
          "w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-1",
          isXRef ? "bg-orange-500/10" : "bg-violet-500/10"
        )}>
          <Bot className={cn("w-4 h-4", isXRef ? "text-orange-500" : "text-violet-500")} />
        </div>
      )}

      <div
        className={cn(
          "max-w-[85%] rounded-lg px-4 py-3 text-sm",
          isUser
            ? isXRef ? "bg-orange-600 text-white" : "bg-violet-600 text-white"
            : "bg-card border"
        )}
      >
        {/* Markdown-ish content */}
        <div className="whitespace-pre-wrap">
          {message.content.split(/(\*\*.*?\*\*|`.*?`)/g).map((part, i) => {
            if (part.startsWith("**") && part.endsWith("**"))
              return <strong key={i}>{part.slice(2, -2)}</strong>;
            if (part.startsWith("`") && part.endsWith("`"))
              return (
                <code
                  key={i}
                  className="px-1 py-0.5 bg-muted rounded text-xs"
                >
                  {part.slice(1, -1)}
                </code>
              );
            return <span key={i}>{part}</span>;
          })}
        </div>

        {/* LLM Analysis Card */}
        {message.llmAnalysis && <LLMAnalysisCard analysis={message.llmAnalysis} />}

        {/* Cross-reference mapping table */}
        {message.crossRefResults && message.crossRefResults.length > 0 && (
          <CrossRefMappingTable mappings={message.crossRefResults} />
        )}

        {/* Clarification cards */}
        {message.clarifications && message.clarifications.length > 0 && (
          <div className="mt-3 space-y-3">
            {message.clarifications.map((c) => (
              <ClarificationCard
                key={c.id}
                clarification={c}
                selectedValue={clarificationAnswers[c.id] || c.default_value || ""}
                onChange={(value) => onClarificationChange(c.id, value)}
              />
            ))}
          </div>
        )}

        {/* Offer results table */}
        {message.rowResults && message.rowResults.length > 0 && (
          <OfferResultsTable
            results={message.rowResults}
            summary={message.summary}
            onExport={onExport}
            onDraftEmail={onDraftEmail}
          />
        )}

        {/* Email draft */}
        {message.emailDraft && <EmailDraftCard draft={message.emailDraft} />}
      </div>

      {isUser && (
        <div className={cn(
          "w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-1",
          isXRef ? "bg-orange-600" : "bg-violet-600"
        )}>
          <User className="w-4 h-4 text-white" />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Cross-Reference Mapping Table
// ---------------------------------------------------------------------------

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const color =
    pct >= 80
      ? "border-green-500 text-green-600 bg-green-500/5"
      : pct >= 60
        ? "border-amber-500 text-amber-600 bg-amber-500/5"
        : "border-red-500 text-red-600 bg-red-500/5";
  return (
    <Badge variant="outline" className={cn("text-[10px] font-mono", color)}>
      {pct}%
    </Badge>
  );
}

function MatchTypeBadge({ matchType }: { matchType: string }) {
  const config: Record<string, { label: string; color: string }> = {
    graph_exact: { label: "Graph", color: "border-green-500 text-green-600 bg-green-500/5" },
    graph_near: { label: "Graph~", color: "border-emerald-500 text-emerald-600 bg-emerald-500/5" },
    llm_inferred: { label: "AI", color: "border-amber-500 text-amber-600 bg-amber-500/5" },
    no_match: { label: "None", color: "border-red-500 text-red-600 bg-red-500/5" },
  };
  const cfg = config[matchType] || config.no_match;
  return (
    <Badge variant="outline" className={cn("text-[10px]", cfg.color)}>
      {cfg.label}
    </Badge>
  );
}

function CrossRefMappingTable({ mappings }: { mappings: CrossRefMapping[] }) {
  const matchCount = mappings.filter((m) => m.match_type !== "no_match").length;
  const graphCount = mappings.filter((m) => m.match_type.startsWith("graph")).length;
  const aiCount = mappings.filter((m) => m.match_type === "llm_inferred").length;

  return (
    <div className="mt-3 space-y-2">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <ArrowLeftRight className="w-3.5 h-3.5 text-orange-500" />
        <span className="font-medium text-foreground">Cross-Reference Mapping</span>
        <span>{matchCount}/{mappings.length} matched</span>
        {graphCount > 0 && (
          <Badge variant="secondary" className="text-[9px]">
            {graphCount} graph
          </Badge>
        )}
        {aiCount > 0 && (
          <Badge variant="secondary" className="text-[9px]">
            {aiCount} AI
          </Badge>
        )}
      </div>
      <div className="overflow-x-auto border rounded-md">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b bg-muted/30">
              <th className="px-2 py-1.5 text-left font-medium">#</th>
              <th className="px-2 py-1.5 text-left font-medium">Competitor Product</th>
              <th className="px-2 py-1.5 text-left font-medium">Dims</th>
              <th className="px-2 py-1.5 text-left font-medium text-center">Qty</th>
              <th className="px-2 py-1.5 text-left font-medium text-orange-600">
                <span className="flex items-center gap-1">
                  <ArrowLeftRight className="w-3 h-3" />
                  MH Equivalent
                </span>
              </th>
              <th className="px-2 py-1.5 text-left font-medium">Housing</th>
              <th className="px-2 py-1.5 text-left font-medium">Confidence</th>
              <th className="px-2 py-1.5 text-left font-medium">Source</th>
              <th className="px-2 py-1.5 text-left font-medium">Notes</th>
              <th className="px-2 py-1.5 text-left font-medium w-8">
                <Network className="w-3 h-3 text-orange-500" />
              </th>
            </tr>
          </thead>
          <tbody>
            {mappings.map((m) => (
              <tr key={m.line_id} className={cn(
                "border-b last:border-0",
                m.match_type === "no_match" && "bg-red-500/5"
              )}>
                <td className="px-2 py-1.5 font-mono text-muted-foreground">{m.line_id}</td>
                <td className="px-2 py-1.5 font-medium max-w-[180px] truncate" title={m.competitor}>
                  {m.competitor}
                  {m.competitor_code && (
                    <span className="text-muted-foreground font-normal ml-1">({m.competitor_code})</span>
                  )}
                </td>
                <td className="px-2 py-1.5 font-mono text-muted-foreground">{m.competitor_dims && m.competitor_dims !== "0x0x0" ? m.competitor_dims : "-"}</td>
                <td className="px-2 py-1.5 text-center font-mono">{m.quantity}</td>
                <td className="px-2 py-1.5 font-medium text-orange-600 dark:text-orange-400 max-w-[200px] truncate" title={m.mh_product}>
                  {m.mh_product || <span className="text-red-500 italic">No match</span>}
                </td>
                <td className="px-2 py-1.5 font-mono">{m.mh_housing_family || "-"}</td>
                <td className="px-2 py-1.5">
                  <ConfidenceBadge confidence={m.confidence} />
                </td>
                <td className="px-2 py-1.5">
                  <MatchTypeBadge matchType={m.match_type} />
                </td>
                <td className="px-2 py-1.5 max-w-[160px] truncate text-muted-foreground" title={[m.dimension_note, m.performance_note].filter(Boolean).join(" | ")}>
                  {m.dimension_note || m.performance_note || "-"}
                </td>
                <td className="px-2 py-1.5">
                  {m.graph_trace && <GraphTracePopover trace={m.graph_trace} />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// LLM Analysis Card
// ---------------------------------------------------------------------------

function LLMAnalysisCard({ analysis }: { analysis: LLMAnalysis }) {
  const [expanded, setExpanded] = useState(true);

  // Normalize: support both new (findings) and legacy (observations/risk_flags/optimization_hints) formats
  const findings: LLMFinding[] = analysis.findings?.length
    ? analysis.findings
    : [
        ...(analysis.risk_flags || []).map((f) => ({
          severity: (f.severity === "high" ? "action_required" : f.severity === "medium" ? "review" : "info") as LLMFinding["severity"],
          units: [] as string[],
          message: f.message,
        })),
        ...(analysis.observations || []).map((o) => ({
          severity: "info" as const,
          units: [] as string[],
          message: o,
        })),
        ...(analysis.optimization_hints || []).map((h) => ({
          severity: "info" as const,
          units: [] as string[],
          message: h,
        })),
      ];

  const severityConfig = {
    action_required: {
      dot: "bg-red-500",
      label: "Action Required",
      textClass: "text-red-600 dark:text-red-400",
    },
    review: {
      dot: "bg-amber-500",
      label: "Review",
      textClass: "text-amber-600 dark:text-amber-400",
    },
    info: {
      dot: "bg-blue-500",
      label: "Info",
      textClass: "text-blue-600 dark:text-blue-400",
    },
  };

  const actionCount = findings.filter((f) => f.severity === "action_required").length;
  const reviewCount = findings.filter((f) => f.severity === "review").length;

  return (
    <Card className="mt-3 p-3 border-l-4 border-violet-500/50 bg-violet-50/5">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 text-xs text-left"
      >
        <Brain className="w-3.5 h-3.5 text-violet-500 shrink-0" />
        <span className="font-medium text-sm">AI Analysis</span>
        {/* Severity summary pills */}
        {actionCount > 0 && (
          <span className="flex items-center gap-1 text-[10px] text-red-600 dark:text-red-400 bg-red-500/10 px-1.5 py-0.5 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
            {actionCount}
          </span>
        )}
        {reviewCount > 0 && (
          <span className="flex items-center gap-1 text-[10px] text-amber-600 dark:text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
            {reviewCount}
          </span>
        )}
        {findings.length > 0 && actionCount === 0 && reviewCount === 0 && (
          <span className="flex items-center gap-1 text-[10px] text-blue-600 dark:text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded-full">
            <CheckCircle2 className="w-2.5 h-2.5" />
            All clear
          </span>
        )}
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 ml-auto shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 ml-auto shrink-0 text-muted-foreground" />
        )}
      </button>

      {expanded && (
        <div className="mt-2 space-y-1.5">
          {/* Summary — one line */}
          <p className="text-xs text-muted-foreground pl-5">{analysis.summary}</p>

          {/* Findings — flat scannable list */}
          {findings.length > 0 && (
            <div className="space-y-0.5 pl-5">
              {findings.map((finding, i) => {
                const cfg = severityConfig[finding.severity] || severityConfig.info;
                return (
                  <div key={i} className="flex items-start gap-2 text-xs py-0.5">
                    <span className={cn("w-2 h-2 rounded-full mt-1 shrink-0", cfg.dot)} />
                    <span className="flex-1 leading-snug">
                      {finding.units.length > 0 && (
                        <span className="font-semibold font-mono text-foreground">
                          {finding.units.join(", ")}{" "}
                        </span>
                      )}
                      <span className="text-muted-foreground">{finding.message}</span>
                    </span>
                  </div>
                );
              })}
            </div>
          )}

          {findings.length === 0 && (
            <p className="text-xs text-muted-foreground pl-5 flex items-center gap-1.5">
              <CheckCircle2 className="w-3 h-3 text-green-500" />
              No issues detected. Ready to generate.
            </p>
          )}
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Email Draft Card
// ---------------------------------------------------------------------------

function EmailDraftCard({ draft }: { draft: { subject: string; body: string } }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(`Subject: ${draft.subject}\n\n${draft.body}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Card className="mt-3 p-3 border-l-4 border-blue-500/50">
      <div className="flex items-center gap-2 mb-2">
        <Mail className="w-4 h-4 text-blue-500" />
        <span className="text-sm font-medium">Email Draft</span>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleCopy}
          className="ml-auto text-xs h-6 px-2"
        >
          {copied ? (
            <Check className="w-3 h-3 mr-1 text-green-500" />
          ) : (
            <Copy className="w-3 h-3 mr-1" />
          )}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <div className="bg-muted/30 rounded p-3 text-xs space-y-2">
        <div>
          <span className="font-medium text-muted-foreground">Subject: </span>
          <span>{draft.subject}</span>
        </div>
        <hr className="border-muted" />
        <div className="whitespace-pre-wrap leading-relaxed">{draft.body}</div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Graph Trace Popover (per row)
// ---------------------------------------------------------------------------

function GraphTracePopover({ trace }: { trace: GraphTrace }) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 });

  const handleOpen = () => {
    if (!open && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      const spaceBelow = window.innerHeight - rect.bottom;
      const popoverHeight = 300; // estimate
      // Open upward if not enough space below
      if (spaceBelow < popoverHeight) {
        setPos({ top: rect.top - popoverHeight, left: rect.right - 320 });
      } else {
        setPos({ top: rect.bottom + 4, left: rect.right - 320 });
      }
    }
    setOpen(!open);
  };

  return (
    <div className="inline-block">
      <button
        ref={buttonRef}
        onClick={handleOpen}
        className="p-0.5 rounded hover:bg-violet-100 dark:hover:bg-violet-900/30"
        title="View graph reasoning"
      >
        <Network className="w-3 h-3 text-violet-500" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div
            className="fixed z-50 w-80 bg-card border rounded-lg shadow-lg p-3 text-xs max-h-[70vh] overflow-y-auto"
            style={{ top: Math.max(8, pos.top), left: Math.max(8, pos.left) }}
          >
            <div className="flex items-center gap-1.5 font-medium mb-2">
              <Network className="w-3.5 h-3.5 text-violet-500" />
              Graph Reasoning Trace
            </div>

            {/* Reasoning steps */}
            <div className="space-y-1 mb-2">
              {trace.reasoning_steps.map((step, i) => (
                <div key={i} className="flex items-start gap-1.5 text-muted-foreground">
                  <span className="text-violet-500 font-mono shrink-0">{i + 1}.</span>
                  <span>{step}</span>
                </div>
              ))}
            </div>

            {/* Nodes consulted */}
            {trace.nodes_consulted.length > 0 && (
              <div className="border-t pt-2 mt-2">
                <div className="font-medium mb-1 text-muted-foreground">Nodes Consulted:</div>
                <div className="flex flex-wrap gap-1">
                  {trace.nodes_consulted.map((node, i) => (
                    <Badge key={i} variant="secondary" className="text-[9px] font-mono">
                      {node.type}: {node.detail}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Rules applied */}
            {trace.rules_applied.length > 0 && (
              <div className="border-t pt-2 mt-2">
                <div className="font-medium mb-1 text-muted-foreground">Rules Applied:</div>
                {trace.rules_applied.map((rule, i) => (
                  <div key={i} className="text-muted-foreground">
                    <span className="font-medium">{rule.rule}:</span> {rule.description}
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function ClarificationCard({
  clarification,
  selectedValue,
  onChange,
}: {
  clarification: Clarification;
  selectedValue: string;
  onChange: (value: string) => void;
}) {
  const severityIcon = {
    info: <HelpCircle className="w-4 h-4 text-blue-500" />,
    warning: <AlertTriangle className="w-4 h-4 text-amber-500" />,
    critical: <XCircle className="w-4 h-4 text-red-500" />,
  }[clarification.severity] || <HelpCircle className="w-4 h-4 text-blue-500" />;

  const severityBorder = {
    info: "border-blue-500/30",
    warning: "border-amber-500/30",
    critical: "border-red-500/30",
  }[clarification.severity] || "border-blue-500/30";

  return (
    <Card className={cn("p-3 border-l-4", severityBorder)}>
      <div className="flex items-start gap-2 mb-2">
        {severityIcon}
        <p className="text-sm font-medium">{clarification.message}</p>
      </div>
      <div className="flex flex-wrap gap-2 ml-6">
        {clarification.options.map((opt) => (
          <Button
            key={opt.value}
            variant={selectedValue === opt.value ? "default" : "outline"}
            size="sm"
            className={cn(
              "text-xs",
              selectedValue === opt.value &&
                "bg-violet-600 hover:bg-violet-700 text-white"
            )}
            onClick={() => onChange(opt.value)}
            title={opt.description}
          >
            {opt.label}
          </Button>
        ))}
      </div>
      {clarification.affected_rows && clarification.affected_rows.length > 0 && (
        <p className="text-xs text-muted-foreground mt-1 ml-6">
          Affects {clarification.affected_rows.length} row(s)
        </p>
      )}
    </Card>
  );
}

function StreamingProgress({
  results,
  progress,
}: {
  results: RowResult[];
  progress: { current: number; total: number } | null;
}) {
  return (
    <div className="flex gap-3">
      <div className="w-7 h-7 rounded-full bg-violet-500/10 flex items-center justify-center shrink-0 mt-1">
        <Loader2 className="w-4 h-4 text-violet-500 animate-spin" />
      </div>
      <Card className="flex-1 p-3 border">
        {progress && (
          <div className="mb-2">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>Generating offer with graph reasoning...</span>
              <span>
                {progress.current}/{progress.total}
              </span>
            </div>
            <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-violet-500 rounded-full transition-all duration-300"
                style={{
                  width: `${(progress.current / progress.total) * 100}%`,
                }}
              />
            </div>
          </div>
        )}
        <div className="space-y-1 max-h-48 overflow-y-auto text-xs font-mono">
          {results.slice(-8).map((r) => (
            <div
              key={r.row_id}
              className={cn(
                "flex items-center gap-2",
                r.status === "error" ? "text-red-500" : "text-muted-foreground"
              )}
            >
              {r.status === "success" ? (
                <CheckCircle2 className="w-3 h-3 text-green-500 shrink-0" />
              ) : (
                <XCircle className="w-3 h-3 text-red-500 shrink-0" />
              )}
              <span>
                {r.unit_id}: {r.duct} → {r.housing || r.detail}
              </span>
              {r.graph_trace && (
                <Network className="w-3 h-3 text-violet-400 shrink-0" />
              )}
              {r.warnings && r.warnings.length > 0 && (
                <AlertTriangle className="w-3 h-3 text-amber-500 shrink-0" />
              )}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function OfferResultsTable({
  results,
  summary,
  onExport,
  onDraftEmail,
}: {
  results: RowResult[];
  summary?: OfferSummary;
  onExport: () => void;
  onDraftEmail: (lang: string) => void;
}) {
  const [expandedProps, setExpandedProps] = useState<Set<string>>(new Set());

  // Group by property
  const byProperty: Record<string, RowResult[]> = {};
  for (const r of results) {
    const prop = r.property || "Unknown";
    if (!byProperty[prop]) byProperty[prop] = [];
    byProperty[prop].push(r);
  }

  const toggleProperty = (prop: string) => {
    setExpandedProps((prev) => {
      const next = new Set(prev);
      if (next.has(prop)) next.delete(prop);
      else next.add(prop);
      return next;
    });
  };

  // Expand all by default
  useEffect(() => {
    setExpandedProps(new Set(Object.keys(byProperty)));
  }, [results.length]);

  return (
    <div className="mt-3 space-y-2">
      {Object.entries(byProperty).map(([prop, propResults]) => (
        <div key={prop} className="border rounded-md overflow-hidden">
          <button
            onClick={() => toggleProperty(prop)}
            className="w-full flex items-center gap-2 px-3 py-2 bg-muted/50 hover:bg-muted text-sm font-medium text-left"
          >
            {expandedProps.has(prop) ? (
              <ChevronDown className="w-4 h-4" />
            ) : (
              <ChevronRight className="w-4 h-4" />
            )}
            {prop}
            <Badge variant="secondary" className="text-xs ml-auto">
              {propResults.length} units
            </Badge>
          </button>

          {expandedProps.has(prop) && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b bg-muted/30">
                    <th className="px-2 py-1.5 text-left font-medium">Unit</th>
                    <th className="px-2 py-1.5 text-left font-medium">Duct</th>
                    <th className="px-2 py-1.5 text-left font-medium">
                      Housing
                    </th>
                    <th className="px-2 py-1.5 text-left font-medium">
                      Filter 1
                    </th>
                    <th className="px-2 py-1.5 text-left font-medium">
                      Transition
                    </th>
                    <th className="px-2 py-1.5 text-left font-medium">
                      Status
                    </th>
                    <th className="px-2 py-1.5 text-left font-medium w-8">
                      <Network className="w-3 h-3 text-violet-500" />
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {propResults.map((r) => (
                    <tr key={r.row_id} className="border-b last:border-0">
                      <td className="px-2 py-1.5 font-mono">{r.unit_id}</td>
                      <td className="px-2 py-1.5 font-mono">{r.duct}</td>
                      <td className="px-2 py-1.5 font-mono text-violet-600 dark:text-violet-400">
                        {r.housing || "-"}
                      </td>
                      <td className="px-2 py-1.5 truncate max-w-[200px]">
                        {r.filter_1
                          ? r.filter_1.replace(/\s+\d+x\d+x\d+$/, "")
                          : "-"}
                      </td>
                      <td className="px-2 py-1.5 font-mono text-xs">
                        {r.transition || "-"}
                      </td>
                      <td className="px-2 py-1.5">
                        {r.status === "success" ? (
                          r.warnings && r.warnings.length > 0 ? (
                            <Badge
                              variant="outline"
                              className="text-[10px] border-amber-500 text-amber-600"
                            >
                              Warning
                            </Badge>
                          ) : (
                            <Badge
                              variant="outline"
                              className="text-[10px] border-green-500 text-green-600"
                            >
                              OK
                            </Badge>
                          )
                        ) : (
                          <Badge variant="destructive" className="text-[10px]">
                            Error
                          </Badge>
                        )}
                      </td>
                      <td className="px-2 py-1.5">
                        {r.graph_trace && (
                          <GraphTracePopover trace={r.graph_trace} />
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}

      {/* Summary + actions */}
      {summary && (
        <Card className="p-3 bg-muted/30">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm">
              <strong>Summary:</strong>{" "}
              {Object.entries(summary.housing_counts)
                .sort(([, a], [, b]) => b - a)
                .map(([name, count]) => `${count}x ${name}`)
                .join(", ")}
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={onExport}
              className="shrink-0"
            >
              <Download className="w-4 h-4 mr-1" />
              Export Excel
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => onDraftEmail("sv")}
              className="shrink-0"
            >
              <Mail className="w-4 h-4 mr-1" />
              Draft Email (SV)
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => onDraftEmail("en")}
              className="shrink-0"
            >
              <Mail className="w-4 h-4 mr-1" />
              Draft Email (EN)
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
