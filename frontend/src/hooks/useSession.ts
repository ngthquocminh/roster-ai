/** Thin TanStack Query wrappers around the application-session API. */
import { useMutation, useQuery } from "@tanstack/react-query";

import { getSession, signOut } from "@/api/auth";


export const sessionQueryKey = ["auth", "session"] as const;

export function useSession() {
  return useQuery({
    queryKey: sessionQueryKey,
    queryFn: getSession,
    retry: false,
  });
}

export function useSignOut() {
  return useMutation({
    mutationFn: signOut,
  });
}
