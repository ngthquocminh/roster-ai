# Adversarial Review — Epic 4 Architecture Spine

**Target:** `_bmad-output/planning-artifacts/architecture/architecture-epic-4-2026-08-27/ARCHITECTURE-SPINE.md`
**Method:** construct concrete story pairs (4.1–4.6) that each satisfy every inherited AD and every EAD to the letter yet can still be built incompatibly by independent dev sessions. Only genuine two-readers-could-diverge cases are listed; no invented findings.

**Verdict:** the spine is strong on state-machine and hashing invariants but leaves **transaction ownership** underspecified across the story boundary in three related ways (which story writes TX3, which story creates `site_baseline`, and what "touch" means for lazy expiry) — each is concrete enough that two dev sessions building 4.1–4.3 in isolation would produce incompatible code, not just style drift. Recommend tightening EAD-1/EAD-6/EAD-7 before dev-story creation for 4.1–4.3.

---

## Finding 1 — CRITICAL: `site_baseline` table creation races between Story 4.1 and Story 4.3

**Pair:** 4.1 vs 4.3

**Text in tension:**
- EAD-1 (binds 4.1, 4.3, 4.4): "The site baseline pointer is a scheduling-owned, dedicated one-row-per-site record (`site_baseline`: ...) ... `Migrations:` additive: 3 tables + `agent_run.status_reason`" — no per-story attribution of which migration lands the table.
- EAD-2 (binds **4.1–4.3**, explicitly): "an absent `site_baseline` row is the valid 'no baseline' state. `ApprovalBindingV1.baseline_version = null` means *expects absence*..."
- Story 4.1 AC1 (epics.md): the pending binding must record "...candidate/version, baseline/version..." at request time — i.e., Story 4.1 must already be able to *read* `site_baseline` (or its absence) to populate the binding.
- EAD-9's supplier table: "Baseline pointer | `site_baseline` (created by Story 4.3) | — (real once 4.3 lands)" — names Story 4.3, not 4.1, as the table's creator, and explicitly says it isn't "real" until then.

**Divergence:** Story 4.1 cannot satisfy its own AC1 (recording `baseline_version`, including the null "no baseline" case per EAD-2) unless `site_baseline` already exists as a schema object. But EAD-9 attributes creation of that table to Story 4.3. A dev session building 4.1 first (numeric/dependency order) either (a) creates the table itself to unblock its own AC — silently taking ownership EAD-9 assigns elsewhere, so when 4.3's session runs later it either re-creates it (migration conflict) or discovers it already exists and has to reverse-engineer whether 4.1's shape matches what 4.3 needs (CAS column, FK, unique `site_id`) — or (b) stubs/skips the check, deferring EAD-2's null-vs-absent semantics until 4.3 lands, silently weakening its own AC. Two sessions reading the same spine can reach either branch and be individually "compliant."

**Fix direction:** EAD-1 or EAD-9 should name one story as migration owner for `site_baseline` (most naturally 4.1, since 4.1 needs to read it before 4.3 needs to write it), and EAD-9's supplier row should stop implying the table is a 4.3-only artifact.

---

## Finding 2 — CRITICAL: no story is named owner of the decide-reject/expire/stale transaction (TX3)

**Pair:** 4.2 vs 4.3

**Text in tension:**
- EAD-6 (binds **4.1–4.3**, 4.5): "Epic 4's atomic bundles are exactly: **request-approval** = ...; **decide-approve** = ...; **decide-reject/expire/stale** = terminal binding + `agent_cancelled(reason)` + audit + event." Three bundles, bound to three stories collectively, no 1:1 story attribution.
- Structural Seed: `application/use_cases/decide_approval.py    # TX2 / TX3 bundles` — one file, both bundles, still no per-story split.
- Story → Architecture Map: **Story 4.2** row lists `AD-2, AD-14, EAD-4, EAD-5, EAD-7` — **EAD-6 is absent**. **Story 4.3** row lists `AD-10, AD-12, AD-22, EAD-1, EAD-2, EAD-6, EAD-8` — EAD-6 present.
- Story 4.2's own ACs (epics.md) narrate the reject path as *committing*: "Given rejection / When the authenticated decision commits / Then the binding becomes terminal rejected, the agent run cancels/ends according to its closed graph... And replay returns the same semantic rejection." This is TX3's exact effect, described in the story whose architecture-map row does **not** cite the bundle that produces it.
- Story 4.3's title and every one of its ACs are approve/promote-only; its only mention of reject/stale/expired is in the *audit-uniqueness* AC ("successful, denied, stale, failed, cancelled, rejected, or expired consequential attempts... audit is... unique"), which is about the audit record, not the state-transition command.

**Divergence:** A dev session on 4.2 reading its own ACs will reasonably conclude it must implement the reject decision endpoint end-to-end (binding → terminal, run → `agent_cancelled`, audit, event) since that's what the AC literally requires and EAD-6 isn't cited to redirect it elsewhere. A dev session on 4.3, seeing EAD-6 in its own governance row and reading "Epic 4's atomic bundles are exactly" as an epic-wide command inventory it is responsible for wiring alongside decide-approve in the same `decide_approval.py`, could just as reasonably build TX3 itself — or skip it, assuming 4.2 already built it since 4.2's ACs describe the user-visible behavior. Either both stories build competing reject/expire/stale code paths against the same `approval_request` row, or neither does and it falls through the gap during integration.

**Fix direction:** EAD-6 (or the Story → Architecture Map) should explicitly assign one story as the sole implementor of the decide-reject/expire/stale bundle and its `POST /approvals/{id}/decide` route, with the other story's ACs reframed as "renders/asserts the outcome this other story produces," not "commits" it.

---

## Finding 3 — HIGH: pending→stale is described in two places with different triggering logic, neither citing the other

**Pair:** 4.2 vs 4.3 (same underlying gap as Finding 2, worth separating because the *conflict resolution logic* differs from plain rejection)

**Text in tension:**
- EAD-2 (binds 4.1–4.3): "Any mismatch in either direction marks the binding `stale` — never a silent rebase, never a second candidate." This is revalidation-time business logic (compare expected vs. current baseline/candidate/hash).
- EAD-6: "any failure rolls the whole bundle back (approve failure returns the binding to **pending** with no baseline change)." This is transactional-failure logic (infra fault, DB error).
- Story 4.2 AC3: "Given the candidate, baseline, parameters, consequence hash, membership, policy, or expiry no longer matches / When the planner attempts approval / Then the request becomes stale or expired..." — narrates staleness as an outcome of *attempting approval*, i.e., inside the decide path.
- Story 4.3 AC1: "Given a valid pending approval / When Approve as baseline is processed / Then current actor/site/membership, policy, binding hashes, candidate feasibility/version, baseline version, expiry, and idempotency are revalidated inside the command transaction" — the same revalidation is described here as Story 4.3's job.

**Divergence:** both stories describe running the identical revalidation checks (candidate/baseline/hash/membership/policy/expiry) as their own AC, with different resulting states depending on interpretation (EAD-6 says a failed approve attempt reverts to `pending`; EAD-2/4.2 says a mismatch produces terminal `stale`). Nothing in the spine distinguishes "the kind of failure that reverts to pending" from "the kind of mismatch that terminalizes to stale," nor names which story's code path is authoritative for making that distinction. A 4.2 implementation and a 4.3 implementation could each independently decide the fork logic differently — one always stale-on-mismatch, one always pending-on-any-failure — and disagree on the same input.

**Fix direction:** EAD-2 or EAD-6 should state explicitly: *any* revalidation mismatch (business) → `stale`; only a transactional/infra fault (write failure) → rollback-to-`pending`; and name the single command/story that implements this fork.

---

## Finding 4 — HIGH: EAD-7's "touch" definition makes reads ambiguous between pure-read and mutating

**Pair:** 4.2 (render/decide) vs 4.5 (proof)

**Text in tension:** EAD-7's rule: "any in-transaction touch of a pending binding (decision attempt, revalidation, replay, **render-time state read that mutates**) evaluates `now() >= expires_at` and, if overdue, persists the terminal `expired` outcome via the decide-expire bundle. An overdue-but-untouched row is *semantically* expired — **reads must present it as expired**  — but its terminal state materializes on first touch."

The phrase "render-time state read that mutates" is internally tensioned: it calls the event a "read" while classifying it as a "touch" that "mutates" and persists a terminal write via the decide-expire bundle (itself one of EAD-6's three fixed transactions, which is a write bundle including audit + event). Meanwhile the same rule separately requires "reads must present it as expired" as if presentation is achievable without persisting anything.

**Divergence:** Story 4.2 owns rendering (its map row cites EAD-7 directly) and Story 4.5 owns proving the guard (also cites EAD-7). Two readings are both defensible:
- **Reading A** (4.2 builds it as side-effecting): loading/reconnecting to an overdue pending approval (a GET, or SSE replay per EAD-4) triggers the full decide-expire bundle as a side effect of rendering — i.e., an idempotent-looking read causes a write, new audit row, and a persisted event, on every subsequent reload until someone else beats it to the row.
- **Reading B** (4.2 builds it as pure): rendering computes `expired` in memory for display only (satisfying "reads must present it as expired") and never persists; the terminal write only happens on the next *actual* decision attempt (approve/reject), i.e., "render-time" was loose language and the parenthetical was describing a decision-adjacent read, not a page load.

Story 4.5's proof suite must assert a demonstrated-red case for whichever reading is correct ("a passing guard that cannot be made to fail by a relevant mutation does not count") — if 4.2 builds Reading B and 4.5's fixtures assume Reading A (or vice versa), the proof will either falsely pass against un-implemented behavior or falsely fail against correctly-implemented behavior.

**Fix direction:** EAD-7 should state plainly whether a GET/render/reconnect is permitted to cause a database write, and if so, whether repeated reloads of the same overdue row are expected to no-op after the first (via the same TX3 idempotency machinery) or are expected to attempt the bundle every time.

---

## Finding 5 — HIGH: request-approval's audit effect_key/uniqueness is unpinned, unlike promotion's

**Pair:** 4.1 vs 4.3

**Text in tension:**
- EAD-6: "HTTP idempotency follows AD-8; **the promotion effect key is the `approval_id` itself**, and success-audit uniqueness on `(site_id, effect_key, outcome)` makes a second pointer movement structurally impossible." This pins the effect_key explicitly, but only for **promotion** (decide-approve).
- EAD-6's TX1 bundle ("request-approval = pending binding + `approval_required` transition + audit + event") also writes an audit row, per AD-12's inherited rule that "successful mutation audit is unique on `(site_id, effect_key, outcome)`."
- AD-12 (inherited): defines the two uniqueness rules generically but does not itself assign per-action effect_keys; that assignment is left to each epic/story.

**Divergence:** nothing in the Epic 4 spine states what `effect_key` Story 4.1's request-approval audit row uses. Two plausible, independently "compliant" choices: (a) reuse `approval_id` as the effect_key (mirroring 4.3's promotion pattern, since it's the same aggregate) — which is fine as long as `outcome` differs ("requested" vs "approved") but was never confirmed as intentional; or (b) use a distinct key (e.g., a fresh idempotency-key hash per AD-8's HTTP scheme, since the *request* command's replay semantics are governed by AD-8's body-hash rule in the Inherited table, not by `approval_id`). A 4.1 dev session and a 4.3 dev session, each only reading their own bundle's line in EAD-6, have no way to confirm they've picked compatible keys/outcome-vocabulary for the same table's uniqueness index without cross-referencing code that doesn't exist yet.

**Fix direction:** EAD-6 (or EAD-1's table description) should name the effect_key and `outcome` literal for the request-approval audit row explicitly, the same way it does for promotion.

---

## Finding 6 — HIGH: AD-8's two idempotency-key shapes collide on Story 4.1's dual initiator ("planner or agent")

**Pair:** 4.1 internal (planner-initiated path vs agent-initiated path), surfacing as a 4.1-vs-4.3 contract mismatch on the shared `approval_request` table

**Text in tension:**
- Parent AD-8 (inherited, binding, unweakenable): "each mutating HTTP command requires an idempotency key scoped to actor, site, operation, and canonical body hash plus expected resource version. **Tool/worker effects use stable `(agent_run_id, tool_call_id)` or job-effect keys.** Database uniqueness protects both."  — two distinct, legitimate key shapes depending on whether the effect originates from an HTTP command or a tool/worker call.
- Epic 4's own Inherited-Invariants row for AD-8 narrows this: "request-approval and decide commands carry actor/site/operation/body-hash idempotency keys plus expected versions; replay returns the original semantic result." — states only the HTTP/body-hash shape for request-approval, silently dropping the tool/worker-effect option AD-8 itself permits.
- Story 4.1 AC1 (epics.md): "**the planner or agent** requests baseline approval" — explicitly names two initiators. Under AD-5's capability-module framing (parent spine), an agent-initiated action normally executes as a typed tool call, which per AD-8 would key on `(agent_run_id, tool_call_id)`, not a body hash.

**Divergence:** if the planner-initiated path is built as an HTTP command (body-hash key) and the agent-initiated path is built as a capability/tool call (agent_run_id/tool_call_id key), the single `approval_request` table's idempotency column and its uniqueness constraint (from EAD-1: "at most one `pending` per agent run, enforced by a partial unique index") must accommodate both shapes — but the Epic 4 spine's own narrowing sentence tells a reader only one shape exists. A dev session that takes the Epic-4 Inherited table at face value (body-hash only) will build a table/index that cannot represent an agent-initiated tool-call request without inventing a synthetic body hash from the tool call args, diverging from whatever a session that instead trusts the parent AD-8 text (and builds a proper `(agent_run_id, tool_call_id)` path) produces.

**Fix direction:** state explicitly, for Story 4.1, whether "the agent requests approval" means (a) the agent emits a typed tool call subject to AD-8's tool/worker key path, or (b) the model can only ever trigger the *same* HTTP command a planner would (in which case "or agent requests" in the AC is describing who ultimately authorizes it, not a second code path) — and if (a), reconcile the single-table idempotency-key shape.

---

## Finding 7 — MEDIUM: EAD-8's baseline-supply guard doesn't name Story 4.2 as a bound consumer, but 4.2 needs the same data

**Pair:** 4.2 vs 4.3 (and the EAD-8 guard itself)

**Text in tension:**
- EAD-8: "**Binds:** Story 4.3; `calculate_comparison`; any future consumer of `get_baseline_assignments`" — 4.2 is not named directly.
- Story 4.2 AC1: the approval review "shows candidate, **current baseline**, material parameters, consequence summary, policy/expiry context, and versions" — this rendering plainly needs baseline-side data, i.e., is "a... consumer of `get_baseline_assignments`" in substance even though not cited by name.
- EAD-8's own rule: "any comparison whose frozen `baseline_schedule_version` is non-null while the baseline assignment supply for that exact version is not authoritatively readable must fail closed... never render an empty read as 'the baseline is empty.'"

**Divergence:** the guard's "any future consumer" catch-all is supposed to cover this, but because Story 4.2's own architecture-map row and AC never cite EAD-8, a dev session building 4.2's baseline-summary rendering (once a real promotion exists from a prior cycle, so `site_baseline` is non-null but assignment data is still unwired per EAD-8's deferral) could independently call whatever baseline-read helper is available, get an empty result, and render it as "baseline has no assignments" — reproducing exactly the false-empty hazard `deferred-work.md`'s 3.8/3.10 entries record, without recognizing that EAD-8 was meant to stop it.

**Fix direction:** add Story 4.2 explicitly to EAD-8's `Binds` line, since its consequence-summary rendering is a textbook instance of "any future consumer."

---

## Finding 8 — MEDIUM: nothing finalizes the resumed `AgentRun` after decide-approve

**Pair:** 4.1 vs 4.3

**Text in tension:**
- EAD-5: "Approve records the decision and returns the run to `agent_running` inside the promotion transaction (AD-7's 'decision recorded' edge)."
- EAD-6's decide-approve bundle: "revalidation + `pending → consumed` + `site_baseline` CAS + audit + event + **run resume**" — stops at resume; no completion step is listed.
- Parent AD-7's `AgentRun` graph: `agent_running` can still go to `agent_completed | agent_timed_out | agent_cancelled | agent_failed` — some subsequent transition must eventually fire, but nothing in Epic 4 (or the cited parent capability/orchestrator machinery) says what drives it, given this is the *first* time an `agent_running` run has ever come back from a pause rather than running continuously from `agent_queued`.

**Divergence:** Story 4.1 (owner of the original pause plumbing) and Story 4.3 (owner of the resume) could each assume the other — or both assume Epic 2/3's pre-existing agent loop transparently continues and self-completes the run post-resume, even though that loop has never previously observed a mid-run resume from `approval_required` and nothing in this spine confirms it's wired to do so. If neither story wires a completion path, a successfully approved run can be left parked in `agent_running` indefinitely.

**Fix direction:** name, even briefly, which component (existing conversation orchestrator vs. a small addition in 4.3) is responsible for driving the resumed run to a terminal state, or explicitly defer it with a trigger (as the spine already does for other gaps in its Deferred table).

---

## Finding 9 — LOW: post-resume worker-event attribution rule is unstated (masked by one-user MVP)

**Pair:** 4.1 vs 4.3 (visible mainly for Story 4.4's provenance projection)

**Text in tension:** EAD-3 defines `initiated_by_actor_id` (who requested) and `decided_by_actor_id` (who approved/rejected) as separate fields, and separately states "worker-driven persisted events set `actor_id` to the initiating human principal of the enqueuing command... not the proposal author." After decide-approve resumes the run and it continues executing (per Finding 8, however that's eventually wired), any further worker-driven events during that continuation aren't clearly assigned to `initiated_by_actor_id` (original requester) vs. `decided_by_actor_id` (approver) by name — only inferable by analogy to the "enqueuing command" phrase, which itself doesn't obviously name the approve-decision as an "enqueuing command." Two-actor test fixtures (per EAD-9's supplier table: "seeded two-actor tests; gap: second real user") would need this pinned to be meaningful; today's one-user MVP makes both fields equal and the divergence untestable, but a 4.1-session and a 4.3-session could still encode different rules in code now that surface only when a second user exists.

**Fix direction:** low priority given the current MVP; worth a one-line clarification before Story 4.4 (provenance) or the second-user trigger.

---

## Summary Table

| # | Pair | Severity | One-line hole |
| --- | --- | --- | --- |
| 1 | 4.1 vs 4.3 | Critical | `site_baseline` table creation ownership contradicts between EAD-1/EAD-2 (needed by 4.1) and EAD-9 ("created by Story 4.3") |
| 2 | 4.2 vs 4.3 | Critical | No story is named owner of the decide-reject/expire/stale (TX3) command; 4.2's ACs narrate it committing, EAD-6/Structural-Seed give it to neither by name |
| 3 | 4.2 vs 4.3 | High | pending→stale (business mismatch) vs pending→pending (transactional failure) fork logic is described twice with no single owner |
| 4 | 4.2 vs 4.5 | High | EAD-7's "render-time state read that mutates" leaves read-vs-write semantics of lazy expiry ambiguous |
| 5 | 4.1 vs 4.3 | High | Request-approval's audit effect_key/outcome vocabulary is never pinned, unlike promotion's explicit `approval_id` key |
| 6 | 4.1 (planner vs agent path) | High | AD-8's HTTP-vs-tool/worker idempotency-key split collides with 4.1's "planner or agent requests" dual initiator |
| 7 | 4.2 vs 4.3/EAD-8 | Medium | EAD-8's consumer guard doesn't name Story 4.2 though its baseline-summary render is a textbook consumer |
| 8 | 4.1 vs 4.3 | Medium | No one finalizes the resumed `AgentRun` after decide-approve returns it to `agent_running` |
| 9 | 4.1 vs 4.3 | Low | Post-resume worker-event actor attribution (initiated vs decided) is unstated, masked by one-user MVP |
