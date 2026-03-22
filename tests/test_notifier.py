import os
import pytest
from unittest.mock import MagicMock, patch
from src.models import Listing
from src.notifier.whatsapp import format_message, send_alert, health_check


def make_listing(**kwargs):
    defaults = dict(id="1", source="nobroker", title="1 BHK in Chromepet",
                    address="Chromepet Main Road", price=12000, url="https://nobroker.in/1",
                    furnishing="semi-furnished", bachelors_allowed=True,
                    rating=4.3, review_snippet="Clean, good water supply",
                    images=["https://img1.jpg", "https://img2.jpg"])
    return Listing(**{**defaults, **kwargs})


def test_format_message_preferred():
    listing = make_listing()
    msg = format_message(listing, "PREFERRED", 3.2)
    assert "PREFERRED" in msg
    assert "3.2km" in msg
    assert "12,000" in msg or "12000" in msg
    assert "nobroker.in" in msg
    assert "4.3/5" in msg
    assert "Clean, good water supply" in msg

def test_format_message_far():
    listing = make_listing(price=9500, rating=4.1)
    msg = format_message(listing, "FAR BUT WORTH IT", 13.5)
    assert "FAR BUT WORTH IT" in msg
    assert "13.5km" in msg

def test_format_message_distance_unknown():
    listing = make_listing()
    msg = format_message(listing, "Distance unknown", None)
    assert "Distance unknown" in msg
    assert "km" not in msg

def test_format_message_no_rating():
    listing = make_listing(rating=None, review_snippet=None)
    msg = format_message(listing, "PREFERRED", 2.0)
    assert "⭐" not in msg

def test_send_alert_calls_twilio(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtest")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    monkeypatch.setenv("WHATSAPP_TO", "whatsapp:+918610385533")

    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.sid = "SMtest123"
    mock_client.messages.create.return_value = mock_msg

    with patch("src.notifier.whatsapp.Client", return_value=mock_client):
        sid = send_alert(make_listing(), "PREFERRED", 3.2)

    assert sid == "SMtest123"
    mock_client.messages.create.assert_called()

def test_health_check_returns_true_on_success(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtest")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    monkeypatch.setenv("WHATSAPP_TO", "whatsapp:+918610385533")

    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(sid="SMhc")

    with patch("src.notifier.whatsapp.Client", return_value=mock_client):
        assert health_check() is True

def test_health_check_returns_false_on_failure(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtest")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    monkeypatch.setenv("WHATSAPP_TO", "whatsapp:+918610385533")

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("Twilio error")

    with patch("src.notifier.whatsapp.Client", return_value=mock_client):
        assert health_check() is False
