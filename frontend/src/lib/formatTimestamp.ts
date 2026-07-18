/**
 * Shortens a backend ISO-8601 UTC timestamp to a fixed-width "YYYY-MM-DD
 * HH:MM" string, so the Run History table's Created/Started/Finished
 * columns stay legible within their fixed `w-[22%]` `whitespace-nowrap`
 * cells (gap G-03-1 / RUN-04). The backend stamps
 * `datetime.now(timezone.utc).isoformat()`, which can be either
 * `+00:00`-offset or `Z`-suffixed and carries microsecond precision (e.g.
 * `2026-07-18T15:53:53.702354+00:00`, 32 chars) — the un-shortened string
 * cannot wrap and the column cannot grow, so it overflows.
 *
 * Deterministic by construction: this slices the leading `YYYY-MM-DDTHH:MM`
 * portion via regex rather than using `toLocaleString`/`toLocaleDateString`/
 * `toLocaleTimeString`, which read the host machine's timezone/locale and
 * would make jsdom tests machine-dependent and flaky. Because the backend's
 * leading date+time portion is already UTC wall-clock, this never shifts
 * the instant — it only drops seconds, microseconds, and offset noise.
 *
 * Defensive fallback (mirrors runStatus.ts / toolLabels.ts): unrecognized
 * input is returned unchanged — never throws, never emits "Invalid Date".
 */
const ISO_DATE_HHMM = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/;

export function formatTimestamp(value: string): string {
  const match = ISO_DATE_HHMM.exec(value);
  if (!match) {
    return value;
  }
  const [, date, hhmm] = match;
  return `${date} ${hhmm}`;
}
