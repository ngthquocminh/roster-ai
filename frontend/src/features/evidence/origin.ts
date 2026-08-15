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

export function consumeOrigin(): EvidenceOrigin | null {
  try {
    const stored = sessionStorage.getItem(STORAGE_KEY);
    if (stored === null) return null;
    sessionStorage.removeItem(STORAGE_KEY);
    const parsed: unknown = JSON.parse(stored);
    return isEvidenceOrigin(parsed) ? parsed : null;
  } catch {
    return null;
  }
}
