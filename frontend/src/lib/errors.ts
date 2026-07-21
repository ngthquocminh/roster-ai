type UserErrorCopy = Readonly<{
  title: string;
  description: string;
}>;

/**
 * Fixed product copy for app-level failures.
 *
 * Error objects may contain backend commands, source paths, stack traces, or
 * exception messages. Components can log those objects for developers, but
 * must render only these values so diagnostic data never crosses into JSX.
 */
export const USER_ERROR_COPY = {
  connection: {
    title: "Couldn't load this content.",
    description: "Try again. If the problem continues, reload the page.",
  },
  unexpectedCrash: {
    title: "Something went wrong.",
    description: "Reload the page and try again.",
  },
  runFailure: {
    title: "Run Failed",
    description: "This run couldn't be completed. Try starting a new run.",
  },
} as const satisfies Record<
  "connection" | "unexpectedCrash" | "runFailure",
  UserErrorCopy
>;

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
