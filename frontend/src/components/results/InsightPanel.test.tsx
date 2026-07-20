/**
 * InsightPanel coverage (UI-SPEC E7, RES-04/RES-05, D-13): idle button,
 * ready renders the report text, not-ready renders the honest fallback
 * copy WITHOUT any destructive/error treatment (the RES-04 guard — branch
 * on `ready`, never on status), and a 502 renders the distinct error copy
 * plus a working "Try Again" retry.
 *
 * Mocks `@/api/insights` (module boundary, not `msw`), mirroring
 * `useRunInsights.test.tsx` / `useTriggerRun.test.tsx`'s harness, and
 * renders `InsightPanel` inside a real `QueryClientProvider` so the
 * `useRunInsights` mutation drives real idle/pending/error/success state.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("@/api/insights", () => ({
  getRunInsights: vi.fn(),
}));

import { getRunInsights } from "@/api/insights";
import { InsightPanel } from "./InsightPanel";

const mockGetRunInsights = getRunInsights as unknown as ReturnType<
  typeof vi.fn
>;

beforeEach(() => {
  mockGetRunInsights.mockReset();
});

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    );
  }
  return render(<InsightPanel runId="r1" />, { wrapper: Wrapper });
}

describe("InsightPanel: idle [UI-SPEC E7/empty]", () => {
  it("shows the 'Get Insight Report' button before any click", () => {
    renderPanel();

    expect(
      screen.getByRole("button", { name: "Get Insight Report" }),
    ).toBeInTheDocument();
  });
});

describe("InsightPanel: ready [UI-SPEC E7/populated, RES-04]", () => {
  it("renders the report text after a { ready:true, report } resolution", async () => {
    mockGetRunInsights.mockResolvedValueOnce({
      ready: true,
      run_id: "r1",
      report: "R",
    });
    renderPanel();

    fireEvent.click(
      screen.getByRole("button", { name: "Get Insight Report" }),
    );

    await waitFor(() => expect(screen.getByText("R")).toBeInTheDocument());
    expect(screen.getByText("R").tagName).toBe("P");
  });

  it("applies break-words so a long unbroken token in the report cannot force horizontal page overflow", async () => {
    const longToken = "X".repeat(300);
    mockGetRunInsights.mockResolvedValueOnce({
      ready: true,
      run_id: "r1",
      report: longToken,
    });
    renderPanel();

    fireEvent.click(
      screen.getByRole("button", { name: "Get Insight Report" }),
    );

    const reportEl = await waitFor(() => screen.getByText(longToken));
    expect(reportEl.className).toContain("break-words");
  });
});

describe("InsightPanel: not-ready [UI-SPEC E7/edge, RES-04 guard]", () => {
  it("renders the not-ready copy and shows NO destructive/error styling — the ready:false branch is on `ready`, not status", async () => {
    mockGetRunInsights.mockResolvedValueOnce({ ready: false, run_id: "r1" });
    renderPanel();

    fireEvent.click(
      screen.getByRole("button", { name: "Get Insight Report" }),
    );

    await waitFor(() =>
      expect(
        screen.getByText("Not ready yet — try again in a moment."),
      ).toBeInTheDocument(),
    );

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Couldn't generate an insight report right now."),
    ).not.toBeInTheDocument();
  });
});

describe("InsightPanel: error [UI-SPEC E7/error, D-13]", () => {
  it("renders the 502 error copy plus a re-enabled Try Again button, and a second click re-invokes the fetch (retry)", async () => {
    mockGetRunInsights.mockRejectedValueOnce({ status: 502 });
    renderPanel();

    fireEvent.click(
      screen.getByRole("button", { name: "Get Insight Report" }),
    );

    await waitFor(() =>
      expect(
        screen.getByText("Couldn't generate an insight report right now."),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByText("The LLM provider may be unavailable."),
    ).toBeInTheDocument();

    const retryButton = screen.getByRole("button", { name: "Try Again" });
    expect(retryButton).toBeEnabled();

    mockGetRunInsights.mockResolvedValueOnce({
      ready: true,
      run_id: "r1",
      report: "Recovered.",
    });
    fireEvent.click(retryButton);

    await waitFor(() =>
      expect(screen.getByText("Recovered.")).toBeInTheDocument(),
    );
    expect(mockGetRunInsights).toHaveBeenCalledTimes(2);
  });
});
