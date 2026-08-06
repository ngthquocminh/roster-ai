import { useState } from "react";

import type { ColumnDef, ScenarioDataListGroup } from "./columns";

function storageKey(group: ScenarioDataListGroup) {
  return `shiftmind.columns.${group}`;
}

function readHidden(group: ScenarioDataListGroup, columns: readonly ColumnDef[]) {
  try {
    const parsed: unknown = JSON.parse(sessionStorage.getItem(storageKey(group)) ?? "[]");
    if (!Array.isArray(parsed) || !parsed.every((key) => typeof key === "string")) return new Set<string>();
    const known = new Map(columns.map((column) => [column.key, column]));
    if (parsed.some((key) => !known.has(key) || known.get(key)?.required)) return new Set<string>();
    return new Set(parsed);
  } catch {
    return new Set<string>();
  }
}

export function useColumnVisibility(
  group: ScenarioDataListGroup,
  columns: readonly ColumnDef[],
  revealedField?: string,
) {
  const [hiddenByGroup, setHiddenByGroup] = useState<Record<string, Set<string>>>({});
  const hidden = hiddenByGroup[group] ?? readHidden(group, columns);
  const target = columns.find((column) => column.key === revealedField);
  const revealedColumn = target && hidden.has(target.key) ? target : undefined;
  const visibleKeys = new Set(
    columns.filter((column) => column.required || !hidden.has(column.key) || column.key === revealedColumn?.key).map((column) => column.key),
  );

  const setColumnVisible = (key: string, visible: boolean) => {
    const column = columns.find((candidate) => candidate.key === key);
    if (!column || column.required || key === revealedColumn?.key) return;
    const next = new Set(hidden);
    if (visible) next.delete(key);
    else next.add(key);
    try {
      sessionStorage.setItem(storageKey(group), JSON.stringify([...next].sort()));
    } catch {
      // Storage unavailable (quota exceeded, disabled) — visibility still updates for this session.
    }
    setHiddenByGroup((current) => ({ ...current, [group]: next }));
  };

  return { hidden, revealedColumn, setColumnVisible, visibleKeys };
}
