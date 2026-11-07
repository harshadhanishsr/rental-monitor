"""Pure-helper tests for the setup wizard."""
import ast

import pytest

from configure import (
    _patch_monitor_cron,
    _render_config,
    _update_env,
)


# ─── _patch_monitor_cron ──────────────────────────────────────────

_YAML = """\
name: Rental Monitor
on:
  schedule:
    - cron: '0 * * * *'
  workflow_dispatch:
"""


def test_patch_cron_hourly():
    out = _patch_monitor_cron(_YAML.replace("0 * * * *", "*/30 * * * *"), 1)
    assert "cron: '0 * * * *'" in out


def test_patch_cron_every_two_hours():
    out = _patch_monitor_cron(_YAML, 2)
    assert "cron: '0 */2 * * *'" in out
    assert "cron: '0 * * * *'" not in out


def test_patch_cron_every_six_hours():
    out = _patch_monitor_cron(_YAML, 6)
    assert "cron: '0 */6 * * *'" in out


def test_patch_cron_preserves_surrounding_yaml():
    out = _patch_monitor_cron(_YAML, 4)
    assert out.startswith("name: Rental Monitor")
    assert "workflow_dispatch:" in out


# ─── _update_env ──────────────────────────────────────────────────

def test_update_env_replaces_existing_key():
    out = _update_env("FOO=old\nBAR=baz\n", {"FOO": "new"})
    assert "FOO=new" in out
    assert "BAR=baz" in out


def test_update_env_adds_missing_key():
    out = _update_env("FOO=x\n", {"BAR": "y"})
    assert "FOO=x" in out
    assert "BAR=y" in out


def test_update_env_preserves_comments():
    src = "# my secrets\nFOO=old\n\n# more\nBAR=keep\n"
    out = _update_env(src, {"FOO": "new"})
    assert "# my secrets" in out
    assert "# more" in out
    assert "FOO=new" in out
    assert "BAR=keep" in out


def test_update_env_empty_input():
    out = _update_env("", {"FOO": "1", "BAR": "2"})
    assert "FOO=1" in out
    assert "BAR=2" in out


def test_update_env_ends_with_newline():
    assert _update_env("FOO=a", {"FOO": "b"}).endswith("\n")


# ─── _render_config ───────────────────────────────────────────────

_VALUES = dict(
    lat=12.9716, lng=80.2435,
    city="Chennai",
    areas=["Pallavaram", "Chromepet"],
    radius=5.0,
    bhk="1bhk", num_people=2, furnishing="any",
    min_rent=5000, max_rent=15000,
    interval_hours=2,
)


def test_render_config_is_valid_python():
    text = _render_config(_VALUES)
    ast.parse(text)


def test_render_config_contains_user_values():
    text = _render_config(_VALUES)
    assert 'CITY = "Chennai"' in text
    assert '"Pallavaram"' in text
    assert '"Chromepet"' in text
    assert '"pallavaram"' in text  # priority lowercased
    assert "MAX_RADIUS_KM = 5.0" in text
    assert 'PROPERTY_TYPE = "1bhk"' in text
    assert "NUM_PEOPLE = 2" in text
    assert "MIN_RENT = 5000" in text
    assert "MAX_RENT = 15000" in text
    assert "CHECK_INTERVAL_SECONDS = 7200" in text  # 2h
    assert 'OFFICE_LAT", "12.971600"' in text
    assert 'OFFICE_LNG", "80.243500"' in text


def test_render_config_far_max_matches_budget():
    text = _render_config(_VALUES)
    assert "FAR_MAX_PRICE  = 15000" in text
