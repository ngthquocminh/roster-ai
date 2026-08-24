from __future__ import annotations

import pytest

from application.grounding.calculators import CalculationArgumentsError
from application.grounding.pagination import drain_projection_group


def test_public_projection_drain_preserves_argument_validation() -> None:
    with pytest.raises(CalculationArgumentsError, match="must be positive"):
        drain_projection_group(
            lambda *_args: None,
            object(),
            __import__("uuid").uuid4(),
            scenario_version_id=__import__("uuid").uuid4(),
            site_id=__import__("uuid").uuid4(),
            page_size=0,
            max_rows=1,
        )
