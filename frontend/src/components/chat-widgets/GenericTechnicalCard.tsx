"use client";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  History,
  AlertTriangle,
  User,
  ChevronRight,
  HelpCircle,
  Copy,
  Plus,
  ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { TechnicalCardData } from "./types";

interface GenericTechnicalCardProps {
  data: TechnicalCardData;
  onProjectClick?: (projectName: string) => void;
}

const getConfidenceColor = (level: string) => {
  switch (level) {
    case "High":
      return "text-emerald-600 bg-emerald-50";
    case "Medium":
      return "text-amber-600 bg-amber-50";
    case "Low":
      return "text-red-600 bg-red-50";
    default:
      return "text-slate-600 bg-slate-50";
  }
};

const getActionIcon = (actionId: string) => {
  switch (actionId) {
    case "copy":
      return <Copy className="w-3 h-3" />;
    case "add":
      return <Plus className="w-3 h-3" />;
    default:
      return <ExternalLink className="w-3 h-3" />;
  }
};

export function GenericTechnicalCard({ data, onProjectClick }: GenericTechnicalCardProps) {
  const handleAction = (actionId: string) => {
    console.log("Action triggered:", actionId, data.title);
    if (actionId === "copy") {
      const specText = data.properties
        .map((p) => `${p.label}: ${p.value}${p.unit ? ` ${p.unit}` : ""}`)
        .join("\n");
      navigator.clipboard.writeText(`${data.title}\n${specText}`);
      alert("Specifications copied to clipboard");
    } else if (actionId === "add") {
      alert(`Added "${data.title}" to quote`);
    }
  };

  return (
    <Card className="overflow-hidden border-l-4 border-l-emerald-500 shadow-sm">
      {/* Header with Title */}
      <div className="px-4 pt-3 pb-2 border-b border-slate-100">
        <h3 className="text-sm font-semibold text-slate-900">{data.title}</h3>
      </div>

      {/* Provenance Chain */}
      <div className="px-4 py-2 bg-slate-50/80 border-b border-slate-100">
        <div className="flex items-center gap-1 text-[10px] flex-wrap">
          {/* Project Reference - Clickable for Deep Dive */}
          <button
            onClick={() => onProjectClick?.(data.reasoning.project_ref)}
            className={cn(
              "flex items-center gap-1 text-blue-700 transition-colors",
              onProjectClick
                ? "hover:text-blue-900 hover:underline cursor-pointer"
                : "cursor-default"
            )}
            disabled={!onProjectClick}
          >
            <History className="w-3 h-3" />
            <span className="font-medium">{data.reasoning.project_ref}</span>
          </button>

          <ChevronRight className="w-3 h-3 text-slate-300" />

          {/* Constraint */}
          <div className="flex items-center gap-1 text-amber-700">
            <AlertTriangle className="w-3 h-3" />
            <span>{data.reasoning.constraint}</span>
          </div>

          <ChevronRight className="w-3 h-3 text-slate-300" />

          {/* Author */}
          <div className="flex items-center gap-1 text-slate-600">
            <User className="w-3 h-3" />
            <span>{data.reasoning.author}</span>
          </div>

          {/* Confidence Badge */}
          <span
            className={cn(
              "ml-auto px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wider",
              getConfidenceColor(data.reasoning.confidence_level)
            )}
          >
            {data.reasoning.confidence_level}
          </span>
        </div>
      </div>

      {/* Properties Grid */}
      <div className="px-4 py-3">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-y-2 gap-x-4">
          {data.properties.map((prop, index) => (
            <div key={index} className="min-w-0">
              <p className="text-[10px] uppercase tracking-wider text-slate-400 mb-0.5 truncate">
                {prop.label}
              </p>
              <div className="flex items-center gap-1">
                <p
                  className={cn(
                    "text-sm font-semibold truncate",
                    prop.is_estimate ? "text-amber-700" : "text-slate-900"
                  )}
                >
                  {prop.value}
                  {prop.unit && (
                    <span className="text-xs font-normal text-slate-500 ml-0.5">
                      {prop.unit}
                    </span>
                  )}
                </p>
                {prop.is_estimate && (
                  <span title="AI Estimate - Verify with customer">
                    <HelpCircle className="w-3 h-3 text-amber-500 flex-shrink-0" />
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Actions */}
      {data.actions && data.actions.length > 0 && (
        <div className="px-4 py-2 border-t border-slate-100 bg-slate-50/50 flex justify-end gap-2">
          {data.actions.map((action, index) => (
            <Button
              key={index}
              variant={action.variant === "primary" ? "default" : "outline"}
              size="sm"
              className={cn(
                "h-7 text-xs px-3",
                action.variant === "primary"
                  ? "bg-emerald-600 hover:bg-emerald-700"
                  : "border-slate-200 text-slate-600 hover:bg-slate-100"
              )}
              onClick={() => handleAction(action.action_id)}
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
