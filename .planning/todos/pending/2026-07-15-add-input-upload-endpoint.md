---
created: 2026-07-15T15:32:34.487Z
title: Add input upload endpoint
area: api
files:
  - backend/api/routers/fixtures.py:14
  - backend/api/routers/scenarios.py:17
  - backend/services/scenario_service.py:17
---

## Problem

Scenarios can only be created from fixtures that already exist on disk in `data/`
(`GET /fixtures` at `fixtures.py:14` lists them; `POST /scenarios` at
`scenarios.py:17` takes a `fixture` name that `scenario_service.create_scenario`
resolves against `ROSTERAI_DATA_DIR`). There is no way to get new workforce/demand
data into the system over HTTP — you must have filesystem access to the server.

**This is a gap between stated product intent and the built system.** `docs/vision.md`
opens its elevator pitch with *"Upload workforce & demand data → describe constraint
tweaks in plain English → CP-SAT solver generates a weekly schedule → Claude explains
insights"*. Three of those four now exist. Upload never got built, and because
Phases 1–3 were all API/CLI-driven by a developer with filesystem access, nothing
ever surfaced the omission.

**Directly relevant to the v0.4 frontend milestone.** A UI without this can only
offer a dropdown of pre-existing fixtures — it cannot let a user bring their own
data. That's either a deliberate scope cut for v0.4 (demo against committed
fixtures) or a requirement, and it's much cheaper to decide during milestone
scoping than mid-way through building ScenarioEditor. Flag it as an explicit
question at v0.4 scoping time.

Carried over from `docs/PLAN.md` Phase 2 follow-ups (marked deferred/optional),
migrated into GSD when that hand-written tracker was retired at the v0.3/v0.4
boundary.

## Solution

TBD. Note two existing constraints that shape this:

- The real weekly input is ~16 MB of JSON and is git-ignored; the committed
  fixture is a deliberately tiny subsample. An upload path needs a size limit and
  a streaming/multipart story, not a naive `json.load` of the request body.
- **Security**: there is a sibling pending todo to harden the scenario fixture path
  against traversal (WR-04). An upload endpoint that writes attacker-named files
  into `data/` makes that hole substantially worse. These two should be designed
  together — do not ship upload before the containment check.
