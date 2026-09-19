import pytest
from src.models import Listing, RunStats
from src.notifier import alert_v2


def _make(**kw) -> Listing:
    base = dict(id="x", source="sulekha", title="1 BHK in Pallavaram",
                address="Pallavaram, Chennai", price=12000,
                url="https://x.test/1", furnishing="semi",
                fingerprint="deadbeef")
    base.update(kw)
    return Listing(**base)


def test_tracking_id_uses_fingerprint_when_present():
    a = alert_v2._tracking_id(_make(fingerprint="abc"))
    b = alert_v2._tracking_id(_make(fingerprint="abc"))
    assert a == b
    assert len(a) == 16


def test_format_includes_price_address_url():
    msg = alert_v2._format(_make(price=11500))
    assert "₹11,500" in msg
    assert "Pallavaram, Chennai" in msg
    assert "https://x.test/1" in msg


@pytest.mark.asyncio
async def test_alert_dispatches_to_thread(monkeypatch):
    calls = []
    def fake_send(l: Listing) -> int | None:
        calls.append(l.url)
        return 4242
    monkeypatch.setattr(alert_v2, "_send", fake_send)
    msg_id = await alert_v2.alert(_make(), RunStats(started_at=0))
    assert msg_id == 4242
    assert calls == ["https://x.test/1"]
