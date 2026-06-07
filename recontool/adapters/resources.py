"""Category 28 — Wordlists & Recon Resources (the self-improvement lane).

This adapter reads what the system has learned so far (detected tech on assets,
harvested URL paths, discovered parameters) from the chaining inputs + artifact
store, generates a TUNED wordlist + regex pack (recontool/learning.py), and writes
them to the artifact lake. Those tuned resources feed content discovery (cat 20),
API/GraphQL recon (cat 23), and parameter discovery (cat 25) on the next pass.

Pure-local (no network), so it runs in any mode including demo/test.
"""
from __future__ import annotations

from recontool.adapters.base import Adapter, AdapterContext, Event
from recontool.adapters.registry import register
from recontool.learning import (
    learn_regex_pack,
    learn_wordlist,
    persist_regex_pack,
    persist_wordlist,
)


@register("p3_enrichment")
class WordlistLearner(Adapter):
    name = "wordlist_learner"
    category = "CAT-28"
    is_active = False                       # local only; touches nothing
    consumes = ("url", "subdomain", "tech")
    produces = ("wordlist", "regex_pack")

    def available(self, ctx: AdapterContext) -> bool:
        return True

    async def run(self, ctx: AdapterContext) -> list[Event]:
        urls = ctx.seeds_of("url")
        tech = ctx.seeds_of("tech")
        params: list[str] = []  # params arrive via endpoint records in later passes
        wl = learn_wordlist(tech=tech, urls=urls, params=params)
        pack = learn_regex_pack(params=params)
        events: list[Event] = []
        if wl.words:
            ref = persist_wordlist(ctx.artifacts.root.parent, wl)
            # record provenance as a finding-free edge/tag-style asset
            events.append(Event.asset(self.name, "wordlist", wl.sha256[:16],
                                      ref=ref, size=len(wl.words)))
        prefix_ref = persist_regex_pack(ctx.artifacts.root.parent, pack)
        events.append(Event.asset(self.name, "regex_pack", pack.sha256[:16],
                                  ref=prefix_ref, size=len(pack.patterns)))
        return events
