"""Remnawave REST endpoints, kept in one place.

Source: the official Remnawave panel API (v2.x) as exposed by remnawave/python-sdk.
Paths are relative to `<panel_url>/api`. Nothing here is invented — an operation that does not
exist in the documented surface is raised as RemnawaveUnsupportedOperation by the client
instead of being guessed.
"""
from __future__ import annotations

# Config profiles
CONFIG_PROFILES = "/config-profiles"
CONFIG_PROFILE = "/config-profiles/{uuid}"
CONFIG_PROFILE_INBOUNDS = "/config-profiles/{uuid}/inbounds"

# Nodes
NODES = "/nodes"
NODE = "/nodes/{uuid}"
NODE_ENABLE = "/nodes/{uuid}/actions/enable"
NODE_RESTART = "/nodes/{uuid}/actions/restart"

# Hosts
HOSTS = "/hosts"
HOST = "/hosts/{uuid}"

# Internal squads (needed so the inbound is actually handed out to users)
INTERNAL_SQUADS = "/internal-squads"
INTERNAL_SQUAD = "/internal-squads/{uuid}"

# Keygen — the panel-wide node certificate that Remnanode expects as SECRET_KEY.
# Newer builds expose it at /keygen/pub-key, older ones at /keygen.
KEYGEN_PUB_KEY = "/keygen/pub-key"
KEYGEN = "/keygen"

# System
SYSTEM_HEALTH = "/system/health"
SYSTEM_STATS = "/system/stats"
