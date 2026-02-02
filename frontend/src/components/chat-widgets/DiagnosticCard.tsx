"use client";

import { useState } from "react";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import { Mail, ClipboardCheck } from "lucide-react";
import { DiagnosticChecklistData } from "./types";
import { cn } from "@/lib/utils";

interface DiagnosticCardProps {
  data: DiagnosticChecklistData;
}

// Helper to extract text from item (handles both string and {id, text} formats)
const getItemText = (item: string | { text?: string; id?: string }): string => {
  if (typeof item === "string") return item;
  if (typeof item === "object" && item !== null) {
    return item.text || item.id || JSON.stringify(item);
  }
  return String(item);
};

export function DiagnosticCard({ data }: DiagnosticCardProps) {
  const [checkedItems, setCheckedItems] = useState<Record<number, boolean>>({});

  // Safety check for missing data
  const items = data?.items || [];

  const toggleItem = (index: number) => {
    setCheckedItems((prev) => ({
      ...prev,
      [index]: !prev[index],
    }));
  };

  const checkedCount = Object.values(checkedItems).filter(Boolean).length;
  const allChecked = items.length > 0 && checkedCount === items.length;

  const handleGenerateEmail = () => {
    // In a real implementation, this would trigger an email generation flow
    const uncheckedItems = items.filter((_, i) => !checkedItems[i]);
    console.log("Generate email for verification:", uncheckedItems);
    alert(`Email draft would include ${uncheckedItems.length} verification items`);
  };

  return (
    <Card className="border-amber-200 bg-gradient-to-br from-amber-50/50 to-orange-50/30 shadow-sm">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base font-semibold text-amber-900">
          <ClipboardCheck className="w-5 h-5 text-amber-600" />
          {data.title}
        </CardTitle>
      </CardHeader>
      <CardContent className="pb-3">
        <div className="space-y-3">
          {items.map((item, index) => (
            <label
              key={index}
              className={cn(
                "flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-all",
                checkedItems[index]
                  ? "bg-emerald-50 border-emerald-200"
                  : "bg-white border-slate-200 hover:border-amber-300 hover:bg-amber-50/50"
              )}
            >
              <Checkbox
                checked={checkedItems[index] || false}
                onCheckedChange={() => toggleItem(index)}
                className="mt-0.5"
              />
              <span
                className={cn(
                  "text-sm leading-relaxed",
                  checkedItems[index] ? "text-emerald-700 line-through" : "text-slate-700"
                )}
              >
                {getItemText(item)}
              </span>
            </label>
          ))}
        </div>

        {/* Progress indicator */}
        <div className="mt-4 flex items-center gap-2">
          <div className="flex-1 h-1.5 bg-slate-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-amber-500 to-emerald-500 transition-all duration-300"
              style={{ width: `${items.length > 0 ? (checkedCount / items.length) * 100 : 0}%` }}
            />
          </div>
          <span className="text-xs font-medium text-slate-500">
            {checkedCount}/{items.length}
          </span>
        </div>
      </CardContent>

      <Separator className="bg-amber-200/50" />

      <CardFooter className="pt-3">
        <Button
          onClick={handleGenerateEmail}
          disabled={allChecked}
          className={cn(
            "w-full",
            allChecked
              ? "bg-emerald-600 hover:bg-emerald-700"
              : "bg-amber-600 hover:bg-amber-700"
          )}
        >
          <Mail className="w-4 h-4 mr-2" />
          {allChecked ? "All Items Verified" : data.email_button_label}
        </Button>
      </CardFooter>
    </Card>
  );
}
