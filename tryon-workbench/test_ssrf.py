"""
Unit tests for the SSRF guard added to main.py.

Run from PJ111ForGemini/Cloud/:
    python -m unittest test_ssrf -v
"""
import os
import sys
import socket
import types
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

# Load main.py with temporary dependency stubs. The patch context restores
# sys.modules after import so this test cannot replace the real ``app`` package
# for other tests in the same pytest process.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

_google = types.ModuleType("google")
_google.genai = MagicMock()  # type: ignore[attr-defined]
_pil = types.ModuleType("PIL")
_pil.Image = MagicMock()  # type: ignore[attr-defined]
_app = types.ModuleType("app")
_app_products = MagicMock()
_app_products.load_catalog = MagicMock()
_app_products.list_products = MagicMock()
_app_products.get_filter_options = MagicMock()
_app_config = MagicMock()
_app_config.resolve_tryon_runtime_config = MagicMock()
_app_config.get_tryon_runtime_status = MagicMock()

_temporary_modules = {
    "google": _google,
    "google.genai": MagicMock(),
    "google.cloud": MagicMock(),
    "google.cloud.firestore": MagicMock(),
    "google.cloud.storage": MagicMock(),
    "PIL": _pil,
    "PIL.Image": MagicMock(),
    "app": _app,
    "app.products": _app_products,
    "app.admin_runtime_config": _app_config,
    "app.admin_report": MagicMock(),
}

import fastapi.staticfiles as _fss  # noqa: E402

with patch.dict(sys.modules, _temporary_modules), patch.object(_fss, "StaticFiles", MagicMock()):
    _spec = importlib.util.spec_from_file_location("_ssrf_main_under_test", Path(_HERE) / "main.py")
    if _spec is None or _spec.loader is None:
        raise RuntimeError("Unable to load main.py for SSRF tests")
    _main_under_test = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_main_under_test)

_check_url_safe_for_ssrf = _main_under_test._check_url_safe_for_ssrf


# ── Helpers ──────────────────────────────────────────────────────────────────

def _addrinfo(ip: str):
    """Minimal getaddrinfo result for a single IP."""
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return [(family, socket.SOCK_STREAM, 6, "", (ip, 0))]


class TestSsrfGuard(unittest.TestCase):

    def _assert_blocked(self, ip: str, scheme: str = "http") -> None:
        with patch("socket.getaddrinfo", return_value=_addrinfo(ip)):
            with self.assertRaises(ValueError):
                _check_url_safe_for_ssrf(f"{scheme}://internal.host/img.jpg")

    def _assert_allowed(self, ip: str, scheme: str = "http") -> None:
        with patch("socket.getaddrinfo", return_value=_addrinfo(ip)):
            _check_url_safe_for_ssrf(f"{scheme}://cdn.example.com/img.jpg")

    # ── scheme validation ─────────────────────────────────────────────────────

    def test_ftp_scheme_blocked(self):
        with self.assertRaises(ValueError):
            _check_url_safe_for_ssrf("ftp://example.com/img.jpg")

    def test_file_scheme_blocked(self):
        with self.assertRaises(ValueError):
            _check_url_safe_for_ssrf("file:///etc/passwd")

    def test_bare_string_blocked(self):
        with self.assertRaises(ValueError):
            _check_url_safe_for_ssrf("not-a-url")

    # ── loopback ──────────────────────────────────────────────────────────────

    def test_ipv4_loopback_127_0_0_1_blocked(self):
        self._assert_blocked("127.0.0.1")

    def test_ipv4_loopback_alt_blocked(self):
        self._assert_blocked("127.0.0.2")

    def test_ipv6_loopback_blocked(self):
        self._assert_blocked("::1")

    # ── RFC-1918 private ranges ────────────────────────────────────────────────

    def test_10_x_blocked(self):
        self._assert_blocked("10.0.0.1")

    def test_172_16_x_blocked(self):
        self._assert_blocked("172.16.0.1")

    def test_172_31_x_blocked(self):
        self._assert_blocked("172.31.255.255")

    def test_192_168_x_blocked(self):
        self._assert_blocked("192.168.1.1")

    # ── link-local and cloud-metadata endpoint ────────────────────────────────

    def test_link_local_169_254_blocked(self):
        self._assert_blocked("169.254.0.1")

    def test_metadata_169_254_169_254_blocked(self):
        self._assert_blocked("169.254.169.254")

    # ── CGNAT (RFC 6598) — not covered by is_private in Python 3.10 ──────────

    def test_cgnat_100_64_low_blocked(self):
        self._assert_blocked("100.64.0.1")

    def test_cgnat_100_64_high_blocked(self):
        self._assert_blocked("100.127.255.255")

    # ── IPv6 private ──────────────────────────────────────────────────────────

    def test_ipv6_fc00_blocked(self):
        self._assert_blocked("fc00::1")

    def test_ipv6_fe80_link_local_blocked(self):
        self._assert_blocked("fe80::1")

    # ── DNS failure ───────────────────────────────────────────────────────────

    def test_unresolvable_hostname_blocked(self):
        with patch("socket.getaddrinfo", side_effect=OSError("NXDOMAIN")):
            with self.assertRaises(ValueError):
                _check_url_safe_for_ssrf("http://nonexistent.invalid/img.jpg")

    # ── public addresses must be allowed ─────────────────────────────────────

    def test_google_dns_8_8_8_8_allowed(self):
        self._assert_allowed("8.8.8.8")

    def test_cloudflare_1_1_1_1_allowed(self):
        self._assert_allowed("1.1.1.1")

    def test_https_public_allowed(self):
        self._assert_allowed("8.8.4.4", scheme="https")


if __name__ == "__main__":
    unittest.main()
