from __future__ import annotations

import signal
from threading import Event
from types import SimpleNamespace

from worker import main as worker_main


def test_worker_loop_sleeps_only_when_no_job_and_stops_after_inflight_work(
    monkeypatch,
) -> None:
    stop = Event()
    outcomes = iter((object(), None))
    calls: list[str] = []

    def fake_run_once(*args, **kwargs):
        calls.append("run")
        if len(calls) == 1:
            stop.set()
        return next(outcomes)

    monkeypatch.setattr(worker_main, "run_once", fake_run_once)
    worker_main.run_worker_loop(
        object(),
        object(),
        object(),
        settings=SimpleNamespace(
            lease_seconds=120, solver_wall_time_limit_seconds=30
        ),
        lease_owner="worker-test",
        poll_interval_seconds=0.01,
        stop_event=stop,
        sleep=lambda _seconds: calls.append("sleep"),
    )

    assert calls == ["run"]


def test_worker_loop_sleeps_after_empty_poll(monkeypatch) -> None:
    stop = Event()
    calls: list[str] = []

    def fake_run_once(*args, **kwargs):
        calls.append("run")
        return None

    def fake_sleep(seconds: float) -> None:
        calls.append(f"sleep:{seconds}")
        stop.set()

    monkeypatch.setattr(worker_main, "run_once", fake_run_once)
    worker_main.run_worker_loop(
        object(),
        object(),
        object(),
        settings=SimpleNamespace(
            lease_seconds=120, solver_wall_time_limit_seconds=30
        ),
        lease_owner="worker-test",
        poll_interval_seconds=0.25,
        stop_event=stop,
        sleep=fake_sleep,
    )

    assert calls == ["run", "sleep:0.25"]


def test_shutdown_handlers_request_cooperative_stop(monkeypatch) -> None:
    registered = {}
    monkeypatch.setattr(
        worker_main.signal,
        "signal",
        lambda signum, handler: registered.setdefault(signum, handler),
    )
    stop = Event()

    worker_main.install_shutdown_handlers(stop)
    registered[signal.SIGTERM](signal.SIGTERM, None)

    assert stop.is_set()
    assert signal.SIGINT in registered

