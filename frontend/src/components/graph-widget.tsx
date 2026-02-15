"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import dynamic from "next/dynamic";
import { Loader2, AlertCircle, Network, ChevronDown, ZoomIn, ZoomOut, Maximize2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiUrl, authFetch } from "@/lib/api";

// Dynamic import for react-force-graph-2d (it uses canvas and needs client-side only)
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full">
      <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
    </div>
  ),
});

// =============================================================================
// TYPES
// =============================================================================

interface GraphNode {
  id: string;
  labels: string[];
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

interface GraphNeighborhoodResponse {
  center_node: GraphNode;
  nodes: GraphNode[];
  relationships: GraphRelationship[];
  truncated: boolean;
}

interface NodeStyle {
  color: string;
  size: number;
  icon: string;
  display_name: string;
  group?: string;
}

interface RelationshipStyle {
  color: string;
  width: number;
  dashed: boolean;
}

interface GraphLayoutConfig {
  charge_strength: number;
  link_distance: number;
  center_strength: number;
}

interface UIConfig {
  graph_visualization: {
    default: NodeStyle;
    node_styles: Record<string, NodeStyle>;
    relationship_styles: Record<string, RelationshipStyle>;
    layout: GraphLayoutConfig;
  };
  entity_card: {
    title_field: string;
    fallback_title_fields: string[];
    priority_fields: string[];
  };
}

// Force graph data types
interface ForceGraphNode {
  id: string;
  name: string;
  displayLabel: string;
  labels: string[];
  properties: Record<string, unknown>;
  color?: string;
  size?: number;
  icon?: string;
  group?: string;
  isCenter?: boolean;
  pathIndex?: number;
  // Position managed by force graph
  x?: number;
  y?: number;
}

interface ForceGraphLink {
  source: string | ForceGraphNode;
  target: string | ForceGraphNode;
  type: string;
  color?: string;
  width?: number;
  dashed?: boolean;
}

interface ForceGraphData {
  nodes: ForceGraphNode[];
  links: ForceGraphLink[];
}

// =============================================================================
// ICON MAPPING (Emoji icons for canvas rendering)
// =============================================================================

const ICON_MAP: Record<string, string> = {
  package: "📦",
  box: "📦",
  puzzle: "🧩",
  filter: "🔲",
  link: "🔗",
  shield: "🛡️",
  settings: "⚙️",
  lightbulb: "💡",
  eye: "👁️",
  "alert-triangle": "⚠️",
  "alert-circle": "⚠️",
  folder: "📁",
  briefcase: "💼",
  circle: "●",
  layers: "📚",
  zap: "⚡",
  "check-circle": "✓",
  "help-circle": "?",
};

// =============================================================================
// LABEL FORMATTING
// =============================================================================

function formatDisplayLabel(name: string, maxLength: number = 15): string {
  if (!name) return "Node";

  // If short enough, return as-is
  if (name.length <= maxLength) return name;

  // Try to split on common separators
  // Pattern: FAMILY-SIZE (e.g., GDC-600x600)
  const dashMatch = name.match(/^([A-Z]{2,4})-?(.+)$/i);
  if (dashMatch) {
    const [, family, rest] = dashMatch;
    // Check if rest contains dimensions
    const dimMatch = rest.match(/(\d+)x(\d+)/);
    if (dimMatch) {
      return `${family}\n${dimMatch[0]}`;
    }
    // Just truncate the rest
    const truncRest = rest.length > 10 ? rest.slice(0, 8) + ".." : rest;
    return `${family}\n${truncRest}`;
  }

  // For materials, show code and short description
  if (name.includes(" - ")) {
    const [code] = name.split(" - ");
    return code;
  }

  // Default: smart truncate
  if (name.length > maxLength) {
    return name.slice(0, maxLength - 2) + "..";
  }

  return name;
}

// =============================================================================
// PROPS
// =============================================================================

export interface GraphWidgetProps {
  nodeId: string | null;
  onNodeClick?: (node: GraphNode) => void;
  height?: number;
  reasoningPath?: string[];
  defaultCollapsed?: boolean;
}

// =============================================================================
// COMPONENT
// =============================================================================

export function GraphWidget({
  nodeId,
  onNodeClick,
  height = 200,
  reasoningPath,
  defaultCollapsed = false,
}: GraphWidgetProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [graphData, setGraphData] = useState<ForceGraphData | null>(null);
  const [uiConfig, setUIConfig] = useState<UIConfig | null>(null);
  const [centerNodeId, setCenterNodeId] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<ForceGraphNode | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const graphRef = useRef<any>(null);

  // Fetch UI config on mount
  useEffect(() => {
    async function fetchConfig() {
      try {
        const response = await fetch(apiUrl("/config/ui"), authFetch());
        if (response.ok) {
          const config = await response.json();
          setUIConfig(config);
        }
      } catch (err) {
        console.warn("Failed to fetch UI config, using defaults:", err);
      }
    }
    fetchConfig();
  }, []);

  // Fetch neighborhood when nodeId changes
  useEffect(() => {
    if (!nodeId) {
      setGraphData(null);
      setCenterNodeId(null);
      return;
    }

    async function fetchNeighborhood() {
      setLoading(true);
      setError(null);

      try {
        const response = await fetch(
          apiUrl(`/graph/neighborhood/${encodeURIComponent(nodeId!)}?depth=1&max_nodes=30`),
          authFetch()
        );

        if (!response.ok) {
          if (response.status === 404) {
            setError("Node not found in the graph");
          } else {
            setError("Failed to load graph neighborhood");
          }
          setGraphData(null);
          return;
        }

        const data: GraphNeighborhoodResponse = await response.json();

        // Build path index map
        const pathIndexMap = new Map<string, number>();
        if (reasoningPath) {
          reasoningPath.forEach((id, idx) => {
            pathIndexMap.set(id, idx + 1);
          });
        }

        // Transform to force graph format with enhanced styling
        const nodes: ForceGraphNode[] = data.nodes.map((node) => {
          const style = getNodeStyle(node.labels[0], uiConfig);
          const isCenter = node.id === data.center_node.id;

          return {
            id: node.id,
            name: node.name,
            displayLabel: formatDisplayLabel(node.name),
            labels: node.labels,
            properties: node.properties,
            color: style.color,
            size: isCenter ? style.size * 1.3 : style.size,
            icon: style.icon,
            group: style.group,
            isCenter,
            pathIndex: pathIndexMap.get(node.id) || pathIndexMap.get(node.name),
          };
        });

        const links: ForceGraphLink[] = data.relationships.map((rel) => {
          const style = getRelStyle(rel.type, uiConfig);
          return {
            source: rel.source,
            target: rel.target,
            type: rel.type,
            color: style.color,
            width: style.width,
            dashed: style.dashed,
          };
        });

        setGraphData({ nodes, links });
        setCenterNodeId(data.center_node.id);
        setSelectedNode(data.center_node.id);
      } catch (err) {
        console.error("Error fetching neighborhood:", err);
        setError("Failed to connect to the server");
        setGraphData(null);
      } finally {
        setLoading(false);
      }
    }

    fetchNeighborhood();
  }, [nodeId, uiConfig, reasoningPath]);

  // Center graph on load
  useEffect(() => {
    if (graphRef.current && graphData && !collapsed) {
      setTimeout(() => {
        graphRef.current?.zoomToFit(400, 30);
      }, 600);
    }
  }, [graphData, collapsed]);

  // Node click handler
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleNodeClick = useCallback(
    (nodeAny: any) => {
      const node = nodeAny as ForceGraphNode;
      setSelectedNode(node.id);
      if (onNodeClick) {
        onNodeClick({
          id: node.id,
          labels: node.labels,
          name: node.name,
          properties: node.properties,
        });
      }
    },
    [onNodeClick]
  );

  // Hover handlers
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleNodeHover = useCallback((node: any) => {
    setHoveredNode(node as ForceGraphNode | null);
  }, []);

  // Zoom controls
  const handleZoomIn = useCallback(() => {
    graphRef.current?.zoom(1.5, 300);
  }, []);

  const handleZoomOut = useCallback(() => {
    graphRef.current?.zoom(0.67, 300);
  }, []);

  const handleFit = useCallback(() => {
    if (graphRef.current && graphData && graphData.nodes.length > 0) {
      // First center at origin, then zoom to fit
      graphRef.current.centerAt(0, 0, 200);
      setTimeout(() => {
        graphRef.current?.zoomToFit(300, 40);
      }, 250);
    }
  }, [graphData]);

  // Custom node canvas rendering - Professional "Ecosystem Map" style
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const nodeCanvasObject = useCallback(
    (nodeAny: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const node = nodeAny as ForceGraphNode;
      const baseSize = node.size || 10;
      const x = node.x || 0;
      const y = node.y || 0;
      const isHovered = hoveredNode?.id === node.id;
      const isSelected = selectedNode === node.id;
      const isDimmed = selectedNode && selectedNode !== node.id && !node.isCenter;

      // Calculate dynamic size
      const size = isHovered ? baseSize * 1.15 : baseSize;
      const alpha = isDimmed ? 0.4 : 1;

      ctx.save();
      ctx.globalAlpha = alpha;

      // Draw glow/shadow for center and selected nodes
      if (node.isCenter || isSelected) {
        ctx.shadowColor = node.color || "#3b82f6";
        ctx.shadowBlur = 12;
      }

      // Draw node circle with gradient
      const gradient = ctx.createRadialGradient(x - size * 0.3, y - size * 0.3, 0, x, y, size);
      gradient.addColorStop(0, lightenColor(node.color || "#94a3b8", 30));
      gradient.addColorStop(1, node.color || "#94a3b8");

      ctx.beginPath();
      ctx.arc(x, y, size, 0, 2 * Math.PI);
      ctx.fillStyle = gradient;
      ctx.fill();

      // Draw border
      ctx.shadowBlur = 0;
      ctx.strokeStyle = node.isCenter ? "#1e293b" : darkenColor(node.color || "#94a3b8", 20);
      ctx.lineWidth = node.isCenter ? 3 : isSelected ? 2.5 : 1.5;
      ctx.stroke();

      // Draw icon in center
      const icon = ICON_MAP[node.icon || "circle"] || "●";
      const iconSize = Math.max(size * 0.8, 8);
      ctx.font = `${iconSize}px sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = "#ffffff";
      ctx.fillText(icon, x, y);

      // Draw path badge if in reasoning path
      if (node.pathIndex) {
        const badgeSize = 7;
        const badgeX = x + size * 0.75;
        const badgeY = y - size * 0.75;
        const colors = ["#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b", "#22c55e"];

        ctx.beginPath();
        ctx.arc(badgeX, badgeY, badgeSize, 0, 2 * Math.PI);
        ctx.fillStyle = colors[(node.pathIndex - 1) % colors.length];
        ctx.fill();
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1.5;
        ctx.stroke();

        ctx.fillStyle = "#ffffff";
        ctx.font = `bold ${badgeSize}px sans-serif`;
        ctx.fillText(String(node.pathIndex), badgeX, badgeY);
      }

      // Draw label - always visible for center/selected, zoom-dependent otherwise
      const showLabel = node.isCenter || isSelected || isHovered || globalScale > 0.6;
      if (showLabel) {
        const fontSize = Math.max(11 / globalScale, 4);
        ctx.font = `${node.isCenter || isSelected ? "600" : "400"} ${fontSize}px Inter, system-ui, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";

        // Text shadow for readability
        ctx.fillStyle = "rgba(255,255,255,0.9)";
        const labelY = y + size + 4;

        // Handle multi-line labels
        const lines = node.displayLabel.split("\n");
        lines.forEach((line, i) => {
          const lineY = labelY + i * (fontSize + 2);
          // Draw white background
          const metrics = ctx.measureText(line);
          ctx.fillStyle = "rgba(255,255,255,0.85)";
          ctx.fillRect(x - metrics.width / 2 - 2, lineY - 1, metrics.width + 4, fontSize + 2);
          // Draw text
          ctx.fillStyle = node.isCenter ? "#1e293b" : "#475569";
          ctx.fillText(line, x, lineY);
        });
      }

      ctx.restore();
    },
    [hoveredNode, selectedNode]
  );

  // Custom link rendering with arrows
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const linkCanvasObject = useCallback(
    (linkAny: any, ctx: CanvasRenderingContext2D) => {
      const link = linkAny as ForceGraphLink;
      const source = link.source as ForceGraphNode;
      const target = link.target as ForceGraphNode;

      if (!source.x || !source.y || !target.x || !target.y) return;

      const isDimmed = selectedNode &&
        selectedNode !== source.id &&
        selectedNode !== target.id;

      ctx.save();
      ctx.globalAlpha = isDimmed ? 0.2 : 0.6;

      // Calculate arrow position
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const len = Math.sqrt(dx * dx + dy * dy);

      if (len === 0) {
        ctx.restore();
        return;
      }

      // Normalize
      const nx = dx / len;
      const ny = dy / len;

      // Offset from node edges
      const sourceSize = (source.size || 10) + 2;
      const targetSize = (target.size || 10) + 6;

      const startX = source.x + nx * sourceSize;
      const startY = source.y + ny * sourceSize;
      const endX = target.x - nx * targetSize;
      const endY = target.y - ny * targetSize;

      // Draw line
      ctx.beginPath();
      ctx.moveTo(startX, startY);
      ctx.lineTo(endX, endY);
      ctx.strokeStyle = link.color || "#cbd5e1";
      ctx.lineWidth = link.width || 1.5;

      if (link.dashed) {
        ctx.setLineDash([6, 3]);
      }

      ctx.stroke();
      ctx.setLineDash([]);

      // Draw arrow
      const arrowLen = 6;
      const arrowWidth = 4;
      const angle = Math.atan2(dy, dx);

      ctx.beginPath();
      ctx.moveTo(endX, endY);
      ctx.lineTo(
        endX - arrowLen * Math.cos(angle - Math.PI / 6),
        endY - arrowLen * Math.sin(angle - Math.PI / 6)
      );
      ctx.lineTo(
        endX - arrowLen * Math.cos(angle + Math.PI / 6),
        endY - arrowLen * Math.sin(angle + Math.PI / 6)
      );
      ctx.closePath();
      ctx.fillStyle = link.color || "#cbd5e1";
      ctx.fill();

      ctx.restore();
    },
    [selectedNode]
  );

  // Empty state
  if (!nodeId) {
    return null;
  }

  return (
    <div className="border-b border-slate-200 dark:border-slate-700 bg-gradient-to-b from-slate-50 to-white dark:from-slate-800 dark:to-slate-800">
      {/* Collapsible Header */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-xs text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-100/50 dark:hover:bg-slate-700/50 transition-colors"
      >
        <Network className="w-4 h-4 text-blue-600" />
        <span className="font-semibold">Product Ecosystem</span>
        {graphData && (
          <span className="text-slate-400 font-normal">
            {graphData.nodes.length} nodes · {graphData.links.length} connections
          </span>
        )}
        <ChevronDown
          className={cn(
            "w-4 h-4 ml-auto text-slate-400 transition-transform duration-200",
            collapsed ? "-rotate-90" : ""
          )}
        />
      </button>

      {/* Graph Container */}
      {!collapsed && (
        <div className="relative" style={{ height, background: "linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)" }}>
          {/* Subtle grid pattern */}
          <div
            className="absolute inset-0 opacity-30"
            style={{
              backgroundImage: "radial-gradient(circle, #cbd5e1 1px, transparent 1px)",
              backgroundSize: "20px 20px"
            }}
          />

          {/* Loading State */}
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center bg-white/60 dark:bg-slate-800/60 backdrop-blur-sm z-10">
              <div className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
                <Loader2 className="w-5 h-5 animate-spin text-blue-600" />
                <span>Loading ecosystem...</span>
              </div>
            </div>
          )}

          {/* Error State */}
          {error && !loading && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 dark:bg-red-900/30 px-3 py-2 rounded-lg">
                <AlertCircle className="w-4 h-4" />
                <span>{error}</span>
              </div>
            </div>
          )}

          {/* Graph */}
          {graphData && !loading && !error && (
            <>
              <ForceGraph2D
                ref={graphRef}
                graphData={graphData}
                width={320}
                height={height}
                nodeCanvasObject={nodeCanvasObject}
                linkCanvasObject={linkCanvasObject}
                onNodeClick={handleNodeClick}
                onNodeHover={handleNodeHover}
                nodeRelSize={1}
                d3AlphaDecay={0.04}
                d3VelocityDecay={0.25}
                cooldownTime={2000}
                enableZoomInteraction={true}
                enablePanInteraction={true}
                enableNodeDrag={true}
              />

              {/* Tooltip */}
              {hoveredNode && (
                <div
                  className="absolute z-20 bg-white dark:bg-slate-800 rounded-lg shadow-lg border border-slate-200 dark:border-slate-700 p-3 max-w-[200px] pointer-events-none"
                  style={{
                    left: Math.min((hoveredNode.x || 0) + 160 + 20, 280),
                    top: Math.max((hoveredNode.y || 0) + 10, 10),
                  }}
                >
                  <div className="font-semibold text-slate-800 dark:text-slate-200 text-sm mb-1">
                    {hoveredNode.name}
                  </div>
                  <div className="text-xs text-slate-500 dark:text-slate-400 mb-2">
                    {hoveredNode.labels[0]}
                  </div>
                  {hoveredNode.properties && Object.keys(hoveredNode.properties).length > 0 && (
                    <div className="text-xs text-slate-600 dark:text-slate-400 space-y-0.5 border-t border-slate-100 dark:border-slate-700 pt-2">
                      {Object.entries(hoveredNode.properties)
                        .filter(([k]) => !["embedding", "id"].includes(k))
                        .slice(0, 3)
                        .map(([key, value]) => (
                          <div key={key} className="flex justify-between gap-2">
                            <span className="text-slate-400">{formatKey(key)}:</span>
                            <span className="font-medium truncate">{String(value).slice(0, 20)}</span>
                          </div>
                        ))}
                    </div>
                  )}
                </div>
              )}

              {/* Zoom Controls */}
              <div className="absolute bottom-3 right-3 flex gap-1.5">
                <button
                  onClick={handleZoomIn}
                  className="p-1.5 bg-white dark:bg-slate-800 rounded-md border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/50 text-slate-600 dark:text-slate-400 shadow-sm transition-colors"
                  title="Zoom in"
                >
                  <ZoomIn className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={handleZoomOut}
                  className="p-1.5 bg-white dark:bg-slate-800 rounded-md border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/50 text-slate-600 dark:text-slate-400 shadow-sm transition-colors"
                  title="Zoom out"
                >
                  <ZoomOut className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={handleFit}
                  className="p-1.5 bg-white dark:bg-slate-800 rounded-md border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/50 text-slate-600 dark:text-slate-400 shadow-sm transition-colors"
                  title="Fit to view"
                >
                  <Maximize2 className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* Legend */}
              <div className="absolute top-3 left-3 flex flex-col gap-1">
                {getUniqueGroups(graphData.nodes, uiConfig)
                  .slice(0, 4)
                  .map(({ group, color, icon }) => (
                    <div
                      key={group}
                      className="flex items-center gap-1.5 px-2 py-1 bg-white/95 dark:bg-slate-800/95 rounded-md text-[10px] text-slate-600 dark:text-slate-400 shadow-sm border border-slate-100 dark:border-slate-700"
                    >
                      <span>{ICON_MAP[icon] || "●"}</span>
                      <span className="font-medium">{group}</span>
                    </div>
                  ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

function getNodeStyle(label: string | undefined, config: UIConfig | null): NodeStyle {
  const defaultStyle: NodeStyle = {
    color: "#94a3b8",
    size: 10,
    icon: "circle",
    display_name: label || "Node",
    group: "Other",
  };

  if (!label || !config) return defaultStyle;

  const style = config.graph_visualization.node_styles[label];
  if (style) {
    return {
      ...defaultStyle,
      ...style,
      display_name: style.display_name || label,
    };
  }

  return {
    ...config.graph_visualization.default,
    display_name: label,
  };
}

function getRelStyle(type: string | undefined, config: UIConfig | null): RelationshipStyle {
  const defaultStyle: RelationshipStyle = {
    color: "#cbd5e1",
    width: 1.5,
    dashed: false,
  };

  if (!type || !config) return defaultStyle;

  const style = config.graph_visualization.relationship_styles[type];
  if (style) {
    return { ...defaultStyle, ...style };
  }

  return defaultStyle;
}

function getUniqueGroups(
  nodes: ForceGraphNode[],
  config: UIConfig | null
): { group: string; color: string; icon: string }[] {
  const groups = new Map<string, { color: string; icon: string }>();

  nodes.forEach((node) => {
    const label = node.labels[0];
    if (label && config) {
      const style = config.graph_visualization.node_styles[label];
      if (style?.group && !groups.has(style.group)) {
        groups.set(style.group, { color: style.color, icon: style.icon });
      }
    }
  });

  return Array.from(groups.entries()).map(([group, { color, icon }]) => ({
    group,
    color,
    icon,
  }));
}

function formatKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/([A-Z])/g, " $1")
    .trim()
    .split(" ")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

function lightenColor(color: string, percent: number): string {
  const num = parseInt(color.replace("#", ""), 16);
  const amt = Math.round(2.55 * percent);
  const R = Math.min(255, (num >> 16) + amt);
  const G = Math.min(255, ((num >> 8) & 0x00ff) + amt);
  const B = Math.min(255, (num & 0x0000ff) + amt);
  return `#${((1 << 24) | (R << 16) | (G << 8) | B).toString(16).slice(1)}`;
}

function darkenColor(color: string, percent: number): string {
  const num = parseInt(color.replace("#", ""), 16);
  const amt = Math.round(2.55 * percent);
  const R = Math.max(0, (num >> 16) - amt);
  const G = Math.max(0, ((num >> 8) & 0x00ff) - amt);
  const B = Math.max(0, (num & 0x0000ff) - amt);
  return `#${((1 << 24) | (R << 16) | (G << 8) | B).toString(16).slice(1)}`;
}

export default GraphWidget;
