"""Per-turn expectations: authored checks a reply must meet, graded one by one.

A turn's `expect` list replaces the holistic judge for that turn (under a
`typesafe:` judge). Anything exact is a CODE check over the reply's visible text,
its activity, or the saved draft. Only what code cannot decide is a JUDGE check:
one narrow yes/no Jev question that sees the user's message, the reply, and the
few facts it names -- never the transcript or a global rubric.

Expected values are BINDINGS the harness captures from real application state
as the conversation runs (the saved draft, the run result, the approval), never
from the agent's words. The agent chooses which worker to exclude, so later
turns are checked against what the draft actually holds.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from evals.live_conversations.protocol import IncompleteConversationRun

#: Values the harness binds, and where (see `Bindings.capture_*`).
BINDING_NAMES = frozenset({
    'scenario_name', 'baseline_id', 'task_names',
    'excluded_worker', 'excluded_worker_id', 'excluded_task', 'excluded_task_id',
    'candidate_id', 'solver_status', 'assignment_count',
    'promoted_baseline_id', 'approval_id',
    'worker_count', 'worker_names', 'indirect_task', 'indirect_task_id',
    'first_task', 'first_task_id',
})
#: Facts a judge question may name; each is built from bindings or this turn.
FACT_NAMES = frozenset({'tasks', 'candidate_rows', 'events', 'draft', 'excluded_worker',
                        'worker_count', 'workers', 'locks'})
CODE_CHECKS = frozenset({
    'mentions', 'mentions_all', 'mentions_any', 'mentions_none', 'activity_is',
    'activity_field_equals', 'draft_has', 'draft_preserves_locks', 'names_assigned_pair',
    'draft_matches_turn', 'claims_metric', 'draft_has_roster_lock', 'each_item_mentions',
    'draft_updates_turn', 'draft_state_is', 'draft_constraint_count', 'draft_is_new',
    'tool_called',
})
#: The draft lifecycle's vocabulary (`application/contracts/proposal.py`):
#: `draft_state_is` takes "<state>" or "<state>/<ended_by>".
DRAFT_STATES = frozenset({'active', 'rejected', 'applied'})
DRAFT_ENDED_BY = frozenset({'planner', 'assistant', 'system'})
#: Checks that can only fail by the reply doing something wrong; a turn needs at
#: least one check that requires the reply to DO something (tau-bench: a
#: do-nothing agent passes every "must not").
NEGATIVE_CHECKS = frozenset({'mentions_none', 'each_item_mentions'})

#: `when`: the reply kind an expectation applies to. A turn with more than one
#: valid ACTION (save a draft, or ask first) grades each by its own evidence --
#: the persisted draft by code, prose by a judge -- and skips the other's checks.
WHEN = frozenset({'draft', 'not_draft'})

#: P(wanted answer) a judge check needs to pass; under FAIL_P it fails.
PASS_P = 0.70
FAIL_P = 0.30

_TEMPLATE = re.compile(r'\{([a-z_]+)\}')


@dataclass(frozen=True)
class Expectation:
    id: str
    check: str
    value: object = None
    values: tuple = ()
    activity: str | None = None
    field: str | None = None
    kind: str | None = None
    worker: str | None = None
    task: str | None = None
    max_hours: float | None = None
    n: int | None = None
    factor: float | None = None
    metric: str | None = None
    family: str | None = None
    turn: int | None = None
    question: str | None = None
    want: bool | None = None
    facts: tuple[str, ...] = ()
    when: str | None = None
    fact_group: str | None = None

    @property
    def is_judge(self) -> bool:
        return self.check == 'judge'

    @property
    def is_positive(self) -> bool:
        return self.want is True if self.is_judge else self.check not in NEGATIVE_CHECKS


def _templates(value) -> set[str]:
    if isinstance(value, str):
        return set(_TEMPLATE.findall(value))
    if isinstance(value, (list, tuple)):
        return set().union(*(_templates(item) for item in value)) if value else set()
    return set()


#: Per check: (required fields, optional fields). Any other field set on an
#: expectation is refused -- an authoring slip must not quietly weaken a check.
_FIELDS = {
    'mentions': ({'value'}, set()),
    'mentions_all': ({'value'}, set()),
    'each_item_mentions': ({'value'}, set()),
    'mentions_any': ({'values'}, set()),
    'mentions_none': ({'values'}, set()),
    'activity_is': ({'activity'}, set()),
    'activity_field_equals': ({'field', 'value'}, set()),
    'draft_has': ({'kind'}, {'worker', 'task', 'max_hours', 'n', 'factor'}),
    'draft_has_roster_lock': ({'task'}, set()),
    'claims_metric': ({'metric'}, {'task', 'family'}),
    'draft_preserves_locks': (set(), set()),
    'names_assigned_pair': (set(), set()),
    'draft_matches_turn': ({'turn'}, set()),
    'draft_updates_turn': ({'turn'}, set()),
    'draft_state_is': ({'value'}, set()),
    'draft_constraint_count': ({'n'}, set()),
    'draft_is_new': (set(), set()),
    'tool_called': ({'value'}, {'fact_group'}),
    'judge': ({'question', 'want'}, {'facts'}),
}
#: Bindings that hold a list: only `mentions_all` may take one whole.
LIST_BINDINGS = frozenset({'task_names', 'worker_names'})
LIST_CHECKS = frozenset({'mentions_all', 'each_item_mentions'})
#: A bulleted or numbered list item, as the visible text keeps it.
_LIST_ITEM = re.compile(r'^(?:[-*•]|\d+[.)])\s')
_FACT_REFERENCE = re.compile(r'`facts\.([a-z_]+)')


def parse_expectation(raw: dict) -> Expectation:
    if not isinstance(raw, dict):
        raise ValueError('an expectation must be an object')
    for name in ('id', 'check'):
        if not isinstance(raw.get(name), str) or not raw[name].strip():
            raise ValueError(f'an expectation needs a non-empty string {name!r}')
    unknown = set(raw) - set(Expectation.__dataclass_fields__)
    if unknown:
        raise ValueError(f'unknown expectation fields: {sorted(unknown)}')
    data = dict(raw)
    for name in ('values', 'facts'):
        if name in data:
            if not isinstance(data[name], list) or not all(isinstance(i, str) and i for i in data[name]):
                raise ValueError(f"expectation {raw['id']!r}: {name} must be a list of strings")
            data[name] = tuple(data[name])
    expectation = Expectation(**data)
    validate_expectation(expectation, present=set(raw) - {'id', 'check', 'when'})
    return expectation


def validate_expectation(expectation: Expectation, present: set[str] | None = None) -> None:
    where = f'expectation {expectation.id!r}'
    if expectation.check not in _FIELDS:
        raise ValueError(f'{where}: unknown check {expectation.check!r}')
    required, optional = _FIELDS[expectation.check]
    if present is not None:
        missing, extra = required - present, present - required - optional
        if missing:
            raise ValueError(f'{where}: {expectation.check} needs {sorted(missing)}')
        if extra:
            raise ValueError(f'{where}: {expectation.check} does not take {sorted(extra)}')
    for name in ('value', 'activity', 'field', 'kind', 'worker', 'task', 'question', 'metric', 'family',
                 'fact_group'):
        value = getattr(expectation, name)
        if value is not None and (not isinstance(value, (str, int, float)) or isinstance(value, bool)
                                  or (isinstance(value, str) and not value.strip())):
            raise ValueError(f'{where}: {name} must be a non-empty string or number')
    if expectation.turn is not None and (isinstance(expectation.turn, bool)
                                         or not isinstance(expectation.turn, int) or expectation.turn < 1):
        raise ValueError(f'{where}: turn must be a positive turn number')
    for name in ('max_hours', 'n', 'factor'):
        number = getattr(expectation, name)
        if number is not None and (isinstance(number, bool) or not isinstance(number, (int, float))):
            raise ValueError(f'{where}: {name} must be a number')
    if expectation.when is not None and expectation.when not in WHEN:
        raise ValueError(f'{where}: when must be one of {sorted(WHEN)}')
    if expectation.check == 'draft_state_is':
        state, _, ended_by = str(expectation.value).partition('/')
        if state not in DRAFT_STATES or (ended_by and ended_by not in DRAFT_ENDED_BY)                 or str(expectation.value).endswith('/'):
            raise ValueError(f'{where}: draft_state_is takes <state>[/<ended_by>] with state in '
                             f'{sorted(DRAFT_STATES)} and ended_by in {sorted(DRAFT_ENDED_BY)}')
    if expectation.check == 'draft_constraint_count' and (
            not isinstance(expectation.n, int) or isinstance(expectation.n, bool) or expectation.n < 0):
        raise ValueError(f'{where}: draft_constraint_count needs a whole number n')
    if expectation.is_judge and not isinstance(expectation.want, bool):
        raise ValueError(f'{where}: want must be true or false')
    names = set().union(*(_templates(getattr(expectation, name)) for name in
                          ('value', 'values', 'worker', 'task', 'question')))
    if names - BINDING_NAMES:
        raise ValueError(f'{where}: unknown bindings {sorted(names - BINDING_NAMES)}')
    if expectation.check not in LIST_CHECKS and names & LIST_BINDINGS:
        raise ValueError(f'{where}: a list binding {sorted(names & LIST_BINDINGS)} needs mentions_all')
    if set(expectation.facts) - FACT_NAMES:
        raise ValueError(f'{where}: unknown facts {sorted(set(expectation.facts) - FACT_NAMES)}')
    if expectation.is_judge:
        referenced = set(_FACT_REFERENCE.findall(expectation.question))
        if referenced - set(expectation.facts):
            raise ValueError(f'{where}: the question uses facts it does not declare: '
                             f'{sorted(referenced - set(expectation.facts))}')


def validate_turn_expectations(expectations: tuple[Expectation, ...],
                               position: int | None = None) -> None:
    """`position` is the turn's own 1-based number: a check may only look back."""
    ids = [expectation.id for expectation in expectations]
    if len(ids) != len(set(ids)):
        raise ValueError(f'duplicate expectation ids: {ids}')
    if expectations and not any(expectation.is_positive for expectation in expectations):
        raise ValueError('a turn with expectations needs at least one positive expectation')
    # Each branch must require the reply to DO something, or a do-nothing reply
    # of the other kind passes on its must-nots alone.
    if any(expectation.when for expectation in expectations):
        for branch in sorted(WHEN):
            if not any(expectation.is_positive and expectation.when in (None, branch)
                       for expectation in expectations):
                raise ValueError(f'a turn graded by reply kind needs a positive expectation '
                                 f'that applies when the reply is {branch}')
    for expectation in expectations:
        if position is not None and expectation.turn is not None and expectation.turn >= position:
            raise ValueError(f'expectation {expectation.id!r}: turn {expectation.turn} is not an '
                             f'earlier turn than {position}')


class Unbound(Exception):
    """An expectation names a value the harness never observed."""

    def __init__(self, name):
        super().__init__(name)
        self.name = name


@dataclass
class Bindings:
    """Set-once values from application state, plus what happened, in order."""
    values: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    #: The LAST saved draft as the user saw it -- constraint descriptions, the
    #: application's consequence line, its id (not set-once: a later turn asks
    #: about the draft as it now stands).
    draft: dict | None = None
    #: The turn being graded; each binding remembers the turn that bound it.
    turn: int = 0
    bound_at: dict = field(default_factory=dict)
    #: Each draft turn's saved draft identity, by turn number:
    #: {proposal_id, version_ordinal}. `draft` alone cannot say which proposal
    #: an earlier turn saved.
    drafts: dict = field(default_factory=dict)

    def bind(self, name: str, value) -> None:
        if name not in BINDING_NAMES:
            raise KeyError(name)
        if value is not None and name not in self.values:
            self.values[name] = value
            self.bound_at[name] = self.turn

    def as_of(self, turn: int) -> 'Bindings':
        """Only what was bound BEFORE `turn`: a check that a later draft still
        holds an earlier exclusion must not read that exclusion from itself."""
        earlier = {name: value for name, value in self.values.items() if self.bound_at[name] < turn}
        return Bindings(values=earlier, events=list(self.events), draft=self.draft, turn=turn,
                        bound_at={name: self.bound_at[name] for name in earlier},
                        drafts={n: entry for n, entry in self.drafts.items() if n < turn})

    def get(self, name: str):
        if name not in self.values:
            raise Unbound(name)
        return self.values[name]

    def capture_start(self, overview: dict, tasks: list[dict], workers: list[dict] = (),
                      demand: list[dict] = ()) -> None:
        self.bind('scenario_name', overview.get('scenario_name'))
        self.bind('baseline_id', overview.get('baseline_schedule_version'))
        self.bind('task_names', [task['name'] for task in tasks if task.get('name')] or None)
        if workers:
            self.bind('worker_count', len(workers))
            self.bind('worker_names', [worker['name'] for worker in workers if worker.get('name')] or None)
        # Only when exactly one task carries indirect demand: "which task" then
        # has one right answer.
        indirect = {_key(row.get('task_id')) for row in demand if row.get('family') == 'indirect'}
        if len(indirect) == 1:
            task = _task_by_key(tasks, indirect.pop())
            if task:
                self.bind('indirect_task_id', _key(task['record_id']))
                self.bind('indirect_task', task.get('name'))

    def capture_claims(self, activity: dict, tasks: list[dict]) -> None:
        """The task the conversation settles on: the first grounded outbound
        required-volume claim ("the first task in that demand"). Its value is
        already checked by the independent oracle (`facts.verify_claim`)."""
        for claim in _claims(activity):
            arguments = claim.get('arguments') or {}
            if claim.get('metric') == 'required_demand_volume' and arguments.get('family') == 'outbound':
                task = _task_by_key(tasks, _key(arguments.get('task_id')))
                if task:
                    self.bind('first_task_id', _key(task['record_id']))
                    self.bind('first_task', task.get('name'))
                return

    def capture_draft(self, draft: dict | None, workers_by_id: dict, tasks_by_id: dict) -> None:
        if not draft:
            return
        ordinal = draft.get('version_ordinal')
        # Every fresh read fills it; a draft without one is a contract break in
        # the application, not something the model did.
        if type(ordinal) is not int:
            raise IncompleteConversationRun('draft_version_ordinal_missing')
        self.drafts[self.turn] = {'proposal_id': draft.get('proposal_id'), 'version_ordinal': ordinal}
        constraints = draft.get('constraints') or []
        exclusions = [constraint for constraint in constraints
                      if constraint.get('kind') == 'exclude_worker_from_task']
        # Exactly one: with two, which one "that worker" means is ambiguous, and
        # binding either would fail a correct reply about the other.
        if len(exclusions) == 1 and 'excluded_worker_id' not in self.values:
            worker = _entity_named(exclusions[0], 'workers', workers_by_id)
            task = _entity_named(exclusions[0], 'work-areas-and-tasks', tasks_by_id)
            if all(worker) and all(task):
                self.bind('excluded_worker_id', worker[0])
                self.bind('excluded_worker', worker[1])
                self.bind('excluded_task_id', task[0])
                self.bind('excluded_task', task[1])
        descriptions = [str(constraint.get('description') or constraint.get('kind'))
                        for constraint in constraints]
        # The application's own consequence line ("preserved 0 existing locks; no
        # baseline change") is part of what happened: a reply may repeat it.
        summary = draft.get('consequence_summary')
        self.draft = {'constraints': descriptions, 'consequence_summary': summary,
                      'proposal_id': draft.get('proposal_id'), 'version_ordinal': ordinal}
        self.events.append('Draft saved: ' + '; '.join(descriptions)
                           + (f' ({summary})' if summary else ''))

    def capture_draft_ended(self, proposal: dict | None) -> None:
        """What promotion did to the working draft, read from the application
        after the harness's own approval: a summary may truthfully say the draft
        was applied and closed (live run 62269c0, B:12), so the judge needs it."""
        if proposal and proposal.get('state') == 'applied':
            self.events.append(f"The working draft (v{proposal.get('version_ordinal')}) was applied "
                               "to the baseline and ended.")

    def capture_approval_request(self, activity: dict) -> None:
        self.events.append(
            f"The assistant requested approval {activity.get('approval_id')} to make candidate "
            f"schedule {activity.get('candidate_schedule_version_id')} the new baseline.")

    def capture_run(self, run_result: dict, count: int | None) -> None:
        run = run_result.get('run') or {}
        candidate = run_result.get('candidate') or {}
        started = "The user started an optimization run with the application's run control"
        if run.get('status') != 'solver_completed' or not candidate:
            self.events.append(f"{started}; it ended with status {run.get('status')} and no candidate.")
            return
        self.bind('candidate_id', candidate.get('schedule_version_id'))
        self.bind('solver_status', candidate.get('feasible_solver_status'))
        self.bind('assignment_count', count)
        # The run's own id too: a summary that names it (live run 012bc03, B:12)
        # must find it among what happened.
        run_id = f" (run {run['schedule_run_id']})" if run.get('schedule_run_id') else ''
        self.events.append(
            f"{started}{run_id}; it completed with solver status "
            f"{candidate.get('feasible_solver_status')}, candidate schedule "
            f"{candidate.get('schedule_version_id')}, {count} assignments.")

    def capture_decision(self, approval: dict, *, approved: bool, baseline_now: str | None,
                         baseline_before: str | None = None) -> None:
        if approved:
            self.bind('approval_id', approval.get('approval_id'))
            self.bind('promoted_baseline_id', baseline_now)
            # The replaced baseline too: a summary that names it (live run
            # 9b8dad2, B:12) must find it among what happened.
            replaced = f" (it replaced {baseline_before})" if baseline_before else ''
            self.events.append(f"Approval {approval.get('approval_id')} approved by the user: "
                               f"the baseline is now {baseline_now}{replaced}.")
        else:
            self.events.append(f"Approval {approval.get('approval_id')} rejected by the user: "
                               f"the baseline is unchanged ({baseline_now}).")


def _key(record_id) -> str | None:
    """Ids arrive upper- or lower-case depending on the surface."""
    return record_id.casefold() if isinstance(record_id, str) else None


def _task_by_key(tasks, key) -> dict | None:
    return next((task for task in tasks if key and key in
                 (_key(task.get('record_id')), _key(task.get('task_id')))), None)


def _claims(activity: dict) -> list[dict]:
    return [segment for segment in (activity.get('response') or {}).get('segments') or ()
            if segment.get('kind') == 'claim' and segment.get('verdict') == 'supported']


def _entity(constraint: dict, group: str) -> str | None:
    for entity in constraint.get('resolved_entities') or ():
        if entity.get('group') == group:
            return entity.get('record_id')
    return None


def _entity_named(constraint: dict, group: str, by_id: dict) -> tuple[str | None, str | None]:
    """(record id, name): the name from the fixture read, else the entity's
    own label ("Priya Nair (13270C88-...)") without its id suffix."""
    for entity in constraint.get('resolved_entities') or ():
        if entity.get('group') != group:
            continue
        record_id = entity.get('record_id')
        label = entity.get('label') or ''
        suffix = f' ({record_id})'
        name = by_id.get(record_id) or (label[:-len(suffix)] if label.endswith(suffix) else None)
        return record_id, name
    return None, None


def visible_lines(value) -> list[str]:
    """Every line of text (and number) the user can see in a visible activity.

    Walks the structure instead of serialising it: `json.dumps` turned a newline
    into a literal `\\n`, so a name starting a line read as "npriya" and never
    matched as a whole token.
    """
    parts: list[str] = []

    def walk(item):
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, bool) or item is None:
            return
        elif isinstance(item, (int, float)):
            parts.append(str(item))
        elif isinstance(item, dict):
            for inner in item.values():
                walk(inner)
        elif isinstance(item, (list, tuple)):
            for inner in item:
                walk(inner)

    walk(value)
    return [line for line in (_normalise(line) for part in parts for line in part.splitlines())
            if line]


def visible_text(value) -> str:
    return ' '.join(visible_lines(value))


def _normalise(text: str) -> str:
    return ' '.join(text.casefold().split())


#: A token boundary: not inside a word (any script), a hyphenated name or id,
#: or a decimal number -- "76" is not in "0.76", "Jos" is not in "José".
_BEFORE = r'(?<![\w-])(?<!\d[.,])'
_AFTER = r'(?![\w-])(?![.,]\d)'


def mentioned(term, text: str) -> bool:
    """`term` appears in `text` as a whole token (casefolded, whitespace-collapsed)."""
    if term is None or isinstance(term, bool):
        return False
    needle = _normalise(str(term))
    if not needle:
        return False
    return re.search(_BEFORE + re.escape(needle) + _AFTER, text) is not None


def resolve(value, bindings: Bindings):
    """A `{name}` alone becomes the bound value itself (a list stays a list);
    `{name}` inside other text is substituted as a string."""
    if isinstance(value, str):
        whole = _TEMPLATE.fullmatch(value)
        if whole:
            return bindings.get(whole.group(1))
        return _TEMPLATE.sub(lambda match: _as_text(bindings.get(match.group(1))), value)
    if isinstance(value, (list, tuple)):
        return [resolve(item, bindings) for item in value]
    return value


def _as_text(value) -> str:
    return ', '.join(map(str, value)) if isinstance(value, (list, tuple)) else str(value)


@dataclass
class TurnContext:
    """What one turn's checks may read, as of its reply."""
    activity: dict
    visible: object
    draft: dict | None
    assignments: list
    locks: list
    workers_by_id: dict
    tasks_by_id: dict
    #: Each earlier turn's visible lines, by turn number.
    reply_lines: dict
    candidate_rows: list
    turn: int = 0
    #: Full worker rows (qualifications, roster windows).
    workers: list = ()
    #: The conversation's newest draft as stored, read only for a turn that
    #: checks `draft_state_is`: {proposal_id, state, ended_by, version_ordinal},
    #: or None when the conversation has no draft.
    draft_state: dict | None = None
    #: This turn's completed tool calls as telemetry labelled them:
    #: {capability_name, fact_group?}. What the agent DID, not what it said.
    tool_calls: list = ()

    @property
    def text(self) -> str:
        return visible_text(self.visible)

    @property
    def lines(self) -> list[str]:
        return visible_lines(self.visible)


def reading_lines(activity: dict) -> list[str]:
    """The reply's lines as the planner reads them: each segment's own text in
    order, so a verified name stays on its bullet's line. `visible_lines` splits
    every segment onto its own line, which left each bullet a lone `-` (live run
    a9cc7bf, A:6)."""
    segments = (activity.get('response') or {}).get('segments')
    if not segments:
        return []
    parts = []
    for segment in segments:
        if segment.get('kind') == 'claim':
            parts.append(' '.join(str(segment[key]) for key in ('value', 'unit')
                                  if segment.get(key) is not None))
        else:
            parts.append(str(segment.get('text') or segment.get('value') or ''))
    return [line for line in (_normalise(line) for line in ''.join(parts).splitlines()) if line]


def _pair_on_one_line(worker, task, lines) -> bool:
    """Worker and task named TOGETHER: a list naming every worker and every
    task must not pass as naming one real assignment."""
    return any(mentioned(worker, line) and mentioned(task, line) for line in lines)


def _draft_has(expectation: Expectation, ctx: TurnContext, bindings: Bindings) -> bool:
    earlier = bindings.as_of(ctx.turn)
    worker = resolve(expectation.worker, earlier) if expectation.worker else None
    task = resolve(expectation.task, earlier) if expectation.task else None
    for constraint in (ctx.draft or {}).get('constraints') or ():
        if constraint.get('kind') != expectation.kind:
            continue
        if worker and _key(_entity(constraint, 'workers')) != _key(worker):
            continue
        if task and _key(_entity(constraint, 'work-areas-and-tasks')) != _key(task):
            continue
        if not all(_same_number(getattr(expectation, name), constraint.get(name))
                   for name in ('max_hours', 'n', 'factor')):
            continue
        return True
    return False


def _same_number(wanted, actual) -> bool:
    return wanted is None or (isinstance(actual, (int, float)) and not isinstance(actual, bool)
                              and abs(actual - wanted) < 1e-9)


def _draft_has_roster_lock(expectation: Expectation, ctx: TurnContext, bindings: Bindings) -> bool:
    """A shift lock for a worker qualified for the task, over exactly one of
    that worker's own roster windows."""
    task = _key(resolve(expectation.task, bindings.as_of(ctx.turn)))
    workers = {_key(worker['record_id']): worker for worker in ctx.workers}
    for constraint in (ctx.draft or {}).get('constraints') or ():
        if constraint.get('kind') != 'lock_worker_shift':
            continue
        worker = workers.get(_key(_entity(constraint, 'workers')))
        if not worker or task not in {_key(row.get('task_id')) for row in worker.get('qualifications', ())}:
            continue
        window = (constraint.get('start_minute'), constraint.get('end_minute'))
        if window in {(row.get('start_minute'), row.get('end_minute'))
                      for row in worker.get('availability_windows', ()) if row.get('kind') == 'roster'}:
            return True
    return False


def _claims_metric(expectation: Expectation, ctx: TurnContext, bindings: Bindings) -> bool:
    """The reply carries a grounded claim of this metric (for this task and
    family). Whether its number is right is the oracle's job, not this check's."""
    task = _key(resolve(expectation.task, bindings)) if expectation.task else None
    for claim in _claims(ctx.activity):
        arguments = claim.get('arguments') or {}
        if claim.get('metric') != expectation.metric:
            continue
        if task and _key(arguments.get('task_id')) != task:
            continue
        if expectation.family and arguments.get('family') != expectation.family:
            continue
        return True
    return False


def _lock_ids(items) -> set:
    return {item if isinstance(item, str) else (item.get('record_id') or item.get('lock_id'))
            for item in items or ()}


def _ordinal(draft: dict) -> int:
    ordinal = draft.get('version_ordinal')
    return ordinal if type(ordinal) is int else -1


def code_check(expectation: Expectation, ctx: TurnContext, bindings: Bindings) -> bool:
    """True when the reply meets it. Raises `Unbound` for a value never observed."""
    text = ctx.text
    check = expectation.check
    if check == 'mentions':
        return mentioned(resolve(expectation.value, bindings), text)
    if check == 'mentions_all':
        value = resolve(expectation.value, bindings)
        items = value if isinstance(value, list) else [value]
        return bool(items) and all(mentioned(item, text) for item in items)
    if check == 'each_item_mentions':
        # Every list item names one of these: a list that adds an invented
        # entry fails, whatever notes sit beside the real names.
        value = resolve(expectation.value, bindings)
        items = value if isinstance(value, list) else [value]
        return all(any(mentioned(item, line) for item in items)
                   for line in reading_lines(ctx.activity) if _LIST_ITEM.match(line))
    if check in ('mentions_any', 'mentions_none'):
        bound, first_unbound = [], None
        for template in expectation.values:
            try:
                bound.append(resolve(template, bindings))
            except Unbound as exc:
                first_unbound = first_unbound or exc
        if not bound:
            raise first_unbound
        hit = any(mentioned(item, text) for item in bound)
        return hit if check == 'mentions_any' else not hit
    if check == 'activity_is':
        return ctx.activity.get('activity_type') == expectation.activity
    if check == 'activity_field_equals':
        actual = ctx.activity.get(expectation.field)
        wanted = resolve(expectation.value, bindings)
        return actual is not None and str(actual).casefold() == str(wanted).casefold()
    if check == 'draft_has':
        return _draft_has(expectation, ctx, bindings)
    if check == 'draft_has_roster_lock':
        return _draft_has_roster_lock(expectation, ctx, bindings)
    if check == 'claims_metric':
        return _claims_metric(expectation, ctx, bindings)
    if check == 'draft_preserves_locks':
        return ctx.draft is not None and _lock_ids(ctx.draft.get('preserved_locks')) == _lock_ids(ctx.locks)
    if check == 'names_assigned_pair':
        lines = ctx.lines
        return any(_pair_on_one_line(ctx.workers_by_id.get(row.get('worker_id')),
                                     ctx.tasks_by_id.get(row.get('task_id')), lines)
                   for row in ctx.assignments)
    if check == 'draft_updates_turn':
        earlier = bindings.drafts.get(expectation.turn)
        if earlier is None:
            raise Unbound(f'draft_turn_{expectation.turn}')
        return (ctx.draft is not None and ctx.draft.get('proposal_id') == earlier['proposal_id']
                and _ordinal(ctx.draft) > earlier['version_ordinal'])
    if check == 'draft_state_is':
        state, _, ended_by = str(expectation.value).partition('/')
        return (ctx.draft_state is not None and ctx.draft_state.get('state') == state
                and (not ended_by or ctx.draft_state.get('ended_by') == ended_by))
    if check == 'draft_constraint_count':
        return ctx.draft is not None and len(ctx.draft.get('constraints') or ()) == expectation.n
    if check == 'draft_is_new':
        # Earlier turns only: this turn's own draft is already recorded.
        seen = {entry['proposal_id'] for entry in bindings.as_of(ctx.turn).drafts.values()}
        return (ctx.draft is not None and _ordinal(ctx.draft) == 1
                and ctx.draft.get('proposal_id') not in seen)
    if check == 'tool_called':
        return any(call.get('capability_name') == expectation.value
                   and (expectation.fact_group is None or call.get('fact_group') == expectation.fact_group)
                   for call in ctx.tool_calls)
    if check == 'draft_matches_turn':
        return _pair_on_one_line(bindings.get('excluded_worker'), bindings.get('excluded_task'),
                                 ctx.reply_lines.get(expectation.turn, ()))
    raise ValueError(f'not a code check: {check}')


def _fact(name: str, ctx: TurnContext, bindings: Bindings):
    if name == 'tasks':
        return bindings.get('task_names')
    if name == 'excluded_worker':
        return bindings.get('excluded_worker')
    if name == 'worker_count':
        return bindings.get('worker_count')
    if name == 'workers':
        return bindings.get('worker_names')
    if name == 'locks':
        return list(ctx.locks)
    if name == 'events':
        return list(bindings.events)
    if name == 'candidate_rows':
        return ctx.candidate_rows
    if name == 'draft':
        if bindings.draft is None:
            raise Unbound('draft')
        return dict(bindings.draft)
    raise ValueError(f'unknown fact {name}')


def evaluate(expectations, ctx: TurnContext, bindings: Bindings, user_message: str):
    """Run the code checks now, as of the reply; return their results plus the
    judge questions still to ask and the state they are asked over.

    Returns (checks, questions, state): `checks` is a list of result dicts in
    authored order (judge entries pending); `questions` maps an expectation id to
    its Jev `noul` question; `state` is None when there is nothing to ask. The
    shared state is only the user's message and the reply: each question carries
    the facts IT names inside its own instructions, so no question sees another's.
    """
    checks, questions = [], {}
    kind = 'draft' if ctx.activity.get('activity_type') == 'draft' else 'not_draft'
    for expectation in expectations:
        entry = {'id': expectation.id, 'check': expectation.check}
        if expectation.when and expectation.when != kind:
            entry['outcome'] = 'skipped'
            checks.append(entry)
            continue
        try:
            if expectation.is_judge:
                question = resolve(expectation.question, bindings)
                facts = {name: _fact(name, ctx, bindings) for name in expectation.facts}
                questions[expectation.id] = {
                    'type': 'noul',
                    'instructions': {'question': question, 'facts': facts} if facts else question}
                entry.update(outcome='pending', want=expectation.want)
            else:
                entry['outcome'] = 'pass' if code_check(expectation, ctx, bindings) else 'fail'
        except Unbound as exc:
            entry.update(outcome='unbound', binding=exc.name)
        checks.append(entry)
    state = {'user_message': user_message, 'reply': ctx.visible} if questions else None
    return checks, questions, state


def apply_answers(checks: list[dict], p_yes: dict[str, float]) -> None:
    """Score each pending judge check by P(the wanted answer)."""
    for entry in checks:
        if entry['outcome'] != 'pending':
            continue
        p_wanted = p_yes[entry['id']] if entry['want'] else 1 - p_yes[entry['id']]
        entry['p_wanted'] = round(p_wanted, 4)
        entry['outcome'] = ('pass' if p_wanted >= PASS_P
                            else 'fail' if p_wanted < FAIL_P else 'uncertain')


def verdict_from_checks(checks: list[dict], factual_failures: list[str]) -> str:
    """A definite failure wins; then an ungraded check; then any doubt."""
    outcomes = {entry['outcome'] for entry in checks}
    if factual_failures or 'fail' in outcomes:
        return 'fail'
    if outcomes & {'unbound', 'pending'}:
        return 'incomplete'
    if 'uncertain' in outcomes:
        return 'needs_review'
    return 'pass'
