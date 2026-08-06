import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { COLUMNS_BY_GROUP } from "./columns";
import { useColumnVisibility } from "./useColumnVisibility";

beforeEach(() => sessionStorage.clear());

describe("useColumnVisibility", () => {
  it("persists optional columns per group for the session", () => {
    const columns = COLUMNS_BY_GROUP.workers;
    const first = renderHook(() => useColumnVisibility("workers", columns));
    act(() => first.result.current.setColumnVisible("grade", false));
    expect(first.result.current.visibleKeys.has("grade")).toBe(false);
    first.unmount();
    const second = renderHook(() => useColumnVisibility("workers", columns));
    expect(second.result.current.visibleKeys.has("grade")).toBe(false);
    const tasks = renderHook(() => useColumnVisibility("work-areas-and-tasks", COLUMNS_BY_GROUP["work-areas-and-tasks"]));
    expect(tasks.result.current.visibleKeys.has("grade")).toBe(false);
    expect(tasks.result.current.visibleKeys.has("function")).toBe(true);
  });

  it("discards hostile storage that names required or unknown columns", () => {
    sessionStorage.setItem("shiftmind.columns.workers", JSON.stringify(["contact_id", "unknown"]));
    const { result } = renderHook(() => useColumnVisibility("workers", COLUMNS_BY_GROUP.workers));
    expect(result.current.visibleKeys.size).toBe(COLUMNS_BY_GROUP.workers.length);
    act(() => result.current.setColumnVisible("contact_id", false));
    expect(result.current.visibleKeys.has("contact_id")).toBe(true);
  });

  it("temporarily reveals a hidden known field without changing storage", () => {
    sessionStorage.setItem("shiftmind.columns.workers", JSON.stringify(["grade"]));
    const { result, rerender } = renderHook(
      ({ field }) => useColumnVisibility("workers", COLUMNS_BY_GROUP.workers, field),
      { initialProps: { field: "grade" as string | undefined } },
    );
    expect(result.current.visibleKeys.has("grade")).toBe(true);
    expect(result.current.revealedColumn?.header).toBe("Grade");
    rerender({ field: undefined });
    expect(result.current.visibleKeys.has("grade")).toBe(false);
    rerender({ field: "unknown" });
    expect(result.current.revealedColumn).toBeUndefined();
  });
});
