---
phase: 260714-owo
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - data/sample_tiny_input_more_tm.json
autonomous: true
requirements:
  - QT-260714-owo   # Quick task: fixture variant with more qualified TM supply
user_setup: []

must_haves:
  truths:
    - "data/sample_tiny_input_more_tm.json exists, is valid JSON, and input_adapter.load_problem parses it without error."
    - "The new fixture contains every original row from sample_tiny_input.json unchanged — no existing row modified or removed in any table."
    - "10-15 new Team Members exist, each qualified for task 99260066-B32A-423D-97A1-8A649BABBAAD and each rostered/available during that task's demanded hours."
    - "Across new + existing qualified members, every one of the 98 demanded hourly buckets for the target task has >=3 (target >=4) qualified members with a covering window."
    - "Loading the new fixture yields more schedulable members qualified for the target task than the original (8 -> 8 + N new)."
  artifacts:
    - data/sample_tiny_input_more_tm.json
  key_links:
    - "Each new Team Member ContactID matches its qualification row AND its window row(s) — input_adapter.py:122-123 drops any member missing BOTH a window and a qualification."
    - "Each new member reuses an existing (EBAID, GradeID) pair so the EBA Grade Rate wage join resolves — input_adapter.py:80,119."
    - "New qualification rows use QualificationID 93FED3C5-2F36-4BA4-BDA8-5AA33095DE3C, TaskID 99260066-B32A-423D-97A1-8A649BABBAAD, DefaultTaskRate ~190.0, TeamMemberTaskRateOverride null."
---

<objective>
Produce a throwaway test fixture `data/sample_tiny_input_more_tm.json`, derived from `data/sample_tiny_input.json` by ADDING new rows only, that increases Team Member supply for task `99260066-B32A-423D-97A1-8A649BABBAAD` (task "C Pick | Picking chill 080"). The goal is to test the hypothesis that adding members who are both (a) qualified for that task and (b) rostered/available during its demanded hours gives the CP-SAT engine's round-1 pass enough schedulable supply for the soft constraint `set_min_workers_per_task n=3` to become satisfiable in round 2.

Purpose: Manual API experimentation (POST /constraints, POST /scenarios/{id}/runs). This is static test data — no application code changes, no committed automated tests.
Output: One new JSON fixture file. All 21 existing tables and their existing rows are preserved verbatim; only 4 tables gain appended rows.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md

# Source fixture (read to copy exact row shapes and reuse IDs) and the adapter that consumes it
@data/sample_tiny_input.json
@backend/ingest/input_adapter.py

## Grounding facts (already verified against the source fixture)

- Top level is a dict of 21 tables. Formatting: `json.dump(..., indent=1)` reproduces the source style (single-space indent). Byte-identical formatting is NOT required (throwaway data) — but existing row CONTENT must be unchanged.
- Target task: `99260066-B32A-423D-97A1-8A649BABBAAD`.
- Demanded hours for the target task: 98 hourly buckets (Outbound Workload rows, Volume > 0) across 7 days `2026-06-01` .. `2026-06-07`, with start hours ranging `05:00` .. `22:00`. The latest bucket starts at 22:00 and ends 23:00 — so a covering window MUST extend to `23:00:00`, not `22:00`.
- Existing qualified members for the target task: 8. QualificationID used = `93FED3C5-2F36-4BA4-BDA8-5AA33095DE3C`; DefaultTaskRate = 190.0; TeamMemberTaskRateOverride = null; EfficiencyPercentage = 100.0.
- 10 distinct existing ContactIDs — new GUIDs must not collide with any of them.
- Adapter contract (input_adapter.py:122-123): a member is included ONLY if it has BOTH >=1 window (Roster Profile or Availability) AND >=1 qualification for an in-scope task. Every new member therefore needs a qualification row AND at least one window row.
- Wage lookup is keyed on `(EBAID, GradeID)` (input_adapter.py:80,119). Reuse an existing pair to guarantee resolution.
- Reusable ID triples already present in the fixture (copy verbatim, do not invent):
  - Full Time / Grade 3 / EA2020-2023: EmploymentTypeID `68DFB248-AF69-400F-8896-5089E2E30DBF`, GradeID `46DEF4DE-AFE4-4778-B704-4826CC21C4D0`, EBAID `F3936C24-1272-4067-8D27-E1E8E81C4474`.
  - Part Time / Grade 3 / EA2020-2023: EmploymentTypeID `8DA32FE3-4B85-4755-BD95-A277DA33CA9F`, same GradeID, same EBAID.
- Row shapes (exact field names — note the source typo `RoatationQualified`):
  - Team Member: `ContactID, SAPID, Team Member, EmploymentTypeID, EmploymentType, GradeID, Grade, EBAID, EBA, PartTimeFlex, ContractedHours, RoatationQualified, MaximumHoursByFortnight, PreferredTaskGroup`.
  - Team Member Qualification and Performance: `ContactID, TaskID, QualificationID, DefaultTaskRate, TeamMemberTaskRateOverride, EfficiencyPercentage, LoadManagementPercentage`.
  - Roster Profile: `VolumeScenarioRosterProfileID, ContactID, Team Member, StartDateTime, EndDateTime`.
  - Availability: `VolumeScenarioAvailabilityID, ContactID, Team Member, StartDateTime, EndDateTime`.
</context>

<tasks>

<task type="auto">
  <name>Task 1: Generate data/sample_tiny_input_more_tm.json with 12 new qualified + rostered members</name>
  <files>data/sample_tiny_input_more_tm.json</files>
  <action>
Write a throwaway generator script in the scratchpad directory (NOT under backend/, NOT committed — it is a build tool, not application code) that loads the source fixture, appends new rows to exactly 4 tables, and writes the new file. Using a script (rather than hand-editing a 420KB file) guarantees existing rows stay byte-identical and new rows match the exact source shapes.

Generator steps:
1. Load `data/sample_tiny_input.json` into a dict, preserving key order (default json.load preserves insertion order).
2. Collect the set of existing ContactIDs from the "Team Member" table so new GUIDs cannot collide.
3. Build 12 new members (index i = 1..12). For each:
   - Deep-copy an existing "Team Member" row as a template so every field (including the source typo field `RoatationQualified`, plus `PartTimeFlex`, `SAPID`, `PreferredTaskGroup`) is present with a valid shape. Override only: `ContactID` (new uppercase GUID, uniqueness-checked against existing set and against already-generated new IDs), `SAPID` (unique plausible string e.g. "99900001".."99900012"), `Team Member` (e.g. "Test Member 01" .. "Test Member 12").
   - Set the reuse triple: use the Full Time / Grade 3 / EA2020-2023 triple (EmploymentTypeID `68DFB248-AF69-400F-8896-5089E2E30DBF`, GradeID `46DEF4DE-AFE4-4778-B704-4826CC21C4D0`, EBAID `F3936C24-1272-4067-8D27-E1E8E81C4474`, EmploymentType "Full Time", Grade "Grade 3", EBA "EA2020-2023"). Keep `ContractedHours` 38 and `MaximumHoursByFortnight` 180 to match existing full-time members. Append to "Team Member".
   - Append one "Team Member Qualification and Performance" row: `ContactID` = the new member's ID, `TaskID` = `99260066-B32A-423D-97A1-8A649BABBAAD`, `QualificationID` = `93FED3C5-2F36-4BA4-BDA8-5AA33095DE3C`, `DefaultTaskRate` = 190.0, `TeamMemberTaskRateOverride` = null, `EfficiencyPercentage` = 100.0, `LoadManagementPercentage` = null (mirror an existing target-task qual row's shape).
   - Append 3 "Roster Profile" window rows covering a rolling block of 3 consecutive days. Member i covers days with 0-indexed offsets {(i-1) mod 7, i mod 7, (i+1) mod 7} within 2026-06-01..2026-06-07. Each window is a full active day: StartDateTime `2026-06-0DT05:00:00`, EndDateTime `2026-06-0DT23:00:00` (23:00 end so the 22:00-start demand bucket is covered). Fields: new uppercase GUID `VolumeScenarioRosterProfileID`, `ContactID` = new member ID, `Team Member` = new member name, `StartDateTime`, `EndDateTime`. This rolling scheme yields >=4 new members covering every one of the 7 days.
4. Do NOT touch any other table or any existing row. Write the result to `data/sample_tiny_input_more_tm.json` with `json.dump(data, f, indent=1, ensure_ascii=False)`.

Generate GUIDs with Python's `uuid.uuid4()` uppercased so they follow the fixture's GUID-style ID convention.
  </action>
  <verify>
    <automated>python -c "import json; s=json.load(open('data/sample_tiny_input.json')); n=json.load(open('data/sample_tiny_input_more_tm.json')); assert set(s)==set(n), 'table set changed'; untouched=[t for t in s if t not in ('Team Member','Team Member Qualification and Performance','Roster Profile','Availability')]; assert all(s[t]==n[t] for t in untouched), 'an untouched table changed'; assert all(n[t][:len(s[t])]==s[t] for t in ('Team Member','Team Member Qualification and Performance','Roster Profile','Availability')), 'existing rows in a touched table were altered/reordered'; added=len(n['Team Member'])-len(s['Team Member']); assert 10<=added<=15, f'added {added} members'; new_ids=[r['ContactID'] for r in n['Team Member'][len(s['Team Member']):]]; assert len(set(new_ids))==len(new_ids), 'dup new ContactID'; assert not (set(new_ids) & set(r['ContactID'] for r in s['Team Member'])), 'new ContactID collides with existing'; print('OK: added', added, 'members; existing rows preserved')"</automated>
  </verify>
  <done>
`data/sample_tiny_input_more_tm.json` exists and is valid JSON. Same 21 tables as source. The 17 untouched tables are content-identical to source. The 4 touched tables begin with all original rows unchanged, then 10-15 new members' rows appended. New ContactIDs are unique and collision-free.
  </done>
</task>

<task type="auto">
  <name>Task 2: Verify adapter load and >=3 qualified-member coverage across all 98 demanded hours</name>
  <files>data/sample_tiny_input_more_tm.json</files>
  <action>
Confirm the new fixture actually achieves the supply goal, using the real adapter and a coverage check. Run a throwaway scratchpad verification script (not committed) that:
1. Imports `load_problem` from `backend/ingest/input_adapter.py` (add `backend/` to sys.path as conftest.py does) and loads BOTH fixtures.
2. Asserts the new fixture loads without error and that the count of schedulable members qualified for task `99260066-B32A-423D-97A1-8A649BABBAAD` increased by the number of new members (original 8 -> 8 + N). This proves each new member survived the adapter's window-AND-qualification filter (input_adapter.py:122-123).
3. Recomputes coverage directly from the fixture: for each of the 98 demanded hourly buckets (Outbound Workload rows for the target task with Volume > 0), count how many target-task-qualified members (existing + new) have a Roster Profile OR Availability window whose [Start, End) interval contains that bucket's start hour. Assert the minimum across all 98 buckets is >= 3 (report how many reach >= 4). Print the original fixture's per-hour minimum alongside for contrast (expected to be < 3, matching the observed hard ceiling).

If the minimum is < 3, the day-distribution in Task 1 fell short — adjust the rolling-window day assignment (add windows on the deficient days) and regenerate before this task passes.
  </action>
  <verify>
    <automated>python -c "import json,sys; sys.path.insert(0,'backend'); from datetime import datetime as D; from collections import defaultdict; TASK='99260066-B32A-423D-97A1-8A649BABBAAD'; d=json.load(open('data/sample_tiny_input_more_tm.json')); base=json.load(open('data/sample_tiny_input.json'));
qc=set(r['ContactID'] for r in d['Team Member Qualification and Performance'] if r['TaskID']==TASK);
win=defaultdict(list);
[win[r['ContactID']].append((D.fromisoformat(r['StartDateTime']),D.fromisoformat(r['EndDateTime']))) for tbl in ('Roster Profile','Availability') for r in d[tbl]];
buckets=[D.fromisoformat(r['StartDateTime']) for r in d['Outbound Workload'] if r['TaskID']==TASK and r['Volume']>0];
cov=[sum(1 for c in qc if any(s<=b<e for s,e in win.get(c,[]))) for b in buckets];
assert len(buckets)==98, f'expected 98 buckets got {len(buckets)}';
assert min(cov)>=3, f'coverage floor {min(cov)} < 3'; print(f'OK: {len(buckets)} buckets, min coverage {min(cov)}, >=4 at {sum(1 for c in cov if c>=4)}/98, qualified members {len(qc)} (was 8)')"</automated>
  </verify>
  <done>
The adapter loads the new fixture cleanly; qualified-member count for the target task = 8 + N. All 98 demanded hourly buckets have >= 3 qualified members with a covering window (report includes how many reach >= 4), confirming the round-1 pass now has real headroom for the `set_min_workers_per_task n=3` soft constraint.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| fixture file -> input_adapter | The new JSON is parsed by `input_adapter.load_problem` and fed to the CP-SAT solver. It is author-controlled local test data, not an untrusted external upload. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-260714-01 | Tampering | Existing rows in the 4 edited tables + 17 untouched tables | low | mitigate | Generator only appends; Task 1 verify asserts untouched tables are content-identical and edited tables preserve all original rows as an unchanged prefix. |
| T-260714-02 | Denial of Service | CP-SAT solve on the enlarged problem | low | accept | New supply is bounded to ~12 members with full-week windows — a modest increase over the existing 10-member fixture, well within current solve scale. Task 2 confirms the adapter builds the problem without error. |
| T-260714-03 | Information Disclosure | GUID / SAPID / member-name values | low | accept | Synthetic placeholder identifiers ("Test Member NN", fabricated GUIDs) — no real PII introduced. |
</threat_model>

<verification>
- `data/sample_tiny_input_more_tm.json` parses as valid JSON with the same 21 tables as the source.
- 17 untouched tables are content-identical to `data/sample_tiny_input.json`; the 4 edited tables retain all original rows unchanged and only append new rows.
- 10-15 new members added, each with: a unique collision-free ContactID, a qualification row for the target task, and >=1 covering window row (satisfying input_adapter.py:122-123).
- `input_adapter.load_problem` loads the new fixture; qualified-member count for the target task rises from 8 to 8 + N.
- All 98 target-task demanded hourly buckets have >= 3 qualified members with covering windows.
</verification>

<success_criteria>
A single new fixture file `data/sample_tiny_input_more_tm.json` exists that (1) is a strict superset of the source (adds rows only), (2) loads through the real input adapter, and (3) provides >= 3 (target >= 4) qualified + available members at every one of the 98 demanded hours for task 99260066-B32A-423D-97A1-8A649BABBAAD — ready for a manual POST /constraints + re-solve to test whether `set_min_workers_per_task n=3` becomes satisfiable.
</success_criteria>

<output>
Create `.planning/quick/260714-owo-create-a-new-data-fixture-variant-of-dat/260714-owo-SUMMARY.md` when done.
</output>
