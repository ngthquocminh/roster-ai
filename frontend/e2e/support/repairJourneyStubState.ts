export const SCENARIO_ID = "11111111-1111-4111-8111-111111111111";
export const SCENARIO_VERSION_ID = "22222222-2222-4222-8222-222222222222";
export const CONVERSATION_ID = "55555555-5555-4555-8555-555555555555";
export const EVIDENCE_RECORD_ID = "outbound:0";
export const PROPOSAL_ID = "77777777-7777-4777-8777-777777777777";
export const PROPOSAL_VERSION_ID = "88888888-8888-4888-8888-888888888888";
export const SCHEDULE_RUN_ID = "99999999-9999-4999-8999-999999999999";

/** The terminal run the journey clicks through to, proving `ScenarioResults`'
 *  `NON_PROMOTABLE` branch (`TerminalOutcomeCard`) renders in a real browser.
 *  `TerminalOutcomeCard` is status-independent — only the badge and `reason`
 *  differ across the four statuses, and the per-status badge literals are
 *  already asserted against the Runs table — so one terminal render closes the
 *  gap without re-proving the badge four times. */
export const TIMED_OUT_RUN_ID = "30303030-3030-4030-8030-303030303030";

const AGENT_RUN_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const DRAFT_ACTIVITY_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const PLANNER_ACTIVITY_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const CANDIDATE_VERSION_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
const ACCEPTED_AT = "2026-08-25T01:00:00Z";
const COMPLETED_AT = "2026-08-25T01:01:00Z";

const evidenceRef = {
  schema_version: "1",
  scenario_version_id: SCENARIO_VERSION_ID,
  checksum_algorithm: "sha256",
  checksum_schema_version: "rfc8785-v1",
  checksum_digest: "a".repeat(64),
  producing_run_version: CANDIDATE_VERSION_ID,
  baseline_schedule_version: null,
  group: "demand",
  record_id: EVIDENCE_RECORD_ID,
  field: "amount",
  start_minute: 2880,
  end_minute: 3600,
} as const;

const draftActivity = {
  schema_version: "1",
  activity_id: DRAFT_ACTIVITY_ID,
  activity_type: "draft",
  conversation_id: CONVERSATION_ID,
  conversation_resource_version: 4,
  scenario_id: SCENARIO_ID,
  scenario_version_id: SCENARIO_VERSION_ID,
  occurred_at: ACCEPTED_AT,
  sequence: "3",
  proposal_id: PROPOSAL_ID,
  proposal_version_id: PROPOSAL_VERSION_ID,
  consequence_summary: "One reversible repair constraint; no baseline change.",
} as const;

const plannerActivity = {
  schema_version: "1",
  activity_id: PLANNER_ACTIVITY_ID,
  activity_type: "planner_message",
  conversation_id: CONVERSATION_ID,
  conversation_resource_version: 3,
  scenario_id: SCENARIO_ID,
  scenario_version_id: SCENARIO_VERSION_ID,
  occurred_at: ACCEPTED_AT,
  sequence: "2",
  message_id: PLANNER_ACTIVITY_ID,
  text: "Create a reversible repair draft.",
} as const;

const metrics = (served: number, cost: number) => ({
  interval_coverage_required_minutes: [["outbound:0", 480]],
  interval_coverage_served_minutes: [["outbound:0", served]],
  function_coverage_required_minutes: [["pick", 480]],
  function_coverage_served_minutes: [["pick", served]],
  overtime_minutes: 0,
  total_cost: cost,
  objective_components: [["coverage_gap", 480 - served]],
  assignment_count: served > 0 ? 1 : 0,
  member_count: served > 0 ? 1 : 0,
  schema_version: "1",
});

const runningRun = {
  schedule_run_id: SCHEDULE_RUN_ID,
  status: "solver_running",
  reason: null,
  resource_version: 2,
  cancellation_requested: false,
  created_at: ACCEPTED_AT,
  finished_at: null,
} as const;

const completedRun = {
  ...runningRun,
  status: "solver_completed",
  resource_version: 3,
  finished_at: COMPLETED_AT,
} as const;

const runningResult = { run: runningRun, candidate: null, comparison: null } as const;
const completedResult = {
  run: completedRun,
  candidate: {
    schedule_version_id: CANDIDATE_VERSION_ID,
    schedule_run_id: SCHEDULE_RUN_ID,
    scenario_id: SCENARIO_ID,
    scenario_version_id: SCENARIO_VERSION_ID,
    proposal_id: PROPOSAL_ID,
    proposal_version_id: PROPOSAL_VERSION_ID,
    feasible_solver_status: "OPTIMAL",
    assignments: [{
      record_id: "candidate-assignment:0",
      worker_id: "worker:0",
      task_id: "pick",
      shift_id: "shift:0",
      start_minute: 2880,
      end_minute: 3360,
    }],
    metrics: metrics(480, 120),
    constraint_results: [],
    warnings: [],
    evidence_refs: [evidenceRef],
    created_at: COMPLETED_AT,
    schema_version: "1",
  },
  comparison: {
    candidate_schedule_version_id: CANDIDATE_VERSION_ID,
    candidate_schedule_run_id: SCHEDULE_RUN_ID,
    scenario_id: SCENARIO_ID,
    scenario_version_id: SCENARIO_VERSION_ID,
    expected_baseline_schedule_version: null,
    current_baseline_schedule_version: null,
    stale: false,
    assignment_diff: {
      added_worker_ids: ["worker:0"],
      removed_worker_ids: [],
      added_shift_ids: ["shift:0"],
      removed_shift_ids: [],
      added_task_ids: ["pick"],
      removed_task_ids: [],
      schema_version: "1",
    },
    candidate_metrics: metrics(480, 120),
    baseline_metrics: metrics(360, 150),
    candidate_constraint_results: [],
    baseline_hard_constraint_results: [],
    warnings: [],
    unresolved_gap_record_ids: [],
    evidence_refs: [evidenceRef],
    schema_version: "1",
  },
} as const;

/** Single source of truth for the terminal rows: `runPage()` renders them in
 *  the Runs table and `terminalResult()` serves the matching result payload, so
 *  a row can never advertise a status its own result endpoint contradicts. */
const TERMINAL_RUNS = [
  ["10101010-1010-4010-8010-101010101010", "solver_completed", null],
  ["20202020-2020-4020-8020-202020202020", "solver_infeasible", "No feasible schedule"],
  [TIMED_OUT_RUN_ID, "solver_timed_out", "Solver ceiling reached"],
  ["40404040-4040-4040-8040-404040404040", "solver_cancelled", "Cancelled by planner"],
  ["50505050-5050-4050-8050-505050505050", "solver_failed", "Solver failed safely"],
] as const;

export const TERMINAL_RUN_IDS: readonly string[] = TERMINAL_RUNS.map(([id]) => id);

export function createRepairJourneyStubState() {
  let messageSent = false;
  // Decision 4a asks for a TEST-controlled progression. A call counter is
  // APP-controlled: any extra read the app happens to issue (a refetch on
  // window focus, a remount, one more assertion) silently advances it and
  // flips the page terminal early. `installApiStubs` returns this object, so
  // the spec advances the phase itself by calling `completeRun()` — extra
  // reads are then harmless and the sequence is a property the test owns.
  let runPhase: "running" | "completed" = "running";

  return {
    acceptMessage() {
      messageSent = true;
      return {
        activity: plannerActivity,
        resource_version: 3,
        agent_run_status: "agent_queued",
        sequence: "2",
        agent_run_id: AGENT_RUN_ID,
      };
    },
    executeTurn() {
      return {
        activity: draftActivity,
        resource_version: 4,
        agent_run_status: "agent_completed",
        sequence: "3",
        agent_run_id: AGENT_RUN_ID,
      };
    },
    timelineItems(baseItems: readonly unknown[] = []) {
      // The planner's own message is part of the persisted timeline the real
      // `finalize_agent_run` path appends to. Omitting it made
      // `useSendMessage.onSettled`'s invalidation erase the sent message from
      // the UI, so the journey was measured against a shape no backend emits.
      return messageSent ? [...baseItems, plannerActivity, draftActivity] : [...baseItems];
    },
    proposal() {
      return {
        proposal_id: PROPOSAL_ID,
        proposal_version_id: PROPOSAL_VERSION_ID,
        scenario_id: SCENARIO_ID,
        scenario_version_id: SCENARIO_VERSION_ID,
        current_scenario_version_id: SCENARIO_VERSION_ID,
        expected_baseline_schedule_version: null,
        resolved_entities: [{
          group: "demand",
          record_id: EVIDENCE_RECORD_ID,
          label: "Outbound demand interval",
          scenario_version_id: SCENARIO_VERSION_ID,
          schema_version: "1",
        }],
        constraints: [{
          kind: "scale_demand",
          resolved_entities: [{
            group: "demand",
            record_id: EVIDENCE_RECORD_ID,
            label: "Outbound demand interval",
            scenario_version_id: SCENARIO_VERSION_ID,
            schema_version: "1",
          }],
          factor: 1.1,
          description: "Scale Outbound demand interval by 1.10.",
          schema_version: "1",
        }],
        preserved_locks: [],
        consequence_summary: draftActivity.consequence_summary,
        canonical_hash: "b".repeat(64),
        canonical_hash_algorithm: "sha256",
        canonical_hash_schema_version: "rfc8785-v1",
        state: "active",
        resource_version: 1,
        stale: false,
        schema_version: "1",
      };
    },
    startedRun() {
      return { schedule_run_id: SCHEDULE_RUN_ID, status: "solver_queued", resource_version: 1 };
    },
    runPage() {
      const terminalRows = TERMINAL_RUNS.map(([scheduleRunId, status, reason], index) => ({
        schedule_run_id: scheduleRunId,
        status,
        reason,
        resource_version: 3,
        created_at: ACCEPTED_AT,
        updated_at: COMPLETED_AT,
        finished_at: COMPLETED_AT,
        scenario_version_id: SCENARIO_VERSION_ID,
        proposal_id: PROPOSAL_ID,
        proposal_version: index + 2,
        baseline_schedule_version: null,
      }));
      return {
        scenario_id: SCENARIO_ID,
        items: [{
          schedule_run_id: SCHEDULE_RUN_ID,
          status: "solver_running",
          reason: null,
          resource_version: 2,
          created_at: ACCEPTED_AT,
          updated_at: ACCEPTED_AT,
          finished_at: null,
          scenario_version_id: SCENARIO_VERSION_ID,
          proposal_id: PROPOSAL_ID,
          proposal_version: 1,
          baseline_schedule_version: null,
        }, ...terminalRows],
        next_cursor: null,
        total_count: 6,
        matching_count: 6,
      };
    },
    /** Advance the scripted run to its terminal state. Called by the spec, not
     *  by a request count, so any number of intervening reads still render the
     *  running state and the reconnect step stays deterministic. */
    completeRun() {
      runPhase = "completed";
    },
    nextResult() {
      return runPhase === "running" ? runningResult : completedResult;
    },
    /** Result payload for one of the pre-terminal rows in `runPage()`. Returns
     *  `undefined` for an unknown id so the caller can fall through to its 404
     *  tail rather than inventing a run. */
    terminalResult(scheduleRunId: string) {
      const entry = TERMINAL_RUNS.find(([id]) => id === scheduleRunId);
      if (!entry) return undefined;
      const [id, status, reason] = entry;
      if (status === "solver_completed") {
        return { ...completedResult, run: { ...completedRun, schedule_run_id: id } };
      }
      return {
        run: {
          schedule_run_id: id,
          status,
          reason,
          resource_version: 3,
          cancellation_requested: status === "solver_cancelled",
          created_at: ACCEPTED_AT,
          finished_at: COMPLETED_AT,
        },
        candidate: null,
        comparison: null,
      };
    },
  };
}
