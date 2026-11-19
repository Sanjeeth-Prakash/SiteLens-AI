"""Fetch one allowlisted HTTPS page and extract human-readable evidence."""

import http.client
import ipaddress
import re
import socket
import ssl
from urllib.parse import quote, urlsplit

from bs4 import BeautifulSoup

DEMO_HOSTS = frozenset({"www.python.org", "www.djangoproject.com", "fastapi.tiangolo.com"})
MAX_HTML_BYTES = 1_000_000
MAX_PAGE_WORDS = 2400
WORDS_PER_PASSAGE = 90


class URLRejected(ValueError):
    """The URL is outside the supported fetch policy."""


class WebsiteUnavailable(RuntimeError):
    """The configured website did not provide usable HTML."""


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Use vetted IPs for TCP, and the original host for TLS verification."""

    def __init__(self, host: str, addresses: list[str]):
        self.addresses = addresses
        self.tls = ssl.create_default_context()
        super().__init__(host, timeout=5, context=self.tls)

    def connect(self) -> None:
        failure: OSError | None = None
        for address in self.addresses[:3]:
            try:
                with_socket = socket.create_connection((address, 443), timeout=self.timeout)
                try:
                    self.sock = self.tls.wrap_socket(with_socket, server_hostname=self.host)
                except OSError:
                    with_socket.close()
                    raise
                return
            except OSError as exc:
                failure = exc
        raise OSError("Could not connect to the public website") from failure


def fetch_page(url: str) -> bytes:
    """Keep the requested destination on the allowlist through TLS setup."""
    parts = urlsplit(url)
    host = parts.hostname
    if (
        parts.scheme != "https"
        or host not in DEMO_HOSTS
        or parts.port not in (None, 443)
        or parts.username is not None
        or parts.fragment
    ):
        raise URLRejected("Use HTTPS on port 443 with an allowlisted hostname and no credentials or fragment.")

    target = quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~")
    if parts.query:
        target += "?" + quote(parts.query, safe="/%?:@!$&'()*+,;=-._~")
    try:
        addresses = sorted({
            info[4][0] for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        }, key=lambda address: (":" in address, address))
        ips = [ipaddress.ip_address(address) for address in addresses]
        if not ips or any(not ip.is_global or ip.is_multicast or ip.is_reserved for ip in ips):
            raise URLRejected("The hostname must resolve exclusively to public addresses.")
        connection = PinnedHTTPSConnection(host, addresses)
        try:
            connection.request("GET", target, headers={
                "Accept": "text/html", "Accept-Encoding": "identity", "User-Agent": "SiteLens-Portfolio/1.0",
            })
            with connection.getresponse() as response:
                if response.status != 200:
                    raise WebsiteUnavailable(f"Website returned HTTP {response.status}. Redirects are disabled.")
                content_type = response.headers.get_content_type()
                if content_type != "text/html" or response.getheader("Content-Encoding", "identity") != "identity":
                    raise WebsiteUnavailable("The website did not return uncompressed HTML.")
                html = response.read(MAX_HTML_BYTES + 1)
                if len(html) > MAX_HTML_BYTES:
                    raise WebsiteUnavailable("The page exceeded the 1 MB HTML limit.")
                return html
        finally:
            connection.close()
    except (OSError, http.client.HTTPException) as exc:
        raise WebsiteUnavailable("Could not read the website.") from exc


def extract_passages(html: bytes) -> dict[str, str]:
    """Return named passages. IDs link model references back to readable text."""
    soup = BeautifulSoup(html, "html.parser")
    for element in soup.select("script, style, nav, footer, noscript, template, aside"):
        element.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    description = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    metadata = " ".join(filter(None, [title, str(description.get("content", "")) if description else ""]))
    body = soup.find("main") or soup.body or soup
    words = body.get_text(" ", strip=True).split()[:MAX_PAGE_WORDS]
    if len(words) < 20:
        raise WebsiteUnavailable("The page has too little readable text for analysis.")
    passages = {"page-title": metadata[:500]} if metadata else {}
    for start in range(0, len(words), WORDS_PER_PASSAGE):
        passages[f"page-{start // WORDS_PER_PASSAGE + 1}"] = " ".join(words[start:start + WORDS_PER_PASSAGE])
    return passages
