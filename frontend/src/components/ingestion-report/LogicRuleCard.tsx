"use client";

import { Card } from "@/components/ui/card";
import {
  Brain,
  Zap,
  AlertTriangle,
  ShieldCheck,
  ArrowDown,
  CheckCircle2,
  Clock,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { PlaybookRule } from "./types";

interface LogicRuleCardProps {
  rule: PlaybookRule;
}

export function LogicRuleCard({ rule }: LogicRuleCardProps) {
  return (
    <Card className="overflow-hidden border-0 shadow-lg bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <div className="px-6 py-4 border-b border-slate-700/50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-green-500 to-green-700 flex items-center justify-center shadow-lg shadow-green-600/30">
              <Brain className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white">
                New Playbook Rule Created
              </h3>
              <p className="text-xs text-slate-400">
                AI learned a new safety protocol from this email thread
              </p>
            </div>
          </div>
          <div
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold",
              rule.status === "active"
                ? "bg-emerald-500/20 text-emerald-400"
                : "bg-amber-500/20 text-amber-400"
            )}
          >
            {rule.status === "active" ? (
              <CheckCircle2 className="w-3.5 h-3.5" />
            ) : (
              <Clock className="w-3.5 h-3.5" />
            )}
            {rule.status === "active" ? "Active" : "Pending Review"}
          </div>
        </div>
      </div>

      {/* Logic Flow */}
      <div className="p-6 space-y-4">
        {/* IF - Trigger */}
        <div className="flex items-start gap-4">
          <div className="flex-shrink-0 w-16 text-right">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
              IF
            </span>
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-green-500/10 border border-green-600/30">
              <Zap className="w-4 h-4 text-green-500 flex-shrink-0" />
              <span className="text-sm text-green-200 font-medium">
                {rule.trigger}
              </span>
            </div>
          </div>
        </div>

        {/* Arrow */}
        <div className="flex items-center gap-4">
          <div className="w-16" />
          <ArrowDown className="w-5 h-5 text-slate-600 mx-4" />
        </div>

        {/* AND - Constraint */}
        <div className="flex items-start gap-4">
          <div className="flex-shrink-0 w-16 text-right">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
              AND
            </span>
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/30">
              <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
              <span className="text-sm text-red-200 font-medium">
                {rule.constraint}
              </span>
            </div>
          </div>
        </div>

        {/* Arrow */}
        <div className="flex items-center gap-4">
          <div className="w-16" />
          <ArrowDown className="w-5 h-5 text-slate-600 mx-4" />
        </div>

        {/* THEN - Outcome */}
        <div className="flex items-start gap-4">
          <div className="flex-shrink-0 w-16 text-right">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
              THEN
            </span>
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30">
              <ShieldCheck className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              <span className="text-sm text-emerald-200 font-medium">
                {rule.outcome}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="px-6 py-3 bg-slate-800/50 border-t border-slate-700/50">
        <p className="text-[10px] text-slate-500 text-center uppercase tracking-wider">
          This rule will be automatically applied to future sales conversations
        </p>
      </div>
    </Card>
  );
}
