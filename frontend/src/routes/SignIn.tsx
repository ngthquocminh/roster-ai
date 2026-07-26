import { useLocation } from "react-router";

import { API_BASE_URL } from "@/lib/env";


const LOGIN_URL = `${API_BASE_URL.replace(/\/$/, "")}/api/v1/auth/login`;

export function SignIn() {
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
  const loginUrl =
    from && from.startsWith("/") && !from.startsWith("//")
      ? `${LOGIN_URL}?${new URLSearchParams({ return_to: from })}`
      : LOGIN_URL;

  return (
    <main className="mx-auto max-w-md px-6 py-16">
      <h1 className="text-2xl font-semibold">ShiftMind</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Sign in to open the seeded site workspace.
      </p>
      <a
        className="mt-6 inline-flex h-8 items-center rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground"
        href={loginUrl}
      >
        Sign in
      </a>
    </main>
  );
}
