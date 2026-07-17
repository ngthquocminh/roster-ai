/**
 * CONS-01 constraint input coverage (UI-SPEC E4): empty-disables-submit,
 * submit issues the mutation, in-flight disables textarea+button, char
 * counter/limit backstop, 503-vs-422 status branching (CONS-05), and the
 * Input-preservation rule (CONS-04) — text preserved on every non-full-
 * success outcome, cleared ONLY on applied.length>0 && rejected.length===0
 * && clarification===null (WR-01: a mixed applied+rejected 200 must NOT
 * clear the text — part of what the user typed still needs attention).
 *
 * Mocks `useApplyConstraint` at the hook boundary (not `@/api/constraints`)
 * so `.mutate`'s `onSuccess` callback can be driven synchronously per test.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("@/hooks/useApplyConstraint", () => ({
  useApplyConstraint: vi.fn(),
}));

import { useApplyConstraint } from "@/hooks/useApplyConstraint";
import { ConstraintInput } from "./ConstraintInput";
import type { components } from "@/api/schema";

type ConstraintParseResponse = components["schemas"]["ConstraintParseResponse"];

const mockUseApplyConstraint = useApplyConstraint as unknown as ReturnType<
  typeof vi.fn
>;

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

function mockHook(overrides: {
  mutate?: ReturnType<typeof vi.fn>;
  isPending?: boolean;
  error?: { status?: number } | null;
}) {
  mockUseApplyConstraint.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    error: null,
    ...overrides,
  });
}

beforeEach(() => {
  mockUseApplyConstraint.mockReset();
});

describe("ConstraintInput: empty [UI-SPEC E4/empty]", () => {
  it("disables submit while the textarea is empty", () => {
    mockHook({});
    render(<ConstraintInput scenarioId="s1" onOutcome={vi.fn()} />);

    expect(
      screen.getByRole("button", { name: "Apply Constraint" }),
    ).toBeDisabled();
  });
});

describe("ConstraintInput: submit [CONS-01]", () => {
  it("issues the mutation with the typed text on submit", () => {
    const mutate = vi.fn();
    mockHook({ mutate });
    const onOutcome = vi.fn();
    render(<ConstraintInput scenarioId="s1" onOutcome={onOutcome} />);

    fireEvent.change(screen.getByLabelText("Constraint text"), {
      target: { value: "keep 2 workers on Pick" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply Constraint" }));

    expect(mutate).toHaveBeenCalledWith(
      "keep 2 workers on Pick",
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });
});

describe("ConstraintInput: in-flight [UI-SPEC E4/loading]", () => {
  it("shows a spinner + 'Applying…' and disables both the textarea and the button", () => {
    mockHook({ isPending: true });
    render(<ConstraintInput scenarioId="s1" onOutcome={vi.fn()} />);

    expect(screen.getByText("Applying…")).toBeInTheDocument();
    expect(screen.getByLabelText("Constraint text")).toBeDisabled();
    expect(screen.getByRole("button", { name: /Applying…/ })).toBeDisabled();
  });
});

describe("ConstraintInput: provider-down [D-04.4, CONS-05]", () => {
  it("renders ProviderDownBanner (default variant, not destructive) and preserves the typed text on a 503", () => {
    mockHook({ error: { status: 503 } });
    render(<ConstraintInput scenarioId="s1" onOutcome={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Constraint text"), {
      target: { value: "some constraint text" },
    });

    const banner = screen.getByTestId("provider-down-banner");
    expect(banner).toBeInTheDocument();
    expect(banner.className).not.toMatch(/destructive/);
    expect(
      screen.getByText("The constraint parser is unavailable right now."),
    ).toBeInTheDocument();
    expect(
      (screen.getByLabelText("Constraint text") as HTMLTextAreaElement).value,
    ).toBe("some constraint text");
  });
});

describe("ConstraintInput: 422 backstop [UI-SPEC E4/422, structural]", () => {
  it("has a 422 branch keyed off status, not message text (backstop — unreachable via client gating in the happy path)", () => {
    mockHook({ error: { status: 422 } });
    render(<ConstraintInput scenarioId="s1" onOutcome={vi.fn()} />);

    expect(screen.getByTestId("validation-error")).toBeInTheDocument();
  });
});

describe("ConstraintInput: input-preservation [CONS-04, generalized rule]", () => {
  it("preserves the typed text on a rejected-only outcome", () => {
    const mutate = vi.fn((_text, options) => {
      options.onSuccess(
        response({ rejected: [{ tool: "scale_demand", error: "bad" }] }),
      );
    });
    mockHook({ mutate });
    render(<ConstraintInput scenarioId="s1" onOutcome={vi.fn()} />);

    const textarea = screen.getByLabelText(
      "Constraint text",
    ) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "some constraint text" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply Constraint" }));

    expect(textarea.value).toBe("some constraint text");
  });

  it("preserves the typed text on a clarification_needed outcome", () => {
    const mutate = vi.fn((_text, options) => {
      options.onSuccess(
        response({
          applied: [
            {
              id: "c1",
              tool: "set_max_hours",
              args: {},
              parsed_constraint: "x",
            },
          ],
          clarification_needed: "Which worker?",
        }),
      );
    });
    mockHook({ mutate });
    render(<ConstraintInput scenarioId="s1" onOutcome={vi.fn()} />);

    const textarea = screen.getByLabelText(
      "Constraint text",
    ) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "some constraint text" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply Constraint" }));

    expect(textarea.value).toBe("some constraint text");
  });

  it("preserves the typed text on a no_constraint_found outcome", () => {
    const mutate = vi.fn((_text, options) => {
      options.onSuccess(response({ no_constraint_found: true }));
    });
    mockHook({ mutate });
    render(<ConstraintInput scenarioId="s1" onOutcome={vi.fn()} />);

    const textarea = screen.getByLabelText(
      "Constraint text",
    ) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "some constraint text" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply Constraint" }));

    expect(textarea.value).toBe("some constraint text");
  });

  it("preserves the typed text on a mixed applied+rejected (no clarification) outcome [WR-01]", () => {
    const mutate = vi.fn((_text, options) => {
      options.onSuccess(
        response({
          applied: [
            {
              id: "c1",
              tool: "set_max_hours",
              args: {},
              parsed_constraint: "x",
            },
          ],
          rejected: [{ tool: "scale_demand", error: "bad" }],
        }),
      );
    });
    mockHook({ mutate });
    render(<ConstraintInput scenarioId="s1" onOutcome={vi.fn()} />);

    const textarea = screen.getByLabelText(
      "Constraint text",
    ) as HTMLTextAreaElement;
    fireEvent.change(textarea, {
      target: { value: "keep 2 workers on Pick and some garbled fragment" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply Constraint" }));

    expect(textarea.value).toBe(
      "keep 2 workers on Pick and some garbled fragment",
    );
  });

  it("clears the textarea ONLY when applied.length > 0 && rejected.length === 0 && clarification_needed === null", () => {
    const mutate = vi.fn((_text, options) => {
      options.onSuccess(
        response({
          applied: [
            {
              id: "c1",
              tool: "set_max_hours",
              args: {},
              parsed_constraint: "x",
            },
          ],
        }),
      );
    });
    mockHook({ mutate });
    const onOutcome = vi.fn();
    render(<ConstraintInput scenarioId="s1" onOutcome={onOutcome} />);

    const textarea = screen.getByLabelText(
      "Constraint text",
    ) as HTMLTextAreaElement;
    fireEvent.change(textarea, {
      target: { value: "keep 2 workers on Pick" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply Constraint" }));

    expect(textarea.value).toBe("");
    expect(onOutcome).toHaveBeenCalledWith(
      expect.objectContaining({
        submittedText: "keep 2 workers on Pick",
      }),
    );
  });
});

describe("ConstraintInput: char-limit backstop [UI-SPEC E4/long-text]", () => {
  it("shows the '{n}/2000' counter past 1800 characters", () => {
    mockHook({});
    render(<ConstraintInput scenarioId="s1" onOutcome={vi.fn()} />);

    const longText = "a".repeat(1801);
    fireEvent.change(screen.getByLabelText("Constraint text"), {
      target: { value: longText },
    });

    expect(screen.getByText("1801/2000")).toBeInTheDocument();
  });

  it("disables submit past 2000 characters", () => {
    mockHook({});
    render(<ConstraintInput scenarioId="s1" onOutcome={vi.fn()} />);

    const overLimitText = "a".repeat(2001);
    fireEvent.change(screen.getByLabelText("Constraint text"), {
      target: { value: overLimitText },
    });

    expect(
      screen.getByRole("button", { name: "Apply Constraint" }),
    ).toBeDisabled();
  });
});
