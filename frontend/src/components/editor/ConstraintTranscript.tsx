/**
 * D-03 session-log container (UI-SPEC E3). Renders nothing — not even
 * placeholder chrome — until the first submission this session (E3/empty),
 * avoiding redundant empty-state stacking above `OverridesList`'s own empty
 * state. Populated: newest entry appended at the bottom (chat convention),
 * auto-scrolling a bottom sentinel into view whenever a new entry is
 * appended (RESEARCH.md Pattern 4 — no repo precedent, implemented per that
 * example directly). Scrolls internally within its own fixed-height region,
 * independent of `OverridesList`'s scroll (both scroll separately).
 *
 * Exports `TranscriptEntryData` — the shared entry type `ConstraintInput`
 * (plan 02-05) builds from (submittedText, response) via its `onOutcome`
 * prop, and `Editor` (plan 02-06) threads through as session `useState`.
 * The 503 provider-down path is NOT a transcript entry — it throws before a
 * 200 body exists (see `ProviderDownBanner`).
 */
import * as React from "react";

import { TranscriptEntry } from "./TranscriptEntry";
import type { components } from "@/api/schema";

export interface TranscriptEntryData {
  id: string;
  submittedText: string;
  response: components["schemas"]["ConstraintParseResponse"];
}

export function ConstraintTranscript({
  entries,
}: {
  entries: TranscriptEntryData[];
}) {
  const bottomRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [entries.length]);

  if (entries.length === 0) {
    return null;
  }

  return (
    <div className="max-h-[420px] overflow-y-auto rounded-md border border-border">
      {entries.map((entry) => (
        <TranscriptEntry key={entry.id} entry={entry} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
