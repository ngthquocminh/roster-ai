"""Shared bounded pagination for immutable scenario projection groups."""
from __future__ import annotations

from typing import Any, Callable
from uuid import UUID

from application.ports.scenario_projection import GroupQueryV1

MAX_PAGES = 512


class CalculationError(Exception):
    """Base for application-owned calculator failures."""


class CalculationArgumentsError(CalculationError):
    pass


class CalculationScenarioNotFoundError(CalculationError):
    pass


class CalculationVersionMismatchError(CalculationError):
    pass


class CalculationSiteMismatchError(CalculationError):
    pass


class CalculationLimitError(CalculationError):
    pass


def drain_projection_group(
    getter: Callable[[Any, UUID, GroupQueryV1], object | None],
    connection: Any,
    scenario_id: UUID,
    *,
    scenario_version_id: UUID,
    site_id: UUID,
    page_size: int,
    max_rows: int,
    filters: tuple[tuple[str, str | int], ...] = (),
) -> tuple[object, ...]:
    """Drain one fact group to exhaustion under an explicit bound."""
    if page_size < 1 or max_rows < 1:
        raise CalculationArgumentsError("page_size and max_rows must be positive")
    cursor = 0
    items: list[object] = []
    matching_count: int | None = None
    seen_cursors: set[int] = set()
    for _ in range(MAX_PAGES):
        if cursor in seen_cursors:
            raise CalculationLimitError("projection cursor did not advance")
        seen_cursors.add(cursor)
        remaining = max_rows - len(items)
        if remaining < 1:
            raise CalculationLimitError(f"calculation exceeded row bound {max_rows}")
        page = getter(
            connection,
            scenario_id,
            GroupQueryV1(cursor=cursor, limit=min(page_size, remaining), filters=filters),
        )
        if page is None:
            raise CalculationScenarioNotFoundError(
                f"scenario {scenario_id} has no projection"
            )
        if page.scenario_version_id != scenario_version_id:
            raise CalculationVersionMismatchError(
                f"page version {page.scenario_version_id} does not match pinned {scenario_version_id}"
            )
        if page.site_id != site_id:
            raise CalculationSiteMismatchError(
                f"page site {page.site_id} does not match trusted {site_id}"
            )
        if matching_count is None:
            matching_count = page.matching_count
            if matching_count > max_rows:
                raise CalculationLimitError(
                    f"calculation requires {matching_count} rows; bound is {max_rows}"
                )
        elif page.matching_count != matching_count:
            raise CalculationError("matching_count changed while paging immutable projection")
        items.extend(page.items)
        if len(items) > max_rows:
            raise CalculationLimitError(f"calculation exceeded row bound {max_rows}")
        if page.next_cursor is None:
            if len(items) != matching_count:
                raise CalculationLimitError(
                    f"projection ended after {len(items)} of {matching_count} matching rows"
                )
            return tuple(items)
        if page.next_cursor <= cursor:
            raise CalculationLimitError("projection cursor did not advance")
        cursor = page.next_cursor
    raise CalculationLimitError(
        f"projection did not terminate within {MAX_PAGES} pages"
    )


__all__ = [
    "MAX_PAGES",
    "CalculationArgumentsError",
    "CalculationError",
    "CalculationLimitError",
    "CalculationScenarioNotFoundError",
    "CalculationSiteMismatchError",
    "CalculationVersionMismatchError",
    "drain_projection_group",
]
