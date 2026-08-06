import { X } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { FilterDef } from "./filters";

type Props = Readonly<{
  filters: readonly FilterDef[];
  activeFilters: Readonly<Record<string, string>>;
  onApply: (values: Record<string, string>) => void;
  onClear: () => void;
  onRemove: (param: string) => void;
}>;

export function FilterBar({ activeFilters, filters, onApply, onClear, onRemove }: Props) {
  const [draft, setDraft] = useState<Record<string, string>>({ ...activeFilters });
  useEffect(() => setDraft({ ...activeFilters }), [activeFilters, filters]);
  const entries = filters.flatMap((filter) => activeFilters[filter.param] ? [[filter, activeFilters[filter.param]] as const] : []);
  const apply = () => onApply(Object.fromEntries(Object.entries(draft).filter(([, value]) => value.trim() !== "").map(([param, value]) => [param, value.trim()])));
  return (
    <section aria-label="Filter records" className="space-y-3 rounded-md border p-3">
      <div className="flex flex-wrap gap-3">
        {filters.map((filter) => (
          <label className="grid gap-1 text-sm" key={filter.param}>
            <span>{filter.label}</span>
            {filter.kind === "select" ? (
              <Select value={draft[filter.param] ?? ""} onValueChange={(value) => setDraft((current) => ({ ...current, [filter.param]: value }))}>
                <SelectTrigger aria-label={filter.label} className="min-h-11 min-w-44"><SelectValue placeholder={`Choose ${filter.label.toLowerCase()}`} /></SelectTrigger>
                <SelectContent>{filter.options?.map((option) => <SelectItem key={option} value={option}>{option}</SelectItem>)}</SelectContent>
              </Select>
            ) : (
              <Input className="min-h-11 min-w-44" type={filter.kind} value={draft[filter.param] ?? ""} onChange={(event) => setDraft((current) => ({ ...current, [filter.param]: event.target.value }))} />
            )}
          </label>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button className="min-h-11" onClick={apply} type="button">Apply</Button>
        <Button className="min-h-11" onClick={onClear} type="button" variant="outline">Clear</Button>
        <Badge variant="secondary">{entries.length} active {entries.length === 1 ? "filter" : "filters"}</Badge>
        {entries.map(([filter, value]) => (
          <Button aria-label={`Remove ${filter.label} filter`} className="min-h-11" key={filter.param} onClick={() => onRemove(filter.param)} type="button" variant="ghost">
            {filter.label}: {value}<X aria-hidden="true" />
          </Button>
        ))}
      </div>
    </section>
  );
}
