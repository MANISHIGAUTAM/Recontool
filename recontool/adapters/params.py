"""Parameter & form extraction (Category 25 — fuzz prep).

Two pure, testable helpers + one adapter:
  * params_from_url(url)      -> query-string parameter names
  * extract_forms(base, html) -> [{action, method, params[]}] from <form> elements
  * ParamMiner adapter        -> mines params from the discovered URL corpus and
                                 attaches them to endpoints (feeds fuzzing prep).

No network for the pure helpers; ParamMiner only reads URLs already in the store.
"""
from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import parse_qsl, urljoin, urlsplit

from recontool.adapters.base import Adapter, AdapterContext, Event
from recontool.adapters.registry import register


def params_from_url(url: str) -> list[str]:
    """Return sorted unique query-string parameter names from a URL."""
    try:
        q = urlsplit(url).query
    except Exception:  # noqa: BLE001
        return []
    return sorted({k for k, _ in parse_qsl(q, keep_blank_values=True)})


class _FormParser(HTMLParser):
    """Collect <form> action/method and contained input/select/textarea names."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms: list[dict] = []
        self._cur: dict | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self._cur = {"action": a.get("action", ""),
                         "method": (a.get("method") or "get").lower(),
                         "params": []}
        elif tag in ("input", "select", "textarea", "button"):
            name = a.get("name")
            if name:
                target = self._cur if self._cur is not None else _LOOSE
                target["params"].append(name)

    def handle_endtag(self, tag):
        if tag == "form" and self._cur is not None:
            self.forms.append(self._cur)
            self._cur = None


_LOOSE = {"params": []}  # inputs outside a <form> (collected loosely)


def extract_forms(base_url: str, html: str) -> list[dict]:
    """Parse forms + inputs from HTML. Returns [{action, method, params[]}]."""
    p = _FormParser()
    _LOOSE["params"] = []
    try:
        p.feed(html or "")
    except Exception:  # noqa: BLE001
        pass
    out = []
    for f in p.forms:
        action = urljoin(base_url, f["action"]) if f["action"] else base_url
        out.append({"action": action, "method": f["method"],
                    "params": sorted(set(f["params"]))})
    if _LOOSE["params"]:
        out.append({"action": base_url, "method": "get",
                    "params": sorted(set(_LOOSE["params"]))})
    return out


@register("p5_deep")
class ParamMiner(Adapter):
    name = "param_miner"
    category = "CAT-25"
    is_active = False          # only parses URLs already collected (no target contact)
    consumes = ("url",)
    produces = ("url",)

    async def run(self, ctx: AdapterContext) -> list[Event]:
        events: list[Event] = []
        for url in ctx.seeds_of("url"):
            params = params_from_url(url)
            if params:
                events.append(Event.endpoint(self.name, url, params=params,
                                              source="param_miner"))
        return events
