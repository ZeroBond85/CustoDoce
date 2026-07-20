"""Deep unit tests for services.url_guard (SSRF defense-in-depth).

Cobre: allowlist http/https, bloqueio de http p/ nao-allowlistados, schemes
perigosos, IPs literais perigosos (IPv4+IPv6 incl. NAT64/6to4/CGNAT/metadata),
resolucao DNS (defesa contra DNS rebinding), e re-validacao de redirect hop
via make_safe_client().
"""
from __future__ import annotations

import socket
from unittest.mock import patch

import httpx
import pytest

import services.url_guard as ug
from services.url_guard import (
    guard_url,
    is_safe_url,
    make_safe_client,
    resolve_public_ips,
    validate_redirect_target,
)


# ─── 1. Allowlist: http e https para hosts conhecidos ──────────────────────
class TestAllowlist:
    @pytest.mark.parametrize(
        "url",
        [
            "https://roldao.com.br/wp-content/a.jpg",
            "http://roldao.com.br/wp-content/a.jpg",          # http permitido p/ allowlist
            "https://blog.roldao.com.br/x.png",
            "https://institucional.supermuffato.com.br/webtools/files/o.jpeg",
            "https://gigavc.vtexassets.com/assets/vtex.file-manager-graphql/images/a.png",
            "https://www.giga.com.vc/encartes",
            "https://d3gdr9n5lqb5z7.cloudfront.net/flyer.png",
            "https://www.tiendeo.com.br/loja/x",
            "https://www.promotons.com.br/b",
            "https://www.kimbino.com.br/c",
            "https://www.portafolhetos.com.br/d",
            "https://na.kimbicdn.com/flyer.jpg",        # Kimbino CDN
            "https://na.leafletscdn.com/thumbor/x/y.jpg",  # Leaflets/Tiendeo CDN
        ],
    )
    def test_allowlisted_hosts_allowed(self, url):
        assert is_safe_url(url) is True
        assert guard_url(url) == url

    @pytest.mark.parametrize(
        "url",
        [
            "http://test.com/4a8a.png",       # placeholder dos Cleanup Store orfaos
            "https://example.com/test.png",
            "https://attacker.com/evil.jpg",
            "https://random-shop.com.br/img.png",
        ],
    )
    def test_non_allowlisted_blocked(self, url):
        assert is_safe_url(url) is False
        assert guard_url(url) is None

    @pytest.mark.parametrize(
        "url",
        [
            "http://attacker.com/x.jpg",   # http p/ nao-allowlistado
            "http://example.com/x.png",
        ],
    )
    def test_http_blocked_for_unknown_host_even_with_allow_http_false(self, url):
        assert is_safe_url(url, allow_http=False) is False


# ─── 2. Schemes perigosos ─────────────────────────────────────────────────
class TestDangerousSchemes:
    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "gopher://169.254.169.254/",
            "ftp://internal.host/",
            "dict://127.0.0.1:11211/",
            "data:text/html,hello",
            "javascript:alert(1)",
        ],
    )
    def test_non_http_schemes_blocked(self, url):
        assert is_safe_url(url) is False
        assert guard_url(url) is None

    def test_empty_and_junk_urls_blocked(self):
        assert is_safe_url("") is False
        assert is_safe_url("not a url") is False
        assert guard_url("") is None


# ─── 3. IPs literais perigosos (IPv4 + IPv6) ──────────────────────────────
class TestDangerousLiteralIPs:
    @pytest.mark.parametrize(
        "ip",
        [
            "169.254.169.254",   # AWS metadata
            "169.254.170.2",     # AWS ECS task creds
            "10.0.0.1",          # RFC1918
            "10.255.255.255",
            "172.16.0.1",        # RFC1918
            "172.31.255.255",
            "192.168.1.1",       # RFC1918
            "100.64.0.1",        # CGNAT
            "100.100.100.200",   # Aliyun metadata
            "127.0.0.1",         # loopback
            "0.0.0.0",           # this network  # noqa: S104
            "8.8.8.8",           # public BUT not allowlisted domain -> blocked
            "1.1.1.1",
        ],
    )
    def test_ipv4_dangerous_or_unallowlisted_blocked(self, ip):
        assert is_safe_url(f"http://{ip}/x") is False
        assert guard_url(f"http://{ip}/x") is None

    @pytest.mark.parametrize(
        "ip",
        [
            "::1",                 # IPv6 loopback
            "fc00::1",             # IPv6 ULA
            "fe80::1",             # IPv6 link-local
            "64:ff9b::a9fe:a9fe",  # NAT64 -> reaches IPv4 metadata
            "2002::1",             # 6to4
            "2606:4700:4700::1111",  # public IPv6 but not allowlisted -> blocked
        ],
    )
    def test_ipv6_dangerous_or_unallowlisted_blocked(self, ip):
        assert is_safe_url(f"http://[{ip}]/x") is False
        assert guard_url(f"http://[{ip}]/x") is None


# ─── 4. Resolucao DNS (defesa DNS rebinding / TOCTOU) ─────────────────────
def _fake_getaddrinfo(map_host_to_ips: dict):
    def _ga(host, *_a, **_k):
        if host not in map_host_to_ips:
            raise socket.gaierror("getaddrinfo failed")
        return [(socket.AF_INET, 0, 0, "", (ip, 0)) for ip in map_host_to_ips[host]]

    return _ga


class TestDNSResolution:
    def test_allowlisted_host_resolving_to_public_ip_allowed(self):
        with patch.object(ug.socket, "getaddrinfo", _fake_getaddrinfo({"roldao.com.br": ["177.54.10.20"]})):
            assert is_safe_url("http://roldao.com.br/a.jpg") is True

    def test_allowlisted_host_resolving_to_internal_ip_blocked(self):
        # DNS rebinding: dominio allowlistado, mas resolve para IP interno.
        with patch.object(ug.socket, "getaddrinfo", _fake_getaddrinfo({"roldao.com.br": ["10.0.0.5"]})):
            assert is_safe_url("http://roldao.com.br/a.jpg") is False
            assert guard_url("http://roldao.com.br/a.jpg") is None

    def test_allowlisted_host_resolving_to_metadata_blocked(self):
        with patch.object(ug.socket, "getaddrinfo", _fake_getaddrinfo({"roldao.com.br": ["169.254.169.254"]})):
            assert is_safe_url("http://roldao.com.br/a.jpg") is False

    def test_allowlisted_host_resolving_to_cgnat_blocked(self):
        with patch.object(ug.socket, "getaddrinfo", _fake_getaddrinfo({"roldao.com.br": ["100.64.0.1"]})):
            assert is_safe_url("http://roldao.com.br/a.jpg") is False

    def test_resolution_failure_blocked(self):
        with patch.object(ug.socket, "getaddrinfo", _fake_getaddrinfo({})):
            assert is_safe_url("http://roldao.com.br/a.jpg") is False

    def test_resolve_public_ips_returns_public(self):
        with patch.object(ug.socket, "getaddrinfo", _fake_getaddrinfo({"roldao.com.br": ["177.54.10.20"]})):
            assert resolve_public_ips("roldao.com.br") == ["177.54.10.20"]

    def test_resolve_public_ips_raises_on_internal(self):
        with patch.object(ug.socket, "getaddrinfo", _fake_getaddrinfo({"roldao.com.br": ["192.168.0.9"]})):
            with pytest.raises(ValueError):
                resolve_public_ips("roldao.com.br")

    def test_dual_stack_all_must_be_public(self):
        # Se QUALQUER IP resolvido for perigoso, bloqueia (defesa TOCTOU).
        with patch.object(ug.socket, "getaddrinfo", _fake_getaddrinfo({"roldao.com.br": ["177.54.10.20", "10.0.0.9"]})):
            assert is_safe_url("http://roldao.com.br/a.jpg") is False


# ─── 5. Re-validacao de redirect hop (validate_redirect_target + hook) ─────
class TestRedirectRevalidation:
    def test_validate_redirect_blocks_dangerous_ip(self):
        with pytest.raises(httpx.UnsupportedProtocol):
            validate_redirect_target("http://169.254.169.254/latest/meta-data/")

    def test_validate_redirect_blocks_unknown_host(self):
        with pytest.raises(httpx.UnsupportedProtocol):
            validate_redirect_target("https://attacker.com/evil")

    def test_validate_redirect_blocks_internal_ip(self):
        with pytest.raises(httpx.UnsupportedProtocol):
            validate_redirect_target("http://10.0.0.5/x")

    def test_validate_redirect_allows_allowlisted(self):
        # Nao levanta para host allowlistado (DNS nao resolvido no teste de
        # unidade pois o guard soh resolve no is_safe_url; aqui validamos o
        # caminho de allowlist via patch de resolucao).
        with patch.object(ug.socket, "getaddrinfo", _fake_getaddrinfo({"supermuffato.com.br": ["177.54.10.20"]})):
            validate_redirect_target("https://supermuffato.com.br/ok")  # nao levanta

    def test_event_hook_wraps_existing_and_blocks_redirect(self):
        captured = []

        def existing(resp: httpx.Response) -> None:
            captured.append(resp.status_code)

        client = make_safe_client(follow_redirects=False, event_hooks={"response": [existing]})
        # o hook interno foi envolvido (nao eh o mesmo objeto do caller)
        assert client.event_hooks["response"][0] is not existing
        # simula um response com next_request apontando p/ host perigoso:
        # o hook existente roda no 302 e o nosso hook levanta antes de seguir.
        resp = httpx.Response(302, headers={"Location": "http://169.254.169.254/meta"})
        resp.next_request = httpx.Request("GET", "http://169.254.169.254/meta")
        with pytest.raises(httpx.UnsupportedProtocol):
            client.event_hooks["response"][0](resp)
        # existing hook ainda roda em response sem redirect
        ok = httpx.Response(200, content=b"x")
        client.event_hooks["response"][0](ok)
        assert captured == [302, 200]


# ─── 6. Integracao com flyer_ocr (allow_http=True) ────────────────────────
class TestFlyerOcrIntegration:
    def test_flyer_ocr_allows_http_allowlisted_via_guard(self, monkeypatch):
        import scrapers.flyer_ocr as flyer_ocr

        # Nao fazemos monkeypatch do guard_url (queremos testar o real).
        downloaded = {}

        class _FakeResp:
            content = b"IMG"

            def raise_for_status(self):
                return None

        class _FakeHttp:
            def get(self, url, **kwargs):
                downloaded["url"] = url
                return _FakeResp()

        # http allowlistado deve passar pelo guard (roldao esta na allowlist).
        out = flyer_ocr._download_image(_FakeHttp(), "http://roldao.com.br/folheto.jpg")
        assert out == b"IMG"
        assert downloaded["url"] == "http://roldao.com.br/folheto.jpg"

    def test_flyer_ocr_blocks_non_allowlisted(self, monkeypatch):
        import scrapers.flyer_ocr as flyer_ocr

        class _FakeHttp:
            def get(self, url, **kwargs):
                raise AssertionError("should never fetch non-allowlisted URL")

        out = flyer_ocr._download_image(_FakeHttp(), "https://attacker.com/x.jpg")
        assert out is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
