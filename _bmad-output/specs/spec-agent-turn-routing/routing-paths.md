# Routing Paths

## Path matrix

| Route | Sent here | Prompt | Tools | Allowed output | Examples |
|---|---|---|---|---|---|
| `scheduling` | default; any doubt, error, timeout, `off` | full (all sections + Scope) | all granted, as today | as today | "who's on Pick Wed?", "cap Ana at 40h", "hi, how many pickers Wed?" |
| `direct` | greeting, thanks, small talk, "what can you do?", "how does approval work?" | Core, Business context, ShiftMind workflow, Greetings and capability questions, Tool routing (as the capability list), Direct rule | none | grounded answer (tool or plain text) | "hi", "thanks!", "what can you help with?" |
| `out_of_scope` | request clearly unrelated to workforce scheduling or this app | Core, Refusal rule | none | `RefusalV1` with reason `out_of_scope` only | "sing a song", "write Python for a quadratic", trivia |

A message mixing a scheduling request with anything else is `scheduling`; the Scope section there answers only the scheduling part.

## Prompt sections

Today's `SCHEDULING_ASSISTANT_INSTRUCTIONS` splits along its existing headings into named sections, in their current order. Joined in order, all today's sections reproduce today's string exactly.

| Section | scheduling | direct | out_of_scope |
|---|---|---|---|
| Core (identity line) | ✓ | ✓ | ✓ |
| **Scope** (new) | ✓ | ✓ | ✓ |
| Business context | ✓ | ✓ | |
| ShiftMind workflow | ✓ | ✓ | |
| Where facts live | ✓ | | |
| Greetings and capability questions | ✓ | ✓ | |
| General tool-calling discipline … Multi-tool workflows (12 sections) | ✓ | | |
| Tool routing | ✓ | ✓ | |
| **Direct rule** (new) | | ✓ | |
| **Refusal rule** (new) | | | ✓ |

- **Scope:** help only with workforce scheduling in this app — its scenario, drafts, runs and baseline. Anything else (code, songs, general knowledge, other business domains): refuse with reason `out_of_scope` and point back to scheduling; in a mixed message answer only the scheduling part.
- **Direct rule:** this reply has no schedule data; never state schedule facts, counts or numbers, and never describe features not listed in Tool routing or the workflow.
- **Refusal rule:** return only the refusal: reason `out_of_scope`, a one-sentence detail, and a `next_step` suggesting one or two example scheduling questions.

## Router question

One Jev `choice` question per turn. Options and criteria:

- `scheduling` — asks about, or to change, the schedule, workers, tasks, demand, drafts, runs or baseline; or refers back to earlier conversation.
- `direct` — only a greeting, thanks, small talk, or a question about what the assistant can do or how the workflow works.
- `out_of_scope` — clearly unrelated to workforce scheduling or this app.

State: the latest planner message and the previous exchange (last two planner messages and last two agent replies), each truncated. A special route is taken only when its probability ≥ the threshold (default 0.85).
