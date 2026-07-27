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
  const router = createMemoryRouter(
    [{ path: "/", Component: FixtureCatalogue }],
    { initialEntries: ["/"] },
  );
  render(<RouterProvider router={router} />);

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
  const router = createMemoryRouter(
    [
      { path: "/", Component: FixtureCatalogue },
      { path: "/signin", element: <p>Sign-in route</p> },
    ],
    { initialEntries: ["/"] },
  );
  render(<RouterProvider router={router} />);

  expect(screen.queryByText("Secret fixture")).not.toBeInTheDocument();
  await screen.findByText("Sign-in route");
  expect(router.state.location.pathname).toBe("/signin");
  expect(router.state.location.state).toEqual({ from: "/" });
});
