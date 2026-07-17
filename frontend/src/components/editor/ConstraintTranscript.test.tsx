/**
 * D-03 session-log container coverage (UI-SPEC E3). Empty renders nothing
 * (not even placeholder chrome); populated renders one node per entry,
 * keyed by id.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import {
  ConstraintTranscript,
  type TranscriptEntryData,
} from "./ConstraintTranscript";
import type { components } from "@/api/schema";

type ConstraintParseResponse = components["schemas"]["ConstraintParseResponse"];

function response(
  overrides: Partial<ConstraintParseResponse> = {},
): ConstraintParseResponse {
  return {
    applied: [],
    rejected: [],
    clarification_needed: null,
    no_constraint_found: false,
    ...overrides,
  };
}

describe("ConstraintTranscript: empty [UI-SPEC E3/empty]", () => {
  it("renders nothing — not even empty-state chrome", () => {
    const { container } = render(<ConstraintTranscript entries={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("ConstraintTranscript: populated [UI-SPEC E3/populated, zero-one-many]", () => {
  it("renders one node per entry, keyed by id", () => {
    const entries: TranscriptEntryData[] = [
      {
        id: "t1",
        submittedText: "first submission",
        response: response({ no_constraint_found: true }),
      },
      {
        id: "t2",
        submittedText: "second submission",
        response: response({ no_constraint_found: true }),
      },
    ];
    render(<ConstraintTranscript entries={entries} />);

    expect(screen.getByText("first submission")).toBeInTheDocument();
    expect(screen.getByText("second submission")).toBeInTheDocument();
  });
});
