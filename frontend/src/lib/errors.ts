/**
 * Single typed accessor for the `status` an API error carries (WR-03).
 *
 * `api/scenarios.ts`/`api/constraints.ts` throw `{ status: response.status,
 * ...error }` on a non-2xx response; TanStack Query surfaces that thrown
 * value as `query.error`/`mutation.error`, typed `unknown`. Three components
 * (`ScenarioHeader`, `ConstraintInput`, `Editor`) each repeated the same
 * `(error as { status?: number } | null)?.status` cast — a future change to
 * the thrown error shape would require hunting down and updating every call
 * site by hand. Centralizing it here means that only has to happen once.
 */
export function getErrorStatus(error: unknown): number | undefined {
  if (typeof error !== "object" || error === null) {
    return undefined;
  }
  const status = (error as { status?: unknown }).status;
  return typeof status === "number" ? status : undefined;
}
