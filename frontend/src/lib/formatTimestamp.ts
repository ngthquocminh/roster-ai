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

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

// `Date`'s UTC-* accessors (unlike `toLocaleString`/`Intl`) read the instant
// itself, never the host machine's timezone, so this stays deterministic in
// jsdom the same way formatTimestamp's regex slice does.
function formatUtc(date: Date): string {
  return `${date.getUTCFullYear()}-${pad2(date.getUTCMonth() + 1)}-${pad2(date.getUTCDate())} ${pad2(date.getUTCHours())}:${pad2(date.getUTCMinutes())}`;
}

const ISO_TIMESTAMP = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):?(\d{2})?/;

// `new Date(string)` is NOT safe here: a zone-naive ISO string (no `Z`/offset)
// parses as HOST-LOCAL time, not UTC, which is exactly the host-dependence
// formatTimestamp's own doc comment warns against. Regex-extracting the
// components and building the instant via `Date.UTC` (which never consults
// host timezone) keeps this deterministic regardless of whether the caller's
// string carries an explicit UTC designator.
function parseUtcEpoch(value: string): number | undefined {
  const match = ISO_TIMESTAMP.exec(value);
  if (!match) {
    return undefined;
  }
  const [, year, month, day, hour, minute, second] = match;
  return Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute), Number(second ?? "0"));
}

function formatDuration(totalMinutes: number): string {
  const days = Math.floor(totalMinutes / 1_440);
  const hours = Math.floor((totalMinutes % 1_440) / 60);
  const minutes = totalMinutes % 60;
  const parts: string[] = [];
  if (days > 0) parts.push(`${days} ${days === 1 ? "day" : "days"}`);
  if (hours > 0) parts.push(`${hours} ${hours === 1 ? "hour" : "hours"}`);
  if (minutes > 0) parts.push(`${minutes} ${minutes === 1 ? "minute" : "minutes"}`);
  return parts.length ? parts.join(" ") : "0 minutes";
}

/**
 * Renders a scenario's time horizon as "start → end (duration)", e.g.
 * "2026-05-31 14:00 → 2026-06-07 14:00 (7 days)", instead of the raw
 * "starts <timestamp>, <N> minutes" shape the API's fields suggest.
 *
 * Falls back to the raw shape (never throws) for an unparseable `start` or a
 * non-finite/negative `minutes`, mirroring formatTimestamp's
 * defensive-fallback convention -- a malformed duration (e.g. a negative one)
 * is worse than a plain fallback, not more informative.
 */
export function formatHorizon(start: string, minutes: number): string {
  const startEpoch = parseUtcEpoch(start);
  if (startEpoch === undefined || !Number.isFinite(minutes) || minutes < 0) {
    return `starts ${start}, ${minutes} minutes`;
  }
  const wholeMinutes = Math.round(minutes);
  const endEpoch = startEpoch + wholeMinutes * 60_000;
  return `${formatUtc(new Date(startEpoch))} → ${formatUtc(new Date(endEpoch))} (${formatDuration(wholeMinutes)})`;
}
