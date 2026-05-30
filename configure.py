#!/usr/bin/env python
"""Rental Monitor — interactive setup wizard.

Run:  uv run python configure.py

Asks plain-English questions and writes every file the monitor needs:
config.py, .env, the GitHub Actions cron, and (if `gh` is installed)
the GitHub repository secrets. Safe to re-run any time you want to
change something — moved cities, want a different radius, etc. Press
Enter at any prompt to keep the value shown in brackets.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from shutil import which


# ─── prompt helpers ────────────────────────────────────────────────

def _ask(question: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        ans = input(f"{question}{suffix}: ").strip()
        if ans:
            return ans
        if default is not None:
            return default
        print("  (required)")


def _ask_int(question: str, default: int | None = None,
             min_val: int | None = None) -> int:
    while True:
        raw = _ask(question, str(default) if default is not None else None)
        try:
            v = int(raw.replace(",", "").replace("₹", "").strip())
        except ValueError:
            print("  please enter a whole number"); continue
        if min_val is not None and v < min_val:
            print(f"  must be at least {min_val}"); continue
        return v


def _ask_float(question: str, default: float | None = None) -> float:
    while True:
        raw = _ask(question, str(default) if default is not None else None)
        try:
            return float(raw)
        except ValueError:
            print("  please enter a number")


def _ask_choice(question: str, choices: list[str], default: str) -> str:
    while True:
        raw = _ask(f"{question} ({'/'.join(choices)})", default).lower()
        if raw in choices:
            return raw
        print(f"  pick one of: {', '.join(choices)}")


def _ask_yesno(question: str, default: bool = True) -> bool:
    suf = "Y/n" if default else "y/N"
    while True:
        ans = input(f"{question} [{suf}]: ").strip().lower()
        if not ans:
            return default
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False


# ─── geocoding ────────────────────────────────────────────────────

def _geocode(area: str, city: str) -> tuple[float, float]:
    """Look up coords for ``area, city`` via Nominatim (free, no key)."""
    import httpx
    query = f"{area}, {city}, India"
    r = httpx.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": query, "format": "json", "limit": 1,
                "countrycodes": "in"},
        headers={"User-Agent": "rental-monitor-configure/1.0"},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if not data:
        raise ValueError(f"couldn't find '{query}' on OpenStreetMap")
    return float(data[0]["lat"]), float(data[0]["lon"])


# ─── file writers ─────────────────────────────────────────────────

_CONFIG_TEMPLATE = '''\
"""User configuration — written by configure.py. Re-run to change."""
import os as _os
from dotenv import load_dotenv as _load_dotenv
_load_dotenv()

OFFICE_LAT = float(_os.environ.get("OFFICE_LAT", "{lat:.6f}"))
OFFICE_LNG = float(_os.environ.get("OFFICE_LNG", "{lng:.6f}"))

CITY = "{city}"

SEARCH_AREAS = [
{areas}
]

PRIORITY_LOCALITIES = {{
{priorities}
}}

MAX_RADIUS_KM = {radius}

ZONE_SUPER_CLOSE_KM = 2.0
ZONE_PREFERRED_KM   = 5.0
ZONE_NEARBY_KM      = 8.0
FAR_MAX_PRICE  = {far_max}
FAR_MIN_RATING = 4.0

PROPERTY_TYPE = "{bhk}"
NUM_PEOPLE = {num_people}
FURNISHING = "{furnishing}"

MIN_RENT = {min_rent}
MAX_RENT = {max_rent}

CHECK_INTERVAL_SECONDS = {interval_seconds}

GROUP_MODE = False
GROUP_MEMBERS = []
MAX_COMMUTE_PER_PERSON_MINUTES = 50
MAX_COMMUTE_PER_PERSON_KM = 15.0
GOOGLE_MAPS_API_KEY = ""

# ─── derived (do not edit) ───
import re as _re

def _parse_property_type(pt: str) -> dict:
    pt = pt.lower().strip()
    m = _re.match(r"(\\d)(bhk|rk|rk\\+?|studio)", pt)
    if m:
        beds = int(m.group(1)); kind = m.group(2)
    elif pt == "studio":
        beds, kind = 1, "rk"
    else:
        beds, kind = 1, "bhk"
    label = f"{{beds}} {{'BHK' if kind == 'bhk' else 'RK'}}"
    slug  = f"{{beds}}{{kind}}"
    return {{"beds": beds, "kind": kind, "label": label, "slug": slug}}

_PT            = _parse_property_type(PROPERTY_TYPE)
BEDROOMS       = _PT["beds"]
IS_RK          = _PT["kind"] == "rk"
PROPERTY_LABEL = _PT["label"]
PROPERTY_SLUG  = _PT["slug"]
'''


def _render_config(values: dict) -> str:
    areas_lines = ",\n".join(f'    "{a}"' for a in values["areas"])
    pri_lines = ",\n".join(f'    "{a.lower()}"' for a in values["areas"])
    return _CONFIG_TEMPLATE.format(
        lat=values["lat"], lng=values["lng"], city=values["city"],
        areas=areas_lines, priorities=pri_lines,
        radius=values["radius"],
        far_max=values["max_rent"],
        bhk=values["bhk"], num_people=values["num_people"],
        furnishing=values["furnishing"],
        min_rent=values["min_rent"], max_rent=values["max_rent"],
        interval_seconds=values["interval_hours"] * 3600,
    )


def _update_env(existing: str, updates: dict[str, str]) -> str:
    """Patch ``KEY=value`` lines in-place; preserve comments + other keys."""
    lines = existing.splitlines()
    seen: set[str] = set()
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if "=" not in stripped or stripped.startswith("#"):
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            lines[i] = f"{key}={updates[key]}"
            seen.add(key)
    for key, val in updates.items():
        if key not in seen:
            lines.append(f"{key}={val}")
    out = "\n".join(lines)
    if not out.endswith("\n"):
        out += "\n"
    return out


_CRON_RE = re.compile(r"^(\s*-\s*cron:\s*)'([^']+)'", re.M)


def _patch_monitor_cron(yaml_text: str, hours: int) -> str:
    """Replace the first cron schedule with one firing every ``hours``."""
    new_cron = "0 * * * *" if hours == 1 else f"0 */{hours} * * *"
    return _CRON_RE.sub(rf"\1'{new_cron}'", yaml_text, count=1)


# ─── external commands ───────────────────────────────────────────

def _gh_set_secret(name: str, value: str) -> bool:
    try:
        subprocess.run(
            ["gh", "secret", "set", name, "--body", value],
            check=True, capture_output=True, text=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _send_telegram_test(token: str, chat_id: str) -> bool:
    import httpx
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id,
                  "text": "✅ Rental monitor configured."},
            timeout=15,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"  telegram test failed: {e}")
        return False


# ─── load current values ─────────────────────────────────────────

def _current_config() -> dict:
    """Pull current config.py values — empty dict if it doesn't import."""
    try:
        import importlib, config  # noqa: E401
        importlib.reload(config)
    except Exception:
        return {}
    out: dict = {}
    for key in (
        "CITY", "SEARCH_AREAS", "MAX_RADIUS_KM", "PROPERTY_TYPE",
        "NUM_PEOPLE", "FURNISHING", "MIN_RENT", "MAX_RENT",
        "CHECK_INTERVAL_SECONDS", "OFFICE_LAT", "OFFICE_LNG",
    ):
        if hasattr(config, key):
            out[key] = getattr(config, key)
    return out


def _current_env() -> dict[str, str]:
    p = Path(".env")
    if not p.exists():
        return {}
    out: dict[str, str] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip()
        if "=" not in stripped or stripped.startswith("#"):
            continue
        k, v = stripped.split("=", 1)
        out[k.strip()] = v.strip()
    return out


# ─── main flow ────────────────────────────────────────────────────

def main() -> None:
    print("\n  Rental Monitor — setup")
    print("  ──────────────────────")
    print("  Press Enter at any prompt to keep the value shown in [brackets].\n")

    cur = _current_config()
    env_cur = _current_env()

    city = _ask("Which city?", cur.get("CITY", "Chennai"))

    cur_areas = cur.get("SEARCH_AREAS") or []
    cur_main = cur_areas[0] if cur_areas else None
    main_area = _ask("Main neighbourhood you want to live near", cur_main)

    lat = lng = None
    print(f"\n  looking up '{main_area}, {city}'…", flush=True)
    try:
        lat, lng = _geocode(main_area, city)
        print(f"  → {lat:.4f}, {lng:.4f}\n")
    except Exception as e:
        print(f"  geocoding failed: {e}")
        lat = _ask_float("Latitude (decimal)", cur.get("OFFICE_LAT"))
        lng = _ask_float("Longitude (decimal)", cur.get("OFFICE_LNG"))

    extra_default = ", ".join(cur_areas[1:]) if len(cur_areas) > 1 else ""
    extra_raw = _ask(
        "Other nearby areas to also search (comma-separated, optional)",
        extra_default or "")
    extra_areas = [a.strip() for a in extra_raw.split(",") if a.strip()]
    areas = [main_area] + extra_areas

    radius = _ask_float("Maximum distance from your area (km)",
                        cur.get("MAX_RADIUS_KM", 5.0))

    bhk_default = cur.get("PROPERTY_TYPE", "1bhk")
    bhk = _ask_choice("Bedrooms", ["1bhk", "2bhk", "3bhk", "1rk"],
                      bhk_default)

    num_people = _ask_int("How many people will live there?",
                          cur.get("NUM_PEOPLE", 1), min_val=1)

    furn_default = cur.get("FURNISHING", "any")
    furnishing = _ask_choice(
        "Furnishing",
        ["any", "furnished", "semi-furnished", "unfurnished"],
        furn_default)

    min_rent = _ask_int("Minimum monthly rent (₹)",
                        cur.get("MIN_RENT", 3000), min_val=0)
    max_rent = _ask_int("Maximum monthly rent (₹)",
                        cur.get("MAX_RENT", 15000), min_val=min_rent)

    interval_default = max(1, cur.get("CHECK_INTERVAL_SECONDS", 3600) // 3600)
    interval_hours = _ask_int("Check every how many hours?",
                              interval_default, min_val=1)

    print("\n  Telegram (https://t.me/BotFather → /newbot if you don't have one)")
    tg_token = _ask("  Bot token", env_cur.get("TELEGRAM_BOT_TOKEN"))
    tg_chat = _ask("  Chat ID", env_cur.get("TELEGRAM_CHAT_ID"))

    print("\n  Summary")
    print(f"    City:    {city}")
    print(f"    Areas:   {', '.join(areas)}")
    print(f"    Centre:  {lat:.4f}, {lng:.4f}")
    print(f"    Radius:  {radius} km")
    print(f"    Type:    {bhk}, {num_people} person(s), {furnishing}")
    print(f"    Budget:  ₹{min_rent:,} – ₹{max_rent:,} / month")
    print(f"    Cycle:   every {interval_hours} h")
    print()
    if not _ask_yesno("Save and apply?", default=True):
        print("aborted.")
        return

    values = dict(
        lat=lat, lng=lng, city=city, areas=areas,
        radius=radius, bhk=bhk, num_people=num_people,
        furnishing=furnishing, min_rent=min_rent, max_rent=max_rent,
        interval_hours=interval_hours,
    )

    Path("config.py").write_text(_render_config(values), encoding="utf-8")
    print("  wrote config.py")

    env_path = Path(".env")
    existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    new_env = _update_env(existing, {
        "TELEGRAM_BOT_TOKEN": tg_token,
        "TELEGRAM_CHAT_ID": tg_chat,
        "OFFICE_LAT": f"{lat:.6f}",
        "OFFICE_LNG": f"{lng:.6f}",
    })
    env_path.write_text(new_env, encoding="utf-8")
    print("  wrote .env (kept out of git)")

    workflow = Path(".github/workflows/monitor.yml")
    if workflow.exists():
        workflow.write_text(
            _patch_monitor_cron(workflow.read_text(encoding="utf-8"),
                                interval_hours),
            encoding="utf-8")
        print(f"  patched cron → every {interval_hours} h")

    if which("gh"):
        ok1 = _gh_set_secret("TELEGRAM_BOT_TOKEN", tg_token)
        ok2 = _gh_set_secret("TELEGRAM_CHAT_ID", tg_chat)
        if ok1 and ok2:
            print("  set GitHub Actions secrets via gh")
        else:
            print("  ⚠ couldn't set GitHub secrets — set them at:")
            print("    https://github.com/<you>/<repo>/settings/secrets/actions")
    else:
        print("  ⚠ gh CLI not found — set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
        print("    in GitHub → Settings → Secrets and variables → Actions")

    print("\n  testing Telegram…")
    if _send_telegram_test(tg_token, tg_chat):
        print("  ✓ message sent — check your Telegram")

    print()
    if _ask_yesno("Commit and push so GitHub starts running it?",
                  default=True):
        subprocess.run(
            ["git", "add", "config.py", ".github/workflows/monitor.yml"],
            check=False)
        subprocess.run(
            ["git", "commit", "-m", "chore: reconfigure rental monitor"],
            check=False)
        subprocess.run(["git", "push"], check=False)
        print("  pushed.")
    else:
        print("  (skipped — commit/push when ready)")

    print("\n  Done. GitHub will run the monitor on its own from now on.\n")


if __name__ == "__main__":
    main()
