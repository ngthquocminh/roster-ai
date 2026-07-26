/** Thin TanStack Query wrappers around the application-session API. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

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
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: signOut,
    onSuccess: () => {
      queryClient.setQueryData(sessionQueryKey, null);
    },
  });
}
