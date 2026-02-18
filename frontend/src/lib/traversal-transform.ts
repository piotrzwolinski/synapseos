/**
 * Transforms GraphTraversal[] data into a format suitable for visualization
 * with react-force-graph-2d and step-by-step playback.
 */

import { GraphTraversal } from "@/components/reasoning-chain";

// =============================================================================
// TYPES
// =============================================================================

export interface TraversalNode {
  id: string;
  label: string;
  layer: 1 | 2 | 3;
  type: string;
  status: "active" | "visited" | "inactive";
  isViolation?: boolean;
}

export interface TraversalLink {
  id: string;
  source: string;
  target: string;
  relationship: string;
  stepIndex: number;
}

export interface TraversalStep {
  index: number;
  operation: string;
  layerName: string;
  layer: number;
  resultSummary: string;
  cypherPattern?: string;
  pathDescription?: string;
  activeNodeIds: string[];
  activeEdgeIds: string[];
  isViolation: boolean;
}

export interface TraversalGraphData {
  nodes: TraversalNode[];
  links: TraversalLink[];
  steps: TraversalStep[];
}

// =============================================================================
// LAYER COLORS (matching LAYER_CONFIG in reasoning-chain.tsx)
// =============================================================================

export const LAYER_COLORS = {
  1: { bg: "#5B8C3E", text: "#2d5a1e", label: "Inventory", light: "#dcfce7" }, // Blue
  2: { bg: "#f59e0b", text: "#92400e", label: "Physics", light: "#fef3c7" }, // Amber
  3: { bg: "#4A7A30", text: "#365314", label: "Playbook", light: "#f0fdf4" }, // Violet
} as const;

// =============================================================================
// PARSING UTILITIES
// =============================================================================

/**
 * Parse a node string like "RequestedMaterial:FZ" or "Application:Hospital"
 * Returns [type, name]
 */
function parseNodeString(nodeStr: string): [string, string] {
  // Handle various formats:
  // "Type:Name", "Name (Type)", "Name"

  // Format: "Type:Name"
  if (nodeStr.includes(":")) {
    const colonIndex = nodeStr.indexOf(":");
    const type = nodeStr.substring(0, colonIndex).trim();
    const name = nodeStr.substring(colonIndex + 1).trim();
    return [type, name];
  }

  // Format: "Name (Type)"
  const parenMatch = nodeStr.match(/^(.+?)\s*\(([^)]+)\)$/);
  if (parenMatch) {
    return [parenMatch[2].trim(), parenMatch[1].trim()];
  }

  // Just a name
  return ["Unknown", nodeStr.trim()];
}

/**
 * Extract node IDs (just the names) from nodes_visited array
 */
function extractNodeIds(nodesVisited: string[]): string[] {
  return nodesVisited.map((nodeStr) => {
    const [, name] = parseNodeString(nodeStr);
    return name;
  });
}

/**
 * Parse path_description to extract edges
 * Format: "UserRequest:FZ ──EVALUATE_AGAINST──▶ Application:Hospital..."
 */
function parsePathDescription(
  pathDesc: string | undefined,
  stepIndex: number
): TraversalLink[] {
  if (!pathDesc) return [];

  const edges: TraversalLink[] = [];

  // Match pattern: "NodeA ──RELATIONSHIP──▶ NodeB" or "NodeA → NodeB"
  // Also handle: "NodeA ──RELATIONSHIP── NodeB" (without arrow)
  const relationshipPattern = /([^\s─▶→]+)\s*[─]+([A-Z_]+)[─▶→]+\s*([^\s─▶→]+)/g;

  let match;
  let edgeIndex = 0;

  while ((match = relationshipPattern.exec(pathDesc)) !== null) {
    const [, sourceRaw, relationship, targetRaw] = match;

    // Parse source and target
    const [, sourceName] = parseNodeString(sourceRaw.trim());
    const [, targetName] = parseNodeString(targetRaw.trim());

    if (sourceName && targetName) {
      edges.push({
        id: `${stepIndex}-${edgeIndex}`,
        source: sourceName,
        target: targetName,
        relationship: relationship.trim(),
        stepIndex,
      });
      edgeIndex++;
    }
  }

  // Fallback: Try simpler arrow pattern "A → B"
  if (edges.length === 0) {
    const simplePattern = /([^\s→]+)\s*→\s*([^\s→]+)/g;
    while ((match = simplePattern.exec(pathDesc)) !== null) {
      const [, sourceRaw, targetRaw] = match;
      const [, sourceName] = parseNodeString(sourceRaw.trim());
      const [, targetName] = parseNodeString(targetRaw.trim());

      if (sourceName && targetName) {
        edges.push({
          id: `${stepIndex}-${edgeIndex}`,
          source: sourceName,
          target: targetName,
          relationship: "RELATES_TO",
          stepIndex,
        });
        edgeIndex++;
      }
    }
  }

  return edges;
}

/**
 * Check if a traversal result indicates a violation/error
 */
function isViolationResult(traversal: GraphTraversal): boolean {
  const summary = traversal.result_summary?.toLowerCase() || "";
  const operation = traversal.operation.toLowerCase();
  const pathDesc = traversal.path_description?.toLowerCase() || "";

  return (
    summary.includes("mismatch") ||
    summary.includes("fail") ||
    summary.includes("violation") ||
    summary.includes("❌") ||
    summary.includes("⛔") ||
    operation.includes("violation") ||
    operation.includes("mismatch") ||
    pathDesc.includes("violation") ||
    pathDesc.includes("⛔")
  );
}

// =============================================================================
// MAIN TRANSFORM FUNCTION
// =============================================================================

/**
 * Transform an array of GraphTraversal objects into visualization-ready data
 */
export function transformTraversalsToGraph(
  traversals: GraphTraversal[]
): TraversalGraphData {
  if (!traversals || traversals.length === 0) {
    return { nodes: [], links: [], steps: [] };
  }

  const nodesMap = new Map<string, TraversalNode>();
  const links: TraversalLink[] = [];
  const steps: TraversalStep[] = [];

  traversals.forEach((traversal, stepIdx) => {
    const isViolation = isViolationResult(traversal);
    const layer = (traversal.layer || 1) as 1 | 2 | 3;

    // Extract nodes from nodes_visited
    traversal.nodes_visited.forEach((nodeStr) => {
      const [type, name] = parseNodeString(nodeStr);

      if (name && !nodesMap.has(name)) {
        // Check if this node is marked as violation in the string
        const nodeIsViolation =
          nodeStr.includes("✗") ||
          nodeStr.includes("vulnerable") ||
          nodeStr.includes("⛔");

        nodesMap.set(name, {
          id: name,
          label: name,
          layer,
          type,
          status: "inactive",
          isViolation: nodeIsViolation,
        });
      }
    });

    // Extract edges from path_description
    const edges = parsePathDescription(traversal.path_description, stepIdx);

    // Also add edges based on relationships array if path parsing didn't yield results
    if (edges.length === 0 && traversal.relationships.length > 0) {
      const nodeIds = extractNodeIds(traversal.nodes_visited);
      // Create edges between consecutive nodes
      for (let i = 0; i < nodeIds.length - 1; i++) {
        const relIndex = Math.min(i, traversal.relationships.length - 1);
        edges.push({
          id: `${stepIdx}-${i}`,
          source: nodeIds[i],
          target: nodeIds[i + 1],
          relationship: traversal.relationships[relIndex] || "RELATES_TO",
          stepIndex: stepIdx,
        });
      }
    }

    links.push(...edges);

    // Create step entry
    const activeNodeIds = extractNodeIds(traversal.nodes_visited);
    const activeEdgeIds = edges.map((e) => `${e.source}-${e.target}`);

    steps.push({
      index: stepIdx,
      operation: traversal.operation,
      layerName: traversal.layer_name,
      layer: traversal.layer,
      resultSummary: traversal.result_summary || "",
      cypherPattern: traversal.cypher_pattern,
      pathDescription: traversal.path_description,
      activeNodeIds,
      activeEdgeIds,
      isViolation,
    });
  });

  return {
    nodes: Array.from(nodesMap.values()),
    links,
    steps,
  };
}

/**
 * Get the current visual state for nodes based on the current step
 */
export function getNodeStateAtStep(
  nodes: TraversalNode[],
  steps: TraversalStep[],
  currentStep: number
): Map<string, "active" | "visited" | "inactive"> {
  const state = new Map<string, "active" | "visited" | "inactive">();

  // Initialize all as inactive
  nodes.forEach((node) => {
    state.set(node.id, "inactive");
  });

  // Mark visited nodes from previous steps
  for (let i = 0; i < currentStep; i++) {
    steps[i]?.activeNodeIds.forEach((nodeId) => {
      state.set(nodeId, "visited");
    });
  }

  // Mark active nodes for current step
  steps[currentStep]?.activeNodeIds.forEach((nodeId) => {
    state.set(nodeId, "active");
  });

  return state;
}

/**
 * Get the current visual state for edges based on the current step
 */
export function getEdgeStateAtStep(
  links: TraversalLink[],
  currentStep: number
): Map<string, "active" | "visited" | "inactive"> {
  const state = new Map<string, "active" | "visited" | "inactive">();

  links.forEach((link) => {
    const edgeKey = `${link.source}-${link.target}`;

    if (link.stepIndex < currentStep) {
      state.set(edgeKey, "visited");
    } else if (link.stepIndex === currentStep) {
      state.set(edgeKey, "active");
    } else {
      state.set(edgeKey, "inactive");
    }
  });

  return state;
}
