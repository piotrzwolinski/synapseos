"use client";

import { Widget, DiagnosticChecklistData, ReferenceCaseData, ActionProposalData, SafetyGuardData, TechnicalCardData, ComparisonCardData } from "./types";
import { DiagnosticCard } from "./DiagnosticCard";
import { ReferenceCaseCard } from "./ReferenceCaseCard";
import { ActionCard } from "./ActionCard";
import { SafetyGuardCard } from "./SafetyGuardCard";
import { GenericTechnicalCard } from "./GenericTechnicalCard";
import { ComparisonCard } from "./ComparisonCard";

interface WidgetRendererProps {
  widget: Widget;
  onProjectClick?: (projectName: string) => void;
}

export function WidgetRenderer({ widget, onProjectClick }: WidgetRendererProps) {
  switch (widget.type) {
    case "safety_guard":
      return <SafetyGuardCard data={widget.data as SafetyGuardData} />;
    case "comparison_card":
      return <ComparisonCard data={widget.data as ComparisonCardData} onProjectClick={onProjectClick} />;
    case "diagnostic_checklist":
      return <DiagnosticCard data={widget.data as DiagnosticChecklistData} />;
    case "reference_case":
      return <ReferenceCaseCard data={widget.data as ReferenceCaseData} />;
    case "action_proposal":
      return <ActionCard data={widget.data as ActionProposalData} />;
    case "technical_card":
      return <GenericTechnicalCard data={widget.data as TechnicalCardData} onProjectClick={onProjectClick} />;
    default:
      return null;
  }
}

interface WidgetListProps {
  widgets: Widget[];
  onProjectClick?: (projectName: string) => void;
}

export function WidgetList({ widgets, onProjectClick }: WidgetListProps) {
  if (!widgets || widgets.length === 0) return null;

  return (
    <div className="grid gap-4 mt-4">
      {widgets.map((widget, index) => (
        <WidgetRenderer key={`${widget.type}-${index}`} widget={widget} onProjectClick={onProjectClick} />
      ))}
    </div>
  );
}
