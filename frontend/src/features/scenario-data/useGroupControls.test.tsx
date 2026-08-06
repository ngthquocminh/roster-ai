import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, useLocation, useNavigate } from "react-router";
import { describe, expect, it } from "vitest";

import { useGroupControls } from "./useGroupControls";

let latestSearch = "";
let goBack: (() => void) | undefined;
function Observer({ children }: { children: ReactNode }) {
  latestSearch = useLocation().search;
  const navigate = useNavigate();
  goBack = () => navigate(-1);
  return children;
}

function makeWrapper(initialEntry: string) {
  return ({ children }: { children: ReactNode }) => <MemoryRouter initialEntries={[initialEntry]}><Observer>{children}</Observer></MemoryRouter>;
}

describe("useGroupControls", () => {
  it("reads valid URL state and falls back safely for garbage sort/order/cursor", () => {
    const valid = renderHook(() => useGroupControls("demand"), { wrapper: makeWrapper("/?group=demand&sort=start_minute&order=desc&cursor=50&family=outbound") });
    expect(valid.result.current).toMatchObject({ sort: "start_minute", order: "desc", cursor: 50, activeFilters: { family: "outbound" } });
    valid.unmount();
    const invalid = renderHook(() => useGroupControls("demand"), { wrapper: makeWrapper("/?group=demand&sort=nope&order=sideways&cursor=-2") });
    expect(invalid.result.current).toMatchObject({ sort: undefined, order: "asc", cursor: 0 });
  });

  it("pushes apply, sort, and page states so Back restores the prior controls", () => {
    const { result } = renderHook(() => useGroupControls("demand"), { wrapper: makeWrapper("/?group=demand&cursor=50") });
    act(() => result.current.applyFilters({ family: "outbound" }));
    expect(latestSearch).toContain("family=outbound");
    expect(latestSearch).not.toContain("cursor=");
    act(() => result.current.changeSort("start_minute"));
    expect(latestSearch).toContain("sort=start_minute");
    act(() => result.current.changePage(50));
    expect(latestSearch).toContain("cursor=50");
    act(() => goBack?.());
    expect(latestSearch).not.toContain("cursor=50");
  });

  it("drops every control parameter when the group changes", () => {
    const { result } = renderHook(() => useGroupControls("demand"), { wrapper: makeWrapper("/?group=demand&sort=family&family=outbound&field=amount") });
    act(() => result.current.changeGroup("workers"));
    expect(latestSearch).toBe("?group=workers");
  });

  it("clear removes all filters and resets cursor while Back restores them", () => {
    const { result } = renderHook(() => useGroupControls("demand"), { wrapper: makeWrapper("/?group=demand&family=outbound&task_id=T-104&cursor=50") });
    act(() => result.current.clearFilters());
    expect(latestSearch).toBe("?group=demand");
    act(() => goBack?.());
    expect(latestSearch).toContain("family=outbound");
    expect(latestSearch).toContain("cursor=50");
  });
});
