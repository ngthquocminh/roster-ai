import { ChevronDown } from "lucide-react";
import { useState } from "react";

import type { ScheduleRunResult } from "@/api/scheduleRuns";
import { InlineAlert } from "@/components/primitives/InlineAlert";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import { ProvenanceTimeline } from "@/features/provenance/ProvenanceTimeline";
import { useRunProvenance } from "@/hooks/useRunProvenance";

type EvidenceRefs = NonNullable<ScheduleRunResult["comparison"]>["evidence_refs"];

/** Troubleshooting data (evidence IDs, decision provenance): collapsed by default, provenance fetched on first open. */
export function DebugDetailsPanel({ runId, scenarioId, evidenceRefs }: Readonly<{ runId: string; scenarioId: string; evidenceRefs: EvidenceRefs | null }>) {
  const [open, setOpen] = useState(false);
  const provenance = useRunProvenance(runId, open);

  return (
    <Collapsible className="rounded-xl border p-4" onOpenChange={setOpen} open={open}>
      <CollapsibleTrigger asChild>
        {/* `whitespace-normal`/`h-auto` override the button's nowrap: at 200% zoom
            the one-line label pushed the chevron past the viewport (WCAG 1.4.10).
            The subtitle is not `text-muted-foreground`: an open ghost trigger sits
            on `bg-muted`, where muted text measures 4.34:1 (WCAG 1.4.3). */}
        <Button className="h-auto min-h-11 w-full justify-between gap-3 whitespace-normal text-left" type="button" variant="ghost">
          <span>Debug details <span className="font-normal">— evidence and decision provenance, for troubleshooting</span></span>
          <ChevronDown aria-hidden="true" className={`size-4 transition-transform ${open ? "rotate-180" : ""}`} />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-3 space-y-5">
        {evidenceRefs ? (
          <section aria-labelledby="result-evidence-heading">
            <h3 className="font-semibold" id="result-evidence-heading">Evidence</h3>
            {evidenceRefs.length ? <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{evidenceRefs.map((ref) => <li key={`${ref.group}:${ref.record_id}`}>{ref.group}: {ref.record_id}</li>)}</ul> : <p className="mt-2 text-sm">No evidence references</p>}
          </section>
        ) : null}
        <section aria-labelledby="decision-provenance-heading">
          <h3 className="font-semibold" id="decision-provenance-heading">Decision provenance</h3>
          {provenance.isPending ? <div aria-label="Loading decision provenance" className="mt-3"><Skeleton className="h-28 w-full" /></div> : null}
          {provenance.isError ? <div className="mt-3"><InlineAlert action={<Button onClick={() => { void provenance.refetch(); }} type="button" variant="outline">Retry provenance</Button>} description="The decision record could not be loaded. Results remain available." title="Decision provenance unavailable" variant="destructive" /></div> : null}
          {provenance.data ? <div className="mt-3"><ProvenanceTimeline provenance={provenance.data} scenarioId={scenarioId} /></div> : null}
        </section>
      </CollapsibleContent>
    </Collapsible>
  );
}
