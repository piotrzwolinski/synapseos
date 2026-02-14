"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import dynamic from "next/dynamic";
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Network,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { GraphTraversal } from "./reasoning-chain";
import {
  transformTraversalsToGraph,
  TraversalGraphData,
  TraversalNode,
  TraversalLink,
  TraversalStep,
  LAYER_COLORS,
  getNodeStateAtStep,
  getEdgeStateAtStep,
} from "@/lib/traversal-transform";

// Dynamic import for react-force-graph-2d (needs client-side only)
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

interface TraversalGraphPlayerProps {
  traversals: GraphTraversal[];
  defaultCollapsed?: boolean;
}

// Force graph node type (extended for rendering)
interface ForceNode extends TraversalNode {
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number;
  fy?: number;
  __status?: "active" | "visited" | "inactive";
}

// Force graph link type (extended for rendering)
interface ForceLink extends Omit<TraversalLink, "source" | "target"> {
  source: string | ForceNode;
  target: string | ForceNode;
  __status?: "active" | "visited" | "inactive";
}

// =============================================================================
// AUTO-PLAY SPEEDS
// =============================================================================

const AUTOPLAY_SPEEDS = [
  { label: "Off", value: 0 },
  { label: "Slow", value: 2500 },
  { label: "Normal", value: 1500 },
  { label: "Fast", value: 800 },
];

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

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

// =============================================================================
// STEP CONTROLS COMPONENT
// =============================================================================

interface StepControlsProps {
  current: number;
  total: number;
  isPlaying: boolean;
  autoplaySpeed: number;
  onStepChange: (step: number) => void;
  onPlayToggle: () => void;
  onSpeedChange: (speed: number) => void;
}

function StepControls({
  current,
  total,
  isPlaying,
  autoplaySpeed,
  onStepChange,
  onPlayToggle,
  onSpeedChange,
}: StepControlsProps) {
  const [showSpeedDropdown, setShowSpeedDropdown] = useState(false);

  const currentSpeedLabel =
    AUTOPLAY_SPEEDS.find((s) => s.value === autoplaySpeed)?.label || "Off";

  return (
    <div className="flex items-center justify-between px-3 py-2 bg-slate-50 border-t border-slate-200">
      {/* Navigation Controls */}
      <div className="flex items-center gap-1">
        <button
          onClick={() => onStepChange(0)}
          disabled={current === 0}
          className={cn(
            "p-1.5 rounded-md transition-colors",
            current === 0
              ? "text-slate-300 cursor-not-allowed"
              : "text-slate-500 hover:bg-slate-200 hover:text-slate-700"
          )}
          title="First step"
        >
          <SkipBack className="w-4 h-4" />
        </button>
        <button
          onClick={() => onStepChange(Math.max(0, current - 1))}
          disabled={current === 0}
          className={cn(
            "p-1.5 rounded-md transition-colors",
            current === 0
              ? "text-slate-300 cursor-not-allowed"
              : "text-slate-500 hover:bg-slate-200 hover:text-slate-700"
          )}
          title="Previous step"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        <button
          onClick={onPlayToggle}
          className={cn(
            "p-2 rounded-lg transition-colors",
            isPlaying
              ? "bg-blue-100 text-blue-600"
              : "bg-slate-200 text-slate-600 hover:bg-blue-50 hover:text-blue-600"
          )}
          title={isPlaying ? "Pause" : "Play"}
        >
          {isPlaying ? (
            <Pause className="w-4 h-4" />
          ) : (
            <Play className="w-4 h-4" />
          )}
        </button>
        <button
          onClick={() => onStepChange(Math.min(total - 1, current + 1))}
          disabled={current === total - 1}
          className={cn(
            "p-1.5 rounded-md transition-colors",
            current === total - 1
              ? "text-slate-300 cursor-not-allowed"
              : "text-slate-500 hover:bg-slate-200 hover:text-slate-700"
          )}
          title="Next step"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
        <button
          onClick={() => onStepChange(total - 1)}
          disabled={current === total - 1}
          className={cn(
            "p-1.5 rounded-md transition-colors",
            current === total - 1
              ? "text-slate-300 cursor-not-allowed"
              : "text-slate-500 hover:bg-slate-200 hover:text-slate-700"
          )}
          title="Last step"
        >
          <SkipForward className="w-4 h-4" />
        </button>
      </div>

      {/* Step Counter */}
      <div className="text-xs font-medium text-slate-600">
        Step{" "}
        <span className="text-blue-600">
          {current + 1}/{total}
        </span>
      </div>

      {/* Auto-play Speed */}
      <div className="relative">
        <button
          onClick={() => setShowSpeedDropdown(!showSpeedDropdown)}
          className="flex items-center gap-1.5 px-2 py-1 text-xs font-medium text-slate-600 bg-white border border-slate-200 rounded-md hover:bg-slate-50 transition-colors"
        >
          <span className="text-slate-400">Auto:</span>
          <span>{currentSpeedLabel}</span>
          <ChevronDown className="w-3 h-3 text-slate-400" />
        </button>
        {showSpeedDropdown && (
          <div className="absolute right-0 bottom-full mb-1 bg-white border border-slate-200 rounded-lg shadow-lg z-20 py-1 min-w-[100px]">
            {AUTOPLAY_SPEEDS.map((speed) => (
              <button
                key={speed.label}
                onClick={() => {
                  onSpeedChange(speed.value);
                  setShowSpeedDropdown(false);
                }}
                className={cn(
                  "w-full px-3 py-1.5 text-xs text-left transition-colors",
                  speed.value === autoplaySpeed
                    ? "bg-blue-50 text-blue-700 font-medium"
                    : "text-slate-600 hover:bg-slate-50"
                )}
              >
                {speed.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// =============================================================================
// STEP INFO PANEL COMPONENT
// =============================================================================

interface StepInfoPanelProps {
  step: TraversalStep | null;
}

function StepInfoPanel({ step }: StepInfoPanelProps) {
  const [showCypher, setShowCypher] = useState(false);

  if (!step) return null;

  const layerConfig = LAYER_COLORS[step.layer as keyof typeof LAYER_COLORS];

  return (
    <div
      className={cn(
        "px-3 py-2 border-t",
        step.isViolation
          ? "bg-red-50 border-red-200"
          : "bg-slate-50 border-slate-200"
      )}
    >
      {/* Operation Title */}
      <div className="flex items-center gap-2 mb-1.5">
        <span
          className={cn(
            "flex-shrink-0 w-5 h-5 rounded text-[10px] font-bold text-white flex items-center justify-center",
            step.isViolation ? "bg-red-500" : ""
          )}
          style={{ backgroundColor: step.isViolation ? undefined : layerConfig?.bg }}
        >
          {step.layer}
        </span>
        <span
          className={cn(
            "text-xs font-semibold",
            step.isViolation ? "text-red-700" : "text-slate-700"
          )}
        >
          {step.isViolation && "⚠️ "}
          {step.operation}
        </span>
        <span className="text-[10px] text-slate-400">({step.layerName})</span>
      </div>

      {/* Result Summary */}
      {step.resultSummary && (
        <div
          className={cn(
            "px-2.5 py-1.5 rounded text-xs",
            step.isViolation
              ? "bg-red-100 text-red-800 border border-red-200"
              : "bg-white text-slate-700 border border-slate-200"
          )}
        >
          {step.isViolation ? "⚠️ " : "✓ "}
          {step.resultSummary}
        </div>
      )}

      {/* Cypher Pattern (collapsible) */}
      {step.cypherPattern && (
        <details className="mt-1.5">
          <summary className="text-[10px] text-slate-400 cursor-pointer hover:text-slate-600">
            Cypher Query ▸
          </summary>
          <code className="block mt-1 px-2 py-1 bg-slate-800 text-emerald-400 text-[10px] rounded font-mono overflow-x-auto whitespace-pre-wrap">
            {step.cypherPattern}
          </code>
        </details>
      )}
    </div>
  );
}

// =============================================================================
// MAIN COMPONENT: TRAVERSAL GRAPH PLAYER
// =============================================================================

export function TraversalGraphPlayer({
  traversals,
  defaultCollapsed = true,
}: TraversalGraphPlayerProps) {
  const [isExpanded, setIsExpanded] = useState(!defaultCollapsed);
  const [currentStep, setCurrentStep] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [autoplaySpeed, setAutoplaySpeed] = useState(0);
  const [hoveredNode, setHoveredNode] = useState<ForceNode | null>(null);
  const graphRef = useRef<any>(null);

  // Transform traversals to graph data
  const graphData = useMemo(
    () => transformTraversalsToGraph(traversals),
    [traversals]
  );

  // Get current step data
  const currentStepData = graphData.steps[currentStep] || null;

  // Calculate node and edge states for current step
  const nodeStates = useMemo(
    () => getNodeStateAtStep(graphData.nodes, graphData.steps, currentStep),
    [graphData.nodes, graphData.steps, currentStep]
  );

  const edgeStates = useMemo(
    () => getEdgeStateAtStep(graphData.links, currentStep),
    [graphData.links, currentStep]
  );

  // Build force graph data with status
  const forceGraphData = useMemo(() => {
    const nodes: ForceNode[] = graphData.nodes.map((node) => ({
      ...node,
      __status: nodeStates.get(node.id) || "inactive",
    }));

    const links: ForceLink[] = graphData.links.map((link) => ({
      ...link,
      __status: edgeStates.get(`${link.source}-${link.target}`) || "inactive",
    }));

    return { nodes, links };
  }, [graphData.nodes, graphData.links, nodeStates, edgeStates]);

  // Auto-play logic
  useEffect(() => {
    if (!isPlaying || autoplaySpeed === 0) return;

    const timer = setTimeout(() => {
      if (currentStep < graphData.steps.length - 1) {
        setCurrentStep((s) => s + 1);
      } else {
        setIsPlaying(false);
      }
    }, autoplaySpeed);

    return () => clearTimeout(timer);
  }, [isPlaying, currentStep, autoplaySpeed, graphData.steps.length]);

  // Center graph when expanded
  useEffect(() => {
    if (isExpanded && graphRef.current) {
      setTimeout(() => {
        graphRef.current?.zoomToFit(400, 30);
      }, 300);
    }
  }, [isExpanded]);

  // Handle play toggle
  const handlePlayToggle = useCallback(() => {
    if (autoplaySpeed === 0) {
      // If speed is off, set to normal speed and start playing
      setAutoplaySpeed(1500);
      setIsPlaying(true);
    } else {
      setIsPlaying((p) => !p);
    }
  }, [autoplaySpeed]);

  // Handle speed change
  const handleSpeedChange = useCallback((speed: number) => {
    setAutoplaySpeed(speed);
    if (speed === 0) {
      setIsPlaying(false);
    }
  }, []);

  // Zoom controls
  const handleZoomIn = useCallback(() => {
    graphRef.current?.zoom(1.5, 300);
  }, []);

  const handleZoomOut = useCallback(() => {
    graphRef.current?.zoom(0.67, 300);
  }, []);

  const handleFit = useCallback(() => {
    graphRef.current?.zoomToFit(300, 40);
  }, []);

  // Node hover
  const handleNodeHover = useCallback((node: any) => {
    setHoveredNode(node as ForceNode | null);
  }, []);

  // Custom node canvas rendering
  const nodeCanvasObject = useCallback(
    (nodeAny: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const node = nodeAny as ForceNode;
      const x = node.x || 0;
      const y = node.y || 0;
      const status = node.__status || "inactive";
      const isHovered = hoveredNode?.id === node.id;

      // Get layer color
      const layerColors = LAYER_COLORS[node.layer] || LAYER_COLORS[1];
      const baseColor = node.isViolation ? "#ef4444" : layerColors.bg;

      // Calculate size and opacity based on status
      let size = 6;
      let alpha = 1;
      let glowColor = baseColor;

      if (status === "active") {
        size = 10;
        alpha = 1;
        glowColor = node.isViolation ? "#ef4444" : "#3b82f6";
      } else if (status === "visited") {
        size = 7;
        alpha = 0.85;
      } else {
        size = 5;
        alpha = 0.35;
      }

      if (isHovered) {
        size *= 1.15;
      }

      ctx.save();
      ctx.globalAlpha = alpha;

      // Draw glow for active nodes
      if (status === "active") {
        ctx.shadowColor = glowColor;
        ctx.shadowBlur = 15;
      }

      // Draw node circle with gradient
      const gradient = ctx.createRadialGradient(
        x - size * 0.3,
        y - size * 0.3,
        0,
        x,
        y,
        size
      );
      gradient.addColorStop(0, lightenColor(baseColor, 30));
      gradient.addColorStop(1, baseColor);

      ctx.beginPath();
      ctx.arc(x, y, size, 0, 2 * Math.PI);
      ctx.fillStyle = gradient;
      ctx.fill();

      // Draw border
      ctx.shadowBlur = 0;
      ctx.strokeStyle =
        status === "active"
          ? darkenColor(baseColor, 30)
          : darkenColor(baseColor, 10);
      ctx.lineWidth = status === "active" ? 2.5 : 1.5;
      ctx.stroke();

      // Draw pulsing animation ring for active nodes
      if (status === "active") {
        const time = Date.now() / 1000;
        const pulseScale = 1 + Math.sin(time * 3) * 0.15;
        ctx.globalAlpha = 0.4 * (1 - Math.sin(time * 3) * 0.5);
        ctx.beginPath();
        ctx.arc(x, y, size * pulseScale * 1.6, 0, 2 * Math.PI);
        ctx.strokeStyle = glowColor;
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.globalAlpha = alpha;
      }

      // Draw label - always show for active/visited, or when zoomed in
      const showLabel = status === "active" || status === "visited" || isHovered || globalScale > 1.2;
      if (showLabel) {
        const fontSize = Math.max(9 / globalScale, 3);
        ctx.font = `${status === "active" ? "600" : "400"} ${fontSize}px Inter, system-ui, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";

        const labelY = y + size + 3;
        const label =
          node.label.length > 15
            ? node.label.slice(0, 14) + ".."
            : node.label;

        // Draw label background with border for better contrast
        const metrics = ctx.measureText(label);
        const padding = 2;
        ctx.fillStyle = "rgba(255,255,255,0.95)";
        ctx.strokeStyle = "rgba(0,0,0,0.1)";
        ctx.lineWidth = 0.5;
        ctx.beginPath();
        ctx.roundRect(
          x - metrics.width / 2 - padding,
          labelY - 1,
          metrics.width + padding * 2,
          fontSize + 3,
          2
        );
        ctx.fill();
        ctx.stroke();

        // Draw label text
        ctx.fillStyle = status === "active" ? "#0f172a" : "#475569";
        ctx.fillText(label, x, labelY + 1);
      }

      ctx.restore();
    },
    [hoveredNode]
  );

  // Custom link rendering
  const linkCanvasObject = useCallback(
    (linkAny: any, ctx: CanvasRenderingContext2D) => {
      const link = linkAny as ForceLink;
      const source = link.source as ForceNode;
      const target = link.target as ForceNode;
      const status = link.__status || "inactive";

      if (!source.x || !source.y || !target.x || !target.y) return;

      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const len = Math.sqrt(dx * dx + dy * dy);
      if (len === 0) return;

      const nx = dx / len;
      const ny = dy / len;

      // Offset from node edges
      const sourceSize = status === "active" ? 12 : 8;
      const targetSize = status === "active" ? 16 : 12;

      const startX = source.x + nx * sourceSize;
      const startY = source.y + ny * sourceSize;
      const endX = target.x - nx * targetSize;
      const endY = target.y - ny * targetSize;

      ctx.save();

      // Set styles based on status
      let lineColor = "#cbd5e1";
      let lineWidth = 1.5;
      let alpha = 0.3;

      if (status === "active") {
        const currentStepInfo = graphData.steps[currentStep];
        lineColor = currentStepInfo?.isViolation ? "#ef4444" : "#3b82f6";
        lineWidth = 3;
        alpha = 1;
      } else if (status === "visited") {
        lineColor = "#64748b";
        lineWidth = 2;
        alpha = 0.7;
      }

      ctx.globalAlpha = alpha;

      // Draw animated dash for active edges
      if (status === "active") {
        const time = Date.now() / 100;
        ctx.setLineDash([8, 4]);
        ctx.lineDashOffset = -time;
      }

      // Draw line
      ctx.beginPath();
      ctx.moveTo(startX, startY);
      ctx.lineTo(endX, endY);
      ctx.strokeStyle = lineColor;
      ctx.lineWidth = lineWidth;
      ctx.stroke();
      ctx.setLineDash([]);

      // Draw arrow
      const arrowLen = status === "active" ? 10 : 7;
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
      ctx.fillStyle = lineColor;
      ctx.fill();

      // Draw relationship label for active edges
      if (status === "active" && link.relationship) {
        const midX = (startX + endX) / 2;
        const midY = (startY + endY) / 2;

        ctx.font = "bold 9px Inter, system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";

        const label = link.relationship.replace(/_/g, " ");
        const metrics = ctx.measureText(label);

        // Background
        ctx.fillStyle = "rgba(255,255,255,0.95)";
        ctx.fillRect(
          midX - metrics.width / 2 - 4,
          midY - 6,
          metrics.width + 8,
          12
        );

        // Text
        ctx.fillStyle = lineColor;
        ctx.fillText(label, midX, midY);
      }

      ctx.restore();
    },
    [currentStep, graphData.steps]
  );

  // Don't render if no traversals
  if (!traversals || traversals.length === 0) {
    return null;
  }

  return (
    <div className="mt-3 border border-slate-200 rounded-lg overflow-hidden bg-white">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 px-3 py-2 bg-slate-50 hover:bg-slate-100 transition-colors"
      >
        <Network className="w-4 h-4 text-blue-600" />
        <span className="text-xs font-semibold text-slate-700">
          Graph Traversal Viewer
        </span>
        <span className="text-[10px] text-slate-400">
          {graphData.nodes.length} nodes · {graphData.steps.length} steps
        </span>
        <ChevronDown
          className={cn(
            "w-4 h-4 ml-auto text-slate-400 transition-transform",
            isExpanded ? "" : "-rotate-90"
          )}
        />
      </button>

      {/* Expanded Content */}
      {isExpanded && (
        <>
          {/* Graph Canvas */}
          <div
            className="relative"
            style={{
              height: 300,
              background: "linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)",
            }}
          >
            {/* Grid pattern */}
            <div
              className="absolute inset-0 opacity-30"
              style={{
                backgroundImage:
                  "radial-gradient(circle, #cbd5e1 1px, transparent 1px)",
                backgroundSize: "20px 20px",
              }}
            />

            {/* Force Graph */}
            <ForceGraph2D
              ref={graphRef}
              graphData={forceGraphData}
              width={undefined}
              height={300}
              nodeCanvasObject={nodeCanvasObject}
              linkCanvasObject={linkCanvasObject}
              onNodeHover={handleNodeHover}
              nodeRelSize={1}
              d3AlphaDecay={0.02}
              d3VelocityDecay={0.4}
              cooldownTime={3000}
              enableZoomInteraction={true}
              enablePanInteraction={true}
              enableNodeDrag={true}
              // @ts-expect-error d3Force exists in library but missing from types
              d3Force={(name, force) => {
                if (name === 'charge') {
                  force.strength(-150);
                }
                if (name === 'link') {
                  force.distance(80);
                }
              }}
            />

            {/* Tooltip */}
            {hoveredNode && (
              <div
                className="absolute z-20 bg-white rounded-lg shadow-lg border border-slate-200 p-2 max-w-[180px] pointer-events-none"
                style={{
                  left: Math.min((hoveredNode.x || 0) + 20, 260),
                  top: Math.max((hoveredNode.y || 0) + 150, 10),
                }}
              >
                <div className="font-semibold text-slate-800 text-xs mb-0.5">
                  {hoveredNode.label}
                </div>
                <div className="text-[10px] text-slate-500">{hoveredNode.type}</div>
                <div className="flex items-center gap-1 mt-1">
                  <span
                    className="w-2 h-2 rounded-full"
                    style={{
                      backgroundColor:
                        LAYER_COLORS[hoveredNode.layer]?.bg || "#94a3b8",
                    }}
                  />
                  <span className="text-[10px] text-slate-400">
                    Layer {hoveredNode.layer}: {LAYER_COLORS[hoveredNode.layer]?.label}
                  </span>
                </div>
              </div>
            )}

            {/* Zoom Controls */}
            <div className="absolute bottom-3 right-3 flex gap-1">
              <button
                onClick={handleZoomIn}
                className="p-1.5 bg-white rounded-md border border-slate-200 hover:bg-slate-50 text-slate-600 shadow-sm transition-colors"
                title="Zoom in"
              >
                <ZoomIn className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={handleZoomOut}
                className="p-1.5 bg-white rounded-md border border-slate-200 hover:bg-slate-50 text-slate-600 shadow-sm transition-colors"
                title="Zoom out"
              >
                <ZoomOut className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={handleFit}
                className="p-1.5 bg-white rounded-md border border-slate-200 hover:bg-slate-50 text-slate-600 shadow-sm transition-colors"
                title="Fit to view"
              >
                <Maximize2 className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Layer Legend */}
            <div className="absolute top-3 left-3 flex flex-col gap-1">
              {([1, 2, 3] as const).map((layer) => {
                const hasNodes = graphData.nodes.some((n) => n.layer === layer);
                if (!hasNodes) return null;

                const config = LAYER_COLORS[layer];
                return (
                  <div
                    key={layer}
                    className="flex items-center gap-1.5 px-2 py-1 bg-white/95 rounded-md text-[10px] text-slate-600 shadow-sm border border-slate-100"
                  >
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: config.bg }}
                    />
                    <span className="font-medium">{config.label}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Step Info Panel */}
          <StepInfoPanel step={currentStepData} />

          {/* Step Controls */}
          <StepControls
            current={currentStep}
            total={graphData.steps.length}
            isPlaying={isPlaying}
            autoplaySpeed={autoplaySpeed}
            onStepChange={setCurrentStep}
            onPlayToggle={handlePlayToggle}
            onSpeedChange={handleSpeedChange}
          />
        </>
      )}
    </div>
  );
}

export default TraversalGraphPlayer;
