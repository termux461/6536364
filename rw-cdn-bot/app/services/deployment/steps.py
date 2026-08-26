"""Deployment state machine definition.

The order below is the contract: the worker walks it top to bottom, records every step in
`deployment_steps`, and can be restarted at any point — completed steps are skipped and every
create operation checks for an existing resource first.
"""
from __future__ import annotations

VALIDATE_DATA = "validate_data"
CHECK_ORIGIN = "check_origin"
PREPARE_ORIGIN = "prepare_origin"
CONFIGURE_FIREWALL = "configure_firewall"
CONFIGURE_SYSCTL = "configure_sysctl"
CONFIGURE_SWAP = "configure_swap"
INSTALL_DOCKER = "install_docker"
INSTALL_NGINX = "install_nginx"
CONFIGURE_SITE = "configure_site"
CONFIGURE_ORIGIN_DNS = "configure_origin_dns"
VERIFY_ORIGIN_DNS = "verify_origin_dns"
CONFIGURE_SSL = "configure_ssl"
CONFIGURE_NGINX = "configure_nginx"
CREATE_REMNAWAVE_PROFILE = "create_remnawave_profile"
CREATE_REMNAWAVE_NODE = "create_remnawave_node"
INSTALL_REMNANODE = "install_remnanode"
CREATE_REMNAWAVE_HOST = "create_remnawave_host"
CREATE_YANDEX_CERTIFICATE = "create_yandex_certificate"
CONFIGURE_ACME_DNS = "configure_acme_dns"
VERIFY_CERTIFICATE = "verify_certificate"
CREATE_YANDEX_CDN = "create_yandex_cdn"
GET_YANDEX_CNAME = "get_yandex_cname"
CONFIGURE_DNS = "configure_dns"
VERIFY_DNS = "verify_dns"
HEALTH_CHECK = "health_check"
COMPLETE = "complete"

STEP_ORDER: list[str] = [
    VALIDATE_DATA,
    CHECK_ORIGIN,
    PREPARE_ORIGIN,
    CONFIGURE_FIREWALL,
    CONFIGURE_SYSCTL,
    CONFIGURE_SWAP,
    INSTALL_DOCKER,
    INSTALL_NGINX,
    CONFIGURE_SITE,
    CONFIGURE_ORIGIN_DNS,
    VERIFY_ORIGIN_DNS,
    CONFIGURE_SSL,
    CONFIGURE_NGINX,
    CREATE_REMNAWAVE_PROFILE,
    CREATE_REMNAWAVE_NODE,
    INSTALL_REMNANODE,
    CREATE_REMNAWAVE_HOST,
    CREATE_YANDEX_CERTIFICATE,
    CONFIGURE_ACME_DNS,
    VERIFY_CERTIFICATE,
    CREATE_YANDEX_CDN,
    GET_YANDEX_CNAME,
    CONFIGURE_DNS,
    VERIFY_DNS,
    HEALTH_CHECK,
    COMPLETE,
]

STEP_TITLES: dict[str, str] = {
    VALIDATE_DATA: "Проверка данных",
    CHECK_ORIGIN: "Проверка Origin Server",
    PREPARE_ORIGIN: "Подготовка Origin Server",
    CONFIGURE_FIREWALL: "Firewall",
    CONFIGURE_SYSCTL: "BBR и лимиты",
    CONFIGURE_SWAP: "Swap",
    INSTALL_DOCKER: "Docker",
    INSTALL_NGINX: "Nginx",
    CONFIGURE_SITE: "Сайт-заглушка",
    CONFIGURE_ORIGIN_DNS: "DNS для Origin Domain",
    VERIFY_ORIGIN_DNS: "Проверка DNS Origin",
    CONFIGURE_SSL: "SSL-сертификат Origin",
    CONFIGURE_NGINX: "Конфигурация Nginx",
    CREATE_REMNAWAVE_PROFILE: "Remnawave Profile",
    CREATE_REMNAWAVE_NODE: "Remnawave Node",
    INSTALL_REMNANODE: "Установка Remnanode",
    CREATE_REMNAWAVE_HOST: "Remnawave Host",
    CREATE_YANDEX_CERTIFICATE: "Yandex Certificate",
    CONFIGURE_ACME_DNS: "DNS-проверка сертификата",
    VERIFY_CERTIFICATE: "Выпуск сертификата",
    CREATE_YANDEX_CDN: "Yandex Cloud CDN",
    GET_YANDEX_CNAME: "CNAME от Yandex",
    CONFIGURE_DNS: "DNS для CDN Domain",
    VERIFY_DNS: "Проверка DNS CDN",
    HEALTH_CHECK: "Health Check",
    COMPLETE: "Завершение",
}

# Steps the user sees in the progress message (the fine-grained ones are collapsed).
PROGRESS_STEPS: list[str] = [
    CHECK_ORIGIN,
    PREPARE_ORIGIN,
    INSTALL_DOCKER,
    CONFIGURE_SSL,
    CONFIGURE_NGINX,
    CREATE_REMNAWAVE_PROFILE,
    CREATE_REMNAWAVE_NODE,
    INSTALL_REMNANODE,
    CREATE_REMNAWAVE_HOST,
    CREATE_YANDEX_CERTIFICATE,
    CREATE_YANDEX_CDN,
    CONFIGURE_DNS,
    VERIFY_DNS,
    HEALTH_CHECK,
]
