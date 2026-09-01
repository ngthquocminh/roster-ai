import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import type { Page, Route } from "@playwright/test";

import {
  CONVERSATION_ID,
  createRepairJourneyStubState,
  EVIDENCE_RECORD_ID,
  PROPOSAL_ID,
  SCHEDULE_RUN_ID,
  SCENARIO_ID,
  SCENARIO_VERSION_ID,
} from "./repairJourneyStubState";

export {
  CONVERSATION_ID,
  EVIDENCE_RECORD_ID,
  PROPOSAL_ID,
  SCHEDULE_RUN_ID,
  SCENARIO_ID,
  SCENARIO_VERSION_ID,
  TERMINAL_RUN_IDS,
  TIMED_OUT_RUN_ID,
} from "./repairJourneyStubState";

type Contract = Readonly<{
  fixture: { fixture_id: string; version: string };
  overview: Record<string, unknown>;
  groups: Record<string, Array<Record<string, unknown>>>;
}>;

// Both governed Gate A fixtures (Story 1.9's evidence template). They're identical except the
// "more_tm" (more team members) variant's workers group has 22 rows instead of 10 — everything
// else is byte-identical — so it's the one that exercises a denser table without changing the
// pagination math (both stay under the default 50-row page limit).
const CONTRACT_FILES = {
  tiny: "sample_tiny_input.projection-v1.json",
  more_tm: "sample_tiny_input_more_tm.projection-v1.json",
} as const;
export type FixtureKey = keyof typeof CONTRACT_FILES;

function loadContract(fixture: FixtureKey): Contract {
  const contractPath = fileURLToPath(
    new URL(`../../../data/contract/${CONTRACT_FILES[fixture]}`, import.meta.url),
  );
  return JSON.parse(readFileSync(contractPath, "utf8")) as Contract;
}

const SITE_ID = "33333333-3333-4333-8333-333333333333";
const common = {
  schema_version: "v1",
  scenario_id: SCENARIO_ID,
  scenario_version_id: SCENARIO_VERSION_ID,
  site_id: SITE_ID,
};

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ body: JSON.stringify(body), contentType: "application/json", status });
}

function catalogueEntry(contract: Contract) {
  return {
    ...common,
    fixture_id: contract.fixture.fixture_id,
    scenario_name: contract.fixture.fixture_id,
    fixture_version: contract.fixture.version,
    checksum_algorithm: "sha256",
    checksum_schema_version: "rfc8785-v1",
    checksum_digest: "a".repeat(64),
    imported_at: "2026-08-06T00:00:00Z",
  };
}

const NON_FILTER_PARAMS = new Set(["cursor", "limit", "order", "sort"]);

// Mirrors backend/adapters/postgres/scenario_projection.py's filter semantics closely enough for
// deterministic e2e fixtures: "_contains" is a case-insensitive substring match, "_gte"/"_lte" are
// numeric bounds, everything else is an exact-match filter on the like-named item field. Without
// this, a11y specs that pass a filter query param would render an identical, unfiltered table.
function matchesFilters(item: Record<string, unknown>, url: URL): boolean {
  for (const [param, value] of url.searchParams) {
    if (NON_FILTER_PARAMS.has(param)) continue;
    if (param.endsWith("_contains")) {
      const field = item[param.slice(0, -"_contains".length)];
      if (typeof field !== "string" || !field.toLowerCase().includes(value.toLowerCase())) return false;
    } else if (param.endsWith("_gte") || param.endsWith("_lte")) {
      const suffixLength = param.endsWith("_gte") ? "_gte".length : "_lte".length;
      const field = Number(item[param.slice(0, -suffixLength)]);
      const bound = Number(value);
      if (Number.isNaN(field) || (param.endsWith("_gte") ? field < bound : field > bound)) return false;
    } else if (String(item[param] ?? "") !== value) {
      return false;
    }
  }
  return true;
}

function pageFor(contract: Contract, group: string, url: URL) {
  const all = contract.groups[group] ?? [];
  const items = all.filter((item) => matchesFilters(item, url));
  const cursor = Number(url.searchParams.get("cursor") ?? 0);
  const limit = Number(url.searchParams.get("limit") ?? 50);
  const page = items.slice(cursor, cursor + limit);
  const nextCursor = cursor + page.length < items.length ? cursor + page.length : null;
  return {
    ...common,
    group,
    items: page,
    next_cursor: nextCursor,
    total_count: all.length,
    matching_count: items.length,
  };
}

export async function installApiStubs(page: Page, options?: { fixture?: FixtureKey }) {
  const contract = loadContract(options?.fixture ?? "tiny");
  const repairJourney = createRepairJourneyStubState();
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (request.method() === "POST" && path === `/api/v1/conversations/${CONVERSATION_ID}/messages`) {
      return json(route, repairJourney.acceptMessage(), 201);
    }
    if (request.method() === "POST" && path.startsWith(`/api/v1/conversations/${CONVERSATION_ID}/agent-runs/`) && path.endsWith("/execute")) {
      return json(route, repairJourney.executeTurn());
    }
    if (request.method() === "POST" && path === "/api/v1/schedule-runs") {
      return json(route, repairJourney.startedRun());
    }
    if (request.method() !== "GET") {
      return json(route, { detail: "Method not allowed in deterministic e2e stub" }, 405);
    }
    if (path === "/api/v1/auth/session") {
      return json(route, {
        app_user_id: "44444444-4444-4444-8444-444444444444",
        site_id: SITE_ID,
        csrf_token: "e2e-csrf-token",
        expires_at: "2099-01-01T00:00:00Z",
      });
    }
    if (path === "/api/v1/scenarios") {
      return json(route, [catalogueEntry(contract)]);
    }
    if (path === "/api/v1/conversations") {
      return json(route, {
        items: [{ id: CONVERSATION_ID, scenario_id: SCENARIO_ID, scenario_version_id: SCENARIO_VERSION_ID, resource_version: 2 }],
        limit: 100,
        has_more: false,
      });
    }
    // Path must match `frontend/src/api/agentAvailability.ts` exactly — the
    // hyphenated form. A `/agent/availability` spelling never matched, so this
    // branch was dead and every Chat open fell through to the 404 tail.
    if (path === "/api/v1/agent-availability") {
      return json(route, { available: true, reason: null, observed_at: "2026-08-25T01:00:00Z" });
    }
    if (path === `/api/v1/conversations/${CONVERSATION_ID}/timeline`) {
      const baseItems = [{
        schema_version: "1",
        activity_id: "66666666-6666-4666-8666-666666666666",
        activity_type: "agent_response",
        conversation_id: CONVERSATION_ID,
        conversation_resource_version: 2,
        scenario_id: SCENARIO_ID,
        scenario_version_id: SCENARIO_VERSION_ID,
        occurred_at: "2026-08-15T00:00:00Z",
        sequence: "1",
        response: {
          schema_version: "1",
          scenario_version_id: SCENARIO_VERSION_ID,
          segments: [{
            schema_version: "1",
            kind: "claim",
            metric: "required_headcount_minutes",
            arguments: { schema_version: "1", task_id: "pick", family: "outbound", start_minute: 2880, end_minute: 3600 },
            result_id: "e2e-result-1",
            value: 720,
            unit: "minutes",
            verdict: "supported",
            failure: null,
            evidence_refs: [{
              schema_version: "1",
              scenario_version_id: SCENARIO_VERSION_ID,
              checksum_algorithm: "sha256",
              checksum_schema_version: "rfc8785-v1",
              checksum_digest: "a".repeat(64),
              producing_run_version: null,
              baseline_schedule_version: null,
              group: "demand",
              record_id: EVIDENCE_RECORD_ID,
              field: "amount",
              start_minute: 2880,
              end_minute: 3600,
            }],
          }],
        },
      }];
      return json(route, {
        conversation_id: CONVERSATION_ID,
        resource_version: repairJourney.timelineItems(baseItems).length === baseItems.length ? 2 : 4,
        latest_agent_run_status: null,
        items: repairJourney.timelineItems(baseItems),
        limit: 200,
        has_more: false,
      });
    }
    if (path === `/api/v1/proposals/${PROPOSAL_ID}`) {
      return json(route, repairJourney.proposal());
    }
    if (path === "/api/v1/schedule-runs") {
      return json(route, repairJourney.runPage());
    }
    if (path === "/api/v1/approvals/provenance") {
      const common = {
        occurred_at: "2026-08-31T01:00:00Z", site_id: SITE_ID,
        actor_id: null, initiated_by_actor_id: null, decided_by_actor_id: null,
        request_id: null, attempt_id: null, conversation_id: CONVERSATION_ID,
        agent_run_id: null, tool_call_id: null, approval_id: null,
        job_attempt_id: null, schedule_run_id: SCHEDULE_RUN_ID, audit_id: null,
        schedule_version_id: null, scenario_version_id: SCENARIO_VERSION_ID,
        evidence_refs: [], schema_version: "v1",
      };
      // One tuple, several items: every audit-sourced provenance item copies the
      // same candidate references, so the accessibility sweep must see the
      // repeated evidence links the real page renders, not one per item.
      const auditRefs = [{ scenario_version_id: SCENARIO_VERSION_ID, checksum_algorithm: "sha256", checksum_schema_version: "rfc8785-v1", checksum_digest: "c".repeat(64), producing_run_version: "run-v1", baseline_schedule_version: null, group: "demand", record_id: "audit-demand-1", field: null, start_minute: null, end_minute: null, schema_version: "v1" }];
      return json(route, {
        schedule_run_id: SCHEDULE_RUN_ID, site_id: SITE_ID, schema_version: "v1",
        items: [
          { ...common, item_type: "approval_decision", approval_id: "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa", decided_by_actor_id: "planner-with-a-deliberately-long-stable-identifier-that-must-wrap-without-scrolling", outcome: "approval_consumed", state: "consumed" },
          { ...common, item_type: "audit_record", audit_id: "dddddddd-4444-4444-8444-dddddddddddd", action: "approval_decision", outcome: "approval_consumed", success: true, safe_summary: "Approval was consumed and the candidate became the baseline.", parameter_hash: "a".repeat(64), consequence_hash: "b".repeat(64), policy_version: "policy-v1", app_version: "e2e", worker_facts: { lease_owner: null, attempt_id: null, fencing_epoch: null }, evidence_refs: auditRefs },
          { ...common, item_type: "baseline_promotion", schedule_version_id: "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb", before_version: "baseline-v12", after_version: "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb", evidence_refs: auditRefs },
        ],
      });
    }
    if (path === `/api/v1/schedule-runs/${SCHEDULE_RUN_ID}/result`) {
      return json(route, repairJourney.nextResult());
    }
    // The pre-terminal rows in `runPage()` need result endpoints too, or the
    // Runs table advertises a "View results" link that 404s and
    // `ScenarioResults`' `NON_PROMOTABLE` branch can never render.
    const resultMatch = /^\/api\/v1\/schedule-runs\/([^/]+)\/result$/.exec(path);
    if (resultMatch) {
      const terminal = repairJourney.terminalResult(resultMatch[1]!);
      if (terminal) return json(route, terminal);
    }
    if (path === `/api/v1/scenarios/${SCENARIO_ID}`) {
      return json(route, {
        ...catalogueEntry(contract),
        baseline_schedule_version: null,
      });
    }
    if (path === `/api/v1/scenarios/${SCENARIO_ID}/projection`) {
      return json(route, {
        ...common,
        ...contract.overview,
        scenario_name: contract.fixture.fixture_id,
        fixture_version: contract.fixture.version,
        projection_generated_at: "2026-08-06T00:00:00Z",
      });
    }
    const prefix = `/api/v1/scenarios/${SCENARIO_ID}/projection/`;
    if (path.startsWith(prefix)) {
      const [group, recordId] = path.slice(prefix.length).split("/");
      if (recordId) {
        if (url.searchParams.get("scenario_version_id") !== SCENARIO_VERSION_ID) {
          return json(route, { type: "about:blank", title: "Evidence version mismatch", status: 404, detail: "The cited version differs.", code: "evidence_version_mismatch" }, 404);
        }
        const record = contract.groups[group!]?.find((item) => item.record_id === decodeURIComponent(recordId));
        return record
          ? json(route, record)
          : json(route, { type: "about:blank", title: "Evidence not found", status: 404, detail: "The cited evidence record was not found.", code: "evidence_not_found" }, 404);
      }
      return json(route, pageFor(contract, group!, url));
    }
    return json(route, { detail: `Unhandled e2e API path: ${path}` }, 404);
  });
  // Returned so a spec can drive the scripted run's phase explicitly
  // (`repairJourney.completeRun()`) instead of depending on how many result
  // reads the application happens to issue. Existing specs ignore it.
  return repairJourney;
}
