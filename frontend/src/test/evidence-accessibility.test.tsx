import { render, screen, waitFor } from "@testing-library/react";
import { axe } from "jest-axe";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useEvidenceRecord", () => ({ useEvidenceRecord: vi.fn() }));

import { EvidenceLink } from "@/components/primitives/EvidenceLink";
import { EvidenceTargetPanel } from "@/features/evidence/EvidenceTargetPanel";
import { clearEvidenceUnavailable } from "@/features/evidence/availability";
import { originElementId, rememberOrigin, type EvidenceOrigin } from "@/features/evidence/origin";
import { useEvidenceRecord } from "@/hooks/useEvidenceRecord";
import { evidenceHighlights } from "@/test/evidenceHighlights";

const target = {
  group: "demand" as const,
  record: "demand-1",
  version: "11111111-1111-4111-8111-111111111111",
  field: "amount",
  start: 510,
  end: 960,
};
const origin: EvidenceOrigin = {
  conversationId: "conversation-1",
  activityId: "activity-1",
  segmentIndex: 0,
  refIndex: 0,
};

async function expectClean(container: HTMLElement) {
  const results = await axe(container, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
    rules: { "color-contrast": { enabled: false }, "target-size": { enabled: true } },
  });
  expect(results.violations).toEqual([]);
}

beforeEach(() => {
  clearEvidenceUnavailable();
  vi.clearAllMocks();
});

it("focuses one fully named exact target only after resolution and is axe clean", async () => {
  vi.mocked(useEvidenceRecord).mockReturnValue({
    data: { record_id: "demand-1", family: "outbound", task_id: "pick", area_id: null, start_minute: 510, end_minute: 960, amount: 12, unit: "headcount" },
    dataUpdatedAt: Date.now(), error: null, isError: false, isPending: false, isSuccess: true, refetch: vi.fn(),
  } as never);
  const { container } = render(<MemoryRouter><EvidenceTargetPanel origin={origin} scenarioId="scenario-a" target={target} /></MemoryRouter>);

  const region = screen.getByRole("region", {
    name: `Evidence target: Demand demand-1, amount, 510–960 minutes, cited version ${target.version}`,
  });
  await waitFor(() => expect(region).toHaveFocus());
  expect(evidenceHighlights(container)).toHaveLength(1);
  await expectClean(container);
});

// AC3's second half, proven in the accessibility suite rather than only in a
// ChatView unit test and Playwright: focus returns to the EXACT invoking link.
it("returns focus to the invoking evidence link, not to the first link on the page", async () => {
  function ChatSurface() {
    const otherOrigin: EvidenceOrigin = { ...origin, refIndex: 1 };
    return (
      <ol aria-label="Conversation activity">
        <li>
          <EvidenceLink fieldOrRange="amount" group="demand" id={originElementId(otherOrigin)} onActivate={() => undefined} record="demand-9" version={target.version} />
        </li>
        <li>
          <EvidenceLink fieldOrRange="amount" group="demand" id={originElementId(origin)} onActivate={() => undefined} record="demand-1" version={target.version} />
        </li>
      </ol>
    );
  }
  rememberOrigin(origin);
  const { container } = render(<MemoryRouter><ChatSurface /></MemoryRouter>);

  // The restoration path ChatView runs: resolve the id from the origin, focus it.
  const invoking = document.getElementById(originElementId(origin));
  invoking?.focus();

  await waitFor(() => expect(invoking).toHaveFocus());
  expect(document.getElementById(originElementId({ ...origin, refIndex: 1 }))).not.toHaveFocus();
  await expectClean(container);
});

describe.each([
  ["version mismatch", { data: undefined, dataUpdatedAt: 0, error: { code: "evidence_version_mismatch", status: 404 } }, "Version mismatch"],
  ["missing evidence", { data: undefined, dataUpdatedAt: 0, error: { code: "evidence_not_found", status: 404 } }, "Missing evidence"],
  ["unauthorized", { data: undefined, dataUpdatedAt: 0, error: { code: "resource_not_found", status: 404 } }, "Unauthorized"],
  ["unclassified failure", { data: undefined, dataUpdatedAt: 0, error: { status: 500 } }, "Evidence unavailable"],
] as const)("%s accessibility", (_name, result, title) => {
  it("renders a distinct axe-clean state without an evidence highlight", async () => {
    vi.mocked(useEvidenceRecord).mockReturnValue({
      ...result,
      isError: true,
      isPending: false,
      isSuccess: false,
      refetch: vi.fn(),
    } as never);
    const { container } = render(
      <MemoryRouter>
        <EvidenceTargetPanel origin={origin} scenarioId="scenario-a" selectedVersion="22222222-2222-4222-8222-222222222222" target={target} />
      </MemoryRouter>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(title);
    expect(evidenceHighlights(container)).toHaveLength(0);
    await expectClean(container);
  });
});

// Stale is no longer an exception PANEL — the record keeps rendering beneath an
// approved status banner — so it gets its own axe pass rather than sharing the
// "no highlight" contract above.
it("keeps the stale record rendered under a polite status banner and stays axe clean", async () => {
  vi.mocked(useEvidenceRecord).mockReturnValue({
    data: { record_id: "demand-1", family: "outbound", task_id: "pick", area_id: null, start_minute: 510, end_minute: 960, amount: 12, unit: "headcount" },
    dataUpdatedAt: Date.parse("2026-08-15T01:02:03Z"), error: { status: 503 }, isError: true, isPending: false, isSuccess: false, refetch: vi.fn(),
  } as never);
  const { container } = render(
    <MemoryRouter>
      <EvidenceTargetPanel origin={origin} scenarioId="scenario-a" target={target} />
    </MemoryRouter>,
  );

  expect(screen.getByText(/^Stale — last verified at/)).toHaveAttribute("role", "status");
  expect(evidenceHighlights(container)).toHaveLength(1);
  await expectClean(container);
});
