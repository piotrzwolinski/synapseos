"use client";

import { useState } from "react";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ShieldAlert, AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { SafetyGuardData } from "./types";
import { cn } from "@/lib/utils";

interface SafetyGuardCardProps {
  data: SafetyGuardData;
}

export function SafetyGuardCard({ data }: SafetyGuardCardProps) {
  const [acknowledged, setAcknowledged] = useState(false);

  const isCritical = data.severity === "critical";

  const handleAcknowledge = () => {
    setAcknowledged(true);
    console.log("Safety warning acknowledged:", data.title);
  };

  return (
    <Card
      className={cn(
        "shadow-sm overflow-hidden transition-all",
        isCritical
          ? "border-red-300 dark:border-red-800 bg-gradient-to-br from-red-50/80 to-rose-50/50 dark:from-red-950/30 dark:to-rose-950/20"
          : "border-amber-300 dark:border-amber-800 bg-gradient-to-br from-amber-50/80 to-orange-50/50 dark:from-amber-950/30 dark:to-orange-950/20"
      )}
    >
      {/* Accent bar */}
      <div
        className={cn(
          "h-1.5",
          isCritical
            ? "bg-gradient-to-r from-red-500 to-rose-600"
            : "bg-gradient-to-r from-amber-500 to-orange-500"
        )}
      />

      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle
            className={cn(
              "flex items-center gap-2 text-base font-semibold",
              isCritical ? "text-red-900 dark:text-red-200" : "text-amber-900 dark:text-amber-200"
            )}
          >
            <ShieldAlert
              className={cn(
                "w-5 h-5",
                isCritical ? "text-red-600" : "text-amber-600"
              )}
            />
            {data.title}
          </CardTitle>
          <Badge
            variant={isCritical ? "destructive" : "warning"}
            className="text-xs gap-1"
          >
            <AlertTriangle className="w-3 h-3" />
            {isCritical ? "Critical" : "Warning"}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="pb-3 space-y-4">
        {/* Risk Description */}
        <div
          className={cn(
            "p-3 rounded-lg border",
            isCritical
              ? "bg-red-100/50 dark:bg-red-900/30 border-red-200 dark:border-red-800"
              : "bg-amber-100/50 dark:bg-amber-900/30 border-amber-200 dark:border-amber-800"
          )}
        >
          <p
            className={cn(
              "text-sm leading-relaxed",
              isCritical ? "text-red-900 dark:text-red-200" : "text-amber-900 dark:text-amber-200"
            )}
          >
            {data.risk_description}
          </p>
        </div>

        {/* Compliance Items */}
        <div className="space-y-2">
          <p
            className={cn(
              "text-xs font-semibold uppercase tracking-wider",
              isCritical ? "text-red-700 dark:text-red-400" : "text-amber-700 dark:text-amber-400"
            )}
          >
            Compliance Requirements
          </p>
          <div className="space-y-1.5">
            {(data.compliance_items || []).map((item, index) => (
              <div
                key={index}
                className={cn(
                  "flex items-start gap-2 text-sm",
                  isCritical ? "text-red-800 dark:text-red-300" : "text-amber-800 dark:text-amber-300"
                )}
              >
                <XCircle
                  className={cn(
                    "w-4 h-4 flex-shrink-0 mt-0.5",
                    isCritical ? "text-red-500" : "text-amber-500"
                  )}
                />
                {item}
              </div>
            ))}
          </div>
        </div>

        {/* Recommendation */}
        <div className="flex items-start gap-3 p-3 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
          <CheckCircle2 className="w-5 h-5 text-emerald-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-xs font-semibold text-emerald-700 dark:text-emerald-400 uppercase tracking-wider mb-0.5">
              Recommendation
            </p>
            <p className="text-sm text-slate-700 dark:text-slate-300">{data.recommendation}</p>
          </div>
        </div>
      </CardContent>

      <Separator
        className={isCritical ? "bg-red-200/50 dark:bg-red-800/50" : "bg-amber-200/50 dark:bg-amber-800/50"}
      />

      <CardFooter className="pt-3">
        <Button
          onClick={handleAcknowledge}
          disabled={acknowledged}
          variant={acknowledged ? "outline" : "default"}
          className={cn(
            "w-full",
            acknowledged
              ? "bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400 border-slate-200 dark:border-slate-700"
              : isCritical
              ? "bg-red-600 hover:bg-red-700"
              : "bg-amber-600 hover:bg-amber-700"
          )}
        >
          {acknowledged ? (
            <>
              <CheckCircle2 className="w-4 h-4 mr-2" />
              Acknowledged
            </>
          ) : (
            <>
              <ShieldAlert className="w-4 h-4 mr-2" />
              {data.acknowledge_label}
            </>
          )}
        </Button>
      </CardFooter>
    </Card>
  );
}
