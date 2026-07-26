import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/auth", () => ({
  getSession: vi.fn(),
  signOut: vi.fn(),
}));

import { getSession, signOut } from "@/api/auth";
import { useSession, useSignOut } from "./useSession";


const mockGetSession = getSession as unknown as ReturnType<typeof vi.fn>;
const mockSignOut = signOut as unknown as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  mockGetSession.mockReset();
  mockSignOut.mockReset();
});

describe("useSession", () => {
  it("queries the thin auth wrapper under the stable session key", async () => {
    const session = {
      app_user_id: "00000000-0000-0000-0000-000000000001",
      site_id: "00000000-0000-0000-0000-000000000002",
      csrf_token: "csrf",
      expires_at: "2030-01-01T00:00:00Z",
    };
    mockGetSession.mockResolvedValueOnce(session);

    const { result } = renderHook(() => useSession(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetSession).toHaveBeenCalledTimes(1);
    expect(result.current.data).toEqual(session);
  });

  it("exposes an unauthenticated session as null", async () => {
    mockGetSession.mockResolvedValueOnce(null);

    const { result } = renderHook(() => useSession(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeNull();
  });
});

describe("useSignOut", () => {
  it("calls the thin sign-out wrapper", async () => {
    mockSignOut.mockResolvedValueOnce({ postLogoutRedirectUrl: null });

    const { result } = renderHook(() => useSignOut(), { wrapper });
    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockSignOut).toHaveBeenCalledTimes(1);
  });

  it("clears the cached session on success so a stale session cannot render post-logout", async () => {
    mockSignOut.mockResolvedValueOnce({ postLogoutRedirectUrl: null });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    queryClient.setQueryData(["auth", "session"], {
      app_user_id: "00000000-0000-0000-0000-000000000001",
      site_id: "00000000-0000-0000-0000-000000000002",
      csrf_token: "csrf",
      expires_at: "2030-01-01T00:00:00Z",
    });
    function localWrapper({ children }: { children: ReactNode }) {
      return (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      );
    }

    const { result } = renderHook(() => useSignOut(), { wrapper: localWrapper });
    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryData(["auth", "session"])).toBeNull();
  });
});
