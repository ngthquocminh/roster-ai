import { useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  cancelScheduleRun,
  type ScheduleRunCancellation,
} from "@/api/scheduleRuns";
import { createIdempotencyKeyHolder } from "@/lib/idempotency";

/**
 * Story 3.4 shipped `POST /schedule-runs/{id}/cancellation`; this is its
 * first frontend consumer. Mirrors `useStartScheduleRun`'s key-holding shape:
 * a key survives a failed attempt (so a lost-response success replays rather
 * than colliding on `resource_version`) and only rotates once acknowledged.
 */
export function useCancelScheduleRun(runId: string) {
  const queryClient = useQueryClient();
  const keys = useRef(createIdempotencyKeyHolder());
  return useMutation({
    mutationFn: (body: ScheduleRunCancellation) =>
      cancelScheduleRun(runId, body, keys.current.current()),
    onSuccess: () => {
      keys.current.settle();
      // Scenario id isn't in scope here; invalidate every Runs page rather
      // than plumb it through just for a cache key.
      void queryClient.invalidateQueries({ queryKey: ["scheduleRuns"] });
    },
    onError: () => {
      // Deliberately does NOT settle: see useStartScheduleRun.
    },
  });
}
