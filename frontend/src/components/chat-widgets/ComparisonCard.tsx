"use client";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  ArrowRight,
  CheckCircle2,
  History,
  Info,
  Plus,
  ExternalLink,
  Copy,
  Shield,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ComparisonCardData, TechCardAction } from "./types";

interface ComparisonCardProps {
  data: ComparisonCardData;
  onProjectClick?: (projectName: string) => void;
}

const getMatchTypeBadge = (matchType: string) => {
  switch (matchType) {
    case "direct":
      return {
        label: "Direct Match",
        color: "bg-emerald-100 text-emerald-700 border-emerald-200",
        icon: <CheckCircle2 className="w-3 h-3" />,
      };
    case "similar":
      return {
        label: "Similar Product",
        color: "bg-blue-100 text-blue-700 border-blue-200",
        icon: <Shield className="w-3 h-3" />,
      };
    case "partial":
      return {
        label: "Partial Match",
        color: "bg-amber-100 text-amber-700 border-amber-200",
        icon: <Info className="w-3 h-3" />,
      };
    default:
      return {
        label: "Match",
        color: "bg-slate-100 text-slate-700 border-slate-200",
        icon: null,
      };
  }
};

const getConfidenceColor = (level: string) => {
  return level === "High"
    ? "text-emerald-600 bg-emerald-50"
    : "text-amber-600 bg-amber-50";
};

const getActionIcon = (actionId: string) => {
  switch (actionId) {
    case "copy":
      return <Copy className="w-3 h-3" />;
    case "add_quote":
      return <Plus className="w-3 h-3" />;
    case "view_specs":
      return <ExternalLink className="w-3 h-3" />;
    default:
      return <ExternalLink className="w-3 h-3" />;
  }
};

export function ComparisonCard({ data, onProjectClick }: ComparisonCardProps) {
  const matchBadge = getMatchTypeBadge(data.match_type);

  const handleAction = (action: TechCardAction) => {
    console.log("Action triggered:", action.action_id, data.title);
    if (action.action_id === "copy") {
      const text = `Competitor: ${data.competitor.name}\nOur Product: ${data.our_product.name}${data.our_product.sku ? ` (${data.our_product.sku})` : ""}`;
      navigator.clipboard.writeText(text);
      alert("Product mapping copied to clipboard");
    } else if (action.action_id === "add_quote") {
      alert(`Added "${data.our_product.name}" to quote`);
    }
  };

  return (
    <Card className="overflow-hidden border-l-4 border-l-blue-500 shadow-md">
      {/* Header */}
      <div className="px-4 py-3 bg-gradient-to-r from-blue-50 to-indigo-50 border-b border-blue-100">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-blue-600" />
            <h3 className="text-sm font-semibold text-slate-900">
              {data.title}
            </h3>
          </div>
          <div className="flex items-center gap-2">
            {/* Match Type Badge */}
            <span
              className={cn(
                "flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border",
                matchBadge.color
              )}
            >
              {matchBadge.icon}
              {matchBadge.label}
            </span>
            {/* Confidence Badge */}
            <span
              className={cn(
                "px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wider",
                getConfidenceColor(data.confidence)
              )}
            >
              {data.confidence}
            </span>
          </div>
        </div>
      </div>

      {/* Product Comparison - Main Visual */}
      <div className="px-4 py-4">
        <div className="flex items-center gap-4">
          {/* Competitor Product */}
          <div className="flex-1 p-3 rounded-lg bg-red-50/50 border border-red-100">
            <p className="text-[10px] uppercase tracking-wider text-red-400 mb-1">
              Competitor
            </p>
            <p className="text-sm font-semibold text-red-700">
              {data.competitor.name}
            </p>
            {data.competitor.manufacturer && (
              <p className="text-xs text-red-500 mt-0.5">
                by {data.competitor.manufacturer}
              </p>
            )}
          </div>

          {/* Arrow */}
          <div className="flex-shrink-0">
            <div className="w-10 h-10 rounded-full bg-gradient-to-r from-blue-500 to-emerald-500 flex items-center justify-center shadow-md">
              <ArrowRight className="w-5 h-5 text-white" />
            </div>
          </div>

          {/* Our Product */}
          <div className="flex-1 p-3 rounded-lg bg-emerald-50/50 border border-emerald-200">
            <p className="text-[10px] uppercase tracking-wider text-emerald-500 mb-1">
              Our Product
            </p>
            <p className="text-sm font-bold text-emerald-700">
              {data.our_product.name}
            </p>
            <div className="flex items-center gap-2 mt-1">
              {data.our_product.sku && (
                <span className="text-xs text-emerald-600 bg-emerald-100 px-1.5 py-0.5 rounded">
                  {data.our_product.sku}
                </span>
              )}
              {data.our_product.price && (
                <span className="text-xs font-semibold text-emerald-700">
                  {data.our_product.price}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Historical Proof */}
      {data.historical_proof && (
        <div className="px-4 py-2 bg-slate-50 border-t border-slate-100">
          <div className="flex items-start gap-2">
            <History className="w-4 h-4 text-slate-400 flex-shrink-0 mt-0.5" />
            <div className="min-w-0">
              <button
                onClick={() =>
                  onProjectClick?.(data.historical_proof!.project_ref)
                }
                className={cn(
                  "text-xs font-medium text-blue-700",
                  onProjectClick
                    ? "hover:text-blue-900 hover:underline cursor-pointer"
                    : "cursor-default"
                )}
                disabled={!onProjectClick}
              >
                Validated in: {data.historical_proof.project_ref}
              </button>
              <p className="text-xs text-slate-500 mt-0.5">
                {data.historical_proof.context}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Technical Notes (Footnote) */}
      {data.technical_notes && (
        <div className="px-4 py-2 bg-amber-50/50 border-t border-amber-100">
          <div className="flex items-start gap-2">
            <Info className="w-3.5 h-3.5 text-amber-500 flex-shrink-0 mt-0.5" />
            <p className="text-[11px] text-amber-700 italic">
              {data.technical_notes}
            </p>
          </div>
        </div>
      )}

      {/* Actions */}
      {data.actions && data.actions.length > 0 && (
        <div className="px-4 py-2 border-t border-slate-100 bg-white flex justify-end gap-2">
          {data.actions.map((action, index) => (
            <Button
              key={index}
              variant={action.variant === "primary" ? "default" : "outline"}
              size="sm"
              className={cn(
                "h-7 text-xs px-3",
                action.variant === "primary"
                  ? "bg-blue-600 hover:bg-blue-700"
                  : "border-slate-200 text-slate-600 hover:bg-slate-100"
              )}
              onClick={() => handleAction(action)}
            >
              {getActionIcon(action.action_id)}
              <span className="ml-1">{action.label}</span>
            </Button>
          ))}
        </div>
      )}
    </Card>
  );
}
