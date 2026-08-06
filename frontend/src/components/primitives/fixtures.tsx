import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

import { EmptyState } from "./EmptyState";
import { EvidenceHighlight } from "./EvidenceHighlight";
import { EvidenceLink } from "./EvidenceLink";
import { InlineAlert } from "./InlineAlert";
import { ReconnectBanner } from "./ReconnectBanner";
import { StatusBadge } from "./StatusBadge";

export type PrimitiveFixture = Readonly<{
  primitive:
    | "StatusBadge"
    | "InlineAlert"
    | "Skeleton"
    | "EmptyState"
    | "ReconnectBanner"
    | "EvidenceLink"
    | "EvidenceHighlight";
  state: string;
  render: () => ReactNode;
}>;

const STATUS_STATES = [
  "queued",
  "running",
  "completed",
  "infeasible",
  "timed out",
  "cancelled",
  "failed",
  "rejected",
  "expired",
  "stale",
] as const;

export const PRIMITIVE_FIXTURES: readonly PrimitiveFixture[] = [
  ...STATUS_STATES.map((status) => ({
    primitive: "StatusBadge" as const,
    state: status,
    render: () => <StatusBadge status={status} />,
  })),
  {
    primitive: "InlineAlert",
    state: "default",
    render: () => (
      <InlineAlert
        description="The saved scenario remains available."
        title="Scenario saved."
      />
    ),
  },
  {
    primitive: "InlineAlert",
    state: "default with action",
    render: () => (
      <InlineAlert
        action={<Button className="min-h-11">Refresh</Button>}
        description="Refresh to load the latest saved scenario."
        title="A newer version is available."
      />
    ),
  },
  {
    primitive: "InlineAlert",
    state: "destructive",
    render: () => (
      <InlineAlert
        description="The requested scenario could not be loaded."
        title="Scenario unavailable."
        variant="destructive"
      />
    ),
  },
  {
    primitive: "InlineAlert",
    state: "destructive with action",
    render: () => (
      <InlineAlert
        action={<Button className="min-h-11" variant="outline">Retry</Button>}
        description="Retry the request when the connection is available."
        title="Connection unavailable."
        variant="destructive"
      />
    ),
  },
  {
    primitive: "Skeleton",
    state: "text line",
    render: () => (
      <section aria-label="Loading text line">
        <p>Loading scenario heading.</p>
        <Skeleton className="h-4 w-48" />
      </section>
    ),
  },
  {
    primitive: "Skeleton",
    state: "table region",
    render: () => (
      <section aria-label="Loading table region">
        <p>Loading scenario data table.</p>
        <div className="space-y-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      </section>
    ),
  },
  {
    primitive: "EmptyState",
    state: "without action",
    render: () => <EmptyState explanation="No scenario records are available." />,
  },
  {
    primitive: "EmptyState",
    state: "with action",
    render: () => (
      <EmptyState
        action={<a className="inline-flex min-h-11 items-center underline" href="/fixtures">Return to fixtures</a>}
        explanation="No records match the current filters."
      />
    ),
  },
  {
    primitive: "ReconnectBanner",
    state: "disconnected",
    render: () => <ReconnectBanner state="disconnected" />,
  },
  {
    primitive: "ReconnectBanner",
    state: "reconnecting",
    render: () => <ReconnectBanner state="reconnecting" />,
  },
  {
    primitive: "ReconnectBanner",
    state: "reconnected",
    render: () => <ReconnectBanner state="reconnected" />,
  },
  {
    primitive: "EvidenceLink",
    state: "record",
    render: () => (
      <EvidenceLink group="Employee" href="#employee-emp-102" record="EMP-102" version="v7" />
    ),
  },
  {
    primitive: "EvidenceLink",
    state: "field or range",
    render: () => (
      <EvidenceLink
        fieldOrRange="13:00–17:00"
        group="Demand"
        record="DEM-204"
        version="v7"
      />
    ),
  },
  {
    primitive: "EvidenceHighlight",
    state: "row",
    render: () => (
      <EvidenceHighlight>Demand DEM-204, 13:00–17:00, fixture v7.</EvidenceHighlight>
    ),
  },
  {
    primitive: "EvidenceHighlight",
    state: "record card",
    render: () => (
      <EvidenceHighlight>Employee EMP-102, fixture v7.</EvidenceHighlight>
    ),
  },
] as const;
