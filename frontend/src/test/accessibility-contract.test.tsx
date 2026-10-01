import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

vi.mock("@/hooks/useScenarioProjection", () => ({
  useScenarioOverview: vi.fn(),
  useWorkAreasAndTasks: vi.fn(),
  useWorkers: vi.fn(),
  useDemand: vi.fn(),
  useBaselineAssignments: vi.fn(),
  useLocks: vi.fn(),
  useConstraintsAndObjectives: vi.fn(),
  useWorkerNameMap: vi.fn(),
  useTaskNameMap: vi.fn(),
}));
vi.mock("@/hooks/useProposal");
vi.mock("@/hooks/useReviseProposal");
vi.mock("@/hooks/useRejectProposal");
vi.mock("@/hooks/useStartScheduleRun");

import { ScenarioDataView } from "@/features/scenario-data/ScenarioDataView";
import { ScenarioVersionContext } from "@/features/scenario-workspace/ScenarioVersionContext";
import { WorkspaceTabs } from "@/features/scenario-workspace/WorkspaceTabs";
import * as hooks from "@/hooks/useScenarioProjection";
import * as proposalHooks from "@/hooks/useProposal";
import * as reviseHooks from "@/hooks/useReviseProposal";
import * as rejectHooks from "@/hooks/useRejectProposal";
import * as startHooks from "@/hooks/useStartScheduleRun";
import { ApprovalDecisionDialog } from "@/features/approvals/ApprovalDecisionDialog";

const decisionMocks = vi.hoisted(() => ({
  approval: {
    approval_id: "55555555-5555-4555-8555-555555555555", state: "pending" as const,
    schedule_run_id: "66666666-6666-4666-8666-666666666666",
    candidate_schedule_version_id: "77777777-7777-4777-8777-777777777777",
    baseline_schedule_version: "baseline-v12", scenario_version_id: "88888888-8888-4888-8888-888888888888",
    consequence_summary: "Candidate replaces baseline-v12.", policy_version: "policy-v1",
    agent_run_id: null, created_at: "2026-08-29T00:00:00Z", expires_at: "2099-08-29T00:00:00Z",
    resource_version: 1,
  },
}));
vi.mock("@/hooks/useApproval", () => ({
  approvalKey: (id: string) => ["approval", id],
  useApproval: () => ({ isSuccess: true, isPending: false, isError: false, data: decisionMocks.approval }),
}));
vi.mock("@/hooks/useDecideApproval", () => ({
  useDecideApproval: () => ({ isPending: false, isError: false, isSuccess: false, error: null, data: undefined, mutate: vi.fn() }),
}));
const decisionApproval = decisionMocks.approval;

async function expectAxeClean(container: HTMLElement) {
  const results = await axe(container, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
    rules: { "color-contrast": { enabled: false }, "target-size": { enabled: true } },
  });
  expect(results.violations).toEqual([]);
}

type Contract = Readonly<{
  fixture: { fixture_id: string; version: string };
  overview: Record<string, unknown>;
  groups: Record<string, Array<Record<string, unknown>>>;
}>;
const contract = JSON.parse(
  readFileSync(resolve(process.cwd(), "../data/contract/sample_tiny_input.projection-v1.json"), "utf8"),
) as Contract;
const scenarioId = "11111111-1111-4111-8111-111111111111";
const queryBase = { error: null, isError: false, isFetching: false, isPending: false, refetch: vi.fn() };
const hookByGroup = {
  "work-areas-and-tasks": hooks.useWorkAreasAndTasks,
  workers: hooks.useWorkers,
  demand: hooks.useDemand,
  "baseline-assignments": hooks.useBaselineAssignments,
  locks: hooks.useLocks,
  "constraints-and-objectives": hooks.useConstraintsAndObjectives,
} as const;

function page(group: keyof typeof hookByGroup) {
  const fallbacks: Partial<Record<keyof typeof hookByGroup, Record<string, unknown>>> = {
    "baseline-assignments": { record_id: "assignment-1", worker_id: "worker-1", task_id: "task-1", shift_id: "shift-1", start_minute: 0, end_minute: 30 },
    locks: { record_id: "lock-1", target_type: "worker", target_ref: "worker-1", scope: "assignment", source: "fixture" },
  };
  const items = contract.groups[group].length > 0
    ? contract.groups[group].slice(0, 1)
    : [fallbacks[group]!];
  return { items, matching_count: items.length, next_cursor: null, total_count: items.length };
}

beforeEach(() => {
  sessionStorage.clear();
  vi.clearAllMocks();
  for (const [group, hook] of Object.entries(hookByGroup)) {
    vi.mocked(hook).mockReturnValue({ ...queryBase, data: page(group as keyof typeof hookByGroup) } as never);
  }
  vi.mocked(hooks.useWorkerNameMap).mockReturnValue({
    ...queryBase,
    data: new Map(contract.groups.workers.map((worker) => [String(worker.contact_id), String(worker.name)])),
  } as never);
  vi.mocked(hooks.useTaskNameMap).mockReturnValue({
    ...queryBase,
    data: new Map(contract.groups["work-areas-and-tasks"].map((task) => [String(task.task_id), String(task.name)])),
  } as never);
  vi.mocked(hooks.useScenarioOverview).mockReturnValue({
    ...queryBase,
    data: {
      ...contract.overview,
      scenario_name: contract.fixture.fixture_id,
      scenario_id: scenarioId,
      fixture_version: contract.fixture.version,
      projection_generated_at: "2026-08-06T00:00:00Z",
    },
  } as never);
});

const accessibleProposal = {
  proposal_id: "11111111-1111-4111-8111-111111111111",
  proposal_version_id: "22222222-2222-4222-8222-222222222222",
  scenario_id: scenarioId,
  scenario_version_id: "44444444-4444-4444-8444-444444444444",
  current_scenario_version_id: "44444444-4444-4444-8444-444444444444",
  expected_baseline_schedule_version: null,
  resolved_entities: [{
    group: "workers" as const, record_id: "worker-1", label: "CONTACT-9",
    scenario_version_id: "44444444-4444-4444-8444-444444444444", schema_version: "1",
  }],
  constraints: [{
    kind: "set_max_hours" as const,
    resolved_entities: [], max_hours: 40,
    description: "Cap CONTACT-9 at 40 hours per week.", schema_version: "1",
  }],
  preserved_locks: [],
  consequence_summary: "One reversible constraint; no baseline change.",
  canonical_hash: "a".repeat(64), canonical_hash_algorithm: "sha256",
  canonical_hash_schema_version: "rfc8785-v1", state: "active" as const,
  resource_version: 1, stale: false, version_ordinal: 3,
  ended_by: null as "planner" | "assistant" | "system" | null,
  applied_version_ordinal: null as number | null, schema_version: "1",
};

function mockProposal(stale = false, overrides: Record<string, unknown> = {}) {
  vi.mocked(proposalHooks.useProposal).mockReturnValue({
    data: stale ? {
      ...accessibleProposal,
      stale: true,
      current_scenario_version_id: "55555555-5555-4555-8555-555555555555",
      ...overrides,
    } : { ...accessibleProposal, ...overrides },
    isPending: false, isError: false, error: null, refetch: vi.fn(),
  } as never);
  vi.mocked(reviseHooks.useReviseProposal).mockReturnValue({ mutate: vi.fn(), reset: vi.fn(), isPending: false } as never);
  vi.mocked(rejectHooks.useRejectProposal).mockReturnValue({ mutate: vi.fn(), isPending: false } as never);
  vi.mocked(startHooks.useStartScheduleRun).mockReturnValue({
    mutate: vi.fn(), isPending: false, data: undefined, error: null,
  } as never);
}

it("preserves heading hierarchy and keyboard reading order through Scenario Data controls", async () => {
  const user = userEvent.setup();
  const { container } = render(
    <MemoryRouter initialEntries={[`/scenarios/${scenarioId}/data?group=demand&family=outbound`]}>
      <main>
        <ScenarioVersionContext context={{
          schema_version: "v1",
          scenario_name: contract.fixture.fixture_id,
          scenario_id: scenarioId,
          scenario_version_id: "33333333-3333-4333-8333-333333333333",
          fixture_version: contract.fixture.version,
          checksum_algorithm: "sha256",
          checksum_schema_version: "rfc8785-v1",
          checksum_digest: "a".repeat(64),
          site_id: "22222222-2222-4222-8222-222222222222",
          baseline_schedule_version: null,
        }} />
        <WorkspaceTabs scenarioId={scenarioId} />
        <ScenarioDataView scenarioId={scenarioId} />
      </main>
    </MemoryRouter>,
  );

  expect(Array.from(container.querySelectorAll("h1, h2, h3")).map((heading) => `${heading.tagName}:${heading.textContent}`)).toEqual([
    `H1:${contract.fixture.fixture_id}`,
    "H2:Scenario Data",
  ]);
  expect(screen.getByRole("link", { name: "Scenario Data" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("tab", { name: "Demand" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("button", { name: "Remove Family filter" })).toHaveTextContent("Family: Outbound");

  const order = [
    screen.getByRole("link", { name: "Change scenario" }),
    screen.getByRole("link", { name: "Chat" }),
    screen.getByRole("link", { name: "Scenario Data" }),
    screen.getByRole("link", { name: "Runs" }),
    screen.getByRole("tab", { name: "Demand" }),
    screen.getByRole("button", { name: "Choose columns" }),
    screen.getByRole("combobox", { name: "Family" }),
    screen.getByRole("textbox", { name: "Task ID" }),
    screen.getByRole("textbox", { name: "Area ID" }),
    screen.getByRole("spinbutton", { name: "Start minute at or after" }),
    screen.getByRole("spinbutton", { name: "End minute at or before" }),
    screen.getByRole("button", { name: "Apply" }),
    screen.getByRole("button", { name: "Clear" }),
    screen.getByRole("button", { name: "Remove Family filter" }),
    screen.getByRole("tabpanel", { name: "Demand" }),
    screen.getByRole("region", { name: "Demand" }),
    screen.getByRole("button", { name: "Sort by Family" }),
  ];
  for (const expected of order) {
    await user.tab();
    expect(expected).toHaveFocus();
  }

  expect(container.querySelector("td[tabindex]")).toBeNull();
  expect(screen.getByRole("region", { name: "Demand" })).toHaveAttribute("tabindex", "0");
});

for (const group of Object.keys(hookByGroup) as Array<keyof typeof hookByGroup>) {
  it(`provides a captioned, keyboard-scrollable ${group} table region`, () => {
    const { container } = render(
      <MemoryRouter initialEntries={[`/data?group=${group}`]}>
        <ScenarioDataView scenarioId={scenarioId} />
      </MemoryRouter>,
    );
    const region = screen.getByRole("region", { name: new RegExp(group.replaceAll("-", " "), "i") });
    expect(region).toHaveAttribute("tabindex", "0");
    const caption = container.querySelector("caption");
    expect(caption).toHaveClass("sr-only");
    expect(caption?.textContent).toBe(region.getAttribute("aria-label"));
  });
}

it("gives a grounded response an author label and a keyboard-operable evidence control", async () => {
  // Task 13 places this here rather than in the component suite: the
  // accessibility floor is proven by automated coverage alone (EXPERIENCE.md),
  // so the assertions belong with the other floor checks, and the focus ring is
  // asserted behaviourally rather than as a Tailwind class string.
  const { ActivityTimeline } = await import("@/features/chat/ActivityTimeline");
  const versionId = "44444444-4444-4444-4444-444444444444";
  const response = {
    schema_version: "1",
    activity_id: "88888888-8888-8888-8888-888888888888",
    activity_type: "agent_response" as const,
    conversation_id: "22222222-2222-2222-2222-222222222222",
    conversation_resource_version: 3,
    scenario_id: "33333333-3333-3333-3333-333333333333",
    scenario_version_id: versionId,
    occurred_at: "2026-08-14T00:00:00Z",
    sequence: "2",
    response: {
      schema_version: "1",
      scenario_version_id: versionId,
      segments: [
        {
          schema_version: "1",
          kind: "claim" as const,
          metric: "required_headcount_minutes" as const,
          arguments: {
            schema_version: "1",
            task_id: "pick",
            family: "outbound" as const,
            start_minute: 2880,
            end_minute: 4320,
          },
          result_id: "result-1",
          value: 2160,
          unit: "minutes" as const,
          verdict: "supported" as const,
          failure: null,
          evidence_refs: [
            {
              schema_version: "1",
              scenario_version_id: versionId,
              checksum_algorithm: "sha256",
              checksum_schema_version: "1",
              checksum_digest: "a".repeat(64),
              producing_run_version: null,
              baseline_schedule_version: null,
              group: "demand" as const,
              record_id: "d-outbound-0",
              field: "amount",
              start_minute: 2880,
              end_minute: 3600,
            },
          ],
        },
      ],
    },
  };

  render(<ActivityTimeline navigate={vi.fn()} items={[response] as never} />);

  // EXPERIENCE.md:85 -- the block is distinguishable by author/type label.
  expect(screen.getByLabelText("ShiftMind response")).toBeInTheDocument();

  // Self-describing accessible name naming group, record, field/range, version.
  const evidence = screen.getByRole("button", {
    name: `Verified Evidence: demand d-outbound-0, amount, 2880–3600 minutes, fixture ${versionId}`,
  });

  // Keyboard-reachable and focusable, asserted by driving the keyboard rather
  // than by matching a utility class.
  await userEvent.tab();
  expect(evidence).toHaveFocus();
});

const dialogueBase = {
  schema_version: "1",
  activity_id: "55555555-5555-4555-8555-555555555555",
  conversation_id: "22222222-2222-4222-8222-222222222222",
  conversation_resource_version: 3,
  scenario_id: scenarioId,
  scenario_version_id: "44444444-4444-4444-8444-444444444444",
  occurred_at: "2026-08-15T00:00:00Z",
  sequence: "2",
};

it("identifies clarification by accessible role and name", async () => {
  const { ActivityTimeline } = await import("@/features/chat/ActivityTimeline");
  const clarification = {
    ...dialogueBase,
    activity_type: "clarification" as const,
    clarification: {
      schema_version: "1",
      question: "Which worker did you mean?",
      scenario_version_id: dialogueBase.scenario_version_id,
      dropped_candidate_count: 0,
      candidates: [],
    },
  };

  render(<ActivityTimeline navigate={vi.fn()} items={[clarification] as never} />);

  expect(screen.getByRole("region", { name: "Clarification" })).toBeInTheDocument();
});

it("names the application-resolved record list distinctly from the question", async () => {
  const { ActivityTimeline } = await import("@/features/chat/ActivityTimeline");
  const clarification = {
    ...dialogueBase,
    activity_type: "clarification" as const,
    clarification: {
      schema_version: "1",
      question: "Which worker did you mean?",
      scenario_version_id: dialogueBase.scenario_version_id,
      dropped_candidate_count: 0,
      candidates: [
        {
          schema_version: "1",
          group: "workers" as const,
          record_id: "w1",
          label: "Taylor (CONTACT-9)",
          scenario_version_id: dialogueBase.scenario_version_id,
        },
      ],
    },
  };

  render(<ActivityTimeline navigate={vi.fn()} items={[clarification] as never} />);

  // Assistive technology gets the same trust boundary a sighted reader does:
  // the verified rows are a named list, separate from the model's own wording.
  expect(
    screen.getByRole("list", { name: "Records in Scenario Data" }),
  ).toBeInTheDocument();
});

it("announces only terminal state while keeping its next step outside the live region", async () => {
  const { ActivityTimeline } = await import("@/features/chat/ActivityTimeline");
  const outcome = {
    ...dialogueBase,
    activity_type: "terminal_outcome" as const,
    outcome: {
      schema_version: "1",
      status: "failed" as const,
      reason: "provider_error" as const,
      detail: "The provider did not complete this turn.",
      next_step: "Try again or review Scenario Data.",
    },
  };

  render(<ActivityTimeline navigate={vi.fn()} items={[outcome] as never} />);

  const status = screen.getByRole("status", { name: "Provider failure" });
  expect(within(status).queryByText(outcome.outcome.next_step)).not.toBeInTheDocument();
  expect(screen.getByText(outcome.outcome.next_step)).toBeInTheDocument();
});

it("makes the Draft card and its discontinuous commands independently identifiable", async () => {
  mockProposal();
  const { DraftCard } = await import("@/features/chat/DraftCard");
  const { container } = render(<DraftCard proposalId={accessibleProposal.proposal_id} />);

  const region = screen.getByRole("region", { name: "Draft proposal" });
  expect(region).toHaveTextContent("Draft — no baseline change");
  const save = screen.getByRole("button", { name: "Save changes" });
  const cancel = screen.getByRole("button", { name: "Cancel" });
  const discard = screen.getByRole("button", { name: "Discard draft" });
  const run = screen.getByRole("button", { name: "Run optimization" });
  const remove = screen.getByRole("button", { name: "Remove Cap CONTACT-9 at 40 hours per week." });
  const names = [save, cancel, discard, run, remove].map((button) => button.getAttribute("aria-label") ?? button.textContent);
  expect(new Set(names).size).toBe(5);
  expect(run).toHaveAccessibleDescription(/starts a bounded computation.*does not change the baseline/i);
  expect(save.parentElement).not.toBe(discard.parentElement);
  // Structural, not merely visual: the rule between the edit commands and the
  // run/discard commands has to be reportable. EXPERIENCE.md makes automated
  // coverage the only proof.
  expect(within(region).getByRole("separator")).toBeInTheDocument();
  // The version and lifecycle state sit beside the title as one readable line.
  expect(within(region).getByText("Working draft · v3")).toBeInTheDocument();
  await expectAxeClean(container);
});

it("keeps the Draft commands discontinuous from Send itself (UX-DR35)", async () => {
  mockProposal();
  const { DraftCard } = await import("@/features/chat/DraftCard");
  const { Composer } = await import("@/features/chat/Composer");

  // Both tests named for this discontinuity previously compared revise against
  // REJECT and never rendered a Send control at all, so the property the AC
  // actually names -- that a draft command is not continuous with Send -- was
  // never asserted against Send.
  render(
    <>
      <Composer
        isPending={false}
        onSend={async () => undefined}
        scenarioId={accessibleProposal.scenario_id}
      />
      <DraftCard proposalId={accessibleProposal.proposal_id} />
    </>,
  );

  const send = screen.getByRole("button", { name: /^send$/i });
  const save = screen.getByRole("button", { name: "Save changes" });
  const discard = screen.getByRole("button", { name: "Discard draft" });
  const run = screen.getByRole("button", { name: "Run optimization" });
  const region = screen.getByRole("region", { name: "Draft proposal" });

  for (const command of [save, discard, run]) {
    expect(command).not.toBe(send);
    expect(command).not.toHaveAccessibleName(send.textContent ?? "");
    // The draft commands live inside the Draft region; Send does not. Being in
    // separate containers is what makes them non-continuous controls rather
    // than a single command strip.
    expect(region).toContainElement(command);
    expect(region).not.toContainElement(send);
    expect(command.parentElement).not.toBe(send.parentElement);
  }
  expect(send).toHaveAttribute("data-variant", "default");
  expect(run).toHaveAttribute("data-variant", "secondary");
});

it("associates the real disabled composer controls with a polite outage alert", async () => {
  const { InlineAlert } = await import("@/components/primitives/InlineAlert");
  const { Composer } = await import("@/features/chat/Composer");
  const descriptionId = "agent-unavailable-description-contract";
  const { container } = render(
    <MemoryRouter>
      <InlineAlert
        description="Scenario Data, saved results, and manual optimization are still available."
        descriptionId={descriptionId}
        live="polite"
        title="Agent unavailable"
      />
      <Composer
        disabledReason={descriptionId}
        isPending={false}
        onSend={async () => undefined}
        scenarioId={scenarioId}
      />
    </MemoryRouter>,
  );

  const status = screen.getByRole("status");
  expect(status).toHaveAttribute("aria-live", "polite");
  expect(status).toContainElement(document.getElementById(descriptionId));
  for (const control of [
    screen.getByRole("textbox"),
    screen.getByRole("button", { name: /^send$/i }),
  ]) {
    expect(control).toBeDisabled();
    expect(control).toHaveAttribute("aria-describedby", descriptionId);
    expect(control.className).not.toMatch(/sr-only/);
  }
  await expectAxeClean(container);
});

it("announces stale Draft state and explains why saving is disabled", async () => {
  mockProposal(true);
  const { DraftCard } = await import("@/features/chat/DraftCard");
  const { container } = render(<DraftCard proposalId={accessibleProposal.proposal_id} />);

  expect(screen.getByRole("status", { name: "Draft is stale" })).toHaveTextContent(
    "The scenario version changed",
  );
  expect(screen.getByText("Working draft · out of date")).toBeInTheDocument();
  const save = screen.getByRole("button", { name: "Save changes" });
  const run = screen.getByRole("button", { name: "Run optimization" });
  expect(save).toBeDisabled();
  expect(save).toHaveAccessibleDescription(/scenario version changed/i);
  expect(run).toBeDisabled();
  expect(run).toHaveAccessibleDescription(/refresh.*before running/i);
  expect(screen.getByRole("button", { name: "Refresh proposal" })).toBeInTheDocument();
  // The described, disabled control must be the real submit control, not a
  // screen-reader-only decoy standing in for one that was never rendered.
  expect(save.className).not.toMatch(/sr-only/);
  // Discard stays available while stale: it changes no baseline.
  expect(screen.getByRole("button", { name: "Discard draft" })).toBeEnabled();
  await expectAxeClean(container);
});

it("associates validation errors with the affected control and keeps the draft accessible", async () => {
  mockProposal();
  const { DraftCard } = await import("@/features/chat/DraftCard");
  const { container } = render(<DraftCard proposalId={accessibleProposal.proposal_id} />);

  const hours = screen.getByRole("spinbutton", { name: "Maximum hours" });
  await userEvent.clear(hours);
  await userEvent.type(hours, "99");
  expect(hours).toHaveAttribute("aria-invalid", "true");
  const message = document.getElementById(hours.getAttribute("aria-describedby")!);
  expect(message).toHaveTextContent(/at most 56/);
  expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Run optimization" })).toHaveAccessibleDescription(
    /Save or cancel your changes first/,
  );
  await expectAxeClean(container);
});

it("announces 'Saved as vN' through a polite live region", async () => {
  mockProposal();
  const mutate = vi.fn();
  vi.mocked(reviseHooks.useReviseProposal).mockReturnValue({ mutate, reset: vi.fn(), isPending: false } as never);
  const { DraftCard } = await import("@/features/chat/DraftCard");
  const { container } = render(<DraftCard proposalId={accessibleProposal.proposal_id} />);

  const hours = screen.getByRole("spinbutton", { name: "Maximum hours" });
  await userEvent.clear(hours);
  await userEvent.type(hours, "36");
  await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
  const { act } = await import("@testing-library/react");
  const [, options] = mutate.mock.calls.at(-1)!;
  mockProposal(false, { version_ordinal: 4, resource_version: 2 });
  act(() => options.onSuccess({ ...accessibleProposal, version_ordinal: 4 }));

  const saved = await screen.findByText("Saved as v4");
  expect(saved).toHaveAttribute("aria-live", "polite");
  expect(saved).toHaveAttribute("role", "status");
  await expectAxeClean(container);
});

it("announces the changed-under-you notice through a polite live region with a Load control", async () => {
  mockProposal();
  const { DraftCard } = await import("@/features/chat/DraftCard");
  const { rowsFromProposal } = await import("@/features/chat/draftEdits");
  const buffer = {
    baseVersionId: "99999999-9999-4999-8999-999999999999",
    rows: rowsFromProposal(accessibleProposal as never).map((row) => ({
      ...row, input: { ...row.input, max_hours: 33 },
    })),
  };
  const { container } = render(
    <DraftCard buffer={buffer} onBufferChange={vi.fn()} proposalId={accessibleProposal.proposal_id} />,
  );

  const notice = screen.getByText(/This draft changed to v3\. Your edits were not saved\./);
  expect(notice).toHaveAttribute("aria-live", "polite");
  expect(notice).toHaveAttribute("role", "status");
  expect(screen.getByRole("button", { name: "Load v3" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  await expectAxeClean(container);
});

it("names the discard confirmation and its two choices distinctly, without a browser dialog", async () => {
  mockProposal();
  const { DraftCard } = await import("@/features/chat/DraftCard");
  const { container } = render(<DraftCard proposalId={accessibleProposal.proposal_id} />);

  await userEvent.click(screen.getByRole("button", { name: "Discard draft" }));
  const group = screen.getByRole("group", { name: "Confirm discard" });
  expect(group).toHaveTextContent("Discard this draft? It can't be restored.");
  const discard = within(group).getByRole("button", { name: "Discard" });
  const keep = within(group).getByRole("button", { name: "Keep" });
  expect(discard).toHaveAttribute("data-variant", "destructive");
  expect(keep).not.toHaveAttribute("data-variant", "destructive");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await expectAxeClean(container);
});

// AC7 "covers every new control" (code review of story-5.11): every input kind,
// the two-input lock row with paired errors, an ENABLED Remove per row, and the
// timeline's "Earlier version" line -- not only the one-row max-hours fixture.
const multiKindConstraints = [
  { kind: "set_min_workers_per_task" as const, resolved_entities: [], n: 2,
    description: "Require at least 2 workers on Picking.", schema_version: "1" },
  { kind: "scale_demand" as const, resolved_entities: [], factor: 1.5,
    description: "Scale Picking demand by 1.5.", schema_version: "1" },
  { kind: "set_max_hours" as const, resolved_entities: [], max_hours: 40,
    description: "Cap CONTACT-9 at 40 hours per week.", schema_version: "1" },
  { kind: "lock_worker_shift" as const, resolved_entities: [], start_minute: 60, end_minute: 480,
    description: "Lock CONTACT-9 from minute 60 to 480.", schema_version: "1" },
  { kind: "exclude_worker_from_task" as const, resolved_entities: [],
    description: "Exclude CONTACT-9 from Picking.", schema_version: "1" },
];

it("names every input kind and every enabled Remove control distinctly, and stays axe clean", async () => {
  mockProposal(false, { constraints: multiKindConstraints });
  const { DraftCard } = await import("@/features/chat/DraftCard");
  const { container } = render(<DraftCard proposalId={accessibleProposal.proposal_id} />);

  for (const name of ["Minimum workers", "Demand factor", "Maximum hours", "Start minute", "End minute"]) {
    expect(screen.getByRole("spinbutton", { name })).toBeEnabled();
  }
  for (const constraint of multiKindConstraints) {
    expect(screen.getByRole("group", { name: constraint.description })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: `Remove ${constraint.description}` })).toBeEnabled();
  }
  await expectAxeClean(container);
});

it("pairs each lock-row error with its own input and stays axe clean", async () => {
  mockProposal(false, { constraints: [multiKindConstraints[3]] });
  const { DraftCard } = await import("@/features/chat/DraftCard");
  const { container } = render(<DraftCard proposalId={accessibleProposal.proposal_id} />);

  const start = screen.getByRole("spinbutton", { name: "Start minute" });
  const end = screen.getByRole("spinbutton", { name: "End minute" });
  await userEvent.clear(start);
  await userEvent.type(start, "-5");
  await userEvent.clear(end);
  await userEvent.type(end, "1.5");
  for (const input of [start, end]) {
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(document.getElementById(input.getAttribute("aria-describedby")!)).toBeInTheDocument();
  }
  expect(start.getAttribute("aria-describedby")).not.toBe(end.getAttribute("aria-describedby"));
  await expectAxeClean(container);
});

it("keeps the timeline's 'Earlier version of this draft' line axe clean", async () => {
  mockProposal();
  const { ActivityTimeline } = await import("@/features/chat/ActivityTimeline");
  const draft = (index: number, summary: string) => ({
    ...dialogueBase,
    activity_id: `cccccccc-cccc-4ccc-8ccc-${String(index).padStart(12, "0")}`,
    activity_type: "draft" as const,
    sequence: String(index),
    proposal_id: accessibleProposal.proposal_id,
    proposal_version_id: `dddddddd-dddd-4ddd-8ddd-${String(index).padStart(12, "0")}`,
    consequence_summary: summary,
  });
  const { container } = render(
    <ActivityTimeline navigate={vi.fn()} items={[draft(1, "Cap at 40."), draft(2, "Cap at 36.")] as never} />,
  );

  expect(screen.getByText(/Earlier version of this draft/)).toBeInTheDocument();
  expect(screen.getAllByRole("region", { name: "Draft proposal" })).toHaveLength(1);
  await expectAxeClean(container);
});

it.each([
  ["Discarded", { state: "rejected", ended_by: "planner" }],
  ["Discarded by assistant", { state: "rejected", ended_by: "assistant" }],
  ["Replaced by a newer draft", { state: "rejected", ended_by: "system" }],
  ["Applied to baseline — v2 promoted", { state: "applied", ended_by: "system", applied_version_ordinal: 2 }],
])("renders the ended state %s read-only and accessible", async (line, overrides) => {
  mockProposal(false, overrides);
  const { DraftCard } = await import("@/features/chat/DraftCard");
  const { container } = render(<DraftCard proposalId={accessibleProposal.proposal_id} />);

  const region = screen.getByRole("region", { name: "Draft proposal" });
  expect(within(region).getByText(line)).toBeInTheDocument();
  expect(within(region).queryByRole("button")).not.toBeInTheDocument();
  expect(within(region).queryByRole("spinbutton")).not.toBeInTheDocument();
  await expectAxeClean(container);
});

it("announces the queued run identity and literal status through a polite live region", async () => {
  mockProposal();
  vi.mocked(startHooks.useStartScheduleRun).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    error: null,
    data: {
      schedule_run_id: "66666666-6666-4666-8666-666666666666",
      status: "solver_queued",
      resource_version: 1,
    },
    variables: {
      proposal_id: accessibleProposal.proposal_id,
      expected_resource_version: 1,
    },
  } as never);
  const { DraftCard } = await import("@/features/chat/DraftCard");
  render(<DraftCard proposalId={accessibleProposal.proposal_id} />);

  const acknowledgement = screen.getByRole("status", { name: "Optimization queued" });
  expect(acknowledgement).toHaveAttribute("aria-live", "polite");
  expect(acknowledgement).toHaveTextContent("solver_queued");
  expect(acknowledgement).toHaveTextContent("66666666-6666-4666-8666-666666666666");
  expect(within(acknowledgement).getByText("66666666-6666-4666-8666-666666666666"))
    .toHaveClass("font-mono", "text-xs");
});

it.each([
  ["clarification with candidates", {
    ...dialogueBase,
    activity_type: "clarification" as const,
    clarification: {
      schema_version: "1",
      question: "Which worker did you mean?",
      scenario_version_id: dialogueBase.scenario_version_id,
      dropped_candidate_count: 1,
      candidates: [{
        schema_version: "1",
        group: "workers" as const,
        record_id: "worker-1",
        label: "CONTACT-9",
        scenario_version_id: dialogueBase.scenario_version_id,
      }],
    },
  }],
  ["clarification without candidates", {
    ...dialogueBase,
    activity_type: "clarification" as const,
    clarification: {
      schema_version: "1",
      question: "Which record did you mean?",
      scenario_version_id: dialogueBase.scenario_version_id,
      dropped_candidate_count: 2,
      candidates: [],
    },
  }],
  ...([
    "provider_error",
    "invalid_output",
    "budget_exhausted",
    "deadline_exceeded",
    "cancelled",
    "capability_error",
    "refused",
    "approval_not_grantable",
  ] as const).map((reason, index) => [reason === "refused" ? "refusal" : reason, {
    ...dialogueBase,
    activity_id: `77777777-7777-4777-8777-${String(index).padStart(12, "0")}`,
    activity_type: "terminal_outcome" as const,
    outcome: {
      schema_version: "1",
      status: reason === "refused" ? "completed" as const : "failed" as const,
      reason,
      detail: `Literal detail for ${reason}.`,
      next_step: "Review Scenario Data.",
    },
  }] as const),
])("is axe clean for %s", async (_name, activity) => {
  const { ActivityTimeline } = await import("@/features/chat/ActivityTimeline");
  const { container } = render(<ActivityTimeline navigate={vi.fn()} items={[activity] as never} />);

  await expectAxeClean(container);
});

it("keeps the approval decision surface named, textual, and touch-sized", async () => {
  const approval = {
    approval_id: "11111111-1111-4111-8111-111111111111", state: "pending" as const,
    schedule_run_id: "22222222-2222-4222-8222-222222222222",
    candidate_schedule_version_id: "33333333-3333-4333-8333-333333333333",
    baseline_schedule_version: "baseline-v12", scenario_version_id: "44444444-4444-4444-8444-444444444444",
    consequence_summary: "Candidate replaces baseline-v12; the operational baseline changes only after confirmation.",
    policy_version: "policy-v1",
    agent_run_id: null, created_at: "2026-08-29T00:00:00Z", expires_at: "2099-08-29T00:00:00Z", resource_version: 1,
  };
  render(<ApprovalDecisionDialog approval={approval} decision="approve" open onOpenChange={vi.fn()} onConfirm={vi.fn()} onRestoreFocus={vi.fn()} pending={false} />);
  const dialog = screen.getByRole("dialog", { name: "Approve candidate as baseline" });
  expect(within(dialog).getByText(/operational baseline changes only after confirmation/)).toBeVisible();
  expect(within(dialog).getByRole("button", { name: /Approve candidate .* replacing baseline-v12/ })).toHaveClass("min-h-11");
  expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveClass("min-h-11");
  await expectAxeClean(document.body);
});

it("keeps Send, Run optimization, and Approve as baseline discontinuous across authority levels (NFR19, UX-DR35)", async () => {
  // The REAL three controls, in one tree. A previous version of this assertion
  // lived in the panel's own test and rendered synthetic `<Button>Send</Button>`
  // and `<Button variant="outline">Run optimization</Button>` -- buttons whose
  // variants the test itself chose, so it could not fail if a real control's
  // treatment changed. It also picked the wrong variant for Run optimization,
  // which DraftCard ships as `secondary`.
  mockProposal();
  const { DraftCard } = await import("@/features/chat/DraftCard");
  const { Composer } = await import("@/features/chat/Composer");
  const { ApprovalDecisionPanel } = await import("@/features/approvals/ApprovalDecisionPanel");

  render(
    <>
      <Composer isPending={false} onSend={async () => undefined} scenarioId={accessibleProposal.scenario_id} />
      <DraftCard proposalId={accessibleProposal.proposal_id} />
      <ApprovalDecisionPanel approvalId={decisionApproval.approval_id} />
    </>,
  );

  const send = screen.getByRole("button", { name: /^send$/i });
  const run = screen.getByRole("button", { name: "Run optimization" });
  const approve = screen.getByRole("button", { name: "Approve as baseline" });

  // Language: three distinct accessible names, none a prefix of another.
  const names = [send, run, approve].map((node) => node.textContent?.trim());
  expect(new Set(names).size).toBe(3);

  // Visual treatment: three distinct variants, read off the real components.
  const variants = [send, run, approve].map((node) => node.getAttribute("data-variant"));
  expect(new Set(variants).size).toBe(3);
  // Consequence: only the baseline-moving control carries the destructive
  // treatment, and it is the only one of the three behind a confirmation.
  expect(approve.getAttribute("data-variant")).toBe("destructive");
  expect(send.getAttribute("data-variant")).not.toBe("destructive");
  expect(run.getAttribute("data-variant")).not.toBe("destructive");
});
