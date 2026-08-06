import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";

vi.mock("@/hooks/useSession", () => ({
  useSignOut: vi.fn(),
}));

import { AppBar } from "./AppBar";
import { useSignOut } from "@/hooks/useSession";


const mockUseSignOut = useSignOut as unknown as ReturnType<typeof vi.fn>;

function renderAppBar() {
  const router = createMemoryRouter(
    [
      { path: "/", Component: AppBar },
      { path: "/signin", Component: () => <p>Sign-in page</p> },
    ],
    { initialEntries: ["/"] },
  );
  render(<RouterProvider router={router} />);
  return router;
}

describe("AppBar sign-out", () => {
  it("uses the governed evidence-link color for Home", () => {
    mockUseSignOut.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    renderAppBar();

    expect(screen.getByRole("link", { name: "Home" })).toHaveClass(
      "text-evidence-link",
    );
  });

  it("navigates to /signin on a plain successful sign-out", async () => {
    const mutateAsync = vi
      .fn()
      .mockResolvedValue({ postLogoutRedirectUrl: null });
    mockUseSignOut.mockReturnValue({ mutateAsync, isPending: false });
    const router = renderAppBar();

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/signin"),
    );
  });

  it("shows an error and does not navigate when sign-out fails", async () => {
    const mutateAsync = vi.fn().mockRejectedValue(new Error("network error"));
    mockUseSignOut.mockReturnValue({ mutateAsync, isPending: false });
    const router = renderAppBar();

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() =>
      expect(screen.getByText("Couldn't load this content.")).toBeInTheDocument(),
    );
    expect(router.state.location.pathname).toBe("/");
  });

  it("navigates the browser to the IdP's end-session URL when the provider returns one", async () => {
    const originalLocation = window.location;
    let hrefValue = "";
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...originalLocation, get href() {
        return hrefValue;
      }, set href(value: string) {
        hrefValue = value;
      } },
    });

    const mutateAsync = vi.fn().mockResolvedValue({
      postLogoutRedirectUrl: "https://fake-idp.test/logout",
    });
    mockUseSignOut.mockReturnValue({ mutateAsync, isPending: false });
    renderAppBar();

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() =>
      expect(hrefValue).toBe("https://fake-idp.test/logout"),
    );

    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
  });
});
