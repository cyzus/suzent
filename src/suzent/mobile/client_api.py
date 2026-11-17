"""Compatibility routes for the original paired-client API."""

from suzent.api.resources import relay_field, revocable_stream
from suzent.api.router import build_legacy_routes

client_routes = build_legacy_routes()

__all__ = ["client_routes", "relay_field", "revocable_stream"]
