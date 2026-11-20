"""Fetch one public webpage and extract human-readable evidence."""

import http.client
import ipaddress
import re
import socket
import ssl
import zlib
from dataclasses import dataclass
from threading import Timer
from time import monotonic
from urllib.parse import quote, urldefrag, urljoin, urlsplit

from bs4 import BeautifulSoup

MAX_HTML_BYTES = 1_000_000
MAX_PAGE_WORDS = 2400
WORDS_PER_PASSAGE = 90
MAX_REDIRECTS = 4
FETCH_SECONDS = 20
SOCKET_SECONDS = 5
WEB_PORTS = {"http": 80, "https": 443}
REDIRECT_CODES = {301, 302, 303, 307, 308}
NONPUBLIC_DOMAINS = {"localhost", "local", "internal", "home.arpa"}
IPV4_EXCLUDED = tuple(map(ipaddress.IPv4Network, ("192.0.0.0/24", "192.88.99.0/24")))
IPV6_PUBLIC_RANGE = ipaddress.IPv6Network("2000::/3")
IPV6_EXCLUDED = tuple(map(ipaddress.IPv6Network, ("2001::/23", "2002::/16", "3fff::/20")))


class URLRejected(ValueError):
    """The URL is outside the supported fetch policy."""


class WebsiteUnavailable(RuntimeError):
    """The website did not provide usable HTML."""


@dataclass(frozen=True)
class FetchedPage:
    url: str
    html: bytes
    encoding: str | None = None


def remaining_seconds(deadline: float) -> float:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("Website fetch exceeded its time budget.")
    return remaining


class PinnedConnection(http.client.HTTPConnection):
    """Connect to a vetted IP while preserving the requested hostname."""

    def __init__(self, host: str, port: int, addresses: list[str], deadline: float):
        super().__init__(host, port)
        self.addresses = addresses
        self.deadline = deadline
        self.tls = ssl.create_default_context() if port == 443 else None

    def connect(self) -> None:
        failure: OSError | None = None
        for address in self.addresses[:3]:
            timeout = min(SOCKET_SECONDS, remaining_seconds(self.deadline))
            raw_socket = None
            try:
                raw_socket = socket.create_connection((address, self.port), timeout=timeout)
                raw_socket.settimeout(min(SOCKET_SECONDS, remaining_seconds(self.deadline)))
                self.sock = self.tls.wrap_socket(raw_socket, server_hostname=self.host) if self.tls else raw_socket
                return
            except OSError as exc:
                if raw_socket is not None:
                    raw_socket.close()
                failure = exc
        raise OSError("Could not connect to the public website") from failure


def parse_destination(url: str) -> tuple[str, int, str]:
    if len(url) > 2083 or any(ord(char) < 32 or char == "\\" for char in url):
        raise URLRejected("The URL is too long or contains invalid characters.")
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").rstrip(".").encode("idna").decode("ascii")
        port = WEB_PORTS.get(parts.scheme)
        requested_port = parts.port
    except (ValueError, UnicodeError) as exc:
        raise URLRejected("Enter a valid public HTTP or HTTPS URL.") from exc
    if (
        port is None
        or not host
        or requested_port not in (None, port)
        or parts.username is not None
        or "%" in host
    ):
        raise URLRejected("Use a public HTTP or HTTPS address on its standard port without credentials.")

    target = quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~")
    if parts.query:
        target += "?" + quote(parts.query, safe="/%?:@!$&'()*+,;=-._~")
    return host, port, target


def public_addresses(host: str, port: int) -> list[str]:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if "." not in host or any(host == name or host.endswith("." + name) for name in NONPUBLIC_DOMAINS):
            raise URLRejected("Use a public hostname or IP address.")
        if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label, re.I) for label in host.split(".")):
            raise URLRejected("The hostname contains invalid characters.")
        # An absolute DNS name avoids adding a local network search suffix.
        records = socket.getaddrinfo(host + ".", port, type=socket.SOCK_STREAM)
        ips = list(dict.fromkeys(ipaddress.ip_address(record[4][0]) for record in records))
    else:
        ips = [ip]
    if not ips or any(not is_public(ip) for ip in ips):
        raise URLRejected("Every destination address must be public.")
    return [str(ip) for ip in sorted(ips, key=lambda ip: ip.version)]


def is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if not ip.is_global or ip.is_multicast or ip.is_reserved:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        return ip.scope_id is None and ip in IPV6_PUBLIC_RANGE and not any(ip in network for network in IPV6_EXCLUDED)
    return not any(ip in network for network in IPV4_EXCLUDED)


def abort_socket(connection: socket.socket) -> None:
    try:
        connection.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def read_html(response: http.client.HTTPResponse) -> bytes:
    if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
        raise WebsiteUnavailable("The website did not return HTML.")
    body = response.read(MAX_HTML_BYTES + 1)
    if len(body) > MAX_HTML_BYTES:
        raise WebsiteUnavailable("The page exceeded the 1 MB download limit.")
    encoding = response.getheader("Content-Encoding", "identity").strip().lower()
    if encoding == "identity":
        return body
    if encoding != "gzip":
        raise WebsiteUnavailable("The website used an unsupported transfer encoding.")
    try:
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        html = decoder.decompress(body, MAX_HTML_BYTES + 1)
    except zlib.error as exc:
        raise WebsiteUnavailable("The website returned invalid compressed HTML.") from exc
    if len(html) > MAX_HTML_BYTES:
        raise WebsiteUnavailable("The page exceeded the 1 MB HTML limit.")
    if not decoder.eof or decoder.unused_data:
        raise WebsiteUnavailable("The website returned invalid compressed HTML.")
    return html


def fetch_hop(url: str, deadline: float) -> FetchedPage | str:
    remaining_seconds(deadline)
    host, port, target = parse_destination(url)
    connection = PinnedConnection(host, port, public_addresses(host, port), deadline)
    timer = None
    try:
        connection.connect()
        timer = Timer(remaining_seconds(deadline), abort_socket, args=(connection.sock,))
        timer.daemon = True
        timer.start()
        host_header = f"[{host}]" if ":" in host else host
        connection.request("GET", target, headers={
            "Host": host_header,
            "Accept": "text/html, application/xhtml+xml",
            "Accept-Encoding": "gzip, identity",
            "User-Agent": "SiteLens-Portfolio/1.1",
        })
        with connection.getresponse() as response:
            if response.status in REDIRECT_CODES:
                location = response.getheader("Location")
                if not location:
                    raise WebsiteUnavailable("The website redirected without a destination.")
                if any(ord(char) < 32 or char == "\\" for char in location):
                    raise URLRejected("The redirect destination contains invalid characters.")
                return location
            if response.status != 200:
                raise WebsiteUnavailable(f"Website returned HTTP {response.status}.")
            html = read_html(response)
            remaining_seconds(deadline)
            scheme = "https" if port == 443 else "http"
            return FetchedPage(f"{scheme}://{host_header}{target}", html, response.headers.get_content_charset())
    finally:
        if timer is not None:
            timer.cancel()
        connection.close()


def fetch_page(url: str) -> FetchedPage:
    """Follow a bounded redirect chain and recheck each destination."""
    deadline = monotonic() + FETCH_SECONDS
    visited = set()
    for _ in range(MAX_REDIRECTS + 1):
        if url in visited:
            raise WebsiteUnavailable("The website has a redirect loop.")
        visited.add(url)
        try:
            result = fetch_hop(url, deadline)
        except (OSError, http.client.HTTPException) as exc:
            raise WebsiteUnavailable("Could not read the website. Check that it is reachable and accepts automated requests.") from exc
        if isinstance(result, FetchedPage):
            return result
        try:
            url = urldefrag(urljoin(url, result)).url
        except ValueError as exc:
            raise URLRejected("The website redirected to an invalid URL.") from exc
    raise WebsiteUnavailable(f"The website exceeded {MAX_REDIRECTS} redirects.")


def extract_passages(html: bytes, encoding: str | None = None) -> dict[str, str]:
    """Return named passages. IDs link model references back to readable text."""
    soup = BeautifulSoup(html, "html.parser", from_encoding=encoding)
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
