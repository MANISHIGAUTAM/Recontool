"""Recontool API / UI layer.

``data.py`` holds pure DB-read helpers (no web deps). ``app.py`` holds the
FastAPI wiring (requires the optional ``fastapi``/``uvicorn`` extras) and is
imported lazily by ``recontool serve`` so the core package stays importable
without the web stack installed.
"""
