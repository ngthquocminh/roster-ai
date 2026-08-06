import { TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useWorkers } from "@/hooks/useScenarioProjection";
import { formatMinuteWindow } from "@/lib/formatShiftWindow";
import { getErrorStatus } from "@/lib/errors";
import { ScenarioDataGroupState } from "../ScenarioDataGroupState";
import { ScenarioDataTable } from "../ScenarioDataTable";

const headers = [
  "Contact ID",
  "Name",
  "Employment type",
  "Grade",
  "EBA",
  "Contracted hours",
  "Qualifications",
  "Availability windows",
];

export function WorkersPanel({ scenarioId }: Readonly<{ scenarioId: string }>) {
  const query = useWorkers(scenarioId);
  const items = query.data?.items ?? [];

  return (
    <ScenarioDataGroupState
      columnCount={headers.length}
      errorStatus={getErrorStatus(query.error)}
      isEmpty={!query.isPending && items.length === 0}
      isError={query.isError}
      isPending={query.isPending}
      onRetry={() => {
        void query.refetch();
      }}
    >
      <ScenarioDataTable caption="Workers">
        <TableHeader>
          <TableRow>
            {headers.map((header) => (
              <TableHead key={header} scope="col">
                {header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <TableRow key={item.record_id}>
              <TableCell className="font-mono text-xs" title={item.contact_id}>
                {item.contact_id}
              </TableCell>
              <TableCell>{item.name}</TableCell>
              <TableCell>{item.employment_type}</TableCell>
              <TableCell>{item.grade}</TableCell>
              <TableCell>{item.eba}</TableCell>
              <TableCell>{item.contracted_hours}</TableCell>
              <TableCell>
                {item.qualifications.length
                  ? item.qualifications.map((q) => `${q.task_id} (${q.rate})`).join(", ")
                  : "—"}
              </TableCell>
              <TableCell>
                {item.availability_windows.length
                  ? item.availability_windows
                      .map((w) => `${w.kind} ${formatMinuteWindow(w.start_minute, w.end_minute)}`)
                      .join("; ")
                  : "—"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </ScenarioDataTable>
    </ScenarioDataGroupState>
  );
}
