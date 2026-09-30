import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DraftCard } from "./DraftCard";
import { rowsFromProposal, type EditBuffer } from "./draftEdits";
import * as proposalHooks from "@/hooks/useProposal";
import * as reviseHooks from "@/hooks/useReviseProposal";
import * as rejectHooks from "@/hooks/useRejectProposal";
import * as projectionHooks from "@/hooks/useScenarioProjection";
import * as startHooks from "@/hooks/useStartScheduleRun";

vi.mock("@/hooks/useProposal");
vi.mock("@/hooks/useReviseProposal");
vi.mock("@/hooks/useRejectProposal");
vi.mock("@/hooks/useScenarioProjection");
vi.mock("@/hooks/useStartScheduleRun");

const mutateRevision = vi.fn();
const mutateRejection = vi.fn();
const mutateStart = vi.fn();
const refetch = vi.fn();
const VERSION = "44444444-4444-4444-8444-444444444444";
const worker = {
  group: "workers" as const, record_id: "w1", label: "Alex (CONTACT-9)",
  scenario_version_id: VERSION, schema_version: "1",
};
const task = {
  group: "work-areas-and-tasks" as const, record_id: "t1", label: "Picking (t1)",
  scenario_version_id: VERSION, schema_version: "1",
};
const constraint = (
  kind: "set_max_hours" | "set_min_workers_per_task" | "scale_demand" | "lock_worker_shift" | "exclude_worker_from_task",
  overrides: Record<string, unknown> = {},
) => ({
  kind,
  resolved_entities: kind === "set_min_workers_per_task" || kind === "scale_demand" ? [task] : kind === "exclude_worker_from_task" ? [worker, task] : [worker],
  description: {
    set_max_hours: "Cap Alex (CONTACT-9) at 40 hours per week.",
    set_min_workers_per_task: "Require at least 2 workers on Picking (t1).",
    scale_demand: "Scale Picking (t1) demand by 1.5.",
    lock_worker_shift: "Lock Alex (CONTACT-9) from minute 60 to 480.",
    exclude_worker_from_task: "Exclude Alex (CONTACT-9) from Picking (t1).",
  }[kind],
  schema_version: "1",
  ...overrides,
});
const proposal = {
  proposal_id: "11111111-1111-4111-8111-111111111111",
  proposal_version_id: "22222222-2222-4222-8222-222222222222",
  scenario_id: "33333333-3333-4333-8333-333333333333",
  scenario_version_id: VERSION,
  current_scenario_version_id: VERSION,
  expected_baseline_schedule_version: "baseline-v1",
  resolved_entities: [worker],
  constraints: [constraint("set_max_hours", { max_hours: 40 })],
  preserved_locks: [{
    record_id: "lock-1", target_type: "worker", target_ref: "w1",
    scope: "assignment", source: "fixture", schema_version: "1",
  }],
  consequence_summary: "One reversible constraint; preserved one existing lock; no baseline change.",
  canonical_hash: "a".repeat(64),
  canonical_hash_algorithm: "sha256",
  canonical_hash_schema_version: "rfc8785-v1",
  state: "active" as "active" | "rejected" | "applied",
  resource_version: 1,
  stale: false,
  version_ordinal: 3 as number | null,
  ended_by: null as "planner" | "assistant" | "system" | null,
  applied_version_ordinal: null as number | null,
  schema_version: "1",
};
const multi = {
  ...proposal,
  constraints: [
    constraint("set_min_workers_per_task", { n: 2 }),
    constraint("scale_demand", { factor: 1.5 }),
    constraint("set_max_hours", { max_hours: 40 }),
    constraint("lock_worker_shift", { start_minute: 60, end_minute: 480 }),
    constraint("exclude_worker_from_task"),
  ],
};

function show(data: unknown) {
  vi.mocked(proposalHooks.useProposal).mockReturnValue({
    data, isPending: false, isError: false, error: null, refetch,
  } as never);
}

beforeEach(() => {
  vi.clearAllMocks();
  show(proposal);
  vi.mocked(reviseHooks.useReviseProposal).mockReturnValue({
    mutate: mutateRevision, isPending: false, isError: false,
  } as never);
  vi.mocked(rejectHooks.useRejectProposal).mockReturnValue({
    mutate: mutateRejection, isPending: false, isError: false,
  } as never);
  vi.mocked(startHooks.useStartScheduleRun).mockReturnValue({
    mutate: mutateStart, isPending: false, isError: false, data: undefined,
  } as never);
  vi.mocked(projectionHooks.useScenarioOverview).mockReturnValue({
    data: { horizon_minutes: 10080 },
  } as never);
});

const card = () => screen.getByRole("region", { name: "Draft proposal" });
const button = (name: string | RegExp) => screen.getByRole("button", { name });
const field = (name: string, scope: HTMLElement | Document = document.body) =>
  within(scope as HTMLElement).getByRole("spinbutton", { name });
async function typeInto(input: HTMLElement, value: string) {
  await userEvent.clear(input);
  if (value !== "") await userEvent.type(input, value);
}

describe("DraftCard — the working draft", () => {
  it("renders the review contract with the version and state beside the title", () => {
    render(<DraftCard proposalId={proposal.proposal_id} />);

    expect(card()).toHaveTextContent("Draft — no baseline change");
    expect(within(card()).getByText("Working draft · v3")).toBeInTheDocument();
    expect(card()).toHaveTextContent("Alex (CONTACT-9)");
    expect(card()).toHaveTextContent("w1");
    expect(card()).toHaveTextContent(proposal.constraints[0].description);
    expect(card()).toHaveTextContent("lock-1");
    expect(card()).toHaveTextContent(proposal.scenario_version_id);
    expect(card()).toHaveTextContent("baseline-v1");
    expect(card()).toHaveTextContent(proposal.consequence_summary);
    // The card keeps the `dl` identifiers and adds the draft's own version.
    expect(within(card()).getByText("Draft version").nextElementSibling).toHaveTextContent("v3");
  });

  it("keeps Save, Discard and Run discontinuous, with a reportable rule between the edit and the run/discard commands", () => {
    render(<DraftCard proposalId={proposal.proposal_id} />);

    const save = button("Save changes");
    const discard = button("Discard draft");
    const run = button("Run optimization");
    for (const control of [save, discard, run, button("Cancel")]) {
      expect(control).toHaveClass("min-h-11");
    }
    expect(save.parentElement).not.toBe(discard.parentElement);
    expect(run).toHaveAttribute("data-variant", "secondary");
    expect(discard).toHaveAttribute("data-variant", "destructive");
    expect(run).toHaveAccessibleDescription(/starts a bounded computation.*does not change the baseline/i);
    expect(within(card()).getByRole("separator")).toBeInTheDocument();
    // The removed controls are gone, not merely renamed.
    expect(screen.queryByRole("combobox", { name: "Constraint to revise" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Revise proposal" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject proposal" })).not.toBeInTheDocument();
  });

  it("shows an input per argument by kind, and none for exclude_worker_from_task", () => {
    show(multi);
    render(<DraftCard proposalId={proposal.proposal_id} />);

    const row = (description: string) => screen.getByRole("group", { name: description });
    expect(field("Minimum workers", row(multi.constraints[0].description))).toHaveValue(2);
    expect(field("Demand factor", row(multi.constraints[1].description))).toHaveValue(1.5);
    expect(field("Maximum hours", row(multi.constraints[2].description))).toHaveValue(40);
    expect(field("Start minute", row(multi.constraints[3].description))).toHaveValue(60);
    expect(field("End minute", row(multi.constraints[3].description))).toHaveValue(480);
    expect(within(row(multi.constraints[4].description)).queryByRole("spinbutton")).not.toBeInTheDocument();
    // Every row can be removed, by an accessible name that includes its description.
    for (const item of multi.constraints) {
      expect(button(`Remove ${item.description}`)).toBeEnabled();
    }
  });

  it("never removes the last row: the control is disabled and says why", async () => {
    render(<DraftCard proposalId={proposal.proposal_id} />);

    const remove = button(`Remove ${proposal.constraints[0].description}`);
    expect(remove).toBeDisabled();
    expect(within(card()).getByText("Discard the draft instead")).toBeInTheDocument();
    expect(remove).toHaveAccessibleDescription("Discard the draft instead");
  });

  it("removes a row locally, and Save then sends the remaining rows in full", async () => {
    show(multi);
    render(<DraftCard proposalId={proposal.proposal_id} />);

    await userEvent.click(button(`Remove ${multi.constraints[1].description}`));
    expect(screen.queryByRole("group", { name: multi.constraints[1].description })).not.toBeInTheDocument();
    await userEvent.click(button("Save changes"));

    const [body] = mutateRevision.mock.calls.at(-1)!;
    expect(body.expected_resource_version).toBe(1);
    expect(body.constraints.map((c: { kind: string }) => c.kind)).toEqual([
      "set_min_workers_per_task", "set_max_hours", "lock_worker_shift", "exclude_worker_from_task",
    ]);
  });

  describe("Save changes and Cancel", () => {
    it("are disabled until there is a difference; Cancel needs only a difference, Save a valid one", async () => {
      render(<DraftCard proposalId={proposal.proposal_id} />);
      expect(button("Save changes")).toBeDisabled();
      expect(button("Cancel")).toBeDisabled();

      await typeInto(field("Maximum hours"), "36");
      expect(button("Save changes")).toBeEnabled();
      expect(button("Cancel")).toBeEnabled();

      // Invalid: Save is off, but you must still be able to cancel the edit.
      await typeInto(field("Maximum hours"), "0");
      expect(button("Save changes")).toBeDisabled();
      expect(button("Cancel")).toBeEnabled();

      // Typing the original value back leaves no difference at all.
      await typeInto(field("Maximum hours"), "40");
      expect(button("Save changes")).toBeDisabled();
      expect(button("Cancel")).toBeDisabled();
    });

    it("sends only identifiers and numbers, never client-authored prose", async () => {
      render(<DraftCard proposalId={proposal.proposal_id} />);
      await typeInto(field("Maximum hours"), "36");
      await userEvent.click(button("Save changes"));

      const [body] = mutateRevision.mock.calls.at(-1)!;
      expect(body.constraints[0].max_hours).toBe(36);
      expect(body.constraints[0].record_id).toBe("w1");
      // The server recomposes these from the pinned projection.
      expect(body.constraints[0]).not.toHaveProperty("description");
      expect(body.constraints[0]).not.toHaveProperty("resolved_entities");
    });

    it("announces 'Saved as vN' in a polite live region and clears the edits", async () => {
      render(<DraftCard proposalId={proposal.proposal_id} />);
      await typeInto(field("Maximum hours"), "36");
      await userEvent.click(button("Save changes"));
      const [, options] = mutateRevision.mock.calls.at(-1)!;

      const saved = { ...proposal, version_ordinal: 4, resource_version: 2 };
      show(saved);
      // The mutate-level callback is what the card acts on.
      const { act } = await import("@testing-library/react");
      act(() => options.onSuccess(saved));

      const status = await screen.findByText("Saved as v4");
      expect(status).toHaveAttribute("aria-live", "polite");
      expect(status).toHaveAttribute("role", "status");
      expect(button("Save changes")).toBeDisabled();
      expect(button("Cancel")).toBeDisabled();
    });

    it("Cancel resets the local edits", async () => {
      render(<DraftCard proposalId={proposal.proposal_id} />);
      await typeInto(field("Maximum hours"), "36");
      await userEvent.click(button("Cancel"));
      expect(field("Maximum hours")).toHaveValue(40);
    });

    it("keeps a planner edit across a background refetch of the same version", async () => {
      const { rerender } = render(<DraftCard proposalId={proposal.proposal_id} />);
      await typeInto(field("Maximum hours"), "36");

      // A refetch returns an equal-but-new object identity; TanStack refetches on
      // window focus by default. The edit must not vanish.
      show({ ...proposal });
      rerender(<DraftCard proposalId={proposal.proposal_id} />);
      expect(field("Maximum hours")).toHaveValue(36);
    });
  });

  describe("validation mirrors the resolver, and errors sit on the affected control", () => {
    it.each([
      ["Minimum workers", "set_min_workers_per_task", { n: 2 }, ["0", "1.5", ""], "3", /whole number greater than 0/],
      ["Demand factor", "scale_demand", { factor: 1.5 }, ["0", ""], "0.5", /greater than 0/],
      ["Maximum hours", "set_max_hours", { max_hours: 40 }, ["0", "57", ""], "56", /at most 56/],
    ] as const)("%s", async (label, kind, args, bad, good, message) => {
      show({ ...proposal, constraints: [constraint(kind, args)] });
      render(<DraftCard proposalId={proposal.proposal_id} />);
      const input = field(label);
      for (const value of bad) {
        await typeInto(input, value);
        expect(input).toHaveAttribute("aria-invalid", "true");
        const described = document.getElementById(input.getAttribute("aria-describedby") ?? "");
        expect(described).toHaveTextContent(message);
        expect(button("Save changes")).toBeDisabled();
      }
      await typeInto(input, good);
      expect(input).not.toHaveAttribute("aria-invalid");
      expect(input).not.toHaveAttribute("aria-describedby");
      expect(button("Save changes")).toBeEnabled();
    });

    it("lock_worker_shift needs whole minutes, start < end, and end within the horizon", async () => {
      show({ ...proposal, constraints: [constraint("lock_worker_shift", { start_minute: 60, end_minute: 480 })] });
      render(<DraftCard proposalId={proposal.proposal_id} />);
      const start = field("Start minute");
      const end = field("End minute");

      await typeInto(end, "60");
      expect(end).toHaveAttribute("aria-invalid", "true");
      expect(start).toHaveAttribute("aria-invalid", "true");
      await typeInto(end, "10081");
      expect(end).toHaveAttribute("aria-invalid", "true");
      expect(document.getElementById(end.getAttribute("aria-describedby")!)).toHaveTextContent("at most 10080");
      await typeInto(end, "480");
      await typeInto(start, "-1");
      expect(start).toHaveAttribute("aria-invalid", "true");
      await typeInto(start, "1.5");
      expect(start).toHaveAttribute("aria-invalid", "true");
      await typeInto(start, "0");
      expect(start).not.toHaveAttribute("aria-invalid");
      expect(end).not.toHaveAttribute("aria-invalid");
      expect(button("Save changes")).toBeEnabled();
      await typeInto(end, "10080");
      expect(end).not.toHaveAttribute("aria-invalid");
    });

    it("skips only the horizon bound while the horizon is unavailable", async () => {
      vi.mocked(projectionHooks.useScenarioOverview).mockReturnValue({ data: undefined } as never);
      show({ ...proposal, constraints: [constraint("lock_worker_shift", { start_minute: 60, end_minute: 480 })] });
      render(<DraftCard proposalId={proposal.proposal_id} />);
      await typeInto(field("End minute"), "99999");
      expect(field("End minute")).not.toHaveAttribute("aria-invalid");
      await typeInto(field("End minute"), "30");
      expect(field("End minute")).toHaveAttribute("aria-invalid", "true");
    });
  });

  describe("Run optimization", () => {
    it("is disabled while there are unsaved edits, with the literal reason", async () => {
      render(<DraftCard proposalId={proposal.proposal_id} />);
      expect(button("Run optimization")).toBeEnabled();
      await typeInto(field("Maximum hours"), "36");
      expect(button("Run optimization")).toBeDisabled();
      expect(button("Run optimization")).toHaveAccessibleDescription(/Save or cancel your changes first/);
      await userEvent.click(button("Cancel"));
      expect(button("Run optimization")).toBeEnabled();
      await userEvent.click(button("Run optimization"));
      expect(mutateStart).toHaveBeenCalledWith({
        proposal_id: proposal.proposal_id, expected_resource_version: 1,
      });
    });
  });

  describe("while an agent turn is in flight", () => {
    it("disables Save, Discard and Run with the literal reason", async () => {
      render(<DraftCard agentTurnInFlight proposalId={proposal.proposal_id} />);
      const hint = screen.getByText("Wait for the assistant to finish");
      for (const name of ["Save changes", "Discard draft", "Run optimization"]) {
        expect(button(name)).toBeDisabled();
        expect(button(name).getAttribute("aria-describedby")).toContain(hint.id);
      }
      // Cancel is a local action and stays under the planner's control.
      await typeInto(field("Maximum hours"), "36");
      expect(button("Save changes")).toBeDisabled();
      expect(button("Cancel")).toBeEnabled();
    });

    it("enables them again when it ends", () => {
      const { rerender } = render(<DraftCard agentTurnInFlight proposalId={proposal.proposal_id} />);
      rerender(<DraftCard proposalId={proposal.proposal_id} />);
      expect(button("Discard draft")).toBeEnabled();
      expect(button("Run optimization")).toBeEnabled();
      expect(screen.queryByText("Wait for the assistant to finish")).not.toBeInTheDocument();
    });
  });

  describe("Discard draft", () => {
    it("asks for an inline two-step confirmation, no browser dialog", async () => {
      const confirm = vi.spyOn(window, "confirm");
      render(<DraftCard proposalId={proposal.proposal_id} />);
      await userEvent.click(button("Discard draft"));

      expect(within(card()).getByText("Discard this draft? It can't be restored.")).toBeInTheDocument();
      expect(mutateRejection).not.toHaveBeenCalled();
      expect(screen.queryByRole("button", { name: "Discard draft" })).not.toBeInTheDocument();
      expect(button("Keep")).toHaveFocus();
      await userEvent.click(button("Discard"));
      expect(mutateRejection).toHaveBeenCalledWith(
        { expected_resource_version: 1 }, expect.anything(),
      );
      expect(confirm).not.toHaveBeenCalled();
    });

    it("Keep withdraws the confirmation and returns focus to Discard draft", async () => {
      render(<DraftCard proposalId={proposal.proposal_id} />);
      await userEvent.click(button("Discard draft"));
      await userEvent.click(button("Keep"));
      expect(screen.queryByText("Discard this draft? It can't be restored.")).not.toBeInTheDocument();
      expect(button("Discard draft")).toHaveFocus();
      expect(mutateRejection).not.toHaveBeenCalled();
    });
  });

  describe("the draft changes under unsaved edits", () => {
    const older: EditBuffer = {
      baseVersionId: "99999999-9999-4999-8999-999999999999",
      rows: rowsFromProposal({ ...proposal, constraints: [constraint("set_max_hours", { max_hours: 30 })] } as never)
        .map((row) => ({ ...row, input: { ...row.input, max_hours: 33 } })),
    };

    it("keeps the local values, disables Save, and offers Load vN", () => {
      render(<DraftCard buffer={older} onBufferChange={vi.fn()} proposalId={proposal.proposal_id} />);

      expect(field("Maximum hours")).toHaveValue(33);
      expect(button("Save changes")).toBeDisabled();
      const notice = screen.getByText(/This draft changed to v3\. Your edits were not saved\./);
      expect(notice).toHaveAttribute("role", "status");
      expect(notice).toHaveAttribute("aria-live", "polite");
      expect(button("Load v3")).toBeEnabled();
    });

    it("Load vN drops the local edits and shows the server rows", async () => {
      const onBufferChange = vi.fn();
      render(<DraftCard buffer={older} onBufferChange={onBufferChange} proposalId={proposal.proposal_id} />);
      await userEvent.click(button("Load v3"));
      expect(onBufferChange).toHaveBeenLastCalledWith(null);
    });

    it("reads the edits from the buffer it is given, so they survive the card moving", () => {
      // The timeline owns the buffer: a remounted card (a newer draft activity)
      // shows the same unsaved values instead of re-seeding from the server.
      const mid: EditBuffer = { baseVersionId: proposal.proposal_version_id, rows: older.rows };
      const { unmount } = render(<DraftCard buffer={mid} onBufferChange={vi.fn()} proposalId={proposal.proposal_id} />);
      expect(field("Maximum hours")).toHaveValue(33);
      unmount();
      render(<DraftCard buffer={mid} onBufferChange={vi.fn()} proposalId={proposal.proposal_id} />);
      expect(field("Maximum hours")).toHaveValue(33);
      expect(button("Run optimization")).toBeDisabled();
    });

    it("hands edits to the owner of the buffer as they are made", async () => {
      const onBufferChange = vi.fn();
      render(<DraftCard buffer={null} onBufferChange={onBufferChange} proposalId={proposal.proposal_id} />);
      await userEvent.type(field("Maximum hours"), "1");
      const next = onBufferChange.mock.calls.at(-1)![0] as EditBuffer;
      expect(next.baseVersionId).toBe(proposal.proposal_version_id);
      expect(next.rows[0].input.max_hours).toBe(401);
    });
  });

  describe("stale", () => {
    beforeEach(() => show({ ...proposal, stale: true, current_scenario_version_id: "55555555-5555-4555-8555-555555555555" }));

    it("announces it, disables inputs, Save and Run with the explanation, and keeps Discard and Refresh", async () => {
      render(<DraftCard proposalId={proposal.proposal_id} />);

      expect(within(card()).getByText("Working draft · out of date")).toBeInTheDocument();
      expect(screen.getByRole("status", { name: "Draft is stale" })).toBeInTheDocument();
      expect(field("Maximum hours")).toBeDisabled();
      expect(button("Save changes")).toBeDisabled();
      expect(button("Save changes")).toHaveAccessibleDescription(/scenario version changed/i);
      expect(button("Save changes").className).not.toMatch(/sr-only/);
      expect(button("Run optimization")).toBeDisabled();
      expect(button("Run optimization")).toHaveAccessibleDescription(/refresh.*before running/i);
      expect(button("Refresh proposal")).toBeInTheDocument();
      // Discard changes no baseline and is the only terminal path a stale draft has.
      expect(button("Discard draft")).toBeEnabled();
      await userEvent.click(button("Refresh proposal"));
      expect(refetch).toHaveBeenCalled();
    });
  });

  describe("ended drafts are read-only facts with one state line", () => {
    it.each([
      ["discarded by the planner", { state: "rejected", ended_by: "planner" }, "Discarded"],
      ["discarded by the assistant", { state: "rejected", ended_by: "assistant" }, "Discarded by assistant"],
      ["replaced by a newer draft", { state: "rejected", ended_by: "system" }, "Replaced by a newer draft"],
      ["applied to the baseline", { state: "applied", ended_by: "system", applied_version_ordinal: 2 }, "Applied to baseline — v2 promoted"],
    ] as const)("%s", (_name, overrides, line) => {
      show({ ...proposal, ...overrides });
      render(<DraftCard proposalId={proposal.proposal_id} />);

      expect(within(card()).getByText(line)).toBeInTheDocument();
      expect(within(card()).queryByRole("button")).not.toBeInTheDocument();
      expect(within(card()).queryByRole("spinbutton")).not.toBeInTheDocument();
      // The constraint list is still shown, read-only.
      expect(card()).toHaveTextContent(proposal.constraints[0].description);
    });

    it("an ended state wins over staleness: no stale notice, no Refresh", () => {
      show({ ...proposal, state: "rejected", ended_by: "planner", stale: true });
      render(<DraftCard proposalId={proposal.proposal_id} />);
      expect(screen.queryByRole("status", { name: "Draft is stale" })).not.toBeInTheDocument();
      expect(screen.queryByRole("status", { name: "Draft is rejected" })).not.toBeInTheDocument();
      expect(within(card()).getByText("Discarded")).toBeInTheDocument();
      expect(within(card()).queryByRole("button")).not.toBeInTheDocument();
    });

    it("rows written before the lifecycle (no version, no ended_by) still render", () => {
      show({ ...proposal, version_ordinal: null, ended_by: null, state: "active" });
      render(<DraftCard proposalId={proposal.proposal_id} />);
      expect(within(card()).getByText("Working draft")).toBeInTheDocument();
      show({ ...proposal, version_ordinal: null, ended_by: null, state: "rejected" });
      render(<DraftCard proposalId={proposal.proposal_id} />);
      expect(screen.getAllByText("Discarded").length).toBeGreaterThan(0);
    });
  });

  describe("command errors", () => {
    it("surfaces a failed command instead of silently re-enabling the button", () => {
      vi.mocked(reviseHooks.useReviseProposal).mockReturnValue({
        mutate: mutateRevision, isPending: false, error: { status: 409 },
      } as never);
      render(<DraftCard proposalId={proposal.proposal_id} />);
      expect(screen.getByText(/changed since you opened it/i)).toBeInTheDocument();
    });

    it.each([
      ["rejected_proposal", /rejected, so it cannot be changed or run/i],
      ["applied_proposal", /applied to the baseline, so it cannot be changed or run/i],
    ])("maps %s from a revise, discard or run", (code, message) => {
      vi.mocked(rejectHooks.useRejectProposal).mockReturnValue({
        mutate: mutateRejection, isPending: false, submittedAt: 5, error: { status: 409, code },
      } as never);
      render(<DraftCard proposalId={proposal.proposal_id} />);
      expect(screen.getByText(message)).toBeInTheDocument();
    });

    it("announces the durable queued run identity without showing progress", () => {
      vi.mocked(startHooks.useStartScheduleRun).mockReturnValue({
        mutate: mutateStart, isPending: false, isError: false,
        data: { schedule_run_id: "66666666-6666-4666-8666-666666666666", status: "solver_queued", resource_version: 1 },
        variables: { proposal_id: proposal.proposal_id, expected_resource_version: 1 },
      } as never);
      render(<DraftCard proposalId={proposal.proposal_id} />);

      const acknowledgement = screen.getByRole("status", { name: "Optimization queued" });
      expect(acknowledgement).toHaveAttribute("aria-live", "polite");
      expect(acknowledgement).toHaveTextContent("66666666-6666-4666-8666-666666666666");
      expect(acknowledgement).toHaveTextContent("solver_queued");
      expect(acknowledgement.querySelector("code")).toHaveClass("font-mono", "text-xs");
      expect(acknowledgement).not.toHaveTextContent(/progress|percent|%/i);
    });

    it("explains the per-site run limit", () => {
      vi.mocked(startHooks.useStartScheduleRun).mockReturnValue({
        mutate: mutateStart, isPending: false, error: { status: 429, code: "site_concurrency_exhausted" }, data: undefined,
      } as never);
      render(<DraftCard proposalId={proposal.proposal_id} />);
      expect(screen.getByText(/site is at its run limit.*try again shortly/i)).toBeInTheDocument();
    });

    it("separates the three distinct 409 codes the run command can return", () => {
      vi.mocked(startHooks.useStartScheduleRun).mockReturnValue({
        mutate: mutateStart, isPending: false, submittedAt: 20,
        error: { status: 409, code: "idempotency_key_conflict" }, data: undefined,
      } as never);
      render(<DraftCard proposalId={proposal.proposal_id} />);
      expect(screen.getByText(/earlier command with different values/i)).toBeInTheDocument();
      expect(screen.queryByText(/refresh to see the current version/i)).not.toBeInTheDocument();
    });

    it("reports a withdrawn compute grant as a settled condition, not a retry", () => {
      vi.mocked(startHooks.useStartScheduleRun).mockReturnValue({
        mutate: mutateStart, isPending: false, submittedAt: 20,
        error: { status: 403, code: "compute_not_granted" }, data: undefined,
      } as never);
      render(<DraftCard proposalId={proposal.proposal_id} />);
      expect(screen.getByText(/optimization is turned off for this site/i)).toBeInTheDocument();
      expect(screen.queryByText(/try again/i)).not.toBeInTheDocument();
    });

    it("shows the newest command failure, not a stale one from another mutation", () => {
      vi.mocked(reviseHooks.useReviseProposal).mockReturnValue({
        mutate: mutateRevision, isPending: false, submittedAt: 10, error: { status: 422, code: "invalid_proposal" },
      } as never);
      vi.mocked(startHooks.useStartScheduleRun).mockReturnValue({
        mutate: mutateStart, isPending: false, submittedAt: 20,
        error: { status: 429, code: "site_concurrency_exhausted" }, data: undefined,
      } as never);
      render(<DraftCard proposalId={proposal.proposal_id} />);
      expect(screen.getByText(/site is at its run limit/i)).toBeInTheDocument();
      expect(screen.queryByText(/check the values/i)).not.toBeInTheDocument();
    });

    it("withdraws the run acknowledgement once the draft moves past that version", () => {
      show({ ...proposal, resource_version: 2 });
      vi.mocked(startHooks.useStartScheduleRun).mockReturnValue({
        mutate: mutateStart, isPending: false,
        data: { schedule_run_id: "66666666-6666-4666-8666-666666666666", status: "solver_queued", resource_version: 1 },
        variables: { proposal_id: proposal.proposal_id, expected_resource_version: 1 },
      } as never);
      render(<DraftCard proposalId={proposal.proposal_id} />);
      expect(screen.queryByRole("status", { name: "Optimization queued" })).not.toBeInTheDocument();
    });
  });

  it("renders the persisted summary while the proposal is still loading", () => {
    vi.mocked(proposalHooks.useProposal).mockReturnValue({
      data: undefined, isPending: true, isError: false, error: null, refetch,
    } as never);
    render(<DraftCard consequenceSummary={proposal.consequence_summary} proposalId={proposal.proposal_id} />);
    expect(card()).toHaveTextContent(proposal.consequence_summary);
  });
});
