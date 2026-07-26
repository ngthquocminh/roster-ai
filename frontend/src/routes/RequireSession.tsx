import { Navigate, Outlet, useLocation } from "react-router";

import { useSession } from "@/hooks/useSession";
import { USER_ERROR_COPY } from "@/lib/errors";


export function RequireSession() {
  const location = useLocation();
  const session = useSession();

  if (session.isPending) {
    return <p className="p-6 text-sm">Checking session…</p>;
  }
  // getSession() already resolves an unauthenticated 401 to `data: null`
  // (see api/auth.ts) — a genuine query error here is a transient/network
  // failure, not "not signed in", so it gets a retry state, not a bounce
  // to /signin that would strand an already-authenticated user.
  if (session.isError) {
    return (
      <div className="p-6 text-sm">
        <p className="font-medium">{USER_ERROR_COPY.connection.title}</p>
        <p className="text-muted-foreground">
          {USER_ERROR_COPY.connection.description}
        </p>
      </div>
    );
  }
  if (!session.data) {
    return (
      <Navigate
        to="/signin"
        replace
        state={{ from: location.pathname + location.search }}
      />
    );
  }
  return <Outlet />;
}
