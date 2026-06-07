"""Atomic checks for content discovery (calibration/hit logic) and parameter/form
extraction. All network-free."""
from __future__ import annotations

from recontool.adapters.content_discovery import (
    BUILTIN_WORDLIST,
    HIT_STATUSES,
    is_hit,
    load_wordlist,
)
from recontool.adapters.params import extract_forms, params_from_url


# ── content discovery: hit vs calibrated not-found ───────────────────────────
def test_is_hit_basic_statuses():
    assert is_hit(200, 1000, None) is True
    assert is_hit(403, 50, None) is True
    assert is_hit(404, 200, None) is False
    assert is_hit(418, 10, None) is False        # not an interesting status


def test_is_hit_soft404_calibration():
    baseline = (200, 500)                         # server soft-404s with 200 + 500 bytes
    assert is_hit(200, 510, baseline) is False    # same-ish length -> not a real hit
    assert is_hit(200, 5000, baseline) is True    # very different length -> real hit
    assert is_hit(301, 100, baseline) is True     # different status -> real hit


def test_wordlist_nonempty_and_high_signal():
    wl = load_wordlist()
    assert len(wl) >= len(BUILTIN_WORDLIST)
    for must in (".git/config", ".env", "admin", "api", "robots.txt"):
        assert must in wl
    assert 200 in HIT_STATUSES and 403 in HIT_STATUSES


# ── parameter extraction from URLs ───────────────────────────────────────────
def test_params_from_url():
    assert params_from_url("https://x.com/s?q=1&page=2&q=3") == ["page", "q"]
    assert params_from_url("https://x.com/no-params") == []
    assert params_from_url("https://x.com/a?redirect=/home&id=") == ["id", "redirect"]


# ── form & input extraction from HTML ────────────────────────────────────────
FORM_HTML = """
<form action="/login" method="POST">
  <input name="username"><input name="password" type="password">
  <button name="submit">go</button>
</form>
<form action="https://api.example.com/search">
  <input name="q"><select name="category"></select>
</form>
<input name="loose_field">
"""


def test_extract_forms():
    forms = extract_forms("https://example.com/page", FORM_HTML)
    login = next(f for f in forms if f["action"].endswith("/login"))
    assert login["method"] == "post"
    assert login["params"] == ["password", "submit", "username"]
    search = next(f for f in forms if "api.example.com" in f["action"])
    assert search["params"] == ["category", "q"]
    # input outside any <form> is captured loosely
    assert any("loose_field" in f["params"] for f in forms)


def test_extract_forms_empty_safe():
    assert extract_forms("https://x.com/", "") == []
    assert isinstance(extract_forms("https://x.com/", "<form><broken"), list)


# ── registration ─────────────────────────────────────────────────────────────
def test_adapters_registered():
    from recontool.adapters.registry import all_adapters, load_builtin
    load_builtin()
    ad = all_adapters()
    assert "pydirb" in ad and ad["pydirb"].is_active is True
    assert "param_miner" in ad
    assert ad["pydirb"].category == "CAT-20"
