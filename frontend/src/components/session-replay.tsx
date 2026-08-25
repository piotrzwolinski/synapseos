"use client";

import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";
import {
  ThinkingTimeline,
  ExplainableChatBubble,
  ProductCardComponent,
  RiskDetectedBanner,
  StatusBadges,
  ClarificationCard,
  ComplianceBadge,
  PolicyWarning,
  type DeepExplainableResponseData,
} from "./reasoning-chain";
import type { TurnSnapshot, FeedbackSessionReplay } from "@/lib/api";

interface SessionReplayProps {
  replay: FeedbackSessionReplay;
}

/**
 * Static replay of a chat session — iterates persisted turns and re-renders
 * the same widget tree the user saw live. Action handlers are intentionally
 * omitted (read-only), so buttons like "Select" or "Add to quote" are inert.
 */
export function SessionReplay({ replay }: SessionReplayProps) {
  if (!replay.turns || replay.turns.length === 0) {
    return (
      <div className="p-8 text-center text-sm text-slate-500 dark:text-slate-400">
        This session has no messages yet.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {replay.turns.map((turn) => (
        <TurnView key={`${turn.role}-${turn.turn_number}`} turn={turn} />
      ))}
    </div>
  );
}

function TurnView({ turn }: { turn: TurnSnapshot }) {
  const isUser = turn.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end min-w-0">
        <div className="max-w-[85%] min-w-0 rounded-2xl px-4 py-3 bg-gradient-to-br from-green-700 to-green-800 text-white">
          <p className="text-sm whitespace-pre-wrap break-words">{turn.message}</p>
          {turn.created_at && (
            <p className="text-[10px] mt-1 text-green-100/80">
              {new Date(turn.created_at).toLocaleString()}
            </p>
          )}
        </div>
      </div>
    );
  }

  // Assistant turn without persisted reasoning — legacy fallback.
  if (!turn.reasoning_data) {
    return (
      <div className="max-w-[85%] min-w-0 rounded-2xl px-4 py-3 bg-slate-50 dark:bg-slate-800 border border-slate-100 dark:border-slate-700">
        <div className="text-[11px] uppercase tracking-wide text-amber-600 dark:text-amber-400 mb-1">
          Legacy turn — not fully reproducible
        </div>
        <div className="prose-chat break-words [&_pre]:whitespace-pre-wrap [&_pre]:break-words">
          <ReactMarkdown>{turn.message || ""}</ReactMarkdown>
        </div>
      </div>
    );
  }

  // Cast persisted JSON to the shape the existing widgets expect.
  const data = turn.reasoning_data as unknown as DeepExplainableResponseData;

  return (
    <div className="max-w-[85%] min-w-0">
      <div className="space-y-3 min-w-0">
        {/* 0. STATUS BADGES */}
        {data.status_badges && data.status_badges.length > 0 && (
          <StatusBadges badges={data.status_badges} />
        )}
        {data.risk_resolved && !data.risk_detected &&
         (!data.status_badges || data.status_badges.length === 0) && (
          <ComplianceBadge />
        )}

        {/* 1. REASONING TIMELINE */}
        {data.reasoning_summary && (
          <ThinkingTimeline
            steps={data.reasoning_summary}
            defaultCollapsed={true}
          />
        )}

        {/* 2. ACTIVE RISK ALERT */}
        {data.risk_detected && (
          <RiskDetectedBanner
            warnings={data.policy_warnings}
            severity={data.risk_severity}
          />
        )}

        {/* 3. TEXT CONTENT */}
        <div
          className={cn(
            "relative rounded-xl px-4 py-3 bg-slate-50/80 dark:bg-slate-800/80",
            "min-w-0 overflow-x-auto break-words [&_pre]:whitespace-pre-wrap [&_pre]:break-words [&_code]:break-words"
          )}
        >
          {(data.content_segments?.length ?? 0) > 0 ? (
            <ExplainableChatBubble segments={data.content_segments} />
          ) : (
            <ReactMarkdown>{turn.message || ""}</ReactMarkdown>
          )}
        </div>

        {/* 4. CLARIFICATION (read-only — no onOptionSelect) */}
        {data.clarification_needed && data.clarification && (
          <div className="mt-3 pointer-events-none opacity-90">
            <ClarificationCard clarification={data.clarification} />
          </div>
        )}

        {/* 5. PRODUCT CARD(S) */}
        {!data.clarification_needed &&
          (data.product_cards?.length || data.product_card) && (
            <div className="mt-3 space-y-3">
              {data.product_cards && data.product_cards.length > 0
                ? data.product_cards.map((card, i) => (
                    <ProductCardComponent
                      key={i}
                      card={card}
                      riskSeverity={
                        data.product_cards!.length > 1
                          ? undefined
                          : data.risk_severity
                      }
                    />
                  ))
                : data.product_card && (
                    <ProductCardComponent
                      card={data.product_card}
                      riskSeverity={data.risk_severity}
                    />
                  )}
            </div>
          )}

        {/* 6. POLICY WARNINGS (if not already shown via risk banner) */}
        {!data.risk_detected &&
         data.policy_warnings &&
         data.policy_warnings.length > 0 && (
          <div className="space-y-2">
            {data.policy_warnings
              .filter((w) => w && w !== "null" && w !== "None")
              .map((warning, idx) => (
                <PolicyWarning key={idx} warning={warning} />
              ))}
          </div>
        )}

        {turn.created_at && (
          <p className="text-[10px] text-slate-400 dark:text-slate-500">
            {new Date(turn.created_at).toLocaleString()}
          </p>
        )}
      </div>
    </div>
  );
}
