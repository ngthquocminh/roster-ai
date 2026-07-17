/**
 * D-04 four-outcome-treatment + D-05 no-match renderer — one submission's
 * applied/rejected/clarification/no-match outcome (CONS-02/03/04). Renders
 * the user's submitted text as the transcript's chat-convention "user line",
 * then each outcome section present in the response that came back. A
 * single response may carry BOTH `applied[]` and `rejected[]` simultaneously
 * (E5 mixed/partial-apply) — both sections render inside this one entry,
 * each with its own distinct treatment.
 *
 * `parsed_constraint` / `error` / `clarification_needed` are all
 * server-influenced strings (T-02-13) rendered only as plain JSX text
 * children — React's default escaping is the complete mitigation; no
 * `dangerouslySetInnerHTML` anywhere in this file.
 */
import { Check, X } from "lucide-react";

import { toolLabel } from "@/lib/toolLabels";
import type { TranscriptEntryData } from "./ConstraintTranscript";

export function TranscriptEntry({ entry }: { entry: TranscriptEntryData }) {
  const { submittedText, response } = entry;
  const { applied, rejected, clarification_needed, no_constraint_found } =
    response;

  return (
    <div className="flex flex-col gap-2 border-b border-border px-4 py-3 last:border-b-0">
      <p className="text-sm leading-[1.5] whitespace-pre-wrap break-words">
        {submittedText}
      </p>

      {applied.length > 0 && (
        <div className="flex flex-col gap-1">
          {applied.map((item) => (
            <div key={item.id} className="flex items-start gap-1.5">
              <Check
                className="mt-0.5 size-4 shrink-0 text-foreground"
                aria-hidden="true"
              />
              <p className="text-sm leading-[1.5] whitespace-pre-wrap break-words">
                {item.parsed_constraint}
              </p>
            </div>
          ))}
        </div>
      )}

      {rejected.length > 0 && (
        <div className="flex flex-col gap-1">
          {rejected.map((item, index) => (
            <div
              key={`${item.tool}-${index}`}
              className="flex items-start gap-1.5"
            >
              <X
                className="mt-0.5 size-4 shrink-0 text-destructive"
                aria-hidden="true"
              />
              <div className="text-destructive">
                <p className="text-sm leading-[1.5] font-medium">
                  Couldn't apply: {toolLabel(item.tool)}
                </p>
                <p className="text-sm leading-[1.5] whitespace-pre-wrap break-words">
                  {item.error}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      {clarification_needed !== null && (
        <div>
          <p className="text-sm leading-[1.5] text-muted-foreground">
            Needs clarification: {clarification_needed}
          </p>
          <p className="text-xs leading-[1.2] text-muted-foreground">
            Rephrase your constraint above and submit again.
          </p>
        </div>
      )}

      {no_constraint_found && (
        <div>
          <p className="text-sm leading-[1.5] text-muted-foreground">
            No constraint was recognized in that text.
          </p>
          <p className="text-xs leading-[1.2] text-muted-foreground">
            Try rephrasing — for example: "keep at least 2 workers on Pick at
            all times."
          </p>
        </div>
      )}
    </div>
  );
}
