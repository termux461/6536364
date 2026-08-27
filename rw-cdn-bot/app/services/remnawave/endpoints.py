"""Remnawave REST endpoints, kept in one place.

Paths are relative to `<panel_url>/api` and are the same in panel API v2 and v3 — verified
against the v2.1.13 OpenAPI document and the v3 route contracts in remnawave/backend
(`libs/contract/api/controllers`). What differs between the two majors is payload and
response detail, and that lives in `dialects.py`.

Nothing here is invented: an operation that does not exist in the documented surface is
raised as RemnawaveUnsupportedOperation by the client instead of being guessed.

Note the update routes. `PATCH` goes to the **collection**, with the uuid in the request body
(`UpdateNodeRequestDto.uuid`, `UpdateHostRequestDto.uuid`, ...) — there is no
`PATCH /nodes/{uuid}` in either major, and calling one answers 404.
"""
from __future__ import annotations

# Config profiles
CONFIG_PROFILES = "/config-profiles"
CONFIG_PROFILE_UPDATE = "/config-profiles"  # PATCH on the collection, uuid goes in the body
CONFIG_PROFILE = "/config-profiles/{uuid}"  # GET, DELETE
CONFIG_PROFILE_INBOUNDS = "/config-profiles/{uuid}/inbounds"

# Nodes
NODES = "/nodes"
NODE_UPDATE = "/nodes"  # PATCH on the collection, uuid goes in the body
NODE = "/nodes/{uuid}"  # GET, DELETE
NODE_ENABLE = "/nodes/{uuid}/actions/enable"
NODE_DISABLE = "/nodes/{uuid}/actions/disable"
NODE_RESTART = "/nodes/{uuid}/actions/restart"

# Hosts
HOSTS = "/hosts"
HOST_UPDATE = "/hosts"  # PATCH on the collection, uuid goes in the body
HOST = "/hosts/{uuid}"  # GET, DELETE

# Internal squads (needed so the inbound is actually handed out to users)
INTERNAL_SQUADS = "/internal-squads"
INTERNAL_SQUAD_UPDATE = "/internal-squads"  # PATCH on the collection, uuid in the body
INTERNAL_SQUAD = "/internal-squads/{uuid}"  # GET, DELETE

# Keygen — the panel-wide node certificate that Remnanode expects as SECRET_KEY.
# One endpoint in both majors; only the field name in the response changed (see dialects.py).
KEYGEN = "/keygen"
# Not in either published contract, but reported by some builds. Tried only after /keygen.
KEYGEN_PUB_KEY = "/keygen/pub-key"

# System
SYSTEM_HEALTH = "/system/health"
SYSTEM_STATS = "/system/stats"
# v3 only — absent on v2, which is what makes it a clean version probe.
SYSTEM_METADATA = "/system/metadata"
