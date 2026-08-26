"""Bash fragments executed on the Origin Server.

Everything is idempotent: re-running a step must not break an already-configured machine.
Values are injected by the caller; nothing about the customer is baked in here.
"""
from __future__ import annotations

import json
import shlex

from app.services.remnawave.templates import XHTTP_PATH, XRAY_PORT

PACKAGES = "ca-certificates curl ufw nginx certbot"


def prepare_packages() -> str:
    return f"""
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y {PACKAGES}
"""


def install_docker() -> str:
    return """
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo "docker already present"
else
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker
docker --version
docker compose version
"""


def configure_firewall(ssh_port: int) -> str:
    """Opens 80/443 and the SSH port. Xray's loopback port is deliberately never exposed."""
    extra = f"ufw allow {int(ssh_port)}/tcp\n" if int(ssh_port) not in (22, 80, 443, 2222) else ""
    return f"""
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 2222/tcp
{extra}ufw --force enable
ufw status verbose
"""


def configure_sysctl() -> str:
    return """
cat >/etc/sysctl.d/99-remnawave-xhttp.conf <<'SYSCTL'
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
net.ipv4.ip_forward=1
fs.file-max=1048576
SYSCTL
sysctl --system >/dev/null
sysctl net.ipv4.tcp_congestion_control
"""


def configure_nginx_limits() -> str:
    """Global nginx tuning from the guide, plus the bits xHTTP depends on.

    `gzip off` matters: the CDN already has compression disabled, and re-compressing a
    tunnelled stream both wastes CPU and changes packet sizes that the padding is trying to
    shape. `send_timeout` is long because a packet-up session is a long-lived request.
    """
    return """
sed -i '/^worker_rlimit_nofile /d' /etc/nginx/nginx.conf
sed -i '/^events {/i worker_rlimit_nofile 1048576;' /etc/nginx/nginx.conf
sed -i 's/worker_connections .*/worker_connections 8192;/' /etc/nginx/nginx.conf

cat >/etc/nginx/conf.d/00-xhttp-tuning.conf <<'TUNING'
# Applied inside http{} — nginx merges conf.d before the site configs.
tcp_nopush on;
tcp_nodelay on;
server_tokens off;
gzip off;
keepalive_timeout 65;
keepalive_requests 1000;
client_body_timeout 60s;
client_header_timeout 60s;
send_timeout 3600s;
ssl_session_cache shared:SSL:20m;
ssl_session_timeout 1d;
ssl_session_tickets off;
TUNING

nginx -t
"""


def configure_swap(size_gb: int = 2) -> str:
    """Creates swap only when the machine has none — an existing setup is left alone."""
    return f"""
if [ "$(swapon --show --noheadings | wc -l)" -gt 0 ]; then
  echo "swap already configured, leaving it untouched"
  swapon --show
else
  fallocate -l {int(size_gb)}G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count={int(size_gb) * 1024}
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >>/etc/fstab
  swapon --show
fi
"""


PLACEHOLDER_SITE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Video Tools</title>
  <style>
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;
         background:#0f1115;color:#e8eaed;display:flex;min-height:100vh;
         align-items:center;justify-content:center}
    main{max-width:520px;padding:40px;text-align:center}
    h1{font-size:2rem;margin-bottom:.5rem}
    p{opacity:.7;line-height:1.6}
  </style>
</head>
<body>
  <main>
    <h1>Video Tools</h1>
    <p>Online media workspace. Convert, trim and package your video files in the browser.</p>
  </main>
</body>
</html>
"""


def create_placeholder_site() -> str:
    payload = shlex.quote(PLACEHOLDER_SITE)
    return f"""
mkdir -p /var/www/html/.well-known/acme-challenge
printf '%s' {payload} >/var/www/html/index.html
chown -R www-data:www-data /var/www/html || true
"""


def bootstrap_nginx_http(origin_domain: str) -> str:
    """Minimal HTTP-only vhost so certbot's webroot challenge can succeed."""
    return f"""
cat >/etc/nginx/conf.d/xhttp-cdn.conf <<NGINX
server {{
    listen 80;
    listen [::]:80;
    server_name {origin_domain} _;
    root /var/www/html;
    location /.well-known/acme-challenge/ {{
        root /var/www/html;
    }}
    location / {{
        try_files \\$uri \\$uri/ /index.html;
    }}
}}
NGINX
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable --now nginx
systemctl reload nginx
"""


def issue_certificate(origin_domain: str, email: str) -> str:
    domain = shlex.quote(origin_domain)
    mail = shlex.quote(email)
    return f"""
if [ -f /etc/letsencrypt/live/{origin_domain}/fullchain.pem ]; then
  echo "certificate already present"
else
  certbot certonly --webroot -w /var/www/html -d {domain} --email {mail} \
    --agree-tos --no-eff-email --non-interactive
fi
test -f /etc/letsencrypt/live/{origin_domain}/fullchain.pem
test -f /etc/letsencrypt/live/{origin_domain}/privkey.pem
"""


def final_nginx_config(origin_domain: str, cdn_domain: str) -> str:
    """443 vhost: static site on /, xHTTP proxied to loopback Xray on the fixed path.

    The upstream keeps connections alive: packet-up opens a new request per packet, so
    without keepalive nginx would burn a TCP handshake on every one of them.

    Two locations are needed — an exact match for the bare path and a prefix match for
    everything under it — because the client uses both forms.
    """
    return f"""
cat >/etc/nginx/conf.d/xhttp-cdn.conf <<'NGINX'
upstream xray_sync {{
    server 127.0.0.1:{XRAY_PORT};
    keepalive 64;
    keepalive_requests 2000;
    keepalive_timeout 60s;
}}

server {{
    listen 80;
    listen [::]:80;
    server_name {origin_domain} _;

    root /var/www/html;

    location /.well-known/acme-challenge/ {{
        root /var/www/html;
    }}

    location / {{
        return 301 https://$host$request_uri;
    }}
}}

server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name {origin_domain} {cdn_domain} _;

    ssl_certificate /etc/letsencrypt/live/{origin_domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{origin_domain}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    root /var/www/html;
    index index.html;

    client_max_body_size 0;

    location = {XHTTP_PATH} {{
        proxy_pass http://xray_sync;
        proxy_http_version 1.1;

        proxy_set_header Host {origin_domain};
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Connection "";
        proxy_set_header Accept-Encoding "";

        proxy_buffering off;
        proxy_request_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        client_max_body_size 0;
    }}

    location ^~ {XHTTP_PATH}/ {{
        proxy_pass http://xray_sync;
        proxy_http_version 1.1;

        proxy_set_header Host {origin_domain};
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Connection "";
        proxy_set_header Accept-Encoding "";

        proxy_buffering off;
        proxy_request_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        client_max_body_size 0;
    }}

    location / {{
        try_files $uri $uri/ /index.html;
    }}
}}
NGINX
nginx -t
systemctl reload nginx
"""


# Remnanode installation lives in node_installer.py — it needs SFTP writes and container
# state inspection, not a one-shot shell script.


def health_check_script(origin_domain: str, cdn_domain: str) -> str:
    """Emits a single JSON line consumed by the health-check step."""
    return f"""
nginx_ok=$(systemctl is-active nginx || echo inactive)
docker_ok=$(systemctl is-active docker || echo inactive)
node_ok=$(docker ps --filter name=remnanode --format '{{{{.Status}}}}' | head -n1)
listen=$(ss -ltn | awk '{{print $4}}' | sed 's/.*://' | sort -u | tr '\\n' ',')
origin_code=$(curl -s -o /dev/null -w '%{{http_code}}' --max-time 20 https://{origin_domain}/ || echo 000)
origin_xhttp=$(curl -s -o /dev/null -w '%{{http_code}}' --max-time 20 https://{origin_domain}{XHTTP_PATH} || echo 000)
cdn_code=$(curl -s -o /dev/null -w '%{{http_code}}' --max-time 25 https://{cdn_domain}/ || echo 000)
cdn_xhttp=$(curl -s -o /dev/null -w '%{{http_code}}' --max-time 25 https://{cdn_domain}{XHTTP_PATH} || echo 000)
xray_local=$(ss -ltn | grep -c '127.0.0.1:{XRAY_PORT}' || true)
xray_public=$(ss -ltn | grep -c '0.0.0.0:{XRAY_PORT}' || true)
printf '{{"nginx":"%s","docker":"%s","remnanode":"%s","listen":"%s","origin":"%s","origin_xhttp":"%s","cdn":"%s","cdn_xhttp":"%s","xray_local":%s,"xray_public":%s}}\\n' \\
  "$nginx_ok" "$docker_ok" "$node_ok" "$listen" "$origin_code" "$origin_xhttp" "$cdn_code" "$cdn_xhttp" "$xray_local" "$xray_public"
"""


def parse_health_output(stdout: str) -> dict:
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return {}
