import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import type { Page, Route } from "@playwright/test";

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

export const SCENARIO_ID = "11111111-1111-4111-8111-111111111111";
const SCENARIO_VERSION_ID = "22222222-2222-4222-8222-222222222222";
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
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

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
      return json(route, pageFor(contract, path.slice(prefix.length), url));
    }
    return json(route, { detail: `Unhandled e2e API path: ${path}` }, 404);
  });
}
