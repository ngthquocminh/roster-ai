import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  createMemoryRouter,
  RouterProvider,
} from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

vi.mock("@/hooks/useScenarioContext", () => ({
  useScenarioContext: vi.fn(),
}));

import { useScenarioContext } from "@/hooks/useScenarioContext";
import { ScenarioWorkspace } from "./ScenarioWorkspace";


const mockContext =
  useScenarioContext as unknown as ReturnType<typeof vi.fn>;
const scenarioId = "11111111-1111-4111-8111-111111111111";
const context = {
  schema_version: "v1",
  scenario_name: "Fixture A",
  scenario_id: scenarioId,
  fixture_version: "v1",
  checksum_algorithm: "sha256",
  checksum_schema_version: "rfc8785-v1",
  checksum_digest: "a".repeat(64),
  site_id: "22222222-2222-4222-8222-222222222222",
  baseline_schedule_version: null,
};

function renderWorkspace() {
  const router = createMemoryRouter(
    [
      {
        path: "/scenarios/:scenarioId",
        Component: ScenarioWorkspace,
        children: [{ index: true, element: <p>Chat route content</p> }],
      },
      { path: "/signin", element: <p>Sign in surface</p> },
      { path: "/", element: <p>Catalogue surface</p> },
    ],
    { initialEntries: [`/scenarios/${scenarioId}`] },
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
  mockContext.mockReset();
});

it("renders persistent context, workspace navigation, and child content", () => {
  mockContext.mockReturnValue({
    data: context,
    error: null,
    isError: false,
    isPending: false,
    refetch: vi.fn(),
  });

  renderWorkspace();

  expect(screen.getByRole("heading", { name: "Fixture A" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Chat" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(screen.getByRole("link", { name: "Scenario Data" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Runs" })).toBeInTheDocument();
  expect(screen.getByText("Results", { selector: "[aria-disabled='true']" })).toBeInTheDocument();
  expect(screen.getByText("Chat route content")).toBeInTheDocument();
});

it("offers no scenario-switching affordance beyond the catalogue return link", () => {
  mockContext.mockReturnValue({
    data: context,
    error: null,
    isError: false,
    isPending: false,
    refetch: vi.fn(),
  });

  renderWorkspace();

  // Enumerate every link rather than probing for a combobox: a switcher built
  // the way this codebase builds navigation — as <Link>s — was invisible to
  // the previous assertion.
  expect(screen.getByRole("link", { name: "Change scenario" })).toHaveAttribute("href", "/");
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  expect(screen.queryAllByRole("button")).toHaveLength(0);
});

it("keeps the persistent context when a background refetch fails", async () => {
  const refetch = vi.fn();
  mockContext.mockReturnValue({
    data: context,
    dataUpdatedAt: Date.parse("2026-07-27T14:32:09Z"),
    error: { status: 503 },
    isError: true,
    isPending: false,
    refetch,
  });

  renderWorkspace();

  // AC #3: the context is persistent. A failed refetch over good cached data
  // must not tear the workspace down — this previously rendered a bare alert.
  expect(screen.getByRole("heading", { name: "Fixture A" })).toBeInTheDocument();
  expect(screen.getByText(scenarioId)).toBeInTheDocument();
  expect(screen.getByText("Not established")).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Change scenario" }),
  ).toBeInTheDocument();
  // EXPERIENCE.md:122's approved stale label, naming when the shown values
  // were last confirmed rather than inventing new vocabulary.
  expect(
    screen.getByText("Stale — last verified at 2026-07-27 14:32"),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(refetch).toHaveBeenCalledOnce();
});

it("renders and focuses a terminal, non-disclosing not-found view", async () => {
  mockContext.mockReturnValue({
    data: undefined,
    error: { status: 404, detail: "Secret fixture" },
    isError: true,
    isPending: false,
    refetch: vi.fn(),
  });

  renderWorkspace();

  const heading = screen.getByRole("heading", { name: "Scenario not found" });
  await waitFor(() => expect(heading).toHaveFocus());
  expect(screen.queryByText("Secret fixture")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Return to catalogue" })).toHaveAttribute(
    "href",
    "/",
  );
});

it("focuses the terminal heading even when stale cached data is present", async () => {
  mockContext.mockReturnValue({
    data: context,
    error: { status: 404 },
    isError: true,
    isPending: false,
    refetch: vi.fn(),
  });

  renderWorkspace();

  // A 404 is authoritative: the scenario is gone, so the terminal view wins
  // over cached data — and must still receive focus (UX-DR27).
  const heading = screen.getByRole("heading", { name: "Scenario not found" });
  await waitFor(() => expect(heading).toHaveFocus());
  expect(screen.queryByRole("heading", { name: "Fixture A" })).not.toBeInTheDocument();
});

it("treats a malformed scenario id as terminal rather than retryable", () => {
  mockContext.mockReturnValue({
    data: undefined,
    error: { status: 422 },
    isError: true,
    isPending: false,
    refetch: vi.fn(),
  });

  renderWorkspace();

  // 422 means the id in the URL is not a UUID. Retrying re-issues a request
  // that cannot succeed, so this must land on the terminal view.
  expect(
    screen.getByRole("heading", { name: "Scenario not found" }),
  ).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
});

it("renders safe retry behavior and a way back for non-terminal failures", () => {
  const refetch = vi.fn();
  mockContext.mockReturnValue({
    data: undefined,
    error: new Error("database internals"),
    isError: true,
    isPending: false,
    refetch,
  });

  renderWorkspace();

  expect(screen.getByRole("alert")).toHaveTextContent(
    "Couldn't load this content.",
  );
  expect(screen.getByRole("alert")).toHaveClass("text-destructive");
  expect(screen.queryByText("database internals")).not.toBeInTheDocument();
  // Without this the generic error state was a navigational dead end.
  expect(screen.getByRole("link", { name: "Return to catalogue" })).toHaveAttribute(
    "href",
    "/",
  );
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(refetch).toHaveBeenCalledOnce();
});

it("redirects to sign-in on 401 and clears the cached session", async () => {
  mockContext.mockReturnValue({
    data: undefined,
    error: { status: 401 },
    isError: true,
    isPending: false,
    refetch: vi.fn(),
  });

  const { queryClient } = renderWorkspace();

  await waitFor(() =>
    expect(screen.getByText("Sign in surface")).toBeInTheDocument(),
  );
  // Navigating away is not enough: RequireSession reads this cache, so a
  // stale truthy session would let Back re-enter the authenticated shell.
  expect(queryClient.getQueryData(["auth", "session"])).toBeNull();
  expect(screen.queryByRole("heading", { name: "Fixture A" })).not.toBeInTheDocument();
});

it("moves focus only once across the loading to loaded transition", async () => {
  const focused: string[] = [];
  const recordFocus = (event: FocusEvent) => {
    const target = event.target as HTMLElement;
    focused.push(`${target.tagName}:${target.textContent ?? ""}`);
  };
  document.addEventListener("focusin", recordFocus);

  mockContext.mockReturnValue({
    data: undefined,
    error: null,
    isError: false,
    isPending: true,
    refetch: vi.fn(),
  });
  const { router } = renderWorkspace();

  expect(screen.getByText("Loading scenario context…")).toBeInTheDocument();

  mockContext.mockReturnValue({
    data: context,
    error: null,
    isError: false,
    isPending: false,
    refetch: vi.fn(),
  });
  await router.navigate(`/scenarios/${scenarioId}`);

  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "Fixture A" })).toHaveFocus(),
  );
  // The transient loading heading must never take focus, or a screen reader
  // is interrupted mid-announcement when the real heading arrives.
  expect(focused.filter((entry) => entry.includes("Scenario workspace"))).toEqual([]);
  expect(focused.filter((entry) => entry.includes("Fixture A"))).toHaveLength(1);
  document.removeEventListener("focusin", recordFocus);
});
