"""Deployment orchestrator.

Walks the state machine defined in steps.py. Every step is idempotent and recorded, so a
worker restart resumes rather than starting over. Transient failures are retried with the
configured backoff; waiting states (DNS propagation, certificate issuance) park the
deployment instead of failing it.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.crypto import secret_box
from app.core.exceptions import (
    CertificatePending,
    DNSNotPropagated,
    PermanentError,
    TransientError,
    WaitingError,
)
from app.core.retry import retry_async
from app.models.enums import DeploymentStatus, OrderStatus, StepStatus, YandexAuthType
from app.repositories import AuditRepository, DeploymentRepository, InfraRepository, OrderRepository
from app.services.deployment import scripts
from app.services.deployment import steps as S
from app.services.deployment.context import DeployContext
from app.services.deployment.node_installer import NodeInstaller, render_compose, wait_until_connected
from app.services.deployment.steps import STEP_ORDER
from app.services.dns import (
    CloudflareDNSProvider,
    DNSProvider,
    DNSRecordSpec,
    ManualDNSProvider,
    YandexDNSProvider,
    verify_a_record,
    verify_cname_record,
)
from app.services.remnawave import RemnawaveClient
from app.services.remnawave.templates import INBOUND_TAG, PROFILE_NAME, XHTTP_PATH, XRAY_PORT
from app.services.ssh import SSHClient
from app.services.vault import purge_yandex_cookies, read_yandex_cookies
from app.services.yandex import ReauthRequired, YandexCloudClient

logger = logging.getLogger(__name__)

ProgressHook = Callable[[int], Awaitable[None]]


class DeploymentService:
    def __init__(self, session: AsyncSession, *, on_progress: ProgressHook | None = None) -> None:
        self.session = session
        self.settings = get_settings()
        self.orders = OrderRepository(session)
        self.deployments = DeploymentRepository(session)
        self.infra = InfraRepository(session)
        self.audit = AuditRepository(session)
        self.on_progress = on_progress
        self._ssh: SSHClient | None = None

    # ------------------------------------------------------------------ entry

    async def run(self, order_id: int) -> DeploymentStatus:
        order = await self.orders.get(order_id)
        if order is None:
            raise PermanentError(f"Order {order_id} not found")

        deployment = await self.deployments.get_or_create(order_id)
        await self.deployments.ensure_steps(deployment, STEP_ORDER)
        await self.deployments.set_status(deployment, DeploymentStatus.RUNNING)
        await self.orders.set_status(order, OrderStatus.DEPLOYING)
        await self.session.commit()

        context = DeployContext(
            order=order,
            deployment=deployment,
            origin=await self.infra.origin_or_create(order_id),
            remnawave=await self.infra.remnawave_or_create(order_id),
            resources=await self.infra.resources_or_create(order_id),
            yandex=await self.infra.yandex_or_create(order_id),
            cookies=await read_yandex_cookies(order_id),
        )

        try:
            status = await self._walk(context)
            if status in (
                DeploymentStatus.COMPLETED,
                DeploymentStatus.FAILED,
                DeploymentStatus.STOPPED,
            ):
                # Terminal run: nothing will need the session again.
                await self._forget_cookies(context)
            return status
        finally:
            if self._ssh is not None:
                await self._ssh.close()
                self._ssh = None

    async def _walk(self, context: DeployContext) -> DeploymentStatus:
        deployment = context.deployment
        for name in STEP_ORDER:
            step = await self.deployments.get_step(deployment.id, name)
            if step is None:
                continue
            if step.status == StepStatus.SUCCESS:
                continue

            handler = getattr(self, f"_step_{name}", None)
            if handler is None:
                await self.deployments.finish_step(step, StepStatus.SKIPPED)
                continue

            await self.deployments.start_step(step)
            await self.deployments.set_status(deployment, DeploymentStatus.RUNNING, current_step=name)
            await self._sync_order_stage(context, name)
            await self.session.commit()
            await self._notify(context.order.id)

            try:
                await retry_async(
                    lambda handler=handler, context=context: handler(context),
                    attempts=self.settings.deploy_max_attempts,
                    delays=self.settings.deploy_retry_delays,
                    retry_on=(TransientError, asyncio.TimeoutError, OSError),
                    label=f"step {name}",
                )
            except ReauthRequired as exc:
                # A dead credential is not a retryable fault and not a dead order: park the
                # deployment and ask a human for a fresh one.
                await self.deployments.finish_step(step, StepStatus.WAITING, str(exc))
                await self.deployments.set_status(
                    deployment, DeploymentStatus.WAITING_REAUTH, current_step=name, error=str(exc)
                )
                await self.audit.log(
                    "deployment.waiting_reauth", order_id=context.order.id, status="waiting",
                    message=f"{name}: {exc}",
                )
                await self.session.commit()
                await self._notify(context.order.id)
                return DeploymentStatus.WAITING_REAUTH
            except WaitingError as exc:
                await self.deployments.finish_step(step, StepStatus.WAITING, str(exc))
                status = (
                    DeploymentStatus.WAITING_CERTIFICATE
                    if isinstance(exc, CertificatePending)
                    else DeploymentStatus.WAITING_DNS
                )
                await self.deployments.set_status(deployment, status, current_step=name, error=str(exc))
                await self.audit.log(
                    "deployment.waiting", order_id=context.order.id, status="waiting",
                    message=f"{name}: {exc}",
                )
                await self.session.commit()
                await self._notify(context.order.id)
                return status
            except Exception as exc:  # noqa: BLE001
                detail = traceback.format_exc()
                logger.error("Deployment %s failed at %s: %s", deployment.id, name, detail)
                await self.deployments.finish_step(step, StepStatus.FAILED, str(exc)[:4000])
                await self.deployments.set_status(
                    deployment, DeploymentStatus.FAILED, current_step=name, error=str(exc)[:4000]
                )
                await self.orders.set_status(context.order, OrderStatus.FAILED, error=str(exc)[:2000])
                await self.audit.log(
                    "deployment.failed", order_id=context.order.id, status="error",
                    message=f"{name}: {detail}",
                )
                await self.session.commit()
                await self._notify(context.order.id)
                return DeploymentStatus.FAILED

            await self.deployments.finish_step(step, StepStatus.SUCCESS)
            await self.session.commit()
            await self._notify(context.order.id)

        await self.deployments.set_status(deployment, DeploymentStatus.COMPLETED, current_step=S.COMPLETE)
        await self.orders.set_status(context.order, OrderStatus.COMPLETED)
        await self.audit.log("deployment.completed", order_id=context.order.id)
        await self.session.commit()
        await self._notify(context.order.id)
        return DeploymentStatus.COMPLETED

    async def _notify(self, order_id: int) -> None:
        if self.on_progress is not None:
            try:
                await self.on_progress(order_id)
            except Exception:
                logger.warning("Progress hook failed", exc_info=True)

    async def _sync_order_stage(self, context: DeployContext, step: str) -> None:
        stage = {
            S.CHECK_ORIGIN: OrderStatus.CONFIGURING_ORIGIN,
            S.PREPARE_ORIGIN: OrderStatus.CONFIGURING_ORIGIN,
            S.CONFIGURE_NGINX: OrderStatus.CONFIGURING_ORIGIN,
            S.CREATE_REMNAWAVE_PROFILE: OrderStatus.CONFIGURING_REMNAWAVE,
            S.CREATE_YANDEX_CERTIFICATE: OrderStatus.CONFIGURING_YANDEX,
            S.CONFIGURE_DNS: OrderStatus.CONFIGURING_DNS,
            S.HEALTH_CHECK: OrderStatus.CHECKING,
        }.get(step)
        if stage is not None and context.order.status != stage:
            await self.orders.set_status(context.order, stage)

    # ------------------------------------------------------------- helpers

    async def ssh(self, context: DeployContext) -> SSHClient:
        if self._ssh is None:
            client = SSHClient(
                context.ssh_credentials(),
                connect_timeout=self.settings.ssh_timeout,
                command_timeout=self.settings.ssh_command_timeout,
            )
            await client.connect()
            self._ssh = client
        return self._ssh

    def remnawave(self, context: DeployContext) -> RemnawaveClient:
        url, token = context.remnawave_credentials()
        return RemnawaveClient(url, token)

    def yandex(self, context: DeployContext) -> YandexCloudClient:
        return YandexCloudClient(
            folder_id=context.yandex.folder_id or "", auth=context.yandex_auth()
        )

    def dns_provider(self, context: DeployContext) -> DNSProvider:
        """Cloudflare if a token was supplied, Cloud DNS if the zone lives in the folder, else manual."""
        stored = dict(context.deployment.context or {})
        token_enc = stored.get("cloudflare_token_enc")
        if token_enc:
            token = secret_box().decrypt(token_enc)
            if token:
                return CloudflareDNSProvider(token)
        if stored.get("dns_provider") == "yandex":
            return YandexDNSProvider(self.yandex(context))
        return ManualDNSProvider()

    # --------------------------------------------------------------- steps

    async def _step_validate_data(self, context: DeployContext) -> None:
        missing: list[str] = []
        if not context.origin_ip:
            missing.append("Origin Server IP")
        if not context.origin_domain:
            missing.append("Origin Domain")
        if not context.cdn_domain:
            missing.append("CDN Domain")
        if not context.origin.ssh_private_key_enc and not context.origin.ssh_password_enc:
            missing.append("SSH credentials")
        if not context.remnawave.panel_url or not context.remnawave.api_token_enc:
            missing.append("Remnawave URL / API token")
        if not context.yandex.folder_id:
            missing.append("Yandex Folder ID")
        if not context.origin.letsencrypt_email:
            missing.append("Email для Let's Encrypt")
        if missing:
            raise PermanentError("Не хватает данных: " + ", ".join(missing))

        if not self._has_yandex_credentials(context):
            # A cookie session that is simply gone (vault TTL, or a restart between the bot
            # and the worker) is a credential to replace, not a broken order: park it in
            # waiting_reauth so /reauth can pick the deployment back up at this same step.
            if (context.yandex.auth_type or YandexAuthType.SERVICE_ACCOUNT) == YandexAuthType.COOKIE:
                raise ReauthRequired(
                    "Сессия Yandex не сохранилась — пришлите свежие cookie командой /reauth"
                )
            raise PermanentError("Не хватает данных: данные доступа к Yandex Cloud")

        if context.origin_domain == context.cdn_domain:
            raise PermanentError("Origin Domain и CDN Domain должны различаться")

        # Fail on missing roles here, at step 1, instead of half-way through when the
        # certificate request comes back 403 with the server already reconfigured.
        stored = dict(context.deployment.context or {})
        report = await self.yandex(context).check_access(
            need_dns=stored.get("dns_provider") == "yandex"
        )
        if report.denied:
            raise PermanentError(
                "Не хватает прав в Yandex Cloud:\n"
                + report.describe()
                + "\nВыдайте роли на каталог "
                + (context.yandex.folder_id or "")
            )
        if report.failed:
            raise TransientError("Yandex Cloud недоступен: " + report.describe())

    @staticmethod
    def _has_yandex_credentials(context: DeployContext) -> bool:
        """Each auth method carries its credential somewhere different."""
        auth_type = context.yandex.auth_type or YandexAuthType.SERVICE_ACCOUNT
        if auth_type == YandexAuthType.COOKIE:
            return bool(context.cookies)
        if auth_type == YandexAuthType.OAUTH:
            return bool(context.yandex.oauth_token_enc)
        return bool(context.yandex.service_account_key_enc)

    async def _step_check_origin(self, context: DeployContext) -> None:
        ssh = await self.ssh(context)
        if not await ssh.check_connection():
            raise TransientError("Origin Server не отвечает на SSH")
        facts = await ssh.gather_facts()
        context.facts = {
            "os": facts.os_name,
            "cpu": facts.cpu_cores,
            "ram_mb": facts.ram_mb,
            "disk_free_mb": facts.disk_free_mb,
            "internet": facts.has_internet,
        }
        context.origin.os_info = facts.os_name[:255]
        context.origin.cpu_cores = facts.cpu_cores
        context.origin.ram_mb = facts.ram_mb
        context.origin.disk_free_mb = facts.disk_free_mb
        context.origin.origin_status = "ready"
        await self.deployments.update_context(context.deployment, {"facts": context.facts})

        if not facts.has_internet:
            raise PermanentError("У Origin Server нет доступа в интернет")
        if facts.disk_free_mb and facts.disk_free_mb < 3000:
            raise PermanentError(f"Недостаточно места на диске: {facts.disk_free_mb} MB")

    async def _step_prepare_origin(self, context: DeployContext) -> None:
        ssh = await self.ssh(context)
        await ssh.run_script(scripts.prepare_packages(), name="packages", timeout=900)

    async def _step_configure_firewall(self, context: DeployContext) -> None:
        ssh = await self.ssh(context)
        await ssh.run_script(scripts.configure_firewall(context.origin.ssh_port), name="ufw")

    async def _step_configure_sysctl(self, context: DeployContext) -> None:
        ssh = await self.ssh(context)
        await ssh.run_script(scripts.configure_sysctl(), name="sysctl")
        await ssh.run_script(scripts.configure_nginx_limits(), name="nginxlimits")

    async def _step_configure_swap(self, context: DeployContext) -> None:
        ssh = await self.ssh(context)
        await ssh.run_script(scripts.configure_swap(), name="swap")

    async def _step_install_docker(self, context: DeployContext) -> None:
        ssh = await self.ssh(context)
        await ssh.run_script(scripts.install_docker(), name="docker", timeout=900)

    async def _step_install_nginx(self, context: DeployContext) -> None:
        ssh = await self.ssh(context)
        await ssh.execute("systemctl enable --now nginx")

    async def _step_configure_site(self, context: DeployContext) -> None:
        ssh = await self.ssh(context)
        await ssh.run_script(scripts.create_placeholder_site(), name="site")
        await ssh.run_script(scripts.bootstrap_nginx_http(context.origin_domain), name="vhost")

    async def _step_configure_origin_dns(self, context: DeployContext) -> None:
        provider = self.dns_provider(context)
        spec = DNSRecordSpec(name=context.origin_domain, record_type="A", value=context.origin_ip)
        if provider.automatic:
            record_id = await provider.create_record(spec)
            await self.infra.upsert_dns_record(
                order_id=context.order.id, provider=provider.name, record_type="A",
                name=spec.name, value=spec.value, external_id=record_id, status="created",
            )
        else:
            await self.infra.upsert_dns_record(
                order_id=context.order.id, provider=provider.name, record_type="A",
                name=spec.name, value=spec.value, external_id=None, status="manual_required",
            )

    async def _step_verify_origin_dns(self, context: DeployContext) -> None:
        if await verify_a_record(context.origin_domain, context.origin_ip):
            return
        raise DNSNotPropagated(
            f"A-запись {context.origin_domain} → {context.origin_ip} ещё не видна публичным резолверам"
        )

    async def _step_configure_ssl(self, context: DeployContext) -> None:
        ssh = await self.ssh(context)
        await ssh.run_script(
            scripts.issue_certificate(context.origin_domain, context.origin.letsencrypt_email or ""),
            name="certbot",
            timeout=600,
        )

    async def _step_configure_nginx(self, context: DeployContext) -> None:
        ssh = await self.ssh(context)
        await ssh.run_script(
            scripts.final_nginx_config(context.origin_domain, context.cdn_domain), name="nginxfinal"
        )

    async def _step_create_remnawave_profile(self, context: DeployContext) -> None:
        async with self.remnawave(context) as client:
            if not await client.health_check():
                raise TransientError("Панель Remnawave недоступна")
            profile = await client.ensure_profile(PROFILE_NAME)
            profile_uuid = str(profile.get("uuid") or profile.get("id"))
            inbound = await client.find_inbound(profile_uuid, INBOUND_TAG)
            if inbound is None:
                raise PermanentError(
                    f"В профиле {PROFILE_NAME} нет inbound {INBOUND_TAG} — проверьте конфигурацию профиля"
                )
            context.resources.profile_uuid = profile_uuid
            context.resources.profile_name = PROFILE_NAME
            context.resources.inbound_uuid = str(inbound.get("uuid") or inbound.get("id"))
            context.resources.inbound_tag = INBOUND_TAG
            context.remnawave.verified = True
            await self.session.flush()

    async def _step_create_remnawave_node(self, context: DeployContext) -> None:
        box = secret_box()
        # A secret already stored for this order (auto-resolved earlier, or pasted by an admin)
        # always wins, so a retry never swaps the container's key underneath a working node.
        override = box.decrypt(context.resources.node_secret_enc)
        async with self.remnawave(context) as client:
            node = await client.ensure_node(
                name=context.node_name,
                address=context.origin_ip,
                profile_uuid=context.resources.profile_uuid or "",
                inbound_uuid=context.resources.inbound_uuid or "",
            )
            node_uuid = str(node.get("uuid") or node.get("id"))
            context.resources.node_uuid = node_uuid
            context.resources.node_name = context.node_name
            secret = await client.node_install_secret(node_uuid, override=override)

        context.resources.node_secret_enc = box.encrypt(secret)
        context.resources.node_compose_enc = box.encrypt(render_compose())
        await self.session.flush()

    async def _step_install_remnanode(self, context: DeployContext) -> None:
        box = secret_box()
        secret = box.decrypt(context.resources.node_secret_enc)
        if not secret:
            raise PermanentError(
                "Нет SECRET_KEY для Remnawave Node — заполните его в админ-панели заказа"
            )

        ssh = await self.ssh(context)
        installer = NodeInstaller(ssh, secret=secret)
        result = await installer.install()

        context.resources.node_compose_enc = box.encrypt(installer.compose_yaml())
        context.deployment.context = {
            **(context.deployment.context or {}),
            "node_install": result.as_dict(),
        }
        await self.session.flush()

        if not result.running:
            raise TransientError("Контейнер remnanode не поднялся")

        async with self.remnawave(context) as client:
            node_uuid = context.resources.node_uuid or ""
            await client.enable_node(node_uuid)
            if await wait_until_connected(client, node_uuid):
                return
        raise TransientError("Remnawave Node не перешла в состояние connected")

    async def _step_create_remnawave_host(self, context: DeployContext) -> None:
        async with self.remnawave(context) as client:
            host = await client.ensure_host(
                profile_uuid=context.resources.profile_uuid or "",
                inbound_uuid=context.resources.inbound_uuid or "",
                cdn_domain=context.cdn_domain,
                node_uuid=context.resources.node_uuid,
            )
            context.resources.host_uuid = str(host.get("uuid") or host.get("id"))
            await client.add_inbound_to_squads(context.resources.inbound_uuid or "")
            await self.session.flush()

    async def _step_create_yandex_certificate(self, context: DeployContext) -> None:
        client = self.yandex(context)
        await client.activate_provider()
        certificate = await client.ensure_certificate(
            name=f"cdn-{context.order.id}", domain=context.cdn_domain
        )
        certificate_id = str(certificate.get("id"))
        context.yandex.certificate_id = certificate_id
        context.yandex.certificate_status = str(certificate.get("status") or "")
        challenge = client.dns_challenge(certificate, context.cdn_domain)
        if challenge:
            context.yandex.acme_challenge_name = challenge["name"]
            context.yandex.acme_challenge_type = challenge["type"]
            context.yandex.acme_challenge_value = challenge["value"]
        await self.session.flush()

    async def _step_configure_acme_dns(self, context: DeployContext) -> None:
        if not context.yandex.acme_challenge_name:
            # Certificate already issued in an earlier run — nothing to publish.
            status = await self.yandex(context).certificate_status(context.yandex.certificate_id or "")
            if status.upper() == "ISSUED":
                return
            raise TransientError("Yandex ещё не выдал параметры DNS-проверки")

        provider = self.dns_provider(context)
        spec = DNSRecordSpec(
            name=context.yandex.acme_challenge_name,
            record_type=context.yandex.acme_challenge_type or "CNAME",
            value=context.yandex.acme_challenge_value or "",
        )
        if provider.automatic:
            record_id = await provider.create_record(spec)
            status = "created"
        else:
            record_id, status = None, "manual_required"
        await self.infra.upsert_dns_record(
            order_id=context.order.id, provider=provider.name, record_type=spec.record_type,
            name=spec.name, value=spec.value, external_id=record_id, status=status,
        )

    async def _step_verify_certificate(self, context: DeployContext) -> None:
        client = self.yandex(context)
        status = await client.certificate_status(context.yandex.certificate_id or "")
        context.yandex.certificate_status = status
        await self.session.flush()
        if status.upper() == "ISSUED":
            return
        if status.upper() in ("INVALID", "REVOKED"):
            raise PermanentError(f"Сертификат Yandex в статусе {status}")
        raise CertificatePending(
            f"Сертификат для {context.cdn_domain} ещё в статусе {status} — ждём DNS-проверку"
        )

    async def _step_create_yandex_cdn(self, context: DeployContext) -> None:
        client = self.yandex(context)
        group = await client.ensure_origin_group(
            name=f"origin-{context.order.id}", origin_domain=context.origin_domain
        )
        group_id = str(group.get("id") or group.get("originGroupId") or "")
        if not group_id:
            raise TransientError("Yandex не вернул id origin-группы")
        context.yandex.origin_group_id = group_id

        # Yandex requires the certificate and the CDN resource to live in the same folder;
        # otherwise it fails with "folder ids of user and certificate don't match".
        certificate_id = context.yandex.certificate_id or ""
        if certificate_id:
            certificate = await client.get_certificate(certificate_id)
            cert_folder = str((certificate or {}).get("folderId") or "")
            if cert_folder and cert_folder != context.yandex.folder_id:
                raise PermanentError(
                    f"Сертификат лежит в каталоге {cert_folder}, а CDN создаётся в "
                    f"{context.yandex.folder_id} — Yandex требует один каталог"
                )

        resource = await client.ensure_cdn_resource(
            cdn_domain=context.cdn_domain,
            origin_group_id=group_id,
            origin_domain=context.origin_domain,
            certificate_id=certificate_id,
        )
        context.yandex.cdn_resource_id = str(resource.get("id") or "")
        await self.session.flush()
        if not context.yandex.cdn_resource_id:
            raise TransientError("Yandex не вернул id CDN-ресурса")

    async def _step_get_yandex_cname(self, context: DeployContext) -> None:
        cname = await self.yandex(context).get_provider_cname()
        context.yandex.cdn_cname = cname
        await self.session.flush()

    async def _forget_cookies(self, context: DeployContext) -> None:
        """Wipe the session the moment it stops being needed."""
        if context.cookies is None:
            return
        context.cookies = None
        await purge_yandex_cookies(context.order.id)
        await self.audit.log(
            "yandex.cookies_purged", order_id=context.order.id, message="сессия удалена"
        )

    async def _step_configure_dns(self, context: DeployContext) -> None:
        provider = self.dns_provider(context)
        spec = DNSRecordSpec(
            name=context.cdn_domain, record_type="CNAME", value=context.yandex.cdn_cname or ""
        )
        if not spec.value:
            raise TransientError("Нет CNAME от Yandex CDN")
        if provider.automatic:
            record_id = await provider.create_record(spec)
            status = "created"
        else:
            record_id, status = None, "manual_required"
        await self.infra.upsert_dns_record(
            order_id=context.order.id, provider=provider.name, record_type="CNAME",
            name=spec.name, value=spec.value, external_id=record_id, status=status,
        )
        # Last step that can touch Yandex: the DNS provider may be Cloud DNS, which needs the
        # same credentials. Dropping the session one step earlier broke every order whose zone
        # lives in the folder — the CNAME record was written with a credential already wiped.
        await self._forget_cookies(context)

    async def _step_verify_dns(self, context: DeployContext) -> None:
        if await verify_cname_record(context.cdn_domain, context.yandex.cdn_cname or ""):
            return
        raise DNSNotPropagated(
            f"CNAME {context.cdn_domain} → {context.yandex.cdn_cname} ещё не виден публичным резолверам"
        )

    async def _step_health_check(self, context: DeployContext) -> None:
        ssh = await self.ssh(context)
        result = await ssh.run_script(
            scripts.health_check_script(context.origin_domain, context.cdn_domain),
            name="health",
            timeout=180,
        )
        health = scripts.parse_health_output(result.stdout)
        context.health = health
        await self.deployments.update_context(context.deployment, {"health": health})

        problems: list[str] = []
        if health.get("nginx") != "active":
            problems.append("nginx не запущен")
        if health.get("docker") != "active":
            problems.append("docker не запущен")
        if not health.get("remnanode"):
            problems.append("контейнер remnanode не найден")
        if int(health.get("xray_local") or 0) < 1:
            problems.append(f"Xray не слушает 127.0.0.1:{scripts.XRAY_PORT}")
        if int(health.get("xray_public") or 0) > 0:
            problems.append(f"порт {XRAY_PORT} открыт наружу — это недопустимо")
        if str(health.get("origin")) != "200":
            problems.append(f"https://{context.origin_domain}/ вернул {health.get('origin')}")
        if str(health.get("cdn")) != "200":
            # CDN edge nodes can take 10–30 minutes to pick up the certificate.
            raise DNSNotPropagated(
                f"CDN ещё не отвечает 200 (получено {health.get('cdn')}); "
                "сертификат применяется на edge-нодах до 30 минут"
            )
        # 400 on the xHTTP path is the expected answer to a plain curl — it proves the path
        # reached Xray, and curl simply is not a VLESS/xHTTP client.
        for key, label in (("origin_xhttp", context.origin_domain), ("cdn_xhttp", context.cdn_domain)):
            code = str(health.get(key))
            if code not in ("400", "200", "404"):
                problems.append(f"https://{label}{XHTTP_PATH} вернул {code}")

        if problems:
            raise PermanentError("Health check не пройден: " + "; ".join(problems))

    async def _step_complete(self, context: DeployContext) -> None:
        await self.audit.log(
            "deployment.result",
            order_id=context.order.id,
            message=(
                f"origin={context.origin_domain} cdn={context.cdn_domain} "
                f"node={context.resources.node_uuid} host={context.resources.host_uuid} "
                f"cert={context.yandex.certificate_id} cdn_res={context.yandex.cdn_resource_id}"
            ),
        )
