import { expect, it, vi } from "vitest";

vi.mock("@/api/scenarioProjection", () => ({
  resolveAssignment: vi.fn(),
  resolveConstraint: vi.fn(),
  resolveDemandInterval: vi.fn(),
  resolveLock: vi.fn(),
  resolveTask: vi.fn(),
  resolveWorker: vi.fn(),
}));

import { resolveDemandInterval } from "@/api/scenarioProjection";
import { resolveEvidenceRecord } from "./resolve";

it("dispatches exactly once with the cited locator", async () => {
  vi.mocked(resolveDemandInterval).mockResolvedValueOnce({ record_id: "demand-1" } as never);
  const target = {
    group: "demand" as const,
    record: "demand-1",
    version: "11111111-1111-4111-8111-111111111111",
    field: "amount",
  };

  await expect(resolveEvidenceRecord("scenario-a", target)).resolves.toEqual({ record_id: "demand-1" });
  expect(resolveDemandInterval).toHaveBeenCalledOnce();
  expect(resolveDemandInterval).toHaveBeenCalledWith("scenario-a", target.record, target.version);
});
