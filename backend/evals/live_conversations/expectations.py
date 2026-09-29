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

#: Values the harness binds, and where (see `Bindings.capture_*`).
BINDING_NAMES = frozenset({
    'scenario_name', 'baseline_id', 'task_names',
    'excluded_worker', 'excluded_worker_id', 'excluded_task', 'excluded_task_id',
    'candidate_id', 'solver_status', 'assignment_count',
    'promoted_baseline_id', 'approval_id',
})
#: Facts a judge question may name; each is built from bindings or this turn.
FACT_NAMES = frozenset({'tasks', 'candidate_rows', 'events', 'draft', 'excluded_worker'})
CODE_CHECKS = frozenset({
    'mentions', 'mentions_all', 'mentions_any', 'mentions_none', 'activity_is',
    'activity_field_equals', 'draft_has', 'draft_preserves_locks', 'names_assigned_pair',
    'draft_matches_turn',
})
#: Checks that can only fail by the reply doing something wrong; a turn needs at
#: least one check that requires the reply to DO something (tau-bench: a
#: do-nothing agent passes every "must not").
NEGATIVE_CHECKS = frozenset({'mentions_none'})

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
    turn: int | None = None
    question: str | None = None
    want: bool | None = None
    facts: tuple[str, ...] = ()

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
    'mentions_any': ({'values'}, set()),
    'mentions_none': ({'values'}, set()),
    'activity_is': ({'activity'}, set()),
    'activity_field_equals': ({'field', 'value'}, set()),
    'draft_has': ({'kind'}, {'worker', 'task', 'max_hours'}),
    'draft_preserves_locks': (set(), set()),
    'names_assigned_pair': (set(), set()),
    'draft_matches_turn': ({'turn'}, set()),
    'judge': ({'question', 'want'}, {'facts'}),
}
#: Bindings that hold a list: only `mentions_all` may take one whole.
LIST_BINDINGS = frozenset({'task_names'})
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
    validate_expectation(expectation, present=set(raw) - {'id', 'check'})
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
    for name in ('value', 'activity', 'field', 'kind', 'worker', 'task', 'question'):
        value = getattr(expectation, name)
        if value is not None and (not isinstance(value, (str, int, float)) or isinstance(value, bool)
                                  or (isinstance(value, str) and not value.strip())):
            raise ValueError(f'{where}: {name} must be a non-empty string or number')
    if expectation.turn is not None and (isinstance(expectation.turn, bool)
                                         or not isinstance(expectation.turn, int) or expectation.turn < 1):
        raise ValueError(f'{where}: turn must be a positive turn number')
    if expectation.max_hours is not None and (isinstance(expectation.max_hours, bool)
                                              or not isinstance(expectation.max_hours, (int, float))):
        raise ValueError(f'{where}: max_hours must be a number')
    if expectation.is_judge and not isinstance(expectation.want, bool):
        raise ValueError(f'{where}: want must be true or false')
    names = set().union(*(_templates(getattr(expectation, name)) for name in
                          ('value', 'values', 'worker', 'task', 'question')))
    if names - BINDING_NAMES:
        raise ValueError(f'{where}: unknown bindings {sorted(names - BINDING_NAMES)}')
    if expectation.check != 'mentions_all' and names & LIST_BINDINGS:
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
                        bound_at={name: self.bound_at[name] for name in earlier})

    def get(self, name: str):
        if name not in self.values:
            raise Unbound(name)
        return self.values[name]

    def capture_start(self, overview: dict, tasks: list[dict]) -> None:
        self.bind('scenario_name', overview.get('scenario_name'))
        self.bind('baseline_id', overview.get('baseline_schedule_version'))
        self.bind('task_names', [task['name'] for task in tasks if task.get('name')] or None)

    def capture_draft(self, draft: dict | None, workers_by_id: dict, tasks_by_id: dict) -> None:
        if not draft:
            return
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
                      'proposal_id': draft.get('proposal_id')}
        self.events.append('Draft saved: ' + '; '.join(descriptions)
                           + (f' ({summary})' if summary else ''))

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
        self.events.append(
            f"{started}; it completed with solver status {candidate.get('feasible_solver_status')}, "
            f"candidate schedule {candidate.get('schedule_version_id')}, {count} assignments.")

    def capture_decision(self, approval: dict, *, approved: bool, baseline_now: str | None) -> None:
        if approved:
            self.bind('approval_id', approval.get('approval_id'))
            self.bind('promoted_baseline_id', baseline_now)
            self.events.append(f"Approval {approval.get('approval_id')} approved by the user: "
                               f"the baseline is now {baseline_now}.")
        else:
            self.events.append(f"Approval {approval.get('approval_id')} rejected by the user: "
                               f"the baseline is unchanged ({baseline_now}).")


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

    @property
    def text(self) -> str:
        return visible_text(self.visible)

    @property
    def lines(self) -> list[str]:
        return visible_lines(self.visible)


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
        if worker and _entity(constraint, 'workers') != worker:
            continue
        if task and _entity(constraint, 'work-areas-and-tasks') != task:
            continue
        if expectation.max_hours is not None and constraint.get('max_hours') != expectation.max_hours:
            continue
        return True
    return False


def _lock_ids(items) -> set:
    return {item if isinstance(item, str) else (item.get('record_id') or item.get('lock_id'))
            for item in items or ()}


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
    if check == 'draft_preserves_locks':
        return ctx.draft is not None and _lock_ids(ctx.draft.get('preserved_locks')) == _lock_ids(ctx.locks)
    if check == 'names_assigned_pair':
        lines = ctx.lines
        return any(_pair_on_one_line(ctx.workers_by_id.get(row.get('worker_id')),
                                     ctx.tasks_by_id.get(row.get('task_id')), lines)
                   for row in ctx.assignments)
    if check == 'draft_matches_turn':
        return _pair_on_one_line(bindings.get('excluded_worker'), bindings.get('excluded_task'),
                                 ctx.reply_lines.get(expectation.turn, ()))
    raise ValueError(f'not a code check: {check}')


def _fact(name: str, ctx: TurnContext, bindings: Bindings):
    if name == 'tasks':
        return bindings.get('task_names')
    if name == 'excluded_worker':
        return bindings.get('excluded_worker')
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
    for expectation in expectations:
        entry = {'id': expectation.id, 'check': expectation.check}
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
