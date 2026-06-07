"""List the input fixtures available to build scenarios from."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends

from api.deps import get_settings
from settings import Settings

router = APIRouter(tags=["fixtures"])


@router.get("/fixtures")
def list_fixtures(settings: Settings = Depends(get_settings)) -> list[str]:
    data_dir = settings.data_dir
    if not os.path.isdir(data_dir):
        return []
    return sorted(
        f for f in os.listdir(data_dir)
        if f.endswith(".json") and os.path.isfile(os.path.join(data_dir, f))
    )
