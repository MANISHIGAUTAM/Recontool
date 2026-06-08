"""Event types and handler registry for the event-driven engine.

Events represent discoveries that trigger downstream actions. Each event type
maps to a set of handler functions that determine what adapters to dispatch next.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Callable


class EventType(str, enum.Enum):
    """All event types the engine can emit and react to."""

    NEW_SUBDOMAIN = "new_subdomain"
    HOST_VALIDATED_LIVE = "host_validated_live"
    NEW_JS_FILE = "new_js_file"
    NEW_ENDPOINT = "new_endpoint"
    NEW_PORT = "new_port"
    ARCHIVE_URL_FOUND = "archive_url_found"
    NEW_FINDING = "new_finding"
    CERT_SAN_DISCOVERED = "cert_san_discovered"
    FORM_DISCOVERED = "form_discovered"


@dataclass
class EngineEvent:
    """A single event emitted by the engine when a new entity is discovered."""

    type: EventType
    data: dict[str, Any]
    source_adapter: str = ""
    depth: int = 0
    branch_id: str = ""
    timestamp: float = 0.0

    @property
    def value(self) -> str:
        """Primary value of the event (hostname, URL, etc.)."""
        return self.data.get("value", "")


# Type alias for handler functions
HandlerFn = Callable[["EngineEvent"], list[str]]


class HandlerRegistry:
    """Maps event types to lists of handler functions.

    Handlers receive an event and return a list of adapter names to dispatch.
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[HandlerFn]] = {
            et: [] for et in EventType
        }

    def register(self, event_type: EventType, handler: HandlerFn) -> None:
        self._handlers[event_type].append(handler)

    def get_handlers(self, event_type: EventType) -> list[HandlerFn]:
        return list(self._handlers.get(event_type, []))

    def get_adapters_for(self, event: EngineEvent) -> list[str]:
        """Get all adapter names that should fire for this event."""
        adapters: list[str] = []
        for handler in self._handlers.get(event.type, []):
            adapters.extend(handler(event))
        return adapters


def build_default_registry() -> HandlerRegistry:
    """Build the default handler registry with standard recon logic.

    Maps each event type to the adapters that should run in response.
    """
    registry = HandlerRegistry()

    def on_new_subdomain(event: EngineEvent) -> list[str]:
        """New subdomain -> DNS resolve + passive lookup + HTTP probe."""
        return [
            "dns_resolve", "hackertarget", "crtsh", "certspotter",
            "http_probe",
        ]

    def on_host_live(event: EngineEvent) -> list[str]:
        """Host confirmed live -> crawl + port scan + screenshot + dir fuzz."""
        return [
            "crawler", "naabu", "gowitness", "ffuf",
        ]

    def on_new_js(event: EngineEvent) -> list[str]:
        """JS file discovered -> parse for endpoints and subdomains."""
        return ["js_analyzer"]

    def on_new_endpoint(event: EngineEvent) -> list[str]:
        """New endpoint -> param extraction + nuclei scan."""
        return ["param_extractor", "nuclei"]

    def on_new_port(event: EngineEvent) -> list[str]:
        """New port discovered -> service fingerprint."""
        return ["service_probe"]

    def on_archive_url(event: EngineEvent) -> list[str]:
        """Archive URL found -> download + parse."""
        return ["wayback_fetch"]

    def on_finding(event: EngineEvent) -> list[str]:
        """New finding -> no automatic dispatch (findings are terminal)."""
        return []

    def on_cert_san(event: EngineEvent) -> list[str]:
        """Cert SAN discovered -> treat as new subdomain for expansion."""
        return ["dns_resolve", "http_probe"]

    def on_form(event: EngineEvent) -> list[str]:
        """Form discovered -> param extraction."""
        return ["param_extractor"]

    registry.register(EventType.NEW_SUBDOMAIN, on_new_subdomain)
    registry.register(EventType.HOST_VALIDATED_LIVE, on_host_live)
    registry.register(EventType.NEW_JS_FILE, on_new_js)
    registry.register(EventType.NEW_ENDPOINT, on_new_endpoint)
    registry.register(EventType.NEW_PORT, on_new_port)
    registry.register(EventType.ARCHIVE_URL_FOUND, on_archive_url)
    registry.register(EventType.NEW_FINDING, on_finding)
    registry.register(EventType.CERT_SAN_DISCOVERED, on_cert_san)
    registry.register(EventType.FORM_DISCOVERED, on_form)

    return registry
