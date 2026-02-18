"use client";

import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ExternalLink, History, AlertTriangle, Lightbulb, CheckCircle2 } from "lucide-react";
import { ReferenceCaseData } from "./types";

interface ReferenceCaseCardProps {
  data: ReferenceCaseData;
}

// Helper to safely extract text from any value
const getText = (value: unknown): string => {
  if (typeof value === "string") return value;
  if (typeof value === "object" && value !== null) {
    const obj = value as Record<string, unknown>;
    return String(obj.text || obj.name || obj.description || obj.value || JSON.stringify(value));
  }
  return value ? String(value) : "Not provided";
};

export function ReferenceCaseCard({ data }: ReferenceCaseCardProps) {
  // Hide widget if essential data is missing
  const projectName = getText(data?.project_name);
  const symptom = getText(data?.symptom);
  const rootCause = getText(data?.root_cause);
  const solution = getText(data?.solution);

  if (projectName === "Not provided" || (symptom === "Not provided" && rootCause === "Not provided" && solution === "Not provided")) {
    return null;
  }

  const handleViewThread = () => {
    // In a real implementation, this would navigate to the original thread
    console.log("View thread for project:", projectName);
    alert(`Would navigate to email thread for: ${projectName}`);
  };

  return (
    <Card className="border-green-200 dark:border-green-800 bg-gradient-to-br from-green-50/50 to-green-50/30 dark:from-green-950/30 dark:to-green-950/20 shadow-sm overflow-hidden">
      {/* Accent bar */}
      <div className="h-1 bg-gradient-to-r from-green-500 to-green-600" />

      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base font-semibold text-green-900 dark:text-green-200">
            <History className="w-5 h-5 text-green-700" />
            Historical Reference
          </CardTitle>
          <Badge variant="info" className="text-xs">
            Case Study
          </Badge>
        </div>
        <p className="text-lg font-bold text-slate-900 dark:text-slate-100 mt-1">
          {projectName}
        </p>
      </CardHeader>

      <CardContent className="pb-3 space-y-3">
        {/* Symptom */}
        <div className="flex items-start gap-3 p-3 rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-100 dark:border-red-800">
          <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-xs font-semibold text-red-700 dark:text-red-400 uppercase tracking-wider mb-0.5">
              Symptom
            </p>
            <p className="text-sm text-red-900 dark:text-red-200">{symptom}</p>
          </div>
        </div>

        {/* Root Cause */}
        <div className="flex items-start gap-3 p-3 rounded-lg bg-amber-50 dark:bg-amber-900/30 border border-amber-100 dark:border-amber-800">
          <Lightbulb className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-xs font-semibold text-amber-700 dark:text-amber-400 uppercase tracking-wider mb-0.5">
              Root Cause
            </p>
            <p className="text-sm text-amber-900 dark:text-amber-200">{rootCause}</p>
          </div>
        </div>

        {/* Solution */}
        <div className="flex items-start gap-3 p-3 rounded-lg bg-emerald-50 dark:bg-emerald-900/30 border border-emerald-100 dark:border-emerald-800">
          <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-xs font-semibold text-emerald-700 dark:text-emerald-400 uppercase tracking-wider mb-0.5">
              Solution Applied
            </p>
            <p className="text-sm text-emerald-900 dark:text-emerald-200">{solution}</p>
          </div>
        </div>
      </CardContent>

      <Separator className="bg-green-200/50 dark:bg-green-900/50" />

      <CardFooter className="pt-3">
        <Button
          variant="outline"
          onClick={handleViewThread}
          className="w-full border-green-200 dark:border-green-800 text-green-800 dark:text-green-500 hover:bg-green-50 dark:hover:bg-green-900/30 hover:text-green-800 dark:hover:text-green-300"
        >
          <ExternalLink className="w-4 h-4 mr-2" />
          {getText(data.link_label) || "View Details"}
        </Button>
      </CardFooter>
    </Card>
  );
}
