import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/scenarioCatalogue", () => ({
  getScenarioContext: vi.fn(),
  listFixtureVersions: vi.fn(),
}));

import {
  getScenarioContext,
  listFixtureVersions,
} from "@/api/scenarioCatalogue";
import {
  fixtureCatalogueQueryKey,
  useFixtureCatalogue,
} from "./useFixtureCatalogue";
import { useScenarioContext } from "./useScenarioContext";


const mockList = listFixtureVersions as unknown as ReturnType<typeof vi.fn>;
const mockGet = getScenarioContext as unknown as ReturnType<typeof vi.fn>;
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

function wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  queryClient.clear();
  mockList.mockReset();
  mockGet.mockReset();
});

describe("catalogue query hooks", () => {
  it("uses the stable fixture catalogue key", async () => {
    mockList.mockResolvedValueOnce([]);

    const { result } = renderHook(() => useFixtureCatalogue(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryData(fixtureCatalogueQueryKey)).toEqual([]);
    expect(mockList).toHaveBeenCalledOnce();
  });

  it("keys scenario context by the stable scenario id", async () => {
    const context = { scenario_id: "scenario-a" };
    mockGet.mockResolvedValueOnce(context);

    const { result } = renderHook(
      () => useScenarioContext("scenario-a"),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(
      queryClient.getQueryData(["scenario-context", "scenario-a"]),
    ).toEqual(context);
    expect(mockGet).toHaveBeenCalledWith("scenario-a");
  });
});
