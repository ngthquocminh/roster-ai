"""Run the durable schedule-job worker as a separately killable process."""
from __future__ import annotations

import argparse
import importlib
import os
import signal
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any, Callable, Protocol
from uuid import uuid4

# Support both ``python -m worker.main`` and the story's explicit
# ``python backend/worker/main.py`` process seam.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker.lease_worker import default_lease_seconds, run_once


DEFAULT_POLL_INTERVAL_SECONDS = 1.0
RUNTIME_FACTORY_ENV = "SHIFTMIND_WORKER_RUNTIME_FACTORY"


class RuntimeFactory(Protocol):
    def __call__(self) -> "WorkerRuntimeV1": ...


@dataclass(frozen=True)
class WorkerRuntimeV1:
    engine: Any
    repository: Any
    scheduler: Any
    settings: Any


def install_shutdown_handlers(stop_event: Event) -> None:
    """Translate process shutdown into a cooperative between-job stop."""

    def request_stop(_signum, _frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)


def run_worker_loop(
    engine: Any,
    repository: Any,
    scheduler: Any,
    *,
    settings: Any,
    lease_owner: str,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    stop_event: Event | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Poll until stopped, allowing an in-flight ``run_once`` to finish."""
    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be positive")
    stopping = stop_event or Event()
    while not stopping.is_set():
        outcome = run_once(
            engine,
            repository,
            scheduler,
            lease_owner=lease_owner,
            lease_seconds=default_lease_seconds(settings),
        )
        if outcome is None and not stopping.is_set():
            sleep(poll_interval_seconds)


def _load_runtime_factory(reference: str) -> RuntimeFactory:
    module_name, separator, attribute = reference.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("runtime factory must use the form 'module:attribute'")
    factory = getattr(importlib.import_module(module_name), attribute)
    if not callable(factory):
        raise TypeError("runtime factory must be callable")
    return factory


def _default_lease_owner() -> str:
    return f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime-factory",
        default=os.environ.get(RUNTIME_FACTORY_ENV),
        help=(
            "callable returning WorkerRuntimeV1, as module:attribute; "
            f"may also be supplied through {RUNTIME_FACTORY_ENV}"
        ),
    )
    parser.add_argument("--lease-owner", default=_default_lease_owner())
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
    )
    args = parser.parse_args(argv)
    if not args.runtime_factory:
        parser.error(
            "--runtime-factory is required until deployment composition is "
            "owned by Epic 5/6"
        )

    runtime = _load_runtime_factory(args.runtime_factory)()
    stop_event = Event()
    install_shutdown_handlers(stop_event)
    try:
        run_worker_loop(
            runtime.engine,
            runtime.repository,
            runtime.scheduler,
            settings=runtime.settings,
            lease_owner=args.lease_owner,
            poll_interval_seconds=args.poll_interval_seconds,
            stop_event=stop_event,
        )
    finally:
        dispose = getattr(runtime.engine, "dispose", None)
        if callable(dispose):
            dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "RUNTIME_FACTORY_ENV",
    "WorkerRuntimeV1",
    "install_shutdown_handlers",
    "main",
    "run_worker_loop",
]
