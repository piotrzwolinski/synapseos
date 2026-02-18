"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import dynamic from "next/dynamic";
import {
  Eye,
  EyeOff,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Loader2,
  X,
  Database,
  AlertTriangle,
  BookOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiUrl, authFetch } from "@/lib/api";
import { GraphTraversal } from "./reasoning-chain";

// Dynamic import for react-force-graph-2d
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full bg-slate-900">
      <Loader2 className="w-6 h-6 animate-spin text-emerald-400" />
    </div>
  ),
});

// =============================================================================
// TYPES
// =============================================================================

interface GraphNode {
  id: string;
  label?: string;  // API returns singular
  labels?: string[]; // Sometimes plural
  name: string;
  properties: Record<string, unknown>;
}

interface GraphRelationship {
  id: string;
  type: string;
  source: string;
  target: string;
  properties: Record<string, unknown>;
}

interface FullGraphData {
  nodes: GraphNode[];
  relationships: GraphRelationship[];
}

interface ForceNode {
  id: string;
  name: string;
  labels: string[];
  properties: Record<string, unknown>;
  layer: "inventory" | "domain" | "playbook" | "unknown";
  isActive: boolean;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number;
  fy?: number;
}

interface ForceLink {
  source: string | ForceNode;
  target: string | ForceNode;
  type: string;
  isActive: boolean;
}

interface GlobalGraphViewerProps {
  traversals?: GraphTraversal[];
  height?: number;
  defaultFocusMode?: boolean;
}

// =============================================================================
// LAYER CLASSIFICATION
// =============================================================================

const INVENTORY_LABELS = [
  "ProductFamily",
  "ProductVariant",
  "Material",
  "Size",
  "Category",
  "Feature",
  "Option",
  "Component",
];

const DOMAIN_LABELS = [
  "Application",
  "Risk",
  "Requirement",
  "Resistance",
  "PhysicalLaw",
  "Regulation",
  "Substance",
  "Environment",
  "CorrosionClass",
];

const PLAYBOOK_LABELS = [
  "Parameter",
  "Question",
  "Strategy",
  "Rule",
  "ClarificationRule",
  "SizingRule",
  "Intent",
];

function classifyNode(labels: string[]): "inventory" | "domain" | "playbook" | "unknown" {
  for (const label of labels) {
    if (INVENTORY_LABELS.includes(label)) return "inventory";
    if (DOMAIN_LABELS.includes(label)) return "domain";
    if (PLAYBOOK_LABELS.includes(label)) return "playbook";
  }
  return "unknown";
}

// =============================================================================
// LAYER COLORS (Cyberpunk Theme)
// =============================================================================

const LAYER_STYLES = {
  inventory: {
    color: "#5B8C3E", // Blue
    glowColor: "#7CB356",
    ghostColor: "#1e3a5f",
    label: "Inventory",
    icon: Database,
  },
  domain: {
    color: "#f97316", // Orange
    glowColor: "#fb923c",
    ghostColor: "#5c3a1a",
    label: "Domain",
    icon: AlertTriangle,
  },
  playbook: {
    color: "#a855f7", // Purple
    glowColor: "#c084fc",
    ghostColor: "#4a2070",
    label: "Playbook",
    icon: BookOpen,
  },
  unknown: {
    color: "#6b7280",
    glowColor: "#9ca3af",
    ghostColor: "#374151",
    label: "Other",
    icon: Database,
  },
};

// =============================================================================
// HELPER: Extract active node IDs from traversals
// =============================================================================

function extractActiveNodeIds(traversals: GraphTraversal[]): Set<string> {
  const ids = new Set<string>();

  traversals.forEach((t) => {
    // Extract from nodes_visited
    t.nodes_visited.forEach((nodeStr) => {
      // Parse "Type:Name" or just "Name"
      const colonIdx = nodeStr.indexOf(":");
      const name = colonIdx >= 0 ? nodeStr.slice(colonIdx + 1).trim() : nodeStr.trim();
      // Remove status markers
      const cleanName = name.replace(/[✓✗⛔]/g, "").trim();
      if (cleanName) ids.add(cleanName.toLowerCase());
    });

    // Extract from path_description
    if (t.path_description) {
      const matches = t.path_description.match(/[A-Za-z0-9_]+(?=:|──|→|$)/g);
      matches?.forEach((m) => {
        const clean = m.replace(/[✓✗⛔]/g, "").trim();
        if (clean && clean.length > 1) ids.add(clean.toLowerCase());
      });
    }
  });

  return ids;
}

// =============================================================================
// NODE DETAIL PANEL
// =============================================================================

interface NodeDetailPanelProps {
  node: ForceNode | null;
  onClose: () => void;
}

function NodeDetailPanel({ node, onClose }: NodeDetailPanelProps) {
  if (!node) return null;

  const style = LAYER_STYLES[node.layer];
  const Icon = style.icon;

  return (
    <div className="absolute top-4 right-4 w-72 bg-slate-800/95 backdrop-blur-sm border border-slate-700 rounded-xl shadow-2xl overflow-hidden z-30">
      {/* Header */}
      <div
        className="px-4 py-3 border-b border-slate-700 flex items-center justify-between"
        style={{ backgroundColor: `${style.color}20` }}
      >
        <div className="flex items-center gap-2">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: style.color }}
          >
            <Icon className="w-4 h-4 text-white" />
          </div>
          <div>
            <h4 className="font-semibold text-white text-sm truncate max-w-[180px]">
              {node.name}
            </h4>
            <p className="text-xs text-slate-400">{node.labels.join(", ")}</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Properties */}
      <div className="p-4 max-h-64 overflow-auto">
        <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-2">
          Properties
        </p>
        {Object.keys(node.properties).length > 0 ? (
          <div className="space-y-2">
            {Object.entries(node.properties)
              .filter(([k]) => !["embedding", "id"].includes(k))
              .slice(0, 8)
              .map(([key, value]) => (
                <div key={key} className="flex justify-between gap-2">
                  <span className="text-xs text-slate-500 truncate">{key}</span>
                  <span className="text-xs text-slate-300 font-medium truncate max-w-[140px]">
                    {String(value).slice(0, 40)}
                  </span>
                </div>
              ))}
          </div>
        ) : (
          <p className="text-xs text-slate-500 italic">No properties</p>
        )}

        {/* Active indicator */}
        {node.isActive && (
          <div className="mt-4 px-3 py-2 bg-emerald-500/20 border border-emerald-500/30 rounded-lg">
            <p className="text-xs text-emerald-400 font-medium">
              Active in current inference
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export function GlobalGraphViewer({
  traversals = [],
  height = 500,
  defaultFocusMode = false,
}: GlobalGraphViewerProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fullGraph, setFullGraph] = useState<FullGraphData | null>(null);
  // Default to Global View (focusMode = false) to show all nodes
  const [focusMode, setFocusMode] = useState(false);
  const [selectedNode, setSelectedNode] = useState<ForceNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<ForceNode | null>(null);
  const graphRef = useRef<any>(null);

  // Extract active node IDs from traversals
  const activeNodeIds = useMemo(
    () => extractActiveNodeIds(traversals),
    [traversals]
  );

  // Fetch full graph data
  useEffect(() => {
    async function fetchGraph() {
      setLoading(true);
      setError(null);

      try {
        const response = await fetch(apiUrl("/graph/data"), authFetch());
        if (!response.ok) throw new Error("Failed to fetch graph data");

        const data: FullGraphData = await response.json();
        setFullGraph(data);
      } catch (err) {
        console.error("Error fetching graph:", err);
        setError("Failed to load knowledge graph");
      } finally {
        setLoading(false);
      }
    }

    fetchGraph();
  }, []);

  // Build force graph data with active highlighting
  const forceGraphData = useMemo(() => {
    if (!fullGraph) return { nodes: [], links: [] };

    const nodes: ForceNode[] = fullGraph.nodes.map((node) => {
      // Handle both label (singular) and labels (plural) formats
      const nodeLabels = node.labels || (node.label ? [node.label] : []);
      const nameLower = node.name?.toLowerCase() || "";
      const idLower = node.id?.toLowerCase() || "";
      const isActive =
        activeNodeIds.has(nameLower) ||
        activeNodeIds.has(idLower) ||
        nodeLabels.some((l) => activeNodeIds.has(l.toLowerCase()));

      return {
        id: node.id,
        name: node.name || node.id,
        labels: nodeLabels,
        properties: node.properties || {},
        layer: classifyNode(nodeLabels),
        isActive,
      };
    });

    // In focus mode, only show active nodes
    const filteredNodes = focusMode
      ? nodes.filter((n) => n.isActive)
      : nodes;

    const nodeIds = new Set(filteredNodes.map((n) => n.id));

    const links: ForceLink[] = fullGraph.relationships
      .filter((rel) => nodeIds.has(rel.source) && nodeIds.has(rel.target))
      .map((rel) => {
        const sourceNode = filteredNodes.find((n) => n.id === rel.source);
        const targetNode = filteredNodes.find((n) => n.id === rel.target);
        const isActive = sourceNode?.isActive && targetNode?.isActive;

        return {
          source: rel.source,
          target: rel.target,
          type: rel.type,
          isActive: isActive ?? false,
        };
      });

    return { nodes: filteredNodes, links };
  }, [fullGraph, activeNodeIds, focusMode]);

  // Stats
  const stats = useMemo(() => {
    const total = fullGraph?.nodes.length || 0;
    const active = forceGraphData.nodes.filter((n) => n.isActive).length;
    return { total, active };
  }, [fullGraph, forceGraphData]);

  // Center on active nodes after load
  useEffect(() => {
    if (!loading && graphRef.current && forceGraphData.nodes.length > 0) {
      setTimeout(() => {
        if (focusMode || stats.active > 0) {
          graphRef.current?.zoomToFit(500, 50);
        } else {
          graphRef.current?.zoomToFit(500, 100);
        }
      }, 1000);
    }
  }, [loading, focusMode, stats.active, forceGraphData.nodes.length]);

  // Zoom controls
  const handleZoomIn = useCallback(() => {
    graphRef.current?.zoom(1.5, 300);
  }, []);

  const handleZoomOut = useCallback(() => {
    graphRef.current?.zoom(0.67, 300);
  }, []);

  const handleFit = useCallback(() => {
    graphRef.current?.zoomToFit(400, 50);
  }, []);

  // Node click
  const handleNodeClick = useCallback((node: any) => {
    setSelectedNode(node as ForceNode);
  }, []);

  // Node hover
  const handleNodeHover = useCallback((node: any) => {
    setHoveredNode(node as ForceNode | null);
  }, []);

  // Custom node rendering (Ghost & Neon effect)
  const nodeCanvasObject = useCallback(
    (nodeAny: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const node = nodeAny as ForceNode;
      const x = node.x || 0;
      const y = node.y || 0;
      const style = LAYER_STYLES[node.layer];
      const isHovered = hoveredNode?.id === node.id;
      const isSelected = selectedNode?.id === node.id;

      // Size based on active state
      let size = node.isActive ? 8 : 4;
      if (isHovered || isSelected) size *= 1.3;

      // Opacity based on active state - make ghost nodes more visible
      const alpha = node.isActive ? 1 : 0.4;

      ctx.save();
      ctx.globalAlpha = alpha;

      // Glow effect for active nodes
      if (node.isActive) {
        ctx.shadowColor = style.glowColor;
        ctx.shadowBlur = isHovered ? 20 : 12;
      }

      // Draw node
      const color = node.isActive ? style.color : style.ghostColor;

      ctx.beginPath();
      ctx.arc(x, y, size, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();

      // Border for active nodes
      if (node.isActive) {
        ctx.strokeStyle = style.glowColor;
        ctx.lineWidth = isSelected ? 2 : 1;
        ctx.stroke();
      }

      // Pulsing ring for active nodes
      if (node.isActive && !focusMode) {
        const time = Date.now() / 1000;
        const pulseAlpha = 0.3 + Math.sin(time * 2) * 0.2;
        ctx.globalAlpha = pulseAlpha;
        ctx.beginPath();
        ctx.arc(x, y, size * 2, 0, 2 * Math.PI);
        ctx.strokeStyle = style.glowColor;
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      ctx.shadowBlur = 0;
      ctx.globalAlpha = alpha;

      // Label for active or hovered nodes
      const showLabel = (node.isActive && globalScale > 0.3) || isHovered || isSelected;
      if (showLabel) {
        const fontSize = Math.max(8 / globalScale, 3);
        ctx.font = `${node.isActive ? "600" : "400"} ${fontSize}px Inter, system-ui, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";

        const label = node.name.length > 12 ? node.name.slice(0, 11) + ".." : node.name;
        const labelY = y + size + 2;

        // Background
        const metrics = ctx.measureText(label);
        ctx.globalAlpha = 0.9;
        ctx.fillStyle = "#0f172a";
        ctx.fillRect(
          x - metrics.width / 2 - 2,
          labelY - 1,
          metrics.width + 4,
          fontSize + 3
        );

        // Text
        ctx.globalAlpha = node.isActive ? 1 : 0.5;
        ctx.fillStyle = node.isActive ? style.glowColor : "#64748b";
        ctx.fillText(label, x, labelY);
      }

      ctx.restore();
    },
    [hoveredNode, selectedNode, focusMode]
  );

  // Custom link rendering
  const linkCanvasObject = useCallback(
    (linkAny: any, ctx: CanvasRenderingContext2D) => {
      const link = linkAny as ForceLink;
      const source = link.source as ForceNode;
      const target = link.target as ForceNode;

      if (!source.x || !source.y || !target.x || !target.y) return;

      ctx.save();

      // Style based on active state - make ghost links more visible
      const alpha = link.isActive ? 0.8 : 0.2;
      const width = link.isActive ? 2 : 0.5;
      const color = link.isActive ? "#059669" : "#475569";

      ctx.globalAlpha = alpha;
      ctx.strokeStyle = color;
      ctx.lineWidth = width;

      // Animated dash for active links
      if (link.isActive) {
        const time = Date.now() / 80;
        ctx.setLineDash([4, 2]);
        ctx.lineDashOffset = -time;
      }

      ctx.beginPath();
      ctx.moveTo(source.x, source.y);
      ctx.lineTo(target.x, target.y);
      ctx.stroke();

      ctx.setLineDash([]);
      ctx.restore();
    },
    []
  );

  // Loading state
  if (loading) {
    return (
      <div
        className="flex items-center justify-center bg-slate-900 rounded-xl"
        style={{ height }}
      >
        <div className="text-center">
          <Loader2 className="w-8 h-8 animate-spin text-emerald-400 mx-auto mb-3" />
          <p className="text-sm text-slate-400">Loading Knowledge Graph...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div
        className="flex items-center justify-center bg-slate-900 rounded-xl"
        style={{ height }}
      >
        <p className="text-sm text-red-400">{error}</p>
      </div>
    );
  }

  return (
    <div className="relative rounded-xl overflow-hidden border border-slate-700" style={{ height }}>
      {/* Graph Canvas */}
      <div
        className="absolute inset-0"
        style={{
          background: "radial-gradient(ellipse at center, #0f172a 0%, #020617 100%)",
        }}
      >
        {/* Grid pattern */}
        <div
          className="absolute inset-0 opacity-10"
          style={{
            backgroundImage:
              "linear-gradient(#334155 1px, transparent 1px), linear-gradient(90deg, #334155 1px, transparent 1px)",
            backgroundSize: "40px 40px",
          }}
        />

        <ForceGraph2D
          ref={graphRef}
          graphData={forceGraphData}
          height={height}
          nodeCanvasObject={nodeCanvasObject}
          linkCanvasObject={linkCanvasObject}
          onNodeClick={handleNodeClick}
          onNodeHover={handleNodeHover}
          nodeRelSize={1}
          d3AlphaDecay={0.01}
          d3VelocityDecay={0.4}
          cooldownTime={5000}
          enableZoomInteraction={true}
          enablePanInteraction={true}
          enableNodeDrag={true}
          // @ts-expect-error d3Force exists in library but missing from types
          d3Force={(name, force) => {
            if (name === "charge") {
              force.strength((node: any) => (node.isActive ? -100 : -30));
            }
            if (name === "link") {
              force.distance(60);
            }
            // Cluster by layer
            if (name === "x") {
              force.strength((node: any) => {
                const layer = (node as ForceNode).layer;
                if (layer === "inventory") return 0.05;
                if (layer === "domain") return 0;
                if (layer === "playbook") return -0.05;
                return 0;
              });
            }
          }}
        />
      </div>

      {/* Header Controls */}
      <div className="absolute top-4 left-4 flex items-center gap-2 z-20">
        <div className="px-3 py-1.5 bg-slate-800/90 backdrop-blur-sm rounded-lg border border-slate-700">
          <span className="text-xs font-semibold text-emerald-400">
            Global Knowledge Map
          </span>
        </div>

        {/* View Mode Toggle */}
        <button
          onClick={() => setFocusMode(!focusMode)}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors",
            focusMode
              ? "bg-emerald-500/20 border-emerald-500/50 text-emerald-400"
              : "bg-green-500/20 border-green-600/50 text-green-500"
          )}
        >
          {focusMode ? (
            <>
              <Eye className="w-3.5 h-3.5" />
              Focus Mode (Active Only)
            </>
          ) : (
            <>
              <EyeOff className="w-3.5 h-3.5" />
              Global Mode (All {stats.total} Nodes)
            </>
          )}
        </button>
      </div>

      {/* Layer Legend */}
      <div className="absolute top-4 right-4 flex flex-col gap-1 z-20">
        {(["inventory", "domain", "playbook"] as const).map((layer) => {
          const style = LAYER_STYLES[layer];
          const Icon = style.icon;
          return (
            <div
              key={layer}
              className="flex items-center gap-2 px-2.5 py-1 bg-slate-800/90 backdrop-blur-sm rounded-md border border-slate-700"
            >
              <span
                className="w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: style.color, boxShadow: `0 0 6px ${style.glowColor}` }}
              />
              <span className="text-[10px] font-medium text-slate-300">
                {style.label}
              </span>
            </div>
          );
        })}
      </div>

      {/* Zoom Controls */}
      <div className="absolute bottom-16 right-4 flex flex-col gap-1 z-20">
        <button
          onClick={handleZoomIn}
          className="p-2 bg-slate-800/90 backdrop-blur-sm rounded-lg border border-slate-700 text-slate-400 hover:text-white transition-colors"
        >
          <ZoomIn className="w-4 h-4" />
        </button>
        <button
          onClick={handleZoomOut}
          className="p-2 bg-slate-800/90 backdrop-blur-sm rounded-lg border border-slate-700 text-slate-400 hover:text-white transition-colors"
        >
          <ZoomOut className="w-4 h-4" />
        </button>
        <button
          onClick={handleFit}
          className="p-2 bg-slate-800/90 backdrop-blur-sm rounded-lg border border-slate-700 text-slate-400 hover:text-white transition-colors"
        >
          <Maximize2 className="w-4 h-4" />
        </button>
      </div>

      {/* Stats Footer */}
      <div className="absolute bottom-0 left-0 right-0 px-4 py-2 bg-slate-900/95 backdrop-blur-sm border-t border-slate-700 flex items-center justify-between z-20">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <Database className="w-3.5 h-3.5 text-slate-500" />
            <span className="text-xs text-slate-400">
              Knowledge Base:{" "}
              <span className="text-white font-semibold">
                {stats.total.toLocaleString()}
              </span>{" "}
              nodes
            </span>
          </div>
          <div className="w-px h-4 bg-slate-700" />
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_6px_#34d399]" />
            <span className="text-xs text-slate-400">
              Active Context:{" "}
              <span className="text-emerald-400 font-semibold">{stats.active}</span>{" "}
              nodes
            </span>
          </div>
        </div>

        {stats.active > 0 && (
          <span className="text-[10px] text-slate-500">
            {((stats.active / stats.total) * 100).toFixed(1)}% of graph active
          </span>
        )}
      </div>

      {/* Node Detail Panel */}
      <NodeDetailPanel
        node={selectedNode}
        onClose={() => setSelectedNode(null)}
      />

      {/* Hover Tooltip */}
      {hoveredNode && !selectedNode && (
        <div
          className="absolute z-30 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-xs text-white pointer-events-none"
          style={{
            left: Math.min((hoveredNode.x || 0) + 20, 200),
            top: (hoveredNode.y || 0) + height / 2 - 10,
          }}
        >
          {hoveredNode.name}
        </div>
      )}
    </div>
  );
}

export default GlobalGraphViewer;
