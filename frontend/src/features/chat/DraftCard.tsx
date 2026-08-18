import { useEffect, useId, useState } from "react";

import type { ProposalConstraint } from "@/api/proposals";
import { InlineAlert } from "@/components/primitives/InlineAlert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { useProposal } from "@/hooks/useProposal";
import { useRejectProposal } from "@/hooks/useRejectProposal";
import { useReviseProposal } from "@/hooks/useReviseProposal";

const PARAMETER: Record<ProposalConstraint["kind"], { key: keyof ProposalConstraint; label: string }> = {
  set_min_workers_per_task: { key: "n", label: "Minimum workers" },
  scale_demand: { key: "factor", label: "Demand factor" },
  lock_worker_shift: { key: "start_minute", label: "Start minute" },
  exclude_worker_from_task: { key: "n", label: "No numeric parameter" },
  set_max_hours: { key: "max_hours", label: "Maximum hours" },
};

function Identifier({ children }: Readonly<{ children: string }>) {
  return <code className="font-mono text-xs break-all">{children}</code>;
}

export function DraftCard({ proposalId }: Readonly<{ proposalId: string }>) {
  const query = useProposal(proposalId);
  const revision = useReviseProposal(proposalId);
  const rejection = useRejectProposal(proposalId);
  const staleDescriptionId = useId();
  const [constraints, setConstraints] = useState<ProposalConstraint[]>([]);
  const [selected, setSelected] = useState("0");

  useEffect(() => {
    if (query.data) {
      setConstraints(query.data.constraints);
      setSelected("0");
    }
  }, [query.data]);

  if (query.isPending) {
    return <p className="text-sm text-muted-foreground">Loading draft proposal…</p>;
  }
  if (query.isError || !query.data) {
    return (
      <InlineAlert
        action={<Button className="min-h-11" onClick={() => query.refetch()} variant="outline">Retry</Button>}
        description="The proposal could not be loaded."
        title="Draft unavailable"
        variant="destructive"
      />
    );
  }

  const proposal = query.data;
  const selectedIndex = Math.min(Number(selected), Math.max(constraints.length - 1, 0));
  const current = constraints[selectedIndex];
  const parameter = current ? PARAMETER[current.kind] : null;
  const updateNumber = (key: keyof ProposalConstraint, raw: string) => {
    const value = raw === "" ? null : Number(raw);
    setConstraints((existing) => existing.map((constraint, index) =>
      index === selectedIndex ? { ...constraint, [key]: value } : constraint,
    ));
  };

  return (
    <Card aria-label="Draft proposal" role="region">
      <CardHeader>
        <CardTitle>Draft — no baseline change</CardTitle>
        <CardDescription>{proposal.consequence_summary}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {proposal.stale ? (
          <div aria-label="Draft is stale" className="rounded-lg border border-destructive/40 p-3" role="status">
            <p className="font-medium text-destructive">Draft is stale</p>
            <p className="text-sm text-muted-foreground" id={staleDescriptionId}>
              The scenario version changed. Refresh before revising this proposal.
            </p>
          </div>
        ) : null}

        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div><dt className="text-muted-foreground">Expected scenario version</dt><dd><Identifier>{proposal.scenario_version_id}</Identifier></dd></div>
          <div><dt className="text-muted-foreground">Current scenario version</dt><dd><Identifier>{proposal.current_scenario_version_id}</Identifier></dd></div>
          <div><dt className="text-muted-foreground">Expected baseline version</dt><dd><Identifier>{proposal.expected_baseline_schedule_version ?? "No baseline version"}</Identifier></dd></div>
          <div><dt className="text-muted-foreground">Proposal version</dt><dd><Identifier>{proposal.proposal_version_id}</Identifier></dd></div>
        </dl>

        <section aria-labelledby={`${staleDescriptionId}-entities`}>
          <h3 className="text-sm font-medium" id={`${staleDescriptionId}-entities`}>Resolved entities</h3>
          <ul className="mt-1 space-y-1 text-sm">
            {proposal.resolved_entities.map((entity) => (
              <li key={`${entity.group}:${entity.record_id}`}>
                {entity.label} · <Identifier>{entity.record_id}</Identifier> · {entity.group}
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby={`${staleDescriptionId}-constraints`} className="space-y-2">
          <h3 className="text-sm font-medium" id={`${staleDescriptionId}-constraints`}>Constraints and objectives</h3>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {proposal.constraints.map((constraint, index) => <li key={`${constraint.kind}-${index}`}>{constraint.description}</li>)}
          </ul>
          {constraints.length ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1 text-sm">
                <span>Constraint to revise</span>
                <Select onValueChange={setSelected} value={String(selectedIndex)}>
                  <SelectTrigger className="min-h-11 w-full" aria-label="Constraint to revise"><SelectValue /></SelectTrigger>
                  <SelectContent>{constraints.map((constraint, index) => <SelectItem key={`${constraint.kind}-${index}`} value={String(index)}>{constraint.description}</SelectItem>)}</SelectContent>
                </Select>
              </label>
              {current && parameter && current.kind !== "exclude_worker_from_task" ? (
                <label className="space-y-1 text-sm">
                  <span>{parameter.label}</span>
                  <Input
                    aria-label={parameter.label}
                    className="min-h-11"
                    disabled={proposal.stale}
                    min="0"
                    onChange={(event) => updateNumber(parameter.key, event.target.value)}
                    type="number"
                    value={String(current[parameter.key] ?? "")}
                  />
                </label>
              ) : null}
              {current?.kind === "lock_worker_shift" ? (
                <label className="space-y-1 text-sm">
                  <span>End minute</span>
                  <Input aria-label="End minute" className="min-h-11" disabled={proposal.stale} min="0" onChange={(event) => updateNumber("end_minute", event.target.value)} type="number" value={String(current.end_minute ?? "")} />
                </label>
              ) : null}
            </div>
          ) : null}
        </section>

        <section aria-labelledby={`${staleDescriptionId}-locks`}>
          <h3 className="text-sm font-medium" id={`${staleDescriptionId}-locks`}>Preserved locks</h3>
          {proposal.preserved_locks.length ? (
            <ul className="mt-1 space-y-1 text-sm">{proposal.preserved_locks.map((lock) => <li key={lock.record_id}><Identifier>{lock.record_id}</Identifier> · {lock.scope} · {lock.target_ref}</li>)}</ul>
          ) : <p className="text-sm text-muted-foreground">No existing locks.</p>}
        </section>
      </CardContent>
      <CardFooter className="block space-y-3">
        {proposal.stale ? (
          <Button className="min-h-11" onClick={() => query.refetch()} type="button" variant="outline">Refresh proposal</Button>
        ) : proposal.state === "active" ? (
          <>
            <div>
              <Button
                aria-describedby={proposal.stale ? staleDescriptionId : undefined}
                className="min-h-11"
                disabled={proposal.stale || revision.isPending}
                onClick={() => revision.mutate({ constraints, expected_resource_version: proposal.resource_version })}
                type="button"
              >Revise proposal</Button>
            </div>
            <Separator />
            <div>
              <Button className="min-h-11" disabled={rejection.isPending} onClick={() => rejection.mutate({ expected_resource_version: proposal.resource_version })} type="button" variant="destructive">Reject proposal</Button>
            </div>
          </>
        ) : <p className="text-sm text-muted-foreground">This proposal was rejected.</p>}
      </CardFooter>
      {proposal.stale ? (
        <button aria-describedby={staleDescriptionId} aria-label="Revise proposal" className="sr-only" disabled type="button" />
      ) : null}
    </Card>
  );
}
