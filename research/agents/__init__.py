"""Optional agent integration package."""

from __future__ import annotations

__all__ = ["is_agents_sdk_available"]


def is_agents_sdk_available() -> bool:
    try:
        import agents  # noqa: F401
    except ImportError:
        return False
    return True
