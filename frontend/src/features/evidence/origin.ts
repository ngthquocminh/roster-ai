export type EvidenceOrigin = Readonly<{
  conversationId: string;
  activityId: string;
  segmentIndex: number;
  refIndex: number;
}>;

const STORAGE_KEY = "shiftmind.evidence-origin";

export function originElementId(origin: EvidenceOrigin): string {
  return `evidence-origin-${origin.activityId}-${origin.segmentIndex}-${origin.refIndex}`;
}

function isEvidenceOrigin(value: unknown): value is EvidenceOrigin {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return typeof candidate.conversationId === "string"
    && typeof candidate.activityId === "string"
    && Number.isInteger(candidate.segmentIndex)
    && Number(candidate.segmentIndex) >= 0
    && Number.isInteger(candidate.refIndex)
    && Number(candidate.refIndex) >= 0;
}

export function rememberOrigin(origin: EvidenceOrigin): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(origin));
  } catch {
    // Storage can be disabled or full; history-state navigation still works.
  }
}

/**
 * Reads the pending origin WITHOUT consuming it, so a caller can check that the
 * restoration target is actually reachable before spending the token. Consuming
 * first and discovering the element is absent loses the origin permanently.
 */
export function peekOrigin(): EvidenceOrigin | null {
  try {
    const stored = sessionStorage.getItem(STORAGE_KEY);
    if (stored === null) return null;
    const parsed: unknown = JSON.parse(stored);
    if (isEvidenceOrigin(parsed)) return parsed;
    // A malformed entry can never become valid; drop it so it cannot be
    // re-read on every render.
    sessionStorage.removeItem(STORAGE_KEY);
    return null;
  } catch {
    return null;
  }
}

export function forgetOrigin(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage can be disabled; there is nothing to forget in that case.
  }
}

export function consumeOrigin(): EvidenceOrigin | null {
  const origin = peekOrigin();
  if (origin) forgetOrigin();
  return origin;
}
