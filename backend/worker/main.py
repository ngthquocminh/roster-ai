"""Run the durable schedule-job worker as a separately killable process."""
from __future__ import annotations

import argparse
import importlib
import logging
import math
import os
import signal
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any, Callable, Protocol
from uuid import uuid4

# Support both ``python -m worker.main`` and the story's explicit
# ``python backend/worker/main.py`` process seam.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.telemetry import JsonLogTelemetrySink, configure_json_logging
from application.ports.telemetry import TelemetrySink
from worker.lease_worker import default_lease_seconds, run_once


DEFAULT_POLL_INTERVAL_SECONDS = 1.0
#: Ceiling for the consecutive-failure backoff. A worker that cannot reach its
#: database must keep retrying — process supervision is Epic 5/6's — but it must
#: not spin against a down dependency either.
MAX_ERROR_BACKOFF_SECONDS = 60.0
RUNTIME_FACTORY_ENV = "SHIFTMIND_WORKER_RUNTIME_FACTORY"
logger = logging.getLogger(__name__)


class RuntimeFactory(Protocol):
    def __call__(self) -> "WorkerRuntimeV1": ...


@dataclass(frozen=True)
class WorkerRuntimeV1:
    engine: Any
    repository: Any
    scheduler: Any
    settings: Any
    telemetry: TelemetrySink | None = None


def install_shutdown_handlers(stop_event: Event) -> None:
    """Translate process shutdown into a cooperative between-job stop."""

    def request_stop(_signum, _frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)


def _report_error(error: BaseException, backoff_seconds: float) -> None:
    """Surface a transient failure through the sanitized JSON log boundary."""
    logger.error(
        "worker run_once failed; retrying in %s seconds",
        backoff_seconds,
        exc_info=(type(error), error, error.__traceback__),
    )


def run_worker_loop(
    engine: Any,
    repository: Any,
    scheduler: Any,
    *,
    settings: Any,
    lease_owner: str,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    stop_event: Event | None = None,
    sleep: Callable[[float], object] | None = None,
    on_error: Callable[[BaseException, float], object] | None = None,
    telemetry: TelemetrySink | None = None,
) -> None:
    """Poll until stopped, allowing an in-flight ``run_once`` to finish.

    A transient failure (dropped connection, saturated pool, lost lease race)
    must not end the process: without it the recovery guarantee this worker
    exists to provide would be defeated by the first blip. Failures back off
    exponentially to `MAX_ERROR_BACKOFF_SECONDS` and reset on the next success.
    """
    if not math.isfinite(poll_interval_seconds) or poll_interval_seconds <= 0:
        # `inf` and `nan` both slip past a bare `<= 0` check, and `sleep(inf)`
        # parks the process in a wait no signal handler can shorten.
        raise ValueError("poll_interval_seconds must be a positive finite number")
    stopping = stop_event or Event()
    # `Event.wait` returns as soon as shutdown is requested; `time.sleep` would
    # resume the full interval first (PEP 475) and delay a supervisor's stop.
    wait = sleep if sleep is not None else stopping.wait
    report = on_error if on_error is not None else _report_error
    backoff_seconds = 0.0
    while not stopping.is_set():
        try:
            outcome = run_once(
                engine,
                repository,
                scheduler,
                lease_owner=lease_owner,
                lease_seconds=default_lease_seconds(settings),
                telemetry=telemetry,
            )
        except Exception as error:  # noqa: BLE001 — a poll loop owns every failure
            backoff_seconds = min(
                MAX_ERROR_BACKOFF_SECONDS,
                max(poll_interval_seconds, backoff_seconds * 2),
            )
            report(error, backoff_seconds)
            if not stopping.is_set():
                wait(backoff_seconds)
            continue
        backoff_seconds = 0.0
        if outcome is None and not stopping.is_set():
            wait(poll_interval_seconds)


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
    configure_json_logging()
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

    stop_event = Event()
    # Installed BEFORE the factory runs: a signal arriving while the factory is
    # opening connections would otherwise take the default disposition and skip
    # the `dispose()` below, leaking them.
    install_shutdown_handlers(stop_event)
    try:
        runtime = _load_runtime_factory(args.runtime_factory)()
    except (ImportError, AttributeError, TypeError, ValueError) as error:
        # A mistyped reference is operator error, not a crash worth a traceback.
        parser.error(
            f"could not load --runtime-factory {args.runtime_factory!r}: "
            f"{type(error).__name__}: {error}"
        )
    try:
        run_worker_loop(
            runtime.engine,
            runtime.repository,
            runtime.scheduler,
            settings=runtime.settings,
            lease_owner=args.lease_owner,
            poll_interval_seconds=args.poll_interval_seconds,
            stop_event=stop_event,
            telemetry=runtime.telemetry or JsonLogTelemetrySink(),
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
    "MAX_ERROR_BACKOFF_SECONDS",
    "RUNTIME_FACTORY_ENV",
    "WorkerRuntimeV1",
    "install_shutdown_handlers",
    "main",
    "run_worker_loop",
]
