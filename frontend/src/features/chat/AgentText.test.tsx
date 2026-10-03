import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AgentText, slotToken, stripRepeatedUnit } from "./AgentText";

describe("AgentText", () => {
  it("renders paragraphs, bold, italic and code", () => {
    render(<AgentText slots={[]} source={"A **bold** and *soft* word with `code`.\n\nSecond paragraph."} />);
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByText("soft").tagName).toBe("EM");
    expect(screen.getByText("code").tagName).toBe("CODE");
    expect(screen.getByText("Second paragraph.")).toBeInTheDocument();
  });

  it("renders bullet and numbered lists", () => {
    render(<AgentText slots={[]} source={"Contains:\n\n- **Set Mika to 16 hours.**\n- No shift locks.\n\n1. first\n2. second"} />);
    const lists = screen.getAllByRole("list");
    expect(lists).toHaveLength(2);
    expect(lists[0].tagName).toBe("UL");
    expect(lists[1].tagName).toBe("OL");
    expect(screen.getByText("Set Mika to 16 hours.").tagName).toBe("STRONG");
  });

  it("leaves unmatched asterisks and underscores as literal text", () => {
    render(<AgentText slots={[]} source={"2 * 3 stays, and **unclosed, and sample_tiny_input_more_tm."} />);
    expect(document.body.textContent).toContain("2 * 3 stays, and **unclosed, and sample_tiny_input_more_tm.");
  });

  it("never interprets HTML in the answer", () => {
    render(<AgentText slots={[]} source={"<img src=x onerror=alert(1)> <b>not bold</b>"} />);
    expect(document.querySelector("img")).toBeNull();
    expect(document.querySelector("b")).toBeNull();
    expect(document.body.textContent).toContain("<b>not bold</b>");
  });

  it("places slots inline, including inside bold text", () => {
    render(
      <AgentText
        slots={[<span data-testid="chip" key="a">22 workers</span>]}
        source={`There are **${slotToken(0)}** in the scenario.`}
      />,
    );
    expect(screen.getByTestId("chip").closest("strong")).not.toBeNull();
  });
});

describe("stripRepeatedUnit", () => {
  it("drops one repeated unit word, singular or plural, and nothing else", () => {
    expect(stripRepeatedUnit(" workers in the scenario.", "workers")).toBe(" in the scenario.");
    expect(stripRepeatedUnit(" Worker in the scenario.", "workers")).toBe(" in the scenario.");
    expect(stripRepeatedUnit(" minutes of coverage", "minutes")).toBe(" of coverage");
    expect(stripRepeatedUnit(" workers.", "workers")).toBe(" .");
    expect(stripRepeatedUnit(" are short on Tuesday.", "workers")).toBe(" are short on Tuesday.");
    expect(stripRepeatedUnit(" workerless shifts", "workers")).toBe(" workerless shifts");
  });
});
