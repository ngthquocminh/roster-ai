import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

vi.mock("@/api/provenance");

import { getRunProvenance } from "@/api/provenance";
import { DebugDetailsPanel } from "./DebugDetailsPanel";

const refs = [{ group: "demand", record_id: "demand-1" }] as never;

function renderPanel(evidenceRefs: never | null = refs) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><DebugDetailsPanel evidenceRefs={evidenceRefs} runId="run-1" scenarioId="s" /></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getRunProvenance).mockResolvedValue({ schedule_run_id: "run-1", site_id: "site", items: [], schema_version: "v1" } as never);
});

it("is collapsed and makes no provenance request until opened", async () => {
  renderPanel();
  expect(screen.queryByRole("heading", { name: "Decision provenance" })).not.toBeInTheDocument();
  expect(getRunProvenance).not.toHaveBeenCalled();

  await userEvent.click(screen.getByRole("button", { name: /Debug details/ }));
  expect(await screen.findByRole("list", { name: "Decision provenance" })).toBeInTheDocument();
  expect(screen.getByText("demand: demand-1")).toBeInTheDocument();
  expect(getRunProvenance).toHaveBeenCalledTimes(1);
});

it("shows the empty evidence text, and omits Evidence when there is no result to cite", async () => {
  const { unmount } = renderPanel([] as never);
  await userEvent.click(screen.getByRole("button", { name: /Debug details/ }));
  expect(screen.getByText("No evidence references")).toBeInTheDocument();
  unmount();

  renderPanel(null);
  await userEvent.click(screen.getByRole("button", { name: /Debug details/ }));
  expect(screen.queryByRole("heading", { name: "Evidence" })).not.toBeInTheDocument();
});

it("offers retry when provenance fails to load", async () => {
  vi.mocked(getRunProvenance).mockRejectedValue({ status: 500 });
  renderPanel();
  await userEvent.click(screen.getByRole("button", { name: /Debug details/ }));
  expect(await screen.findByText("Decision provenance unavailable")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retry provenance" })).toBeInTheDocument();
});
