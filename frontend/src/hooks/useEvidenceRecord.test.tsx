import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

vi.mock("@/features/evidence/resolve", () => ({ resolveEvidenceRecord: vi.fn() }));

import { resolveEvidenceRecord } from "@/features/evidence/resolve";
import { useEvidenceRecord } from "./useEvidenceRecord";

const target = {
  group: "demand" as const,
  record: "demand-1",
  version: "11111111-1111-4111-8111-111111111111",
};

beforeEach(() => vi.clearAllMocks());

it("keys exact evidence by cited version and does not retry failures", async () => {
  vi.mocked(resolveEvidenceRecord).mockRejectedValueOnce(new Error("missing"));
  const queryClient = new QueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
  const { result } = renderHook(() => useEvidenceRecord("scenario-a", target), { wrapper });

  await waitFor(() => expect(result.current.isError).toBe(true));
  expect(resolveEvidenceRecord).toHaveBeenCalledOnce();
  expect(queryClient.getQueryCache().getAll()[0]?.queryKey).toEqual([
    "evidence-record",
    "scenario-a",
    "demand",
    "demand-1",
    target.version,
  ]);
});

it("is disabled without a valid target", async () => {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
  renderHook(() => useEvidenceRecord("scenario-a", null), { wrapper });
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(resolveEvidenceRecord).not.toHaveBeenCalled();
});

it.each([
  ["version mismatch", { code: "evidence_version_mismatch", status: 404 }],
  ["missing evidence", { code: "evidence_not_found", status: 404 }],
  ["unauthorized", { code: "resource_not_found", status: 404 }],
  ["stale refresh", { code: "upstream_unavailable", status: 503 }],
])("resolves the cited locator exactly once for %s", async (_state, error) => {
  vi.mocked(resolveEvidenceRecord).mockRejectedValueOnce(error);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
  const { result } = renderHook(() => useEvidenceRecord("scenario-a", target), { wrapper });

  await waitFor(() => expect(result.current.isError).toBe(true));
  expect(resolveEvidenceRecord).toHaveBeenCalledOnce();
  expect(resolveEvidenceRecord).toHaveBeenCalledWith("scenario-a", target);
});
