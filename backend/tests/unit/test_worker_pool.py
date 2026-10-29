import threading
import pytest
from pydantic import ValidationError
from app.core.config import Settings, settings
from app.worker import runner


@pytest.mark.parametrize('value', [0, -1, 33])
def test_worker_concurrency_rejects_unsafe_slot_counts(value):
    with pytest.raises(ValidationError):
        Settings(WORKER_CONCURRENCY=value)


def test_pool_stops_admission_and_drains_all_slots(monkeypatch):
    monkeypatch.setattr(settings, 'WORKER_CONCURRENCY', 2)
    stop = threading.Event()
    arrived = threading.Barrier(3)
    drained = []
    def loop(event, *, maintenance):
        arrived.wait(timeout=5)
        event.wait(5)
        drained.append(maintenance)
    monkeypatch.setattr(runner, '_run_loop', loop)
    failures = []
    def supervise():
        try:
            runner._run_pool(stop)
        except BaseException as exc:
            failures.append(exc)
    thread = threading.Thread(target=supervise)
    thread.start()
    arrived.wait(timeout=5)
    stop.set()
    thread.join(timeout=5)
    assert not thread.is_alive() and not failures
    assert sorted(drained) == [False, True]  # only one maintenance coordinator


def test_unexpected_slot_exit_stops_the_pool_instead_of_silently_losing_capacity(monkeypatch):
    monkeypatch.setattr(settings, 'WORKER_CONCURRENCY', 2)
    stop = threading.Event()
    def loop(event, *, maintenance):
        if not maintenance:
            event.wait(5)
    monkeypatch.setattr(runner, '_run_loop', loop)
    with pytest.raises(RuntimeError, match='exited unexpectedly'):
        runner._run_pool(stop)
    assert stop.is_set()
