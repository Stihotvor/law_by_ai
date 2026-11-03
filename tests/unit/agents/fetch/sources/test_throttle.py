import threading

import pytest

from agents.fetch.sources._throttle import Throttle


class Fake:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _throttle(fake: Fake, interval: float = 0.5) -> Throttle:
    return Throttle(lambda: interval, clock=fake.clock, sleep=fake.sleep)


def test_first_call_does_not_sleep() -> None:
    fake = Fake()
    _throttle(fake).wait()
    assert fake.sleeps == []


def test_second_call_sleeps_remaining() -> None:
    fake = Fake()
    t = _throttle(fake)
    t.wait()
    fake.now += 0.1
    t.wait()
    assert fake.sleeps == [pytest.approx(0.4)]


def test_gap_counts_from_last_return() -> None:
    fake = Fake()
    t = _throttle(fake)
    t.wait()
    fake.now += 0.1
    t.wait()
    fake.now += 0.2
    t.wait()
    assert fake.sleeps == [pytest.approx(0.4), pytest.approx(0.3)]


def test_late_call_does_not_sleep() -> None:
    fake = Fake()
    t = _throttle(fake)
    t.wait()
    fake.now += 1.0
    t.wait()
    assert fake.sleeps == []


def test_exact_interval_does_not_sleep() -> None:
    fake = Fake()
    t = _throttle(fake)
    t.wait()
    fake.now += 0.5
    t.wait()
    assert fake.sleeps == []


@pytest.mark.parametrize("interval", [0.0, -1.0])
def test_non_positive_interval_never_sleeps(interval: float) -> None:
    fake = Fake()
    t = _throttle(fake, interval)
    for _ in range(3):
        t.wait()
    assert fake.sleeps == []


def test_interval_read_on_every_call() -> None:
    fake = Fake()
    value = [0.0]
    t = Throttle(lambda: value[0], clock=fake.clock, sleep=fake.sleep)
    t.wait()
    t.wait()
    assert fake.sleeps == []
    value[0] = 2.0
    t.wait()
    assert fake.sleeps == [pytest.approx(2.0)]
    value[0] = 0.0
    t.wait()
    assert len(fake.sleeps) == 1


def test_threads_are_serialised() -> None:
    fake = Fake()
    inside = 0
    overlap = False
    guard = threading.Lock()

    def sleep(seconds: float) -> None:
        nonlocal inside, overlap
        with guard:
            inside += 1
            overlap = overlap or inside > 1
        fake.sleep(seconds)
        with guard:
            inside -= 1

    t = Throttle(lambda: 0.5, clock=fake.clock, sleep=sleep)
    threads = [threading.Thread(target=t.wait) for _ in range(6)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert not overlap
    assert fake.sleeps == [pytest.approx(0.5)] * 5


def test_sleep_is_bounded() -> None:
    fake = Fake()
    t = _throttle(fake, interval=1e9)
    t.wait()
    t.wait()
    assert fake.sleeps == [60.0]
