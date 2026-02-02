"use client";

import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { PlusCircle, Lock, Package, TrendingUp, Check, BrainCircuit } from "lucide-react";
import { ActionProposalData } from "./types";
import { cn } from "@/lib/utils";

interface ActionCardProps {
  data: ActionProposalData;
}

export function ActionCard({ data }: ActionCardProps) {
  const handleAddToQuote = () => {
    if (data.is_locked) return;
    console.log("Add to quote:", data.product_name);
    alert(`Added ${data.product_name} to quote`);
  };

  return (
    <Card
      className={cn(
        "shadow-sm overflow-hidden transition-all",
        data.is_locked
          ? "border-slate-200 bg-slate-50 opacity-60 grayscale"
          : "border-emerald-200 bg-gradient-to-br from-emerald-50/50 to-teal-50/30"
      )}
    >
      {/* Accent bar */}
      <div
        className={cn(
          "h-1",
          data.is_locked
            ? "bg-slate-300"
            : "bg-gradient-to-r from-emerald-500 to-teal-500"
        )}
      />

      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle
            className={cn(
              "flex items-center gap-2 text-base font-semibold",
              data.is_locked ? "text-slate-500" : "text-emerald-900"
            )}
          >
            {data.title}
          </CardTitle>
          {data.is_locked && (
            <Badge variant="secondary" className="text-xs gap-1">
              <Lock className="w-3 h-3" />
              Locked
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="pb-3 space-y-4">
        {/* Reasoning / Explainability Section */}
        {data.reasoning && (data.reasoning.source_project || data.reasoning.trigger_event) && (
          <div
            className={cn(
              "flex items-start gap-3 p-3 rounded-lg border",
              data.is_locked
                ? "bg-slate-100 border-slate-200"
                : "bg-blue-50 border-blue-100"
            )}
          >
            <BrainCircuit
              className={cn(
                "w-5 h-5 mt-0.5 flex-shrink-0",
                data.is_locked ? "text-slate-400" : "text-blue-600"
              )}
            />
            <div className="flex-1 min-w-0">
              <p
                className={cn(
                  "text-xs font-semibold uppercase tracking-wider mb-1",
                  data.is_locked ? "text-slate-400" : "text-blue-700"
                )}
              >
                Why this recommendation
              </p>
              <p
                className={cn(
                  "text-sm leading-relaxed",
                  data.is_locked ? "text-slate-500" : "text-blue-900"
                )}
              >
                {data.reasoning.source_project && (
                  <>Based on <span className="font-semibold">{data.reasoning.source_project}</span></>
                )}
                {data.reasoning.author && (
                  <>, solution by <span className="font-medium">{data.reasoning.author}</span></>
                )}
                {data.reasoning.trigger_event && (
                  <> to address: <span className="italic">{data.reasoning.trigger_event}</span></>
                )}
              </p>
              {data.reasoning.confidence && (
                <p
                  className={cn(
                    "text-xs mt-1.5 font-medium",
                    data.is_locked ? "text-slate-400" : "text-blue-600"
                  )}
                >
                  Confidence: {data.reasoning.confidence}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Product Name */}
        <div
          className={cn(
            "flex items-center gap-3 p-3 rounded-lg border",
            data.is_locked
              ? "bg-slate-100 border-slate-200"
              : "bg-white border-emerald-100"
          )}
        >
          <div
            className={cn(
              "w-10 h-10 rounded-lg flex items-center justify-center",
              data.is_locked ? "bg-slate-200" : "bg-emerald-100"
            )}
          >
            <Package
              className={cn(
                "w-5 h-5",
                data.is_locked ? "text-slate-400" : "text-emerald-600"
              )}
            />
          </div>
          <div>
            <p
              className={cn(
                "text-xs font-medium uppercase tracking-wider mb-0.5",
                data.is_locked ? "text-slate-400" : "text-slate-500"
              )}
            >
              Product
            </p>
            <p
              className={cn(
                "font-semibold",
                data.is_locked ? "text-slate-500" : "text-slate-900"
              )}
            >
              {data.product_name}
            </p>
          </div>
        </div>

        {/* Specs */}
        <div className="space-y-2">
          <p
            className={cn(
              "text-xs font-semibold uppercase tracking-wider",
              data.is_locked ? "text-slate-400" : "text-slate-500"
            )}
          >
            Specifications
          </p>
          <div className="space-y-1.5">
            {(data.specs || []).map((spec, index) => (
              <div
                key={index}
                className={cn(
                  "flex items-center gap-2 text-sm",
                  data.is_locked ? "text-slate-400" : "text-slate-700"
                )}
              >
                <Check
                  className={cn(
                    "w-4 h-4 flex-shrink-0",
                    data.is_locked ? "text-slate-300" : "text-emerald-500"
                  )}
                />
                {spec}
              </div>
            ))}
          </div>
        </div>

        {/* Price Impact */}
        <div
          className={cn(
            "flex items-center gap-3 p-3 rounded-lg border",
            data.is_locked
              ? "bg-slate-100 border-slate-200"
              : "bg-amber-50 border-amber-100"
          )}
        >
          <TrendingUp
            className={cn(
              "w-5 h-5",
              data.is_locked ? "text-slate-400" : "text-amber-600"
            )}
          />
          <div>
            <p
              className={cn(
                "text-xs font-medium uppercase tracking-wider mb-0.5",
                data.is_locked ? "text-slate-400" : "text-amber-700"
              )}
            >
              Price Impact
            </p>
            <p
              className={cn(
                "font-bold",
                data.is_locked ? "text-slate-500" : "text-amber-900"
              )}
            >
              {data.price_impact}
            </p>
          </div>
        </div>
      </CardContent>

      <Separator className={data.is_locked ? "bg-slate-200" : "bg-emerald-200/50"} />

      <CardFooter className="pt-3">
        <Button
          onClick={handleAddToQuote}
          disabled={data.is_locked}
          className={cn(
            "w-full",
            data.is_locked
              ? "bg-slate-300 text-slate-500 cursor-not-allowed"
              : "bg-emerald-600 hover:bg-emerald-700"
          )}
        >
          {data.is_locked ? (
            <>
              <Lock className="w-4 h-4 mr-2" />
              Verification Required
            </>
          ) : (
            <>
              <PlusCircle className="w-4 h-4 mr-2" />
              Add to Quote
            </>
          )}
        </Button>
      </CardFooter>
    </Card>
  );
}
