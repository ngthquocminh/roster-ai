import { Navigate, Outlet, useLocation } from "react-router";

import { useSession } from "@/hooks/useSession";


export function RequireSession() {
  const location = useLocation();
  const session = useSession();

  if (session.isPending) {
    return <p className="p-6 text-sm">Checking session…</p>;
  }
  if (session.isError || !session.data) {
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
