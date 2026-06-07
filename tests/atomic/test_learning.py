"""Unit tests for the category-28 learning engine (wordlists + regex packs)."""
from __future__ import annotations

from recontool.learning import (
    learn_regex_pack,
    learn_wordlist,
    persist_regex_pack,
    persist_wordlist,
)


def test_wordlist_from_tech_seeds():
    wl = learn_wordlist(tech=["wordpress"])
    assert "wp-login.php" in wl.words and "wp-admin" in wl.words


def test_wordlist_from_url_paths():
    wl = learn_wordlist(urls=["https://x.com/api/v1/users", "https://x.com/admin/login"])
    assert {"api", "v1", "users", "admin", "login"} <= set(wl.words)


def test_wordlist_includes_params_and_base():
    wl = learn_wordlist(params=["redirect", "token"], base=["robots.txt"])
    assert {"redirect", "token", "robots.txt"} <= set(wl.words)


def test_wordlist_is_deterministic_and_sorted():
    a = learn_wordlist(tech=["php"], urls=["https://x.com/a/b"])
    b = learn_wordlist(tech=["php"], urls=["https://x.com/a/b"])
    assert a.words == b.words == sorted(a.words)
    assert a.sha256 == b.sha256


def test_regex_pack_always_has_secret_patterns():
    pack = learn_regex_pack()
    assert "aws_access_key" in pack.patterns and "jwt" in pack.patterns


def test_regex_pack_learns_params():
    pack = learn_regex_pack(params=["redirect_uri", "id"])
    assert "param_redirect_uri" in pack.patterns and "param_id" in pack.patterns
    # junk param names are rejected
    pack2 = learn_regex_pack(params=["bad name!", ""])
    assert not any(k.startswith("param_bad") for k in pack2.patterns)


def test_persist_wordlist_and_regex_pack(tmp_path):
    wl = learn_wordlist(tech=["express"])
    ref = persist_wordlist(tmp_path, wl)
    assert (tmp_path / ref).exists()
    assert ref.startswith("wordlists/")
    pack = learn_regex_pack(params=["q"])
    pref = persist_regex_pack(tmp_path, pack)
    assert (tmp_path / pref).exists() and pref.startswith("regex_packs/")
    # content-addressed: filename embeds the hash prefix
    assert wl.sha256[:12] in ref
