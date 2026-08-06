/**
 * Formats a schedule row's hour-offset `start_h`/`end_h` (hours from horizon
 * start, per docs/API.md's time-representation note) into a "Day N,
 * HH:MM–HH:MM" string (RES-03, D-10).
 *
 * Rounds once in total minutes (`Math.round(h * 60)`) rather than rounding
 * hours and minutes independently — the latter can round 23.999h up to
 * hour 24 *and* minute 0 separately, rendering the nonsensical "24:00"
 * instead of the correct next-day "00:00". Day numbering is 1-indexed
 * (hours 0-24 => "Day 1"), matching docs/API.md's own "day-2 06:00 = 30.0h"
 * worked example and CoverageByDayTable's `Number(dayKey) + 1` convention
 * (plan 04-04) — both tables must label the same calendar day identically.
 *
 * Shifts can legitimately cross midnight (see
 * backend/ingest/scenario_time.py's day_window_hours handling of windows
 * where "end <= start -> end is next day"); when start and end land on
 * different days, both are labeled explicitly rather than collapsing to a
 * single-day prefix.
 */
function formatDayTime(h: number): { day: number; hhmm: string } {
  const totalMinutes = Math.round(h * 60);
  const day = Math.floor(totalMinutes / 1440) + 1; // 1-indexed: hours 0-24 => "Day 1"
  const minutesOfDay = totalMinutes % 1440;
  const hh = String(Math.floor(minutesOfDay / 60)).padStart(2, "0");
  const mm = String(minutesOfDay % 60).padStart(2, "0");
  return { day, hhmm: `${hh}:${mm}` };
}

export function formatShiftWindow(startH: number, endH: number): string {
  const start = formatDayTime(startH);
  const end = formatDayTime(endH);
  if (start.day === end.day) {
    return `Day ${start.day}, ${start.hhmm}–${end.hhmm}`;
  }
  return `Day ${start.day}, ${start.hhmm} – Day ${end.day}, ${end.hhmm}`;
}

export function formatMinuteWindow(startMinute: number, endMinute: number): string {
  return formatShiftWindow(startMinute / 60, endMinute / 60);
}
