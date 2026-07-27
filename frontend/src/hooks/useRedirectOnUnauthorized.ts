/**
 * Shared 401 handling for the governed scenario surfaces.
 *
 * Not a TanStack Query wrapper like its neighbours: the catalogue and the
 * workspace carried byte-identical redirect effects, and both dropped the
 * server's rejection on the floor. Navigating away is not enough — the
 * `["auth","session"]` cache still holds the session the server just refused
 * and `client.ts` still holds its CSRF token in module scope, so
 * `RequireSession` keeps reading a truthy session and Back re-renders the
 * authenticated shell over a dead one.
 */
import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router";

import { setCsrfToken } from "@/api/client";
import { sessionQueryKey } from "@/hooks/useSession";


export function useRedirectOnUnauthorized(errorStatus: number | undefined) {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  useEffect(() => {
    if (errorStatus !== 401) {
      return;
    }
    queryClient.setQueryData(sessionQueryKey, null);
    setCsrfToken(null);
    void navigate("/signin", {
      replace: true,
      state: { from: location.pathname + location.search },
    });
  }, [errorStatus, location.pathname, location.search, navigate, queryClient]);
}
