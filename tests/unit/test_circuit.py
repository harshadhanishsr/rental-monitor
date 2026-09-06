import pytest
from src.core.circuit import Breaker, BreakerOpen


def test_opens_after_threshold():
    b = Breaker(threshold=3)
    for _ in range(3):
        b.record_failure()
    assert b.is_open


def test_success_resets():
    b = Breaker(threshold=3)
    b.record_failure()
    b.record_success()
    assert not b.is_open


def test_check_raises_when_open():
    b = Breaker(threshold=1)
    b.record_failure()
    with pytest.raises(BreakerOpen):
        b.check()
