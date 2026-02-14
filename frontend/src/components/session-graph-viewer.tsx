"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import dynamic from "next/dynamic";
import {
  Loader2,
  Database,
  Package,
  Tag,
  Layers,
  RefreshCw,
  X,
  CheckCircle2,
  AlertCircle,
  Lock,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiUrl, authFetch, getSessionId } from "@/lib/api";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full bg-slate-900">
      <Loader2 className="w-6 h-6 animate-spin text-cyan-400" />
    </div>
  ),
});

// =============================================================================
// TYPES
// =============================================================================

interface SessionNode {
  id: string;
  labels: string[];
  name: string;
  properties: Record<string, unknown>;
}

interface SessionRelationship {
  id: string;
  type: string;
  source: string;
  target: string;
  properties: Record<string, unknown>;
}

interface SessionGraphData {
  nodes: SessionNode[];
  relationships: SessionRelationship[];
}

interface ForceNode {
  id: string;
  name: string;
  labels: string[];
  properties: Record<string, unknown>;
  nodeType: "session" | "project" | "tag" | "material" | "family" | "dimension";
  isComplete?: boolean;
  x?: number;
  y?: number;
}

interface ForceLink {
  source: string | ForceNode;
  target: string | ForceNode;
  type: string;
}

interface SessionState {
  session_id: string;
  project: {
    name?: string;
    customer?: string;
    locked_material?: string;
    detected_family?: string;
  } | null;
  tags: Array<{
    tag_id: string;
    filter_width?: number;
    filter_height?: number;
    filter_depth?: number;
    housing_width?: number;
    housing_height?: number;
    housing_length?: number;
    product_code?: string;
    weight_kg?: number;
    is_complete?: boolean;
  }>;
  tag_count: number;
  reasoning_paths?: Array<{ tag_id: string; path: string }>;
}

interface SessionGraphViewerProps {
  sessionState?: SessionState | null;
  height?: number;
  onRefresh?: () => void;
}

// =============================================================================
// NODE TYPE CLASSIFICATION
// =============================================================================

function classifySessionNode(labels: string[]): ForceNode["nodeType"] {
  for (const label of labels) {
    if (label === "Session") return "session";
    if (label === "ActiveProject") return "project";
    if (label === "TagUnit") return "tag";
    if (label === "Material") return "material";
    if (label === "ProductFamily") return "family";
    if (label === "DimensionModule") return "dimension";
  }
  return "session";
}

// =============================================================================
// STYLING
// =============================================================================

const NODE_STYLES: Record<ForceNode["nodeType"], { color: string; glow: string; size: number }> = {
  session: { color: "#3b82f6", glow: "#60a5fa", size: 10 },
  project: { color: "#10b981", glow: "#34d399", size: 14 },
  tag: { color: "#f59e0b", glow: "#fbbf24", size: 12 },
  material: { color: "#8b5cf6", glow: "#a78bfa", size: 8 },
  family: { color: "#06b6d4", glow: "#22d3ee", size: 8 },
  dimension: { color: "#6b7280", glow: "#9ca3af", size: 6 },
};

const REL_COLORS: Record<string, string> = {
  WORKING_ON: "#10b981",
  HAS_UNIT: "#f59e0b",
  USES_MATERIAL: "#8b5cf6",
  TARGETS_FAMILY: "#06b6d4",
  SIZED_AS: "#6b7280",
};

// =============================================================================
// COMPONENT
// =============================================================================

export default function SessionGraphViewer({
  sessionState,
  height = 400,
  onRefresh,
}: SessionGraphViewerProps) {
  const [graphData, setGraphData] = useState<SessionGraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedNode, setSelectedNode] = useState<ForceNode | null>(null);
  const graphRef = useRef<any>(null);

  const fetchGraphData = useCallback(async () => {
    const sid = getSessionId();
    setLoading(true);
    try {
      const response = await fetch(
        apiUrl(`/session/graph/${sid}/visualization`),
        authFetch()
      );
      if (response.ok) {
        const data = await response.json();
        setGraphData(data);
      }
    } catch (err) {
      console.error("Failed to fetch session graph:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch graph when sessionState changes
  useEffect(() => {
    if (sessionState && sessionState.tag_count > 0) {
      fetchGraphData();
    }
  }, [sessionState, fetchGraphData]);

  // Transform data for ForceGraph2D
  const forceData = useCallback(() => {
    if (!graphData) return { nodes: [], links: [] };

    const nodes: ForceNode[] = graphData.nodes.map((n) => {
      const nodeType = classifySessionNode(n.labels);
      return {
        id: n.id,
        name: n.name,
        labels: n.labels,
        properties: n.properties,
        nodeType,
        isComplete: nodeType === "tag" ? Boolean(n.properties.is_complete) : undefined,
      };
    });

    const nodeIds = new Set(nodes.map((n) => n.id));
    const links: ForceLink[] = graphData.relationships
      .filter((r) => nodeIds.has(r.source) && nodeIds.has(r.target))
      .map((r) => ({
        source: r.source,
        target: r.target,
        type: r.type,
      }));

    return { nodes, links };
  }, [graphData]);

  const data = forceData();
  const isEmpty = !sessionState || sessionState.tag_count === 0;

  // Canvas rendering
  const nodeCanvasObject = useCallback(
    (node: ForceNode, ctx: CanvasRenderingContext2D) => {
      const style = NODE_STYLES[node.nodeType];
      const x = node.x || 0;
      const y = node.y || 0;
      const size = style.size;

      // Glow
      ctx.shadowColor = style.glow;
      ctx.shadowBlur = 12;

      // Circle
      ctx.beginPath();
      ctx.arc(x, y, size, 0, 2 * Math.PI);
      ctx.fillStyle = style.color;
      ctx.fill();

      // Complete/incomplete indicator for tags
      if (node.nodeType === "tag") {
        ctx.shadowBlur = 0;
        ctx.beginPath();
        ctx.arc(x + size * 0.7, y - size * 0.7, 4, 0, 2 * Math.PI);
        ctx.fillStyle = node.isComplete ? "#10b981" : "#ef4444";
        ctx.fill();
      }

      // Label
      ctx.shadowBlur = 0;
      ctx.font = "10px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.fillStyle = "#e2e8f0";
      ctx.fillText(node.name, x, y + size + 12);
    },
    []
  );

  const linkCanvasObject = useCallback(
    (link: ForceLink, ctx: CanvasRenderingContext2D) => {
      const source = link.source as ForceNode;
      const target = link.target as ForceNode;
      if (!source.x || !target.x) return;

      ctx.beginPath();
      ctx.moveTo(source.x, source.y!);
      ctx.lineTo(target.x, target.y!);
      ctx.strokeStyle = REL_COLORS[link.type] || "#4b5563";
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Label
      const midX = (source.x + target.x) / 2;
      const midY = (source.y! + target.y!) / 2;
      ctx.font = "8px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.fillStyle = "#64748b";
      ctx.fillText(link.type, midX, midY - 4);
    },
    []
  );

  return (
    <div className="flex flex-col bg-slate-900 rounded-lg border border-slate-700 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-slate-700 bg-slate-800/50">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-cyan-400" />
          <span className="text-sm font-medium text-slate-200">
            Session Graph (Layer 4)
          </span>
          {sessionState && sessionState.tag_count > 0 && (
            <span className="text-xs bg-cyan-900/50 text-cyan-300 px-2 py-0.5 rounded-full">
              {sessionState.tag_count} tag{sessionState.tag_count !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              fetchGraphData();
              onRefresh?.();
            }}
            className="p-1 rounded hover:bg-slate-700 text-slate-400 hover:text-slate-200"
          >
            <RefreshCw className={cn("w-3.5 h-3.5", loading && "animate-spin")} />
          </button>
        </div>
      </div>

      {/* State Summary */}
      {sessionState && sessionState.project && (
        <div className="px-4 py-2 border-b border-slate-700/50 bg-slate-800/30">
          <div className="flex flex-wrap gap-3 text-xs">
            {sessionState.project.name && (
              <div className="flex items-center gap-1 text-emerald-400">
                <Package className="w-3 h-3" />
                <span>{sessionState.project.name}</span>
              </div>
            )}
            {sessionState.project.locked_material && (
              <div className="flex items-center gap-1 text-violet-400">
                <Lock className="w-3 h-3" />
                <span>{sessionState.project.locked_material}</span>
              </div>
            )}
            {sessionState.project.detected_family && (
              <div className="flex items-center gap-1 text-cyan-400">
                <Database className="w-3 h-3" />
                <span>{sessionState.project.detected_family}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tags Summary */}
      {sessionState && sessionState.tags.length > 0 && (
        <div className="px-4 py-2 border-b border-slate-700/50 bg-slate-800/20">
          <div className="flex flex-wrap gap-2">
            {sessionState.tags.map((tag) => (
              <div
                key={tag.tag_id}
                className={cn(
                  "flex items-center gap-1.5 px-2 py-1 rounded text-xs border",
                  tag.is_complete
                    ? "border-emerald-700 bg-emerald-900/30 text-emerald-300"
                    : "border-amber-700 bg-amber-900/30 text-amber-300"
                )}
              >
                <Tag className="w-3 h-3" />
                <span className="font-mono">{tag.tag_id}</span>
                {tag.housing_width && tag.housing_height && (
                  <span className="text-slate-400">
                    {tag.housing_width}x{tag.housing_height}
                  </span>
                )}
                {tag.is_complete ? (
                  <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                ) : (
                  <AlertCircle className="w-3 h-3 text-amber-400" />
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Reasoning Paths */}
      {sessionState?.reasoning_paths && sessionState.reasoning_paths.length > 0 && (
        <div className="px-4 py-2 border-b border-slate-700/50 bg-slate-800/10">
          <div className="text-xs text-slate-500 mb-1">Reasoning Paths</div>
          {sessionState.reasoning_paths.map((rp) => (
            <div key={rp.tag_id} className="text-xs text-slate-400 font-mono mb-0.5">
              <span className="text-amber-400">Tag {rp.tag_id}</span>
              <span className="text-slate-600 mx-1">:</span>
              {rp.path}
            </div>
          ))}
        </div>
      )}

      {/* Graph Visualization */}
      <div style={{ height }} className="relative">
        {isEmpty ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-500">
            <Database className="w-8 h-8 mb-2 opacity-30" />
            <p className="text-sm">No session state yet</p>
            <p className="text-xs mt-1">Send a message with project specs to populate</p>
          </div>
        ) : loading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="w-6 h-6 animate-spin text-cyan-400" />
          </div>
        ) : data.nodes.length > 0 ? (
          <ForceGraph2D
            ref={graphRef}
            graphData={data}
            width={undefined}
            height={height}
            backgroundColor="#0f172a"
            nodeCanvasObject={nodeCanvasObject as any}
            nodePointerAreaPaint={((node: ForceNode, color: string, ctx: CanvasRenderingContext2D) => {
              const size = NODE_STYLES[node.nodeType]?.size || 8;
              ctx.beginPath();
              ctx.arc(node.x || 0, node.y || 0, size + 4, 0, 2 * Math.PI);
              ctx.fillStyle = color;
              ctx.fill();
            }) as any}
            linkCanvasObject={linkCanvasObject as any}
            onNodeClick={(node: any) => setSelectedNode(node as ForceNode)}
            d3AlphaDecay={0.05}
            d3VelocityDecay={0.4}
            cooldownTicks={60}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-slate-500">
            <p className="text-sm">Graph data loading...</p>
          </div>
        )}

        {/* Node Detail Panel */}
        {selectedNode && (
          <div className="absolute top-2 right-2 w-56 bg-slate-800 border border-slate-600 rounded-lg shadow-xl p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-200">{selectedNode.name}</span>
              <button
                onClick={() => setSelectedNode(null)}
                className="p-0.5 rounded hover:bg-slate-700"
              >
                <X className="w-3 h-3 text-slate-400" />
              </button>
            </div>
            <div className="text-xs space-y-1">
              <div className="text-slate-500">
                Type: <span className="text-slate-300">{selectedNode.labels.join(", ")}</span>
              </div>
              {Object.entries(selectedNode.properties)
                .filter(([k]) => !k.startsWith("_") && k !== "id" && k !== "session_id")
                .slice(0, 8)
                .map(([key, value]) => (
                  <div key={key} className="flex justify-between">
                    <span className="text-slate-500">{key}:</span>
                    <span className="text-slate-300 text-right ml-2 truncate max-w-[120px]">
                      {String(value ?? "-")}
                    </span>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 px-4 py-1.5 border-t border-slate-700/50 bg-slate-800/30">
        {[
          { type: "session" as const, label: "Session" },
          { type: "project" as const, label: "Project" },
          { type: "tag" as const, label: "Tag Unit" },
          { type: "material" as const, label: "Material" },
          { type: "family" as const, label: "Family" },
        ].map((item) => (
          <div key={item.type} className="flex items-center gap-1 text-xs text-slate-500">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: NODE_STYLES[item.type].color }}
            />
            {item.label}
          </div>
        ))}
      </div>
    </div>
  );
}
