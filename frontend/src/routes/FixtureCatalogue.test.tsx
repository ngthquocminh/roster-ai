import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import {
  createMemoryRouter,
  RouterProvider,
} from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

vi.mock("@/hooks/useFixtureCatalogue", () => ({
  useFixtureCatalogue: vi.fn(),
}));

import { useFixtureCatalogue } from "@/hooks/useFixtureCatalogue";
import { FixtureCatalogue } from "./FixtureCatalogue";


const mockCatalogue =
  useFixtureCatalogue as unknown as ReturnType<typeof vi.fn>;

function renderCatalogue() {
  const router = createMemoryRouter(
    [
      { path: "/", Component: FixtureCatalogue },
      { path: "/signin", element: <p>Sign-in route</p> },
    ],
    { initialEntries: ["/"] },
  );
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { queryClient, router };
}

beforeEach(() => {
  mockCatalogue.mockReset();
});

it("focuses the catalogue heading when the route opens", async () => {
  mockCatalogue.mockReturnValue({
    data: [],
    error: null,
    isError: false,
    isPending: false,
    refetch: vi.fn(),
  });

  renderCatalogue();

  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "Fixture catalogue" })).toHaveFocus(),
  );
});

it("routes a catalogue-query 401 to sign-in without rendering cached rows", async () => {
  mockCatalogue.mockReturnValue({
    data: [
      {
        scenario_id: "secret-scenario",
        scenario_name: "Secret fixture",
      },
    ],
    error: { status: 401 },
    isError: true,
    isPending: false,
    refetch: vi.fn(),
  });

  const { queryClient, router } = renderCatalogue();

  expect(screen.queryByText("Secret fixture")).not.toBeInTheDocument();
  await screen.findByText("Sign-in route");
  expect(router.state.location.pathname).toBe("/signin");
  expect(router.state.location.state).toEqual({ from: "/" });
  // The server rejected this session, so the cached copy RequireSession reads
  // must go with it — otherwise Back re-enters the authenticated shell.
  expect(queryClient.getQueryData(["auth", "session"])).toBeNull();
});
