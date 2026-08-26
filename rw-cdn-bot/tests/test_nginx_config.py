from app.services.deployment import scripts
from app.services.remnawave.templates import XHTTP_PATH, XRAY_PORT


def test_nginx_proxies_xhttp_to_loopback_only():
    config = scripts.final_nginx_config("origin.example.com", "cdn.example.com")
    assert f"server 127.0.0.1:{XRAY_PORT};" in config
    assert "proxy_pass http://xray_sync;" in config
    assert "listen 443 ssl;" in config
    assert "/etc/letsencrypt/live/origin.example.com/fullchain.pem" in config


def test_both_exact_and_prefix_locations_exist():
    """Clients use the bare path and paths under it; one location alone drops half of them."""
    config = scripts.final_nginx_config("origin.example.com", "cdn.example.com")
    assert f"location = {XHTTP_PATH} " in config
    assert f"location ^~ {XHTTP_PATH}/ " in config


def test_upstream_keeps_connections_alive():
    """packet-up opens a request per packet — without keepalive every one costs a handshake."""
    config = scripts.final_nginx_config("origin.example.com", "cdn.example.com")
    assert "upstream xray_sync {" in config
    assert "keepalive 64;" in config
    assert "keepalive_requests 2000;" in config


def test_proxy_settings_required_for_streaming():
    config = scripts.final_nginx_config("origin.example.com", "cdn.example.com")
    assert "proxy_buffering off;" in config
    assert "proxy_request_buffering off;" in config
    assert "proxy_cache off;" in config
    assert "proxy_read_timeout 3600s;" in config
    assert 'proxy_set_header Connection "";' in config
    assert 'proxy_set_header Accept-Encoding "";' in config


def test_host_header_is_pinned_to_the_origin_domain():
    config = scripts.final_nginx_config("origin.example.com", "cdn.example.com")
    assert "proxy_set_header Host origin.example.com;" in config


def test_global_tuning_disables_gzip():
    """Re-compressing a tunnelled stream wastes CPU and reshapes the padded packet sizes."""
    tuning = scripts.configure_nginx_limits()
    assert "gzip off;" in tuning
    assert "worker_connections 8192;" in tuning
    assert "worker_rlimit_nofile 1048576;" in tuning
    assert "send_timeout 3600s;" in tuning


def test_firewall_never_opens_the_xray_port():
    rules = scripts.configure_firewall(2222)
    assert str(XRAY_PORT) not in rules
    for port in ("22/tcp", "80/tcp", "443/tcp", "2222/tcp"):
        assert f"ufw allow {port}" in rules


def test_swap_is_not_recreated_when_present():
    assert "swap already configured" in scripts.configure_swap()


def test_health_output_parsing():
    stdout = 'noise\n{"nginx":"active","docker":"active","cdn":"200","xray_local":1,"xray_public":0}\n'
    parsed = scripts.parse_health_output(stdout)
    assert parsed["nginx"] == "active"
    assert parsed["xray_public"] == 0
