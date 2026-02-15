"use client";

import { Card } from "@/components/ui/card";
import {
  Sparkles,
  Bot,
  MessageSquare,
  X,
  ShieldAlert,
  TrendingUp,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Simulation } from "./types";

interface ImpactSimulatorProps {
  simulation: Simulation;
}

export function ImpactSimulator({ simulation }: ImpactSimulatorProps) {
  return (
    <Card className="overflow-hidden border border-slate-200 dark:border-slate-700 shadow-md">
      {/* Header */}
      <div className="px-5 py-3 border-b border-slate-100 dark:border-slate-700 bg-gradient-to-r from-slate-50 to-white dark:from-slate-800 dark:to-slate-800">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center">
            <Sparkles className="w-4 h-4 text-white" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              Impact Preview
            </h3>
            <p className="text-[10px] text-slate-500 dark:text-slate-400">
              See how the AI response changes with new knowledge
            </p>
          </div>
        </div>
      </div>

      {/* User Query */}
      <div className="px-5 py-3 bg-slate-50 dark:bg-slate-800 border-b border-slate-100 dark:border-slate-700">
        <div className="flex items-start gap-2">
          <MessageSquare className="w-4 h-4 text-slate-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-[10px] font-medium text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-1">
              Example Query
            </p>
            <p className="text-sm text-slate-700 dark:text-slate-300 italic">
              "{simulation.user_query}"
            </p>
          </div>
        </div>
      </div>

      {/* Split View: Before / After */}
      <div className="grid grid-cols-2 divide-x divide-slate-200 dark:divide-slate-700">
        {/* BEFORE - Old Response */}
        <div className="p-4 bg-slate-100/50 dark:bg-slate-800/50 relative">
          {/* Strikethrough overlay */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <X className="w-24 h-24 text-red-200/30" strokeWidth={1} />
          </div>

          <div className="relative">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-6 h-6 rounded-full bg-slate-300 dark:bg-slate-600 flex items-center justify-center">
                <Bot className="w-3.5 h-3.5 text-slate-500 dark:text-slate-400" />
              </div>
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                Before
              </span>
            </div>

            <div className="p-3 rounded-lg bg-white/60 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700">
              <p className="text-sm text-slate-500 dark:text-slate-400 line-through decoration-red-400/50 leading-relaxed opacity-70">
                {simulation.before_response}
              </p>
            </div>

            <div className="mt-2 flex items-center gap-1 text-[10px] text-slate-400">
              <TrendingUp className="w-3 h-3 rotate-180 text-red-400" />
              <span>Risk: Unaware of safety hazards</span>
            </div>
          </div>
        </div>

        {/* AFTER - New Response */}
        <div className="p-4 bg-emerald-50/30 dark:bg-emerald-900/10 relative">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-6 h-6 rounded-full bg-gradient-to-br from-emerald-500 to-green-600 flex items-center justify-center">
              <Bot className="w-3.5 h-3.5 text-white" />
            </div>
            <span className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">
              After (Current)
            </span>
          </div>

          <div className="p-3 rounded-lg bg-white dark:bg-slate-800 border-2 border-emerald-500 shadow-sm shadow-emerald-500/10">
            <div className="flex items-start gap-2">
              <ShieldAlert className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-slate-800 dark:text-slate-200 leading-relaxed font-medium">
                {simulation.after_response}
              </p>
            </div>
          </div>

          <div className="mt-2 flex items-center gap-1 text-[10px] text-emerald-600 dark:text-emerald-400">
            <TrendingUp className="w-3 h-3 text-emerald-500" />
            <span>Safety-aware, compliance-first response</span>
          </div>
        </div>
      </div>
    </Card>
  );
}
