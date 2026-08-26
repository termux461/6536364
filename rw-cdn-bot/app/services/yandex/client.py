"""Yandex Cloud client: Certificate Manager, Cloud CDN and Cloud DNS.

Endpoints used (public REST API):
  IAM          POST   https://iam.api.cloud.yandex.net/iam/v1/tokens
  Certificates POST   https://certificate-manager.api.cloud.yandex.net/certificate-manager/v1/certificates/requestNew
               GET    .../certificates/{id}?view=FULL           (returns challenges[].dnsChallenge)
               GET    .../certificates?folderId=&view=FULL
  CDN          POST   https://cdn.api.cloud.yandex.net/cdn/v1/originGroups
               POST   https://cdn.api.cloud.yandex.net/cdn/v1/resources
               GET    https://cdn.api.cloud.yandex.net/cdn/v1/resources/{id}
               GET    https://cdn.api.cloud.yandex.net/cdn/v1/resources?folderId=
               GET    https://cdn.api.cloud.yandex.net/cdn/v1/cname?folderId=   (provider CNAME)
               POST   https://cdn.api.cloud.yandex.net/cdn/v1/provider/activate
  DNS          GET    https://dns.api.cloud.yandex.net/dns/v1/zones?folderId=
               POST   https://dns.api.cloud.yandex.net/dns/v1/zones/{id}:updateRecordSets
  Operations   GET    https://operation.api.cloud.yandex.net/operations/{id}
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.exceptions import TransientError, YandexAPIError
from app.core.retry import retry_async
from app.services.remnawave.templates import CDN_HTTP_METHODS
from app.services.yandex.auth import AUTH_SERVICE_ACCOUNT, YandexAuth, build_auth

logger = logging.getLogger(__name__)

CM_URL = "https://certificate-manager.api.cloud.yandex.net/certificate-manager/v1"
CDN_URL = "https://cdn.api.cloud.yandex.net/cdn/v1"
DNS_URL = "https://dns.api.cloud.yandex.net/dns/v1"
RM_URL = "https://resource-manager.api.cloud.yandex.net/resource-manager/v1"
IAM_API_URL = "https://iam.api.cloud.yandex.net/iam/v1"
OPERATION_URL = "https://operation.api.cloud.yandex.net/operations"


def bool_option(value: bool, enabled: bool = True) -> dict:
    return {"enabled": enabled, "value": value}


# What the account behind the credentials must be able to do, and the role that grants it.
# Probed empirically (a real API call per capability), so the check is right even if Yandex
# renames a role — the role name is only what we suggest in the error message.
CAP_CERTIFICATES = "certificates"
CAP_CDN = "cdn"
CAP_DNS = "dns"

REQUIRED_ROLES = {
    CAP_CERTIFICATES: "certificate-manager.editor",
    CAP_CDN: "cdn.editor",
    CAP_DNS: "dns.editor",
}
CAP_TITLES = {
    CAP_CERTIFICATES: "выпуск сертификатов Let's Encrypt (Certificate Manager)",
    CAP_CDN: "создание CDN-ресурсов",
    CAP_DNS: "управление записями Cloud DNS",
}


def _reason(exc: BaseException) -> str:
    """A human-readable cause.

    Timeouts and several httpx errors stringify to an empty string, which produced messages
    that ended in a bare colon and told the user nothing. Fall back to the exception type,
    and name the common network cases outright.
    """
    text = str(exc).strip()
    if text:
        return text[:200]

    name = type(exc).__name__
    if "Timeout" in name:
        return f"таймаут подключения ({name}) — сервер не достучался до API Yandex"
    if "Connect" in name or "Network" in name or "Proxy" in name:
        return f"нет сетевого доступа к API Yandex ({name})"
    if "SSL" in name or "Certificate" in name:
        return f"ошибка TLS при обращении к API Yandex ({name})"
    return name


@dataclass(slots=True)
class AccessReport:
    """Result of a permission preflight, per capability."""

    granted: list[str] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.denied and not self.failed

    def missing_roles(self) -> list[str]:
        return [REQUIRED_ROLES[cap] for cap in self.denied if cap in REQUIRED_ROLES]

    def describe_denied(self) -> str:
        """Only the capabilities that came back 403 — these really are missing roles."""
        return "\n".join(
            f"нет прав на {CAP_TITLES.get(cap, cap)} — выдайте роль {REQUIRED_ROLES[cap]}"
            for cap in self.denied
        )

    def describe_failed(self) -> str:
        """Probes that never got an answer. Not a permission problem — do not say it is.

        All capabilities failing with the same reason means the cause is upstream of any
        single service (bad credentials, unreachable API), so it is reported once.
        """
        if not self.failed:
            return ""
        reasons = set(self.failed.values())
        if len(reasons) == 1:
            return reasons.pop()
        return "\n".join(
            f"{CAP_TITLES.get(cap, cap)}: {reason}" for cap, reason in self.failed.items()
        )

    def describe(self) -> str:
        parts = [self.describe_denied(), self.describe_failed()]
        return "\n".join(p for p in parts if p)


class YandexCloudClient:
    def __init__(
        self,
        service_account_key: str | dict | None = None,
        folder_id: str = "",
        *,
        auth: YandexAuth | None = None,
        timeout: int = 45,
    ) -> None:
        """Either pass a ready `auth` provider, or a service account key for the default one."""
        self.folder_id = folder_id
        self._auth = auth or build_auth(
            auth_type=AUTH_SERVICE_ACCOUNT, service_account_key=service_account_key  # type: ignore[arg-type]
        )
        self._timeout = timeout

    @property
    def auth(self) -> YandexAuth:
        return self._auth

    async def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {await self._auth.token()}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, url: str, *, attempts: int = 3, **kwargs) -> Any:
        async def _call() -> Any:
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.request(
                        method, url, headers=await self._headers(), **kwargs
                    )
            except httpx.HTTPError as exc:
                # httpx errors are not OSError, so retry_async would let them straight through
                # and the step would fail permanently on what is a plain network hiccup. The
                # endpoint is deliberately left out of the message: retry_async already logs
                # it, and an identical cause across probes has to render as one line in
                # AccessReport.describe_failed() rather than one per service.
                raise TransientError(_reason(exc)) from exc
            if response.status_code in (429, 500, 502, 503, 504):
                raise TransientError(f"Yandex {url} -> HTTP {response.status_code}")
            if response.status_code == 404 and method.upper() == "GET":
                return None
            if response.status_code >= 400:
                raise YandexAPIError(response.status_code, response.text, url)
            return response.json() if response.content else None

        return await retry_async(_call, attempts=attempts, label=f"yandex {method} {url}")

    async def _list(
        self, url: str, key: str, *, attempts: int = 3, params: dict | None = None
    ) -> list[dict]:
        """Read every page of a list endpoint.

        Yandex caps a page at 100 items and hands back `nextPageToken`. Reading only the first
        page made `find_certificate` and `find_cdn_resource` miss objects that already exist,
        so a re-run created a duplicate instead of reusing one — and a folder with more than
        100 certificates could never converge.
        """
        collected: list[dict] = []
        query = dict(params or {})
        seen_tokens: set[str] = set()
        while True:
            data = await self._request("GET", url, attempts=attempts, params=query)
            page = (data or {}).get(key) or []
            collected.extend(item for item in page if isinstance(item, dict))
            token = str((data or {}).get("nextPageToken") or "")
            if not token or token in seen_tokens:
                return collected
            seen_tokens.add(token)
            query["pageToken"] = token

    # --------------------------------------------------- resource discovery

    async def list_clouds(self, *, attempts: int = 3) -> list[dict]:
        return await self._list(f"{RM_URL}/clouds", "clouds", attempts=attempts)

    async def list_folders(self, cloud_id: str, *, attempts: int = 3) -> list[dict]:
        return await self._list(
            f"{RM_URL}/folders", "folders", attempts=attempts, params={"cloudId": cloud_id}
        )

    async def discover_scope(self) -> dict:
        """What this credential can actually see: clouds and the folders inside them.

        Lets the bot fill in Cloud ID and Folder ID instead of asking the customer to hunt
        for them in the console. A single cloud with a single folder needs no question at all.
        """
        clouds = await self.list_clouds()
        scope: dict = {"clouds": clouds, "folders": {}}
        for cloud in clouds:
            cloud_id = str(cloud.get("id") or "")
            if cloud_id:
                scope["folders"][cloud_id] = await self.list_folders(cloud_id)
        return scope

    # ----------------------------------------------------------- role granting

    async def user_id_by_login(self, login: str) -> str | None:
        """Resolve a Yandex login to the account id used in access bindings."""
        try:
            data = await self._request(
                "GET",
                f"{IAM_API_URL}/yandexPassportUserAccounts:byLogin",
                attempts=1,
                params={"login": login.strip().lstrip("@")},
            )
        except YandexAPIError as exc:
            if exc.status in (403, 404):
                return None
            raise
        return str((data or {}).get("id") or "") or None

    async def folder_access_bindings(self, folder_id: str) -> list[dict]:
        data = await self._request(
            "GET", f"{RM_URL}/folders/{folder_id}:listAccessBindings", attempts=1
        )
        return list((data or {}).get("accessBindings") or [])

    async def grant_roles(
        self, folder_id: str, *, subject_id: str, subject_type: str, roles: list[str]
    ) -> None:
        """Add role bindings on the folder.

        Uses updateAccessBindings with ADD deltas, never setAccessBindings — the latter
        replaces every binding on the resource and would silently delete the customer's
        existing access.
        """
        deltas = [
            {
                "action": "ADD",
                "accessBinding": {
                    "roleId": role,
                    "subject": {"id": subject_id, "type": subject_type},
                },
            }
            for role in roles
        ]
        operation = await self._request(
            "POST",
            f"{RM_URL}/folders/{folder_id}:updateAccessBindings",
            attempts=1,
            json={"accessBindingDeltas": deltas},
        )
        await self.wait_operation(operation)

    async def ensure_roles(self, folder_id: str, report: AccessReport, *, subject: dict) -> bool:
        """Try to grant whatever the preflight found missing. True if anything was granted.

        Only works when the credential itself may manage access on the folder — a cloud owner
        can, a locked-down service account cannot. A 403 here is an expected outcome, not a
        failure worth raising: the caller falls back to asking a human.
        """
        roles = report.missing_roles()
        if not roles or not subject.get("id"):
            return False
        try:
            await self.grant_roles(
                folder_id,
                subject_id=str(subject["id"]),
                subject_type=str(subject.get("type") or "userAccount"),
                roles=roles,
            )
        except YandexAPIError as exc:
            if exc.status in (401, 403):
                logger.info("Cannot self-grant roles on %s: no admin rights", folder_id)
                return False
            raise
        return True

    # ------------------------------------------------------------------ access

    async def check_access(self, *, need_dns: bool = False) -> AccessReport:
        """Verify the account can actually do the three things a deployment needs.

        Runs a cheap read against each service. A 403 means the role is missing; anything
        else is reported separately so a transient outage is not mistaken for a permission
        problem. Cookie and OAuth auth act as the user, service account auth as the robot —
        either way the folder-level roles have to be there.
        """
        report = AccessReport()
        probes: list[tuple[str, Any]] = [
            (CAP_CERTIFICATES, self.list_certificates),
            (CAP_CDN, self.list_cdn_resources),
        ]
        if need_dns:
            probes.append((CAP_DNS, self.list_dns_zones))

        for capability, probe in probes:
            try:
                # One attempt: this is a preflight, not the real call. Retrying a 5xx here
                # would make the check take a minute for no extra information.
                await probe(attempts=1)
            except YandexAPIError as exc:
                if exc.status in (401, 403):
                    report.denied.append(capability)
                else:
                    report.failed[capability] = f"HTTP {exc.status}"
            except TransientError as exc:
                report.failed[capability] = _reason(exc)
            except Exception as exc:  # noqa: BLE001 — a probe must never abort the check
                report.failed[capability] = _reason(exc)
            else:
                report.granted.append(capability)
        return report

    # -------------------------------------------------------------- operations

    async def wait_operation(
        self, operation: dict | None, *, timeout: int = 300, interval: int = 5
    ) -> dict:
        """Block until an Operation is done; raises on operation error.

        A 204 or an empty body leaves `operation` as None — that is a completed call with
        nothing to poll, not a crash.
        """
        operation = operation or {}
        if operation.get("done"):
            return operation
        operation_id = operation.get("id")
        if not operation_id:
            return operation
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            current = await self._request("GET", f"{OPERATION_URL}/{operation_id}")
            if current and current.get("done"):
                if current.get("error"):
                    raise YandexAPIError(400, str(current["error"]), f"operations/{operation_id}")
                return current
            await asyncio.sleep(interval)
        raise TransientError(f"Yandex operation {operation_id} did not finish in {timeout}s")

    # ------------------------------------------------------------ certificates

    async def list_certificates(self, *, attempts: int = 3) -> list[dict]:
        return await self._list(
            f"{CM_URL}/certificates",
            "certificates",
            attempts=attempts,
            params={"folderId": self.folder_id, "view": "FULL"},
        )

    async def find_certificate(self, domain: str) -> dict | None:
        for certificate in await self.list_certificates():
            if domain in (certificate.get("domains") or []):
                return certificate
        return None

    async def create_certificate(self, *, name: str, domain: str) -> dict:
        """Request a Let's Encrypt certificate validated by a DNS CNAME challenge."""
        payload = {
            "folderId": self.folder_id,
            "name": name,
            "domains": [domain],
            "challengeType": "DNS_CNAME",
        }
        operation = await self._request("POST", f"{CM_URL}/certificates/requestNew", json=payload)
        done = await self.wait_operation(operation, timeout=120)
        response = done.get("response") or {}
        certificate_id = response.get("id") or (done.get("metadata") or {}).get("certificateId")
        if not certificate_id:
            raise YandexAPIError(500, str(done), "certificates/requestNew")
        return await self.get_certificate(certificate_id) or {"id": certificate_id}

    async def get_certificate(self, certificate_id: str) -> dict | None:
        return await self._request(
            "GET", f"{CM_URL}/certificates/{certificate_id}", params={"view": "FULL"}
        )

    async def ensure_certificate(self, *, name: str, domain: str) -> dict:
        existing = await self.find_certificate(domain)
        if existing:
            logger.info("Reusing existing Yandex certificate for %s", domain)
            return existing
        return await self.create_certificate(name=name, domain=domain)

    @staticmethod
    def dns_challenge(certificate: dict, domain: str) -> dict | None:
        """Extract the _acme-challenge CNAME that Yandex expects for the domain."""
        for challenge in certificate.get("challenges") or []:
            if challenge.get("domain") != domain:
                continue
            dns = challenge.get("dnsChallenge")
            if dns:
                return {
                    "name": dns.get("name", "").rstrip("."),
                    "type": dns.get("type", "CNAME"),
                    "value": dns.get("value", "").rstrip("."),
                }
        return None

    async def certificate_status(self, certificate_id: str) -> str:
        certificate = await self.get_certificate(certificate_id)
        return str((certificate or {}).get("status") or "UNKNOWN")

    # --------------------------------------------------------------------- CDN

    async def activate_provider(self) -> None:
        """Idempotent: activating an already active provider is not an error we need to surface."""
        try:
            await self._request(
                "POST",
                f"{CDN_URL}/provider/activate",
                json={"folderId": self.folder_id, "providerType": "ourcdn"},
            )
        except YandexAPIError as exc:
            if exc.status in (409, 400):
                logger.info("Yandex CDN provider already activated for folder %s", self.folder_id)
                return
            raise

    async def list_origin_groups(self) -> list[dict]:
        return await self._list(
            f"{CDN_URL}/originGroups", "originGroups", params={"folderId": self.folder_id}
        )

    async def ensure_origin_group(self, *, name: str, origin_domain: str) -> dict:
        for group in await self.list_origin_groups():
            if group.get("name") == name:
                return group
        payload = {
            "folderId": self.folder_id,
            "name": name,
            "useNext": True,
            "origins": [{"source": origin_domain, "enabled": True, "backup": False}],
        }
        operation = await self.wait_operation(
            await self._request("POST", f"{CDN_URL}/originGroups", json=payload), timeout=180
        )
        return operation.get("response") or {}

    async def list_cdn_resources(self, *, attempts: int = 3) -> list[dict]:
        return await self._list(
            f"{CDN_URL}/resources",
            "resources",
            attempts=attempts,
            params={"folderId": self.folder_id},
        )

    async def find_cdn_resource(self, cname: str) -> dict | None:
        for resource in await self.list_cdn_resources():
            if resource.get("cname") == cname:
                return resource
        return None

    async def get_cdn_resource(self, resource_id: str) -> dict | None:
        return await self._request("GET", f"{CDN_URL}/resources/{resource_id}")

    def _vpn_resource_options(self, origin_domain: str) -> dict:
        """CDN must pass requests through untouched.

        No caching, no gzip, no large-file segmentation, no query-param caching. `ignoreCookie`
        only affects cache keys — the Cookie header itself still reaches the origin, which xHTTP
        needs for its `chunk` and `visitor_id` values.
        """
        return {
            "disableCache": bool_option(True),
            "edgeCacheSettings": {"enabled": True, "defaultValue": "0"},
            "browserCacheSettings": {"enabled": True, "value": "0"},
            "ignoreQueryParams": bool_option(True),
            "ignoreCookie": bool_option(True),
            "gzipOn": bool_option(False),
            "fetchedCompressed": bool_option(False),
            "slice": bool_option(False),
            "disableProxyForceRanges": bool_option(True),
            "redirectHttpToHttps": bool_option(False),
            "forwardHostHeader": bool_option(False),
            "hostOptions": {"host": {"enabled": True, "value": origin_domain}},
            "allowedHttpMethods": {"enabled": True, "value": list(CDN_HTTP_METHODS)},
        }

    async def create_cdn_resource(
        self, *, cdn_domain: str, origin_group_id: str, origin_domain: str, certificate_id: str
    ) -> dict:
        payload = {
            "folderId": self.folder_id,
            "cname": cdn_domain,
            "origin": {"originGroupId": str(origin_group_id)},
            "originProtocol": "HTTPS",
            "active": True,
            "options": self._vpn_resource_options(origin_domain),
            "sslCertificate": {"type": "CM", "data": {"cm": {"id": certificate_id}}},
        }
        operation = await self.wait_operation(
            await self._request("POST", f"{CDN_URL}/resources", json=payload), timeout=300
        )
        return operation.get("response") or {}

    async def ensure_cdn_resource(
        self, *, cdn_domain: str, origin_group_id: str, origin_domain: str, certificate_id: str
    ) -> dict:
        existing = await self.find_cdn_resource(cdn_domain)
        if existing:
            logger.info("Reusing existing Yandex CDN resource for %s", cdn_domain)
            return existing
        return await self.create_cdn_resource(
            cdn_domain=cdn_domain,
            origin_group_id=origin_group_id,
            origin_domain=origin_domain,
            certificate_id=certificate_id,
        )

    async def update_cdn_resource(self, resource_id: str, **fields) -> dict:
        operation = await self._request(
            "PATCH", f"{CDN_URL}/resources/{resource_id}", json={"resourceId": resource_id, **fields}
        )
        return await self.wait_operation(operation, timeout=300)

    async def delete_cdn_resource(self, resource_id: str) -> None:
        operation = await self._request("DELETE", f"{CDN_URL}/resources/{resource_id}")
        await self.wait_operation(operation, timeout=180)

    async def get_provider_cname(self) -> str:
        """The generated edge endpoint (….edgecdn.ru / ….yccdn.cloud.yandex.net). Never hardcoded."""
        data = await self._request("GET", f"{CDN_URL}/cname", params={"folderId": self.folder_id})
        cname = (data or {}).get("cname")
        if not cname:
            raise YandexAPIError(500, str(data), "cdn/v1/cname")
        return str(cname).rstrip(".")

    # --------------------------------------------------------------- Cloud DNS

    async def list_dns_zones(self, *, attempts: int = 3) -> list[dict]:
        return await self._list(
            f"{DNS_URL}/zones", "dnsZones", attempts=attempts, params={"folderId": self.folder_id}
        )

    async def find_dns_zone(self, fqdn: str) -> dict | None:
        """Longest-suffix match, so sub.example.com resolves to the example.com zone."""
        best: dict | None = None
        for zone in await self.list_dns_zones():
            zone_name = str(zone.get("zone") or "").rstrip(".")
            if not zone_name:
                continue
            if (fqdn == zone_name or fqdn.endswith("." + zone_name)) and (
                best is None or len(zone_name) > len(str(best.get("zone")).rstrip("."))
            ):
                best = zone
        return best

    async def upsert_dns_record(
        self, *, zone_id: str, name: str, record_type: str, value: str, ttl: int = 300
    ) -> None:
        payload = {
            "deletions": [],
            "replacements": [
                {"name": name if name.endswith(".") else name + ".", "type": record_type,
                 "ttl": ttl, "data": [value]}
            ],
        }
        operation = await self._request(
            "POST", f"{DNS_URL}/zones/{zone_id}:updateRecordSets", json=payload
        )
        await self.wait_operation(operation, timeout=120)
