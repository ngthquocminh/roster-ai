import { useSyncExternalStore } from "react";

import { originElementId, type EvidenceOrigin } from "./origin";

// Deliberately module-scoped rather than persisted: the marker survives the
// SPA jump/return flow but a reload re-derives state from immutable history.
// `persisted_event` is an audit row with no UPDATE grant (Decision 6).
const unavailableOrigins = new Set<string>();

// The set is external mutable state read during render, so it needs a real
// subscription: without one the timeline only happened to update because
// ChatView unmounts across the jump, and a concurrent render could observe two
// different values of the same set within one tree.
const listeners = new Set<() => void>();
let version = 0;

function emit(): void {
  version += 1;
  for (const listener of listeners) listener();
}

export function markEvidenceUnavailable(origin: EvidenceOrigin): void {
  const key = originElementId(origin);
  if (unavailableOrigins.has(key)) return;
  unavailableOrigins.add(key);
  emit();
}

// The mark must be reversible: `Missing evidence` offers Retry, and a Retry that
// resolves leaves the timeline asserting the opposite of the panel unless the
// success path clears it.
export function unmarkEvidenceUnavailable(origin: EvidenceOrigin): void {
  const key = originElementId(origin);
  if (!unavailableOrigins.delete(key)) return;
  emit();
}

export function isEvidenceUnavailable(origin: EvidenceOrigin): boolean {
  return unavailableOrigins.has(originElementId(origin));
}

export function clearEvidenceUnavailable(): void {
  if (!unavailableOrigins.size) return;
  unavailableOrigins.clear();
  emit();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getVersion(): number {
  return version;
}

/**
 * Subscribes the caller to availability changes. Returns an opaque version so a
 * component can call it ONCE (hook count stays stable regardless of how many
 * claims or refs it renders) and then read `isEvidenceUnavailable` freely.
 */
export function useEvidenceAvailability(): number {
  return useSyncExternalStore(subscribe, getVersion, getVersion);
}
