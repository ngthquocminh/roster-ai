import { EVIDENCE_HIGHLIGHT_CLASS } from "@/components/primitives/EvidenceHighlight";

const HIGHLIGHT_TOKENS = EVIDENCE_HIGHLIGHT_CLASS.split(" ").filter(Boolean);

/**
 * Finds every rendered evidence highlight.
 *
 * Deliberately NOT `[class="${EVIDENCE_HIGHLIGHT_CLASS}"]`: `EvidenceHighlight`
 * composes its class list through `cn(EVIDENCE_HIGHLIGHT_CLASS, className)`, so
 * one caller passing a `className` — or tailwind-merge reordering a token —
 * makes an exact-string selector match nothing. Both "exactly one" and "none"
 * assertions would then pass for the wrong reason, which is precisely the
 * uniqueness guarantee UX-DR18 asks these tests to enforce.
 */
export function evidenceHighlights(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>("*")).filter((element) =>
    HIGHLIGHT_TOKENS.every((token) => element.classList.contains(token)),
  );
}
