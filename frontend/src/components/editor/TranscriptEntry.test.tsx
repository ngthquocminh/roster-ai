/**
 * D-04 four-outcome-treatment + D-05 no-match coverage (CONS-02/03/04).
 * Asserts each outcome renders its own distinct treatment, that a rejected
 * item's error string renders VERBATIM (not paraphrased), and that
 * applied+rejected can render together within one entry (E5 mixed).
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { TranscriptEntry } from "./TranscriptEntry";
import type { TranscriptEntryData } from "./ConstraintTranscript";
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

function entry(overrides: Partial<TranscriptEntryData> = {}): TranscriptEntryData {
  return {
    id: "e1",
    submittedText: "keep 2 workers on Pick",
    response: response(),
    ...overrides,
  };
}

describe("TranscriptEntry: applied [D-04.1, CONS-02]", () => {
  it("renders the parsed_constraint string verbatim with a Check icon (neutral/foreground)", () => {
    const { container } = render(
      <TranscriptEntry
        entry={entry({
          response: response({
            applied: [
              {
                id: "c1",
                tool: "set_min_workers_per_task",
                args: {},
                parsed_constraint: "At least 2 workers on Pick at all times",
              },
            ],
          }),
        })}
      />,
    );

    const appliedText = screen.getByText(
      "At least 2 workers on Pick at all times",
    );
    expect(appliedText).toBeInTheDocument();
    expect(container.querySelector("svg")).toBeInTheDocument();
  });
});

describe("TranscriptEntry: rejected [D-04.2, CONS-03]", () => {
  it("renders 'Couldn't apply: {Tool Label}' + the backend's error string verbatim, both in text-destructive, with an X icon", () => {
    render(
      <TranscriptEntry
        entry={entry({
          response: response({
            rejected: [
              {
                tool: "scale_demand",
                error:
                  "factor must be positive, got -1. Use a value > 0…",
              },
            ],
          }),
        })}
      />,
    );

    expect(
      screen.getByText("Couldn't apply: Scale demand"),
    ).toBeInTheDocument();
    const errorNode = screen.getByText(
      "factor must be positive, got -1. Use a value > 0…",
    );
    expect(errorNode).toBeInTheDocument();
    expect(errorNode.closest(".text-destructive")).not.toBeNull();
  });
});

describe("TranscriptEntry: mixed applied+rejected [E5 mixed/partial-apply]", () => {
  it("renders both sections within one entry, each with its own distinct treatment", () => {
    render(
      <TranscriptEntry
        entry={entry({
          response: response({
            applied: [
              {
                id: "c1",
                tool: "set_max_hours",
                args: {},
                parsed_constraint: "Cap member m1 at 40 hours per week",
              },
            ],
            rejected: [
              {
                tool: "scale_demand",
                error: "factor must be positive, got -1.",
              },
            ],
          }),
        })}
      />,
    );

    expect(
      screen.getByText("Cap member m1 at 40 hours per week"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Couldn't apply: Scale demand"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("factor must be positive, got -1."),
    ).toBeInTheDocument();
  });
});

describe("TranscriptEntry: clarification_needed [D-04.3, CONS-04]", () => {
  it("renders 'Needs clarification: {text}' neutral/muted with the rephrase caption", () => {
    render(
      <TranscriptEntry
        entry={entry({
          response: response({
            clarification_needed: "Which worker did you mean?",
          }),
        })}
      />,
    );

    expect(
      screen.getByText("Needs clarification: Which worker did you mean?"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Rephrase your constraint above and submit again."),
    ).toBeInTheDocument();
  });
});

describe("TranscriptEntry: no_constraint_found [D-05]", () => {
  it("renders the neutral no-match message + rephrase-example caption", () => {
    render(
      <TranscriptEntry
        entry={entry({ response: response({ no_constraint_found: true }) })}
      />,
    );

    expect(
      screen.getByText("No constraint was recognized in that text."),
    ).toBeInTheDocument();
  });
});
