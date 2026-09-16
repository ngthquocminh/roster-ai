import { expect, test } from "@playwright/test";
import { writeFile } from "node:fs/promises";

// Opt-in real stack. No route interception, mocked HTTP, or inserted history.
test("live introduction survives six turns and browser reload", async ({ page }, testInfo) => {
  const observed: unknown[] = [];
  await page.goto("/api/v1/auth/login");
  await page.getByRole("link", { name: "sample_tiny_input", exact: true }).click();
  await page.getByRole("button", { name: "New conversation", exact: true }).click();
  const messages = [
    "HI my name is Minh", "how can you help me?", "how many work are therre?",
    "I mean workers in this scenario.", "What was my name again?",
    "Summarize what we learned about the workers.",
  ];
  try {
    for (const [index, message] of messages.entries()) {
      if (index === 4) await page.reload();
      await page.getByRole("textbox", { name: "Message", exact: true }).fill(message);
      const terminal = page.waitForResponse(response =>
        response.request().method() === "POST" && /\/agent-runs\/[^/]+\/execute$/.test(response.url()),
      { timeout: 100_000 });
      await page.getByRole("button", { name: "Send", exact: true }).click();
      const response = await terminal;
      expect(response.status()).toBe(200);
      const value = await response.json();
      observed.push({ user: message, ...value });
      expect(value.agent_run_status).toBe("agent_completed");
      expect(value.activity.activity_type).not.toBe("terminal_outcome");
      if (index === 4) {
        expect(value.activity.activity_type).toBe("agent_response");
        expect(value.activity.response.segments.some((segment: { text?: string }) =>
          segment.text?.includes("Minh"))).toBe(true);
      }
      await expect(page.getByRole("textbox", { name: "Message", exact: true })).toHaveValue("");
    }
    await page.screenshot({ path: testInfo.outputPath("six-turn-reload.png"), fullPage: true });
  } finally {
    const artifact = testInfo.outputPath("planner-visible-turns.json");
    await writeFile(artifact, JSON.stringify({ kind: "live-browser-observations-not-semantic-acceptance", url: page.url(), turns: observed }, null, 2));
    await testInfo.attach("planner-visible-turns", {
      path: artifact,
      contentType: "application/json",
    });
  }
});
