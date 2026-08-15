import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

vi.mock("@/hooks/useEvidenceRecord", () => ({ useEvidenceRecord: vi.fn() }));

import { evidenceHighlights } from "@/test/evidenceHighlights";
import { useEvidenceRecord } from "@/hooks/useEvidenceRecord";
import { EvidenceTargetPanel } from "./EvidenceTargetPanel";
import { clearEvidenceUnavailable, isEvidenceUnavailable } from "./availability";
import type { EvidenceOrigin } from "./origin";

const target = {
  group: "demand" as const,
  record: "demand-1",
  version: "11111111-1111-4111-8111-111111111111",
  field: "amount",
  start: 510,
  end: 960,
};

beforeEach(() => {
  clearEvidenceUnavailable();
  vi.clearAllMocks();
});

it("waits for the exact record, then renders and focuses one named highlight", async () => {
  vi.mocked(useEvidenceRecord).mockReturnValue({
    data: {
      record_id: "demand-1",
      family: "outbound",
      task_id: "pick",
      area_id: "area-1",
      start_minute: 510,
      end_minute: 960,
      amount: 12,
      unit: "headcount",
    },
    dataUpdatedAt: Date.now(),
    error: null,
    isError: false,
    isPending: false,
    isSuccess: true,
    refetch: vi.fn(),
  } as never);

  const { container } = render(
    <MemoryRouter>
      <EvidenceTargetPanel scenarioId="scenario-a" target={target} />
    </MemoryRouter>,
  );

  const region = screen.getByRole("region", {
    name: `Evidence target: Demand demand-1, amount, 510–960 minutes, cited version ${target.version}`,
  });
  await waitFor(() => expect(region).toHaveFocus());
  expect(evidenceHighlights(container)).toHaveLength(1);
  expect(screen.getByRole("button", { name: "Copy Record ID demand-1" })).toBeInTheDocument();
  expect(screen.getByText("Day 1, 08:30–16:00")).toBeInTheDocument();
  expect(screen.getByText("Targeted field").nextElementSibling).toHaveTextContent("amount");
  expect(screen.queryByRole("button", { name: "Return to claim" })).not.toBeInTheDocument();
});

it("renders a shape-matched skeleton without an empty highlight while loading", () => {
  vi.mocked(useEvidenceRecord).mockReturnValue({
    data: undefined,
    error: null,
    isError: false,
    isPending: true,
    isSuccess: false,
    refetch: vi.fn(),
  } as never);
  const { container } = render(
    <MemoryRouter>
      <EvidenceTargetPanel scenarioId="scenario-a" target={target} />
    </MemoryRouter>,
  );

  expect(screen.getByRole("status", { name: "Loading cited evidence" })).toBeInTheDocument();
  expect(evidenceHighlights(container)).toHaveLength(0);
});

it("keeps the workspace selected version and renders a mismatch instead of retargeting", () => {
  vi.mocked(useEvidenceRecord).mockReturnValue({
    data: undefined,
    error: { code: "evidence_version_mismatch", status: 404 },
    isError: true,
    isPending: false,
    isSuccess: false,
    refetch: vi.fn(),
  } as never);
  const { container } = render(
    <MemoryRouter>
      <EvidenceTargetPanel
        scenarioId="scenario-a"
        selectedVersion="22222222-2222-4222-8222-222222222222"
        target={target}
      />
    </MemoryRouter>,
  );

  const alert = screen.getByRole("alert");
  expect(alert).toHaveTextContent("Version mismatch");
  expect(alert).toHaveTextContent(target.version);
  expect(alert).toHaveTextContent("22222222-2222-4222-8222-222222222222");
  expect(evidenceHighlights(container)).toHaveLength(0);
});

it("returns to the byte-identical conversation in the unchanged scenario", async () => {
  vi.mocked(useEvidenceRecord).mockReturnValue({
    data: { record_id: "demand-1", family: "outbound", task_id: "pick", area_id: null, start_minute: 510, end_minute: 960, amount: 12, unit: "headcount" },
    dataUpdatedAt: Date.now(), error: null, isError: false, isPending: false, isSuccess: true, refetch: vi.fn(),
  } as never);
  const origin: EvidenceOrigin = {
    conversationId: "conversation%2Fliteral",
    activityId: "activity-1",
    segmentIndex: 0,
    refIndex: 0,
  };
  const router = createMemoryRouter([
    { path: "*", element: <EvidenceTargetPanel origin={origin} scenarioId="scenario-a" target={target} /> },
  ], { initialEntries: ["/scenarios/scenario-a/data?group=demand"] });
  render(<RouterProvider router={router} />);

  await userEvent.click(screen.getByRole("button", { name: "Return to claim" }));

  await waitFor(() => expect(router.state.location.pathname).toBe("/scenarios/scenario-a"));
  expect(router.state.location.search).toBe("?conversation=conversation%252Fliteral");
});

it("renders missing evidence with retry and marks the origin unavailable", () => {
  const origin: EvidenceOrigin = { conversationId: "conversation-1", activityId: "activity-1", segmentIndex: 0, refIndex: 0 };
  vi.mocked(useEvidenceRecord).mockReturnValue({
    data: undefined, error: { code: "evidence_not_found", status: 404 }, isError: true, isPending: false, isSuccess: false, refetch: vi.fn(),
  } as never);
  const { container } = render(<MemoryRouter><EvidenceTargetPanel origin={origin} scenarioId="scenario-a" target={target} /></MemoryRouter>);

  expect(screen.getByRole("alert")).toHaveTextContent("Missing evidence");
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Return to claim" })).toBeInTheDocument();
  expect(isEvidenceUnavailable(origin)).toBe(true);
  expect(evidenceHighlights(container)).toHaveLength(0);
});

it("uses byte-identical non-disclosing unauthorized copy for either server detail", () => {
  const renderUnauthorized = (detail: string) => {
    vi.mocked(useEvidenceRecord).mockReturnValue({
      data: undefined, error: { code: "resource_not_found", detail, status: 404 }, isError: true, isPending: false, isSuccess: false, refetch: vi.fn(),
    } as never);
    return render(<MemoryRouter><EvidenceTargetPanel scenarioId="scenario-a" target={target} /></MemoryRouter>);
  };
  const first = renderUnauthorized("record exists");
  const firstText = screen.getByRole("alert").textContent;
  first.unmount();
  renderUnauthorized("record absent");

  expect(screen.getByRole("alert")).toHaveTextContent("Evidence is not available to this session.");
  expect(screen.getByRole("alert").textContent).toBe(firstText);
  expect(screen.getByRole("alert")).not.toHaveTextContent(/exists|absent/);
});

it("labels cached evidence stale without discarding the record it already holds", () => {
  const origin: EvidenceOrigin = { conversationId: "conversation-1", activityId: "activity-1", segmentIndex: 0, refIndex: 0 };
  vi.mocked(useEvidenceRecord).mockReturnValue({
    data: { record_id: "demand-1", amount: 12 }, dataUpdatedAt: Date.parse("2026-08-15T01:02:03Z"), error: { status: 503 }, isError: true, isPending: false, isSuccess: false, refetch: vi.fn(),
  } as never);
  const { container } = render(<MemoryRouter><EvidenceTargetPanel origin={origin} scenarioId="scenario-a" target={target} /></MemoryRouter>);

  // ScenarioWorkspace.tsx:118-137's approved pattern: only the message is a live
  // region, the control sits outside it, and the content stays on screen.
  const staleMessage = screen.getByText(/^Stale — last verified at/);
  expect(staleMessage).toHaveAttribute("role", "status");
  expect(staleMessage).not.toContainElement(screen.getByRole("button", { name: "Retry" }));
  expect(screen.getByRole("button", { name: "Return to claim" })).toBeInTheDocument();
  expect(evidenceHighlights(container)).toHaveLength(1);
  expect(screen.getByRole("button", { name: "Copy Record ID demand-1" })).toBeInTheDocument();
  // The whole panel must not become an assertive live region.
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("states a terminal unclassified failure instead of rendering nothing", () => {
  const origin: EvidenceOrigin = { conversationId: "conversation-1", activityId: "activity-1", segmentIndex: 0, refIndex: 0 };
  vi.mocked(useEvidenceRecord).mockReturnValue({
    // A 500 from scenario_projection.py:499, or a transport failure with no
    // `code` at all. `retry: false` makes this terminal, not transient.
    data: undefined, dataUpdatedAt: 0, error: { status: 500 }, isError: true, isPending: false, isSuccess: false, refetch: vi.fn(),
  } as never);
  const { container } = render(<MemoryRouter><EvidenceTargetPanel origin={origin} scenarioId="scenario-a" target={target} /></MemoryRouter>);

  expect(screen.getByRole("alert")).toHaveTextContent("Evidence unavailable");
  expect(screen.getByRole("alert")).toHaveTextContent("No current or similar record was substituted.");
  expect(screen.getByRole("button", { name: "Return to claim" })).toBeInTheDocument();
  expect(evidenceHighlights(container)).toHaveLength(0);
  expect(container).not.toBeEmptyDOMElement();
});

it("branches on the RFC 7807 code even when a cached record is still present", () => {
  const origin: EvidenceOrigin = { conversationId: "conversation-1", activityId: "activity-1", segmentIndex: 0, refIndex: 0 };
  vi.mocked(useEvidenceRecord).mockReturnValue({
    // A refetch (refetchOnWindowFocus is on by default) fails on a record that
    // has since been deleted, while TanStack still holds the old data.
    data: { record_id: "demand-1" }, dataUpdatedAt: Date.now(), error: { code: "evidence_not_found", status: 404 }, isError: true, isPending: false, isSuccess: false, refetch: vi.fn(),
  } as never);
  const { container } = render(<MemoryRouter><EvidenceTargetPanel origin={origin} scenarioId="scenario-a" target={target} /></MemoryRouter>);

  // Decision 5: the code wins over the presence of cached data. Showing "Stale"
  // here contradicted the timeline, which marks the same claim unavailable.
  expect(screen.getByRole("alert")).toHaveTextContent("Missing evidence");
  expect(screen.queryByText(/^Stale — last verified at/)).not.toBeInTheDocument();
  expect(evidenceHighlights(container)).toHaveLength(0);
  expect(isEvidenceUnavailable(origin)).toBe(true);
});

it("clears the unavailable mark when a retry resolves the cited record", async () => {
  const origin: EvidenceOrigin = { conversationId: "conversation-1", activityId: "activity-1", segmentIndex: 0, refIndex: 0 };
  vi.mocked(useEvidenceRecord).mockReturnValue({
    data: undefined, dataUpdatedAt: 0, error: { code: "evidence_not_found", status: 404 }, isError: true, isPending: false, isSuccess: false, refetch: vi.fn(),
  } as never);
  const first = render(<MemoryRouter><EvidenceTargetPanel origin={origin} scenarioId="scenario-a" target={target} /></MemoryRouter>);
  expect(isEvidenceUnavailable(origin)).toBe(true);
  first.unmount();

  vi.mocked(useEvidenceRecord).mockReturnValue({
    data: { record_id: "demand-1", amount: 12 }, dataUpdatedAt: Date.now(), error: null, isError: false, isPending: false, isSuccess: true, refetch: vi.fn(),
  } as never);
  render(<MemoryRouter><EvidenceTargetPanel origin={origin} scenarioId="scenario-a" target={target} /></MemoryRouter>);

  // Otherwise the timeline keeps a red "Evidence unavailable" beside a link
  // that now works, for the rest of the session.
  await waitFor(() => expect(isEvidenceUnavailable(origin)).toBe(false));
});
