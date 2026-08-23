import { useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  startScheduleRun,
  type ScheduleRunStart,
} from "@/api/scheduleRuns";
import { scheduleRunsKey } from "@/hooks/useScheduleRuns";
import { createIdempotencyKeyHolder } from "@/lib/idempotency";

export function useStartScheduleRun() {
  const queryClient = useQueryClient();
  // One key per command intent, held across retries. A key minted inside the
  // request function would be new on every attempt, so the server could never
  // recognise a retry and AD-8's replay path would be unreachable from here.
  const keys = useRef(createIdempotencyKeyHolder());
  return useMutation({
    mutationFn: (body: ScheduleRunStart) =>
      startScheduleRun(body, keys.current.current()),
    onSuccess: () => {
      keys.current.settle();
      // The started run is a new row in the Runs list. Without this, Story
      // 3.7's Retry button reports "Run <id> queued" while the table it was
      // clicked from keeps showing the old page -- and because the key HAS
      // settled, a planner who clicks again because "nothing happened" mints
      // a fresh key and starts a second real run. Mirrors
      // `useCancelScheduleRun`; the scenario id is not in scope here, so the
      // whole prefix is invalidated rather than plumbed through.
      void queryClient.invalidateQueries({ queryKey: scheduleRunsKey() });
    },
    onError: () => {
      // Deliberately does NOT settle: the next attempt reuses the same key so a
      // command that succeeded behind a lost response replays instead of
      // colliding on the resource version.
    },
  });
}
