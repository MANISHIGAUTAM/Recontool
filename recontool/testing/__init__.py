"""Test/demo support: in-process mock recon environment + fixtures.

This package is import-safe in production but only *used* when mode is demo/test.
It provides a deterministic, network-free environment so the full pipeline can be
exercised end-to-end without ever touching a real target or third-party provider.
"""
