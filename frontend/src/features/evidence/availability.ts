import { originElementId, type EvidenceOrigin } from "./origin";

// Deliberately module-scoped rather than persisted: the marker survives the
// SPA jump/return flow but a reload re-derives state from immutable history.
const unavailableOrigins = new Set<string>();

export function markEvidenceUnavailable(origin: EvidenceOrigin): void {
  unavailableOrigins.add(originElementId(origin));
}

export function isEvidenceUnavailable(origin: EvidenceOrigin): boolean {
  return unavailableOrigins.has(originElementId(origin));
}

export function clearEvidenceUnavailable(): void {
  unavailableOrigins.clear();
}
