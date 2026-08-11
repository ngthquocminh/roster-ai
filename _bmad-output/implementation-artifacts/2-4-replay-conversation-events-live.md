---
baseline_commit: 7b8df5a5d57a908b0063a6465ed97b0eb416bd50
---

# Story 2.4: Replay Conversation Events Live

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want live conversation updates that survive reconnects,
So that returning to a conversation never duplicates or loses activity.

**This is the transport story.** Story 2.3 built the record — four governed tables, the
`PersistedEventV1` envelope, monotonic decimal per-stream sequences, and a bounded timeline
read. It is `done` and green at this story's `baseline_commit` (`7b8df5a`, `main`). Story 2.3
explicitly handed this story four things by name: the SSE endpoint, `Last-Event-ID`
validation, replay, and 15-second heartbeats — plus the NFR35 reconnect-replay measurement
(`2-3…md:72-73`).

**This story is also the first NFR35 threshold owned outside Epic 1.** A miss blocks
implementation acceptance (AD-26, and AC3's own words). That is not a formality: the
measurement is the acceptance boundary, not a report written after the fact.

**Unblocks:** Story 3.5 (which reuses this transport for run-progress replay and owns the
*other* SSE-adjacent NFR35 threshold), Story 3.7 (run monitoring), and Story 6.3's
CloudFront/ALB edge proof, which re-proves this contract through real proxies.

---

### Five decisions were made at story creation — do not re-litigate them

#### Decision 1 — The SSE route must **not** take `Depends(get_site_context)`

This is the single most dangerous trap in the story, and it fails as a production outage
rather than a red test.

`get_site_context` (`backend/api/deps.py:138-163`) is a generator dependency wrapping
`with engine.begin() as connection:`. It holds **one pooled PostgreSQL connection inside an
open transaction for the entire request lifetime**. That is correct and cheap for a request
that lives 40 ms. An SSE connection lives for minutes or hours. `_site_context_engine` builds
a default-pooled `create_engine` (pool_size 5, max_overflow 10), so **fifteen concurrent
Chat tabs would consume every connection the application has** and every other endpoint —
sign-in, Scenario Data, the timeline read — would block. The connections would additionally
sit `idle in transaction`, pinning the oldest snapshot and blocking vacuum.

**Instead:** the stream opens a *short* site-scoped transaction per poll and closes it. Task 3
extracts the trusted-context body (`set_config('app.site_id', …, true)` +
`SET LOCAL ROLE shiftmind_runtime`) into one reusable context manager used by **both**
`get_site_context` and the stream, so there remains exactly one place in the repository that
establishes site context. Do not write a second copy inline in the router.

Corollary, from the ledger: `deferred-work.md`'s 2026-07-24 item says *"the next story that
calls it from a live FastAPI request handler must route it through a worker thread to avoid
blocking the event loop."* This is that story. Every poll goes through
`fastapi.concurrency.run_in_threadpool`, the same mechanism `api/main.py:198` and
`api/deps.py:125` already use for `resolve_session`. A synchronous SQLAlchemy call awaited
directly inside an async generator blocks the whole event loop for every other client.

#### Decision 2 — Hand-roll SSE with `StreamingResponse`. Do **not** add `sse-starlette`

AR27: *"add and lock each planned dependency only at its implementation gate"*, and Story
5.3's AC4 restates *"unused planned dependencies are not added prematurely."* `sse-starlette`
is **not** in the architecture spine's Stack table (`ARCHITECTURE-SPINE.md:262-290`), so it is
not a planned seed — adding it would need the same AR19/AR27 justification ceremony Story 2.1
had to run for PydanticAI, to buy roughly forty lines of formatting.

What AD-21 actually requires is small and fully specified: `id: <stream_uuid>:<sequence>`,
`event: <event_type>`, `data: <json>`, a blank line between frames, and a comment-only
heartbeat. Verified against Starlette's own source at this baseline:

- `BaseHTTPMiddleware` does **not** buffer a streaming body. Its internal `body_stream()`
  yields each chunk as it arrives. Both `@app.middleware("http")` layers in `api/main.py`
  are therefore transparent to the stream — but Task 8 proves it rather than trusting it,
  because the whole feature is dead if that ever regresses.
- `StreamingResponse` raises `starlette.requests.ClientDisconnect` on disconnect under ASGI
  spec ≥ 2.4 and races `listen_for_disconnect` under older servers. Let the generator exit on
  it; do not build a second disconnect watchdog.

#### Decision 3 — The stream is read through the **existing** `ConversationRepository`, not a new port

AD-22 gives the conversation aggregate ownership of its own messages, agent runs, and events;
the stream's identity *is* the conversation UUID, pinned in the database by
`ck_persisted_event_stream_is_conversation` (`adapters/postgres/schema.py:329`). Adding a
second port for "the event stream" would split one aggregate across two seams.

So this story adds **one method** to `application/ports/conversation.py` —
"events on this stream with sequence strictly greater than N, oldest first, bounded" — and its
adapter implementation. No new package, no new port module.

**This has a consequence for the deferred-work ledger, and the ledger is wrong.**
`deferred-work.md`'s *"Deferred from: story-2-3 creation"* item nominates Story 2.4 as the
earliest candidate for the `ScenarioCatalogueReader` AD-1 leak, on the stated premise that 2.4
*"adds the next `application/ports/` module (the SSE/event-stream port)"*. **That premise is
false** — per the above, no new port module is created. Task 10 corrects the ledger entry in
place rather than leaving a false premise to mislead the next reader. It does **not** close
the item: the real fix (tier 3) refactors a Gate A read port, its adapter, `api/deps.py`, and
the fixture-catalogue router, and this story already carries a threshold that blocks its own
acceptance. Taking tier 1 or 2 would be worse than leaving it — someone would delete the
`ALLOWED_LEAKS` entry while the vendor type still sat in the contract.

#### Decision 4 — A rejected `Last-Event-ID` **terminates** the browser's `EventSource`; the client re-establishes from its own cursor

This is what AC2's second half is describing, and the mechanism matters.

Per the WHATWG spec, a browser `EventSource` auto-reconnects on a *network* failure and
replays the last `id:` it saw in the `Last-Event-ID` header — but on a **non-200 response, or
a response that is not `text/event-stream`, it fails the connection permanently**: it fires
`error`, sets `readyState = CLOSED`, and never retries. That is exactly the behaviour this
story needs, and it is also the trap: if the server *did* answer a bad cursor with a 200 and
an error frame, the browser would auto-retry forever with the same poisoned header.

So: reject with a real problem response (Task 5), and let the client's `onerror` handler
close the dead source and construct a new one carrying its own persisted cursor as a **query
parameter** (Task 7). `EventSource` cannot set request headers — this is why the endpoint
accepts the cursor two ways, and why the query parameter is not redundant with the header.

Precedence, fixed here: **the `Last-Event-ID` header wins when present**; the
`?last_event_id=` query parameter is the fallback. One resolution rule, stated in the
router, so the two paths cannot disagree.

#### Decision 5 — Non-disclosure is achieved by **never looking up the foreign stream**

AC2 requires the rejection to reveal *"no other stream's existence, sequence position, or
content."* The mechanical guarantee is not careful copywriting, it is control flow:

> When the cursor's `<stream_uuid>` does not equal the conversation UUID in the URL path,
> **reject on the string comparison alone.** Issue no query. Ever.

If no query is issued, no timing signal, error-shape difference, or row count can leak.
A test asserts the mismatch path performs zero database calls (Task 8) — an assertion about
the mechanism, not about the wording.

All three AC2 rejection causes — malformed, foreign stream, impossible sequence — return
**one** stable code and one body. They are the same event to the planner and must be
indistinguishable to a prober.

---

## Acceptance Criteria

1. **Given** a persisted conversation event stream **when** the browser connects or reconnects
   with `Last-Event-ID` **then** the server validates stream identity and replays only greater
   decimal sequences using the canonical SSE ID format **and** 15-second comment heartbeats
   carry no ID and are not persisted. *(AR21)*

2. **Given** a `Last-Event-ID` that is malformed, references a different stream, or carries a
   sequence the stream cannot contain **when** the server validates it **then** the connection
   is rejected with a stable non-disclosing problem response that reveals no other stream's
   existence, sequence position, or content, and no events are replayed from the mismatched
   stream **and** the browser recovers by re-establishing the stream from its own persisted
   cursor or falling back to labelled polling, without duplicating or silently dropping
   visible activity. *(AR21, UX-DR6, UX-DR20)*

3. **Given** the NFR35 measurement fixture and protocol used in Story 1.4, applied to a
   conversation whose stream holds the largest Gate A replay backlog **when** the browser
   reconnects with a stale `Last-Event-ID` **then** every run replays to current state within
   5 seconds, measured from reconnect request receipt to delivery of the last outstanding
   persisted event **and** the measured values are recorded as release evidence and a miss
   blocks implementation acceptance of this story. *(NFR35)*

## Tasks / Subtasks

- [ ] **Task 1: The cursor contract — parse, validate, compare** (AC: #1, #2)
  - [ ] `backend/application/contracts/stream_cursor.py` — a frozen `StreamCursorV1`
        (`stream_id: UUID`, `sequence: Decimal`) plus a parser for AD-21's
        `<stream_uuid>:<sequence>` format. Frozen dataclass, `V1` suffix, `schema_version` —
        mirror `contracts/persisted_event.py`, the closest existing example.
  - [ ] The parser returns a typed failure, never raises past the boundary and never returns
        a partially-parsed value. Reject: missing or extra `:`, a non-UUID left side, a
        non-numeric right side, a **non-integral** decimal (`persisted_event.sequence` is
        `Numeric(38, 0)` — `1.5` is a value the stream cannot contain), a negative value, and
        anything exceeding 38 digits.
  - [ ] **Compare sequences as `Decimal`, never as strings.** `"10" < "9"` is true for strings
        and is the classic silent replay bug — it would drop every event from sequence 10
        onward for a client resuming at 9.
  - [ ] Zero is a legal *cursor* (meaning "replay everything") while never being a legal
        *stored* sequence: allocation is `max + 1` starting from 0, so the lowest stored value
        is 1. Say so in the module docstring and test both.
  - [ ] **Acceptance boundary:** a table-driven test over at least the eight rejection cases
        above plus the accepting cases, asserting each rejection is the *same* typed failure —
        Decision 5 requires callers be unable to branch on the reason.

- [ ] **Task 2: Extend the conversation port and its adapter with a replay read** (AC: #1, #2)
  - [ ] Add one method to `backend/application/ports/conversation.py`:
        `events_after(connection: Any, *, stream_id: UUID, after: Decimal, limit: int) ->
        tuple[PersistedEventV1, ...] | None`. `None` means the conversation is not visible to
        this site — the same absence-equals-denial shape `timeline()` already uses.
  - [ ] Keep `connection: Any` (`ports/scenario_projection.py:104`). **Do not** copy
        `ports/scenario_catalogue.py:9`'s `from sqlalchemy import Connection`; the guard in
        `tests/architecture/test_conversation_boundaries.py` already covers this file and will
        go red.
  - [ ] `backend/adapters/postgres/conversation.py` — implement it beside `timeline()`. Filter
        on `stream_id` (not `conversation_id`), order by `sequence` **ascending**, bound with
        `limit`. Reuse the existing `_event_from_row`; do not write a second row mapper.
  - [ ] Ascending here, descending in `timeline()`, and both are correct: `timeline()` shows
        the newest window of an unbounded history, replay drains forward from a cursor. Add a
        one-line comment saying so, because the asymmetry looks like a bug.
  - [ ] Reaching a reserved discriminant raises `UnsupportedActivityPayloadError` exactly as
        `timeline()` does. **The stream must not die on it** — Task 4 terminates that one
        connection with a stable state; it does not let a `500` escape mid-body.
  - [ ] **Acceptance boundary:** a `@pytest.mark.postgres` test proves (a) `after=0` returns
        the whole stream in ascending sequence order, (b) `after=max` returns empty, (c) a
        Site B session gets `None` for a Site A conversation, indistinguishable from absence —
        same shape as the existing cases in `tests/test_conversations_postgres.py`.

- [ ] **Task 3: One reusable site-context manager** (AC: #1, #3)
  - [ ] Extract the body of `get_site_context` (`api/deps.py:138-163`) into a
        `@contextmanager site_context(engine, site_id) -> Iterator[Connection]` in the same
        module. `get_site_context` becomes a thin dependency that yields from it. **Behaviour
        must not change** — including the `finally` block's deliberate swallow of the
        `InFailedSqlTransaction` that would otherwise mask a real error.
  - [ ] The stream uses `site_context(...)` directly, per **Decision 1**: one short
        transaction per poll, opened and closed inside `run_in_threadpool`. Never a
        request-lifetime transaction, never a second engine (`_site_context_engine` is
        `lru_cache`d — reuse it).
  - [ ] **Acceptance boundary:** every existing test that exercises `get_site_context` stays
        green unmodified, and a new test asserts a poll leaves no open transaction — take the
        pool's checked-out-connection count before and after and assert it returns to its
        prior value.

- [ ] **Task 4: The SSE endpoint** (AC: #1, #2)
  - [ ] `GET /api/v1/conversations/{conversation_id}/events` in the existing
        `backend/api/routers/conversations.py`. **A GET, under `/conversations`** — Story 2.3's
        Decision 1 still binds: nothing may mount under `/api/v1/scenarios`.
  - [ ] `StreamingResponse(media_type="text/event-stream")` with
        `Cache-Control: no-cache, no-transform` and `X-Accel-Buffering: no`. `no-transform`
        and `X-Accel-Buffering` exist because AD-21 says *"no generic CloudFront buffering
        toggle is assumed"* — Story 6.3 proves the edge, this story must not make that
        story's job harder by omitting the origin-side hints.
  - [ ] Frame format, exactly: `id: <stream_uuid>:<sequence>\n`, `event: <event_type>\n`,
        `data: <compact json of the activity item>\n\n`. The `data:` payload is the **same**
        `ActivityItemOut` shape the timeline returns, including `sequence` **as a string**
        (`api/schemas.py:138`) — one shape, so a client can merge a replayed event and a
        fetched timeline item without a second mapper.
  - [ ] **Build that payload with the router's existing `_activity(event)` helper**
        (`api/routers/conversations.py:33-39`), not a second projection function. A frame and a
        timeline item that drift apart break the client's merge silently.
  - [ ] Heartbeat: `: heartbeat\n\n` — a **comment** frame, every 15 s of stream idleness.
        No `id:`, no `event:`, no `data:`, never persisted, never written to any table.
        Emit one immediately on connect so a proxy sees bytes before any idle timeout.
  - [ ] Replay first (all events after the cursor, drained in bounded batches), then poll for
        new ones on a fixed short interval. Track the last emitted sequence in the generator
        so the heartbeat timer and the poll cursor cannot disagree.
  - [ ] Exit cleanly on `starlette.requests.ClientDisconnect` and on
        `UnsupportedActivityPayloadError`; both end the generator without emitting a partial
        frame. Do not build a second disconnect watchdog (**Decision 2**).
  - [ ] **Acceptance boundary:** `TestClient(...).stream("GET", …)` receives, in order, a
        heartbeat comment, then every replayed frame with a well-formed `id:`; a test asserts
        no heartbeat line contains `id:`; and a test asserts `persisted_event`'s row count is
        unchanged across a stream that emitted heartbeats.

- [ ] **Task 5: Cursor rejection — one code, one body, zero queries** (AC: #2)
  - [ ] Resolve the cursor per **Decision 4**: `Last-Event-ID` header first, then
        `?last_event_id=`, then absent (= replay from 0).
  - [ ] Reject all three AC2 causes with the *same* RFC 7807 response via `api/problems.py`:
        status `400`, one stable code (`stream_cursor_invalid`), fixed title and detail.
        Unknown or cross-site conversation keeps the existing `404 resource_not_found` — that
        is the conversation's own non-disclosure shape, unchanged from Story 2.3.
  - [ ] **Foreign-stream rejection issues no query at all** (**Decision 5**). Compare the
        parsed `stream_id` to the path UUID before touching the database.
  - [ ] "A sequence the stream cannot contain" = anything Task 1 rejects, **plus** a value
        greater than the stream's current maximum sequence. That check reads only the URL's
        own authorized stream, so it discloses nothing. A cursor *equal* to the maximum is
        legal and means "nothing outstanding" — a common, correct state, not an error.
  - [ ] Because the rejection is a non-200 before the body opens, the response is
        `application/problem+json`, not `text/event-stream`. That is what makes the browser
        fail the source permanently instead of retry-looping (**Decision 4**).
  - [ ] **Acceptance boundary:** four HTTP tests — malformed cursor, foreign-stream cursor,
        beyond-maximum cursor, non-integral cursor — each returning byte-identical problem
        bodies; plus a test asserting the foreign-stream path performs zero database calls
        (patch the repository and assert it was never invoked).

- [ ] **Task 6: Publish the contract without pretending it is JSON** (AC: #1, #2)
  - [ ] Declare the route in OpenAPI with a `text/event-stream` 200 response and the
        `ProblemDetailsV1` error statuses, so the endpoint is discoverable and the Gate A
        OpenAPI audit sees it. Run `npm run codegen`; **never hand-edit `schema.d.ts`.**
  - [ ] **This is the one endpoint the frontend does not call through `client.ts`.**
        `openapi-fetch` returns parsed bodies and cannot consume a stream. Add a small
        `conversationEventsUrl(conversationId, cursor?)` helper to
        `frontend/src/api/conversations.ts` that builds the URL from `API_BASE_URL` — so
        there is still exactly one module that knows the base URL, which is the actual rule
        `client.ts`'s docstring is protecting. Document the exception where the helper lives.
  - [ ] **Leave `withCredentials` at its default.** `API_BASE_URL` is the SPA's own origin
        (`frontend/.env.example`; Vite proxies `/api` in both `server` and `preview`), so the
        session cookie rides along same-origin. Setting `withCredentials: true` would only
        matter cross-origin, where it fails anyway — the API leaves `allow_credentials` at
        `False` under D-02 (`api/main.py:248-256`). A cross-origin `VITE_API_BASE_URL` breaks
        this feature; say so in the helper's comment.
  - [ ] **Acceptance boundary:** `npm run typecheck` passes and the new module hand-authors no
        request/response interface.

- [ ] **Task 7: The live timeline hook** (AC: #2)
  - [ ] `frontend/src/hooks/useConversationStream.ts`. It owns: opening the source, holding
        the cursor, merging events, the reconnect state machine, and the polling fallback.
  - [ ] **jsdom has no `EventSource`** — verified absent from jsdom's interface registry at
        this baseline. Take the constructor as an injectable parameter defaulting to
        `globalThis.EventSource`, matching the repo's "dependency overrides in tests"
        convention. A hook that reaches for a global jsdom does not define is untestable, and
        a polyfill dependency is not warranted for one seam.
  - [ ] Cursor persistence: keep the last seen `sequence` **as a string** (never `Number` —
        the whole reason 2.3 serialized it as a string), keyed by conversation ID in
        `sessionStorage`, mirrored in a ref. This is AC2's *"its own persisted cursor"*.
  - [ ] **Seed the first cursor from the timeline's newest item, not from `0`.** The timeline
        read is tail-anchored and capped at 200 (`api/routers/conversations.py:68`), so a
        first connect at `0` would replay the entire history the read deliberately truncated —
        every one of those events arriving as a "new" frame. Connect with no cursor **only**
        when the conversation has no items at all.
  - [ ] The merged list is the timeline window plus what has arrived since; it must stay
        bounded (UX-DR24 — no unbounded growth, no infinite scroll). Cap it at the same window
        the timeline uses and keep the existing "Showing the most recent N activities" copy
        honest.
  - [ ] **Merge by `activity_id`, never by position** (UX-DR6). The same-tab case is the
        proof: `useSendMessage` already invalidates the timeline on success, so the sender's
        own message arrives twice — once from the refetch, once from the stream. Exactly one
        card must render.
  - [ ] Reconnect state machine drives the existing `ReconnectBanner`
        (`components/primitives/ReconnectBanner.tsx`): `disconnected` → `reconnecting` →
        `reconnected`. Do not invent a fourth state — the component has no runtime guard for
        one (`deferred-work.md`, story-1.6 review). **This hook is that component's first
        real caller**; its own Dev Notes predicted exactly this.
  - [ ] On `error`: `close()` the dead source and re-establish from the persisted cursor
        (**Decision 4**). After a bounded number of consecutive failures, fall back to
        **labelled** polling — TanStack Query `refetchInterval` on the existing
        `useConversationTimeline`, with visible copy saying updates are delayed. AC2 requires
        the fallback; EXPERIENCE.md's Runs row fixes the wording rule (*"labels delayed
        updates"*). Silent polling is a failure of this AC.
  - [ ] **Acceptance boundary:** five tests against a stub `EventSource` — a replayed event
        already present renders one card; a rejected connection re-establishes with the
        stored cursor in the query string; repeated failures switch to labelled polling and
        the label is visible; the banner walks all three states; and the stored cursor
        survives a remount.

- [ ] **Task 8: Prove the transport, not just the handler** (AC: #1, #2)
  - [ ] A test that streams **through the real app** (`TestClient(app)`, both
        `@app.middleware("http")` layers active) and asserts frames arrive **incrementally** —
        that the first frame is readable before the generator has finished. Decision 2 is
        based on reading Starlette's `BaseHTTPMiddleware.body_stream()`; this test is what
        keeps it true. If it ever fails, the feature is dead and the cause will be invisible
        without it.
  - [ ] A test that the unauthenticated case is rejected by the existing middleware
        (`401 authentication_required`) before any stream opens — the response must be
        `application/problem+json`, never an empty `text/event-stream`.
  - [ ] No CSRF test is needed and none should be added: `GET` is not in `_UNSAFE_METHODS`
        (`api/main.py:160`). `EventSource` cannot send `X-CSRF-Token`, which is precisely why
        this endpoint has to be a `GET`.
  - [ ] **Acceptance boundary:** all three above green, and
        `test_gate_a_mutation_audit.py::test_gate_a_scenario_openapi_surface_is_get_only`
        still green and **unmodified**.

- [ ] **Task 9: The NFR35 reconnect-replay measurement** (AC: #3)
  - [ ] `@pytest.mark.postgres` test in `backend/tests/test_postgres_integration.py`, modelled
        exactly on `test_nfr35_exact_evidence_targets_meet_two_second_threshold` there — the
        established shape, including the `print("…MEASUREMENTS=" + json.dumps(...))` marker
        that `scripts/regenerate_evidence.py` parses.
  - [ ] Protocol, verbatim from `requirements-inventory.md`'s normative table: largest Gate A
        fixture at full committed size (`sample_tiny_input_more_tm.json`, `v1`); warm process
        and warm pool; **one discarded warm-up**; **three consecutive runs, every one must
        pass**; threshold **5000 ms**.
  - [ ] Clock boundary is AC3's, not Story 1.4's: **reconnect request receipt → delivery of
        the last outstanding persisted event.** Start the clock at the request, stop it when
        the test reads the final replayed frame off the stream, then break and close.
  - [ ] *"The largest Gate A replay backlog"* names no number, so **fix one and record it**:
        seed the stream with at least **200** persisted events — the timeline read cap
        (`api/routers/conversations.py:68`), i.e. the largest number of activities the product
        will render at once. Reconnect with a cursor of `0` (the stalest possible) so the whole
        backlog replays. Write the chosen count into the evidence file's `protocol` block; do
        not leave it implied by the measurement array's length alone.
  - [ ] Generate `evidence/story-2.4/nfr35-sse-reconnect-replay.json`. **Follow
        `docs/EVIDENCE-CONVENTION.md` exactly: commit code → confirm `git status --porcelain`
        is empty → measure → generate through `scripts/evidence_binding.resolve_bindings()` →
        commit the evidence separately.** Never hand-type it, and never copy Story 1.4's file
        as a template — that habit is what produced four unreproducible bindings (the
        convention doc's own table).
  - [ ] This is a **new** evidence file, so `regenerate_evidence.py` cannot bootstrap it — that
        script rewrites bindings on files that already exist. Follow `backend/evals/report.py`'s
        `write_evaluation_report` instead: resolve bindings first, then write. Afterwards, add
        the file to `EVIDENCE_FILES` and a marker to `_MEASUREMENT_MARKERS` in
        `regenerate_evidence.py` so it is re-bindable like every other file.
  - [ ] **Do not register this in the Gate A registry** (`scripts/gate_a_checks.py`). Gate A is
        Epic 1's gate and is closed; NFR35's aggregate is a **Gate B** row (`epics.md:1522`).
        The repo-wide `test_evidence_convention.py` sweep picks the new file up automatically —
        that is the coverage that matters here.
  - [ ] **Acceptance boundary:** three runs all ≤ 5000 ms with the backlog recorded, the file
        fully bound with `working_tree_dirty: false`, and
        `uv run --frozen pytest tests/test_evidence_convention.py` green.

- [ ] **Task 10: Ledger hygiene** (AC: none — housekeeping, do not skip)
  - [ ] Correct the `deferred-work.md` *"Deferred from: story-2-3 creation (2026-08-10)"* entry
        in place: strike the false premise that Story 2.4 adds a new `application/ports/`
        module, record **why** (Decision 3 — the replay read belongs on the existing
        `ConversationRepository` under AD-22), and restate the owner as *"the next story that
        modifies `ScenarioCatalogueReader` or its adapter for any reason."* Follow the
        strike-through-and-correct-in-place format the `alembic.ini` entry already uses; do not
        delete the item and do not close it.
  - [ ] Leave `ALLOWED_LEAKS` in `tests/architecture/test_conversation_boundaries.py` exactly
        as it is. `test_every_allowed_leak_still_exists_and_still_leaks` will go red if anyone
        half-fixes the leak, which is the behaviour we want.
  - [ ] The `translate.py:61-105` silent-drop item stays open and untouched — Story 2.3
        judged it live in **2.5**, and that judgement is unchanged here: this story still
        executes no turn and rehydrates no `AgentTurnV1`.

- [ ] **Task 11: Full regression gate** (AC: #1, #2, #3)
  - [ ] Backend: `uv run --frozen pytest`; `uv run --frozen pytest -m postgres` (Docker
        PostgreSQL 18 via `docker-compose.yml`).
  - [ ] `alembic check` **from the repository root**: `uv run --project backend alembic check`
        → *"No new upgrade operations detected."* From `backend/` it fails with
        `No 'script_location' key found in configuration` — a working-directory mistake that
        reads like a missing config. `deferred-work.md` carries the corrected measurement
        table; **do not synthesize a temporary alembic config.**
  - [ ] **This story adds no migration.** It only reads `persisted_event`, and `GRANT SELECT`
        is already in place from `a4f92d7c8e31`. If you find yourself writing a revision, stop
        — something has gone wrong.
  - [ ] Frontend: `npm run codegen`, `npm run typecheck`, `npm run lint`, `npm test`,
        `npm run build`, `npm run test:e2e` (build-first since Story 2.2).
  - [ ] **Re-run Gate A and report by name.** AR28 binds every story. Regenerate
        `evidence/story-1.11/gate-a-readiness-report.json` per the evidence convention and
        confirm `gate_a_passed` still reads `true`.
  - [ ] **Re-derive baselines at the start rather than trusting these.** Recorded at
        `baseline_commit` (`7b8df5a`, Story 2.3 `done` and merged): backend **545 passed /
        7 deselected**; postgres **27 passed**; live **7 skipped** (no API key); frontend
        **54 files / 307 tests**; e2e **46 passed**; `alembic check` zero diff;
        `gate_a_passed: true`.
  - [ ] **Acceptance boundary:** every suite green at its re-derived baseline plus this
        story's new tests, Gate A still `true`, and AC3's evidence file bound and passing.

## Dev Notes

### What this story is, and what it is not

It is: one cursor contract, one port method, one adapter query, one `GET` streaming endpoint,
one React hook, and one measured threshold.

It is **not**:

| Not this | Owned by | Why not here |
|---|---|---|
| Any new event *producer* | Stories 2.5, 3.5 | see the honesty note below |
| Executing an agent turn | Story 2.5 | Story 2.3's Decision 2 still stands |
| Run-progress events, the worker, job leases | Epic 3 | Story 3.5 owns the run stream and its own NFR35 threshold |
| Idempotency keys | Epic 3 | AD-8 does not bind FR-4 |
| The CloudFront/ALB edge proof | Story 6.3 | AD-21's end-to-end proxy test is that story's AC |
| Evidence navigation, grounding | Stories 2.7, 2.8 | no agent response exists yet |
| A migration of any kind | — | the tables and grants already exist |

### The honesty problem, stated plainly

**The only event type that exists is `planner_message_accepted`.** No agent runs; nothing
transitions out of `agent_queued`. So the live stream's only real content is a planner message
accepted by *another* tab or session on the same conversation — plus the sender's own message
echoing back beside the mutation's refetch, which is exactly what makes the AC2 dedup test
meaningful rather than theoretical.

That is a real, demonstrable, testable feature and it is what the ACs ask for. **Do not dress
it up.** UX-DR5 forbids anthropomorphic waiting; EXPERIENCE.md's Chat row requires literal
persisted state. No typing indicator, no "Agent is working…", no fabricated progress frames,
and no placeholder event types emitted to make the stream look busy.

### The six traps, ranked by how quietly they fail

1. **`Depends(get_site_context)` on the SSE route.** Passes every test, works perfectly for one
   developer, and takes the application down at fifteen concurrent tabs. Decision 1.
2. **Comparing sequences as strings.** `"10" > "9"` is `false`; a client resuming at sequence 9
   silently loses everything from 10 on. Task 1.
3. **Synchronous SQLAlchemy awaited inside the async generator.** Every poll freezes the event
   loop for every other client. Symptom is "the app got slow", cause is invisible. Decision 1.
4. **Querying the foreign stream before rejecting it.** Looks defensive, *is* the disclosure.
   Decision 5.
5. **A 200 response carrying an error frame for a bad cursor.** Browser retries forever with
   the same poisoned header. Decision 4.
6. **Reaching for `EventSource` in a jsdom test.** Fails loudly, but only once someone writes
   the test — and the temptation is then to skip the test rather than inject the seam. Task 7.

### Existing conventions to match, not reinvent

| Need | Copy the pattern from |
|---|---|
| Versioned contract dataclass, `V1`, `schema_version` | `backend/application/contracts/persisted_event.py` |
| Port as `Protocol`, `connection: Any` | `backend/application/ports/conversation.py` — **not** `scenario_catalogue.py` |
| Bounded ordered event read, row → envelope mapping | `backend/adapters/postgres/conversation.py:103-135, 271-284` |
| Router shape, `_PROBLEM_RESPONSES`, `Depends` | `backend/api/routers/conversations.py` |
| RFC 7807 responses | `backend/api/problems.py` |
| Threadpool offload of sync DB work | `backend/api/deps.py:125`, `backend/api/main.py:198` |
| NFR35 measurement test + marker print | `backend/tests/test_postgres_integration.py` (both `test_nfr35_*`) |
| New evidence file generated, not templated | `backend/evals/report.py:write_evaluation_report` |
| Postgres test fixtures | `backend/conftest.py:83-101` |
| TanStack Query hook | `frontend/src/hooks/useConversationTimeline.ts` |
| Activity dedup by ID | `frontend/src/features/chat/ActivityTimeline.tsx` and its test |
| Reconnect states | `frontend/src/components/primitives/ReconnectBanner.tsx` |
| Error status extraction | `frontend/src/lib/errors.ts:getErrorStatus` |
| Absolute backend imports | every module: `from application.contracts… import …` |

### Latest technical information (verified 2026-08-11 against the pinned versions)

**Starlette (via FastAPI, repository lock).** Read from Starlette's own source at this
baseline, not from memory:

- `BaseHTTPMiddleware`'s internal `body_stream()` yields each response chunk as it arrives and
  never accumulates the body — so both `@app.middleware("http")` layers pass a stream through
  unbuffered. Release note 0.38.3 also fixed `BaseHTTPMiddleware` polling for disconnects via
  `StreamingResponse`. Task 8 asserts the behaviour rather than relying on it.
- `StreamingResponse` under ASGI spec ≥ 2.4 catches the server's `OSError` and raises
  `starlette.requests.ClientDisconnect`; under < 2.4 it races `stream_response` against
  `listen_for_disconnect` in a collapsing task group. Either way, letting the generator exit on
  `ClientDisconnect` is the supported pattern — do not hand-roll a disconnect watchdog.
- Starlette's docs list `EventSourceResponse` only as a **third-party** response
  (`sse-starlette`). It is not part of the framework, and Decision 2 declines to add it.

**`EventSource` (WHATWG HTML).** Auto-reconnects on network failure and replays the last seen
`id:` via the `Last-Event-ID` header. On a non-200 status or a non-`text/event-stream`
content type it **fails the connection permanently** — `error` fires, `readyState` becomes
`CLOSED`, no retry. It cannot set request headers, which is why the cursor is also accepted as
a query parameter and why the endpoint is a `GET` with no CSRF requirement.

**PostgreSQL / SQLAlchemy 2.0.51.** `persisted_event.sequence` is `Numeric(38, 0,
asdecimal=True)` → Python `Decimal`, scale 0. `Decimal("1.5")` is representable in Python but
is not a value the column can hold — Task 1 rejects it as *"a sequence the stream cannot
contain"*, which is AC2's exact phrase. Keep the string serialization on the wire
(`api/schemas.py:138`): a JSON number is an IEEE-754 double in the browser and would corrupt
the cursor.

**Why polling and not `LISTEN`/`NOTIFY`.** `LISTEN` requires a dedicated connection held open
per listener for the life of the subscription — the exact resource profile Decision 1 exists to
avoid, one layer down. A short bounded poll against an indexed
`(stream_id, sequence)` unique constraint is the right shape at this scale, and it is the shape
Story 3.5 will reuse. Record the chosen interval in the router; do not make it configurable
without a requirement asking for it.

### Project Structure Notes

- **New (backend):** `backend/application/contracts/stream_cursor.py`, tests for it, and the
  NFR35 measurement test.
- **Modified (backend):** `backend/application/ports/conversation.py` (one method),
  `backend/adapters/postgres/conversation.py` (one query), `backend/api/deps.py`
  (`site_context` extraction), `backend/api/routers/conversations.py` (the stream endpoint),
  `backend/api/schemas.py` if the frame payload needs a name,
  `backend/scripts/regenerate_evidence.py` (register the new evidence file),
  `_bmad-output/implementation-artifacts/deferred-work.md` (Task 10).
- **New (frontend):** `frontend/src/hooks/useConversationStream.ts` and its test.
- **Modified (frontend):** `frontend/src/api/conversations.ts` (URL helper),
  `frontend/src/features/chat/ChatView.tsx` (banner + labelled-polling state),
  `frontend/src/api/schema.d.ts` (**generated only**), `frontend/openapi.json` (generated).
- **New (evidence):** `evidence/story-2.4/nfr35-sse-reconnect-replay.json`.
- **Not modified (verify a zero-line diff):** `backend/agent/**`,
  `backend/application/contracts/{activity,persisted_event,agent_runtime}.py`,
  `backend/application/use_cases/accept_turn.py`, `backend/llm/**`, `backend/services/**`,
  `backend/domain/**`, `backend/engine/**`, `backend/migrations/**`,
  `backend/tests/test_gate_a_mutation_audit.py`.
- **Chat code stays in `frontend/src/features/chat/`.** `frontend/src/test/
  scenarioDataBoundaries.test.ts` audits `features/scenario-data/` for mutation affordances;
  keep this feature outside its scope, as Story 2.3 did.
- **Architecture tests stay at `backend/tests/architecture/`**, not the spine's root-level
  path — the variance carried since Story 2.1 (pytest runs from `backend/` with
  `testpaths = ["tests"]`).

### Anti-patterns for this story

- **Do not take `Depends(get_site_context)` on the streaming route.** Decision 1.
- **Do not add `sse-starlette`, `starlette-sse`, or any other new dependency.** Decision 2.
- **Do not create a new `application/ports/` module** for the event stream. Decision 3.
- **Do not query the database for a stream named in a rejected `Last-Event-ID`.** Decision 5.
- **Do not compare sequences as strings**, and do not "simplify" the cursor to an `int`.
- **Do not persist heartbeats**, give them an `id:`, or emit them as `event:` frames.
- **Do not write a migration.** The tables and the `SELECT` grant already exist.
- **Do not emit a placeholder or synthetic event** to make the stream look active, and do not
  add a typing indicator, animated ellipsis, or ETA (UX-DR5).
- **Do not poll silently** when the stream is unavailable — AC2 requires the fallback be
  *labelled*.
- **Do not fix `application/ports/scenario_catalogue.py` here**, and do not delete its
  `ALLOWED_LEAKS` entry. Task 10.
- **Do not hand-type the evidence file** or copy Story 1.4's as a template.
- **Do not tune the NFR35 threshold, shrink the backlog, or reduce the run count** to make the
  measurement pass. A miss blocks acceptance and is a valid, honest outcome to report —
  the same posture Story 1.11 held with `gate_a_passed: false`.
- **Do not weaken Gate A.** If a change breaks `ScenarioDataParity.test.tsx`,
  `scenarioDataBoundaries.test.ts`, `legacyReachability.test.ts`, or
  `test_gate_a_mutation_audit.py`, fix the change.
- **Do not add a CI workflow.** `.github/` still does not exist; pipeline ownership remains out
  of scope.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.4] — story statement and all three
  acceptance criteria, verbatim
- [Source: epics.md, *Additional Requirements*] — AR21 (persisted event fields, SSE ID format,
  greater-sequence replay, 15-second non-persisted heartbeats through CloudFront/ALB), AR13
  (persisted SSE from FastAPI, one `openapi-fetch` client, RFC 7807), AR26 (structural seed),
  AR27 (lock each planned dependency only at its implementation gate), AR28 (no later gate
  weakens an earlier one)
- [Source: epics.md, *UX Design Requirements*] — UX-DR6 (durable timeline, dedupe replay by
  event identity), UX-DR20 (non-disclosing exception states), UX-DR5 (no anthropomorphic
  waiting), UX-DR24 (no unbounded scroll), UX-DR25 (distinct Chat states)
- [Source: epics.md:1522, *Release Gate*] — NFR35's four thresholds are a **Gate B** row, not
  Gate A
- [Source: requirements-inventory.md, *NFR35 measurement protocol (normative)*] — fixture
  scale, environment, warm state, one discarded warm-up, three consecutive runs with an
  all-runs rule, clock boundaries, evidence format; and the Story 1.4 / 1.5 / 2.4 / 3.5
  allocation
- [Source: ARCHITECTURE-SPINE.md, AD-21 lines 210-214] — `PersistedEventV1` fields, SSE `id` =
  `<stream_uuid>:<sequence>`, `Last-Event-ID` must match the URL stream, replay returns only
  greater sequences, 15-second heartbeat comments with no ID and no persistence, and the
  no-assumed-buffering-toggle rule
- [Source: ARCHITECTURE-SPINE.md, AD-26 lines 241-245] — AD-21 owns reconnect replay ≤ 5 s
  measured to client receipt, on the CI reference environment against the largest Gate A
  fixture; a threshold miss blocks acceptance of its owning story
- [Source: ARCHITECTURE-SPINE.md, AD-6 lines 78-82] — persisted monotonic event sequences feed
  SSE replay; neither process memory nor the stream is authoritative
- [Source: ARCHITECTURE-SPINE.md, AD-22 line 220] — the conversation aggregate owns its
  messages, agent runs, and events (Decision 3's evidence)
- [Source: ARCHITECTURE-SPINE.md, AD-23 line 226] — forced RLS, transaction-local trusted site
  context (Decision 1's constraint)
- [Source: ARCHITECTURE-SPINE.md, AD-4 line 70] — no scenario-source mutation route; why
  nothing mounts under `/api/v1/scenarios`
- [Source: ARCHITECTURE-SPINE.md, *Stack* lines 262-290] — `sse-starlette` is absent
  (Decision 2's evidence)
- [Source: ux-designs/…/EXPERIENCE.md:83, 107, 120-125] — conversation timeline reconstructs by
  persisted event identity; reconnect banner states; the Chat and Runs stale/reconnect columns,
  including *"If event stream is down, polling/status refresh … labels delayed updates"*
- [Source: ux-designs/…/EXPERIENCE.md, *Flow 5 — Reconnect and recover durable work*] — the
  reconnect journey and its *"stream replay remains unavailable → labelled delayed-update
  polling"* failure path
- [Source: _bmad-output/implementation-artifacts/2-3-create-and-revisit-durable-conversations.md:63-75]
  — Story 2.3's Decision 3 table handing SSE, `Last-Event-ID`, replay, heartbeats, and the
  NFR35 measurement to this story
- [Source: backend/api/deps.py:133-163] — `_site_context_engine` and `get_site_context`; the
  request-lifetime transaction Decision 1 refuses to reuse
- [Source: backend/api/main.py:142-238, 250-266] — both `@app.middleware("http")` layers,
  `_UNSAFE_METHODS` (GET is exempt from CSRF), `allow_credentials` left at `False`
- [Source: backend/api/routers/conversations.py] — the router this story extends, and
  `ActivityItemOut`'s string `sequence`
- [Source: backend/adapters/postgres/conversation.py:103-135, 249-284] — `timeline()`'s
  tail-anchored window, `UnsupportedActivityPayloadError`, `_event_from_row`
- [Source: backend/adapters/postgres/schema.py:310-345] — `persisted_event`'s
  `Numeric(38, 0)` sequence, `uq_persisted_event_stream_sequence`,
  `ck_persisted_event_stream_is_conversation`, and the existing indexes
- [Source: backend/migrations/versions/a4f92d7c8e31_add_durable_conversations.py] — the
  existing `GRANT SELECT`; why this story needs no migration
- [Source: backend/tests/test_postgres_integration.py, both `test_nfr35_*`] — the measurement
  test shape and the `MEASUREMENTS=` marker `regenerate_evidence.py` parses
- [Source: backend/scripts/regenerate_evidence.py:63-79, 116-125] — `EVIDENCE_FILES` and
  `_MEASUREMENT_MARKERS`, the two registries Task 9 extends
- [Source: backend/evals/report.py:43-95] — `write_evaluation_report`: resolve bindings first,
  then write; the pattern for a *new* evidence file
- [Source: docs/EVIDENCE-CONVENTION.md] — commit → clean tree → measure → generate → commit
  evidence separately; the repo-wide sweep; the monotone-rule principle
- [Source: frontend/src/components/primitives/ReconnectBanner.tsx] — the three-state banner
  this story is the first real caller of
- [Source: frontend/src/api/client.ts:27-31, frontend/src/lib/env.ts, frontend/.env.example,
  frontend/vite.config.ts:12-37] — `credentials: "include"`, the single `API_BASE_URL`, and the
  same-origin proxy that makes the session cookie reach an `EventSource`
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] — the 2026-07-24
  threadpool-offload item (Decision 1), the story-2-3-creation `scenario_catalogue` item and
  its false premise about this story (Decision 3, Task 10), the story-1.6 `ReconnectBanner`
  runtime-guard item (Task 7), and the still-open `translate.py` item (Task 10)
- [Source: backend/tests/architecture/test_conversation_boundaries.py] — `GUARDED`,
  `ALLOWED_LEAKS`, and `test_every_allowed_leak_still_exists_and_still_leaks`
- [Source: /kludex/starlette — middleware/base.py `body_stream()`, responses.py
  `listen_for_disconnect` / `ClientDisconnect`, docs/responses.md, release notes 0.38.3] — the
  streaming and disconnect facts quoted in *Latest technical information*

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List

## Change Log

| Date | Change |
|---|---|
| 2026-08-11 | Story created on branch `story/2-4-replay-conversation-events-live`. Five creation-time decisions recorded: the SSE route must not hold a request-lifetime site transaction; SSE is hand-rolled on `StreamingResponse` rather than adding `sse-starlette` under AR27; the replay read extends the existing `ConversationRepository` rather than creating a new port (which falsifies the deferred-work ledger's premise for assigning the `scenario_catalogue` AD-1 leak here); a rejected cursor returns a non-200 so `EventSource` fails permanently and the client re-establishes from its own persisted cursor; and non-disclosure is guaranteed by issuing zero queries on a foreign-stream cursor. |
