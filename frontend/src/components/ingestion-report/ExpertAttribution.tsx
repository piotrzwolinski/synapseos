"use client";

import { Card } from "@/components/ui/card";
import { Award, User, Quote } from "lucide-react";
import { Expert } from "./types";

interface ExpertAttributionProps {
  expert: Expert;
}

export function ExpertAttribution({ expert }: ExpertAttributionProps) {
  // Generate initials from name
  const initials = expert.name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase();

  return (
    <Card className="overflow-hidden border border-slate-200 dark:border-slate-700 shadow-md h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-700 bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-950/30 dark:to-orange-950/20">
        <div className="flex items-center gap-2">
          <Award className="w-4 h-4 text-amber-600" />
          <span className="text-xs font-semibold text-amber-800 dark:text-amber-300 uppercase tracking-wider">
            Knowledge Source
          </span>
        </div>
      </div>

      {/* Expert Profile */}
      <div className="p-5">
        <div className="flex flex-col items-center text-center">
          {/* Avatar */}
          <div className="relative mb-3">
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center shadow-lg">
              <span className="text-xl font-bold text-white">{initials}</span>
            </div>
            <div className="absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-amber-400 flex items-center justify-center shadow-md border-2 border-white dark:border-slate-800">
              <Award className="w-3 h-3 text-white" />
            </div>
          </div>

          {/* Name & Role */}
          <h4 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-0.5">
            {expert.name}
          </h4>
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">{expert.role}</p>

          {/* Contribution */}
          <div className="w-full p-3 rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-100 dark:border-slate-700">
            <div className="flex items-start gap-2">
              <Quote className="w-4 h-4 text-slate-300 dark:text-slate-600 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-slate-600 dark:text-slate-400 italic leading-relaxed text-left">
                {expert.contribution}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="px-4 py-2 bg-slate-50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-700">
        <p className="text-[9px] text-slate-400 dark:text-slate-500 text-center">
          This expert's knowledge is now part of the AI playbook
        </p>
      </div>
    </Card>
  );
}
