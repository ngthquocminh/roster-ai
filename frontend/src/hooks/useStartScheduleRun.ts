import { useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  startScheduleRun,
  type ScheduleRunStart,
} from "@/api/scheduleRuns";
import { createIdempotencyKeyHolder } from "@/lib/idempotency";

export function useStartScheduleRun() {
  // One key per command intent, held across retries. A key minted inside the
  // request function would be new on every attempt, so the server could never
  // recognise a retry and AD-8's replay path would be unreachable from here.
  const keys = useRef(createIdempotencyKeyHolder());
  return useMutation({
    mutationFn: (body: ScheduleRunStart) =>
      startScheduleRun(body, keys.current.current()),
    onSuccess: () => {
      keys.current.settle();
    },
    onError: () => {
      // Deliberately does NOT settle: the next attempt reuses the same key so a
      // command that succeeded behind a lost response replays instead of
      // colliding on the resource version.
    },
  });
}
