import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

vi.mock("@/hooks/useEvidenceRecord", () => ({ useEvidenceRecord: vi.fn() }));

import { EVIDENCE_HIGHLIGHT_CLASS } from "@/components/primitives/EvidenceHighlight";
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
    name: `Evidence target: demand demand-1, amount, 510–960 minutes, fixture ${target.version}`,
  });
  await waitFor(() => expect(region).toHaveFocus());
  expect(container.querySelectorAll(`[class="${EVIDENCE_HIGHLIGHT_CLASS}"]`)).toHaveLength(1);
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
  expect(container.querySelector(`[class="${EVIDENCE_HIGHLIGHT_CLASS}"]`)).toBeNull();
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
  expect(container.querySelector(`[class="${EVIDENCE_HIGHLIGHT_CLASS}"]`)).toBeNull();
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
  expect(container.querySelector(`[class="${EVIDENCE_HIGHLIGHT_CLASS}"]`)).toBeNull();
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

it("labels cached evidence stale with only the approved status and refresh action", () => {
  vi.mocked(useEvidenceRecord).mockReturnValue({
    data: { record_id: "demand-1" }, dataUpdatedAt: Date.parse("2026-08-15T01:02:03Z"), error: { status: 503 }, isError: true, isPending: false, isSuccess: false, refetch: vi.fn(),
  } as never);
  const { container } = render(<MemoryRouter><EvidenceTargetPanel scenarioId="scenario-a" target={target} /></MemoryRouter>);

  expect(screen.getByRole("status")).toHaveTextContent(/^Stale — last verified at/);
  expect(screen.getByRole("button", { name: "Refresh" })).toBeInTheDocument();
  expect(container.querySelector(`[class="${EVIDENCE_HIGHLIGHT_CLASS}"]`)).toBeNull();
});
