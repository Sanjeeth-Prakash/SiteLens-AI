import gzip
from email.message import Message
from time import monotonic
from unittest.mock import Mock

import pytest

from app.website import (
    MAX_HTML_BYTES,
    MAX_REDIRECTS,
    PinnedConnection,
    URLRejected,
    WebsiteUnavailable,
    extract_passages,
    fetch_page,
)


def fake_response(status=200, body=b"<html>Example</html>", **headers):
    message = Message()
    for name, value in headers.items():
        message[name.replace("_", "-")] = value
    response = Mock(status=status, headers=message)
    response.getheader.side_effect = message.get
    response.read.side_effect = lambda limit: body[:limit]
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    return response


@pytest.fixture
def network(monkeypatch):
    responses = iter(())
    visited = []
    dns_queries = []

    def resolve(host, port, **kwargs):
        dns_queries.append((host, port))
        addresses = ["93.184.216.34", "127.0.0.1"] if host == "mixed.example." else ["93.184.216.34"]
        return [(None, None, None, None, (address, port)) for address in addresses]

    def connect(host, port, addresses, deadline):
        connection = Mock()

        def request(method, path, **kwargs):
            visited.append((host, port, addresses, path))

        connection.request.side_effect = request
        connection.getresponse.side_effect = lambda: next(responses)
        return connection

    def install(*values):
        nonlocal responses
        responses = iter(values)
        visited.clear()
        dns_queries.clear()
        monkeypatch.setattr("app.website.socket.getaddrinfo", resolve)
        monkeypatch.setattr("app.website.PinnedConnection", connect)
        return visited, dns_queries

    return install


def test_follows_redirects_and_preserves_final_source(network):
    visited, dns = network(
        fake_response(301, Location="https://school.example/en/"),
        fake_response(302, Location="admissions#requirements"),
        fake_response(Content_Type="text/html; charset=utf-8"),
    )
    page = fetch_page("http://school.example/")
    assert page.url == "https://school.example/en/admissions"
    assert page.encoding == "utf-8"
    assert dns == [("school.example.", 80), ("school.example.", 443), ("school.example.", 443)]
    assert visited == [
        ("school.example", 80, ["93.184.216.34"], "/"),
        ("school.example", 443, ["93.184.216.34"], "/en/"),
        ("school.example", 443, ["93.184.216.34"], "/en/admissions"),
    ]


def test_tls_connects_to_vetted_ip_with_original_hostname(monkeypatch):
    tcp_connect = Mock()
    tls = Mock()
    monkeypatch.setattr("app.website.socket.create_connection", tcp_connect)
    monkeypatch.setattr("app.website.ssl.create_default_context", lambda: tls)
    connection = PinnedConnection("school.example", 443, ["93.184.216.34"], monotonic() + 20)
    connection.connect()
    assert tcp_connect.call_args.args == (("93.184.216.34", 443),)
    tls.wrap_socket.assert_called_once_with(tcp_connect.return_value, server_hostname="school.example")


@pytest.mark.parametrize("destination", [
    "http://127.0.0.1/",
    "https://mixed.example/",
    "https://[::ffff:127.0.0.1]/",
    "ftp://school.example/",
])
def test_redirect_is_checked_before_opening_a_connection(network, destination):
    visited, _ = network(fake_response(302, Location=destination))
    with pytest.raises(URLRejected):
        fetch_page("https://school.example/")
    assert len(visited) == 1


def test_redirect_loop_and_hop_limit(network):
    network(fake_response(302, Location="/"))
    with pytest.raises(WebsiteUnavailable, match="redirect loop"):
        fetch_page("https://school.example/")
    visited, _ = network(*(fake_response(302, Location=f"/{i}") for i in range(MAX_REDIRECTS + 1)))
    with pytest.raises(WebsiteUnavailable, match="exceeded"):
        fetch_page("https://school.example/")
    assert len(visited) == MAX_REDIRECTS + 1


def test_gzip_html_and_character_encoding(network):
    html = (
        "<html><title>École Exemple</title><main>This example school teaches students "
        "in all age groups and offers a programme of regular academic lessons and community activities.</main></html>"
    ).encode("iso-8859-1")
    network(fake_response(body=gzip.compress(html), Content_Type="text/html; charset=iso-8859-1", Content_Encoding="gzip"))
    page = fetch_page("https://school.example/")
    assert page.html == html
    assert extract_passages(page.html, page.encoding)["page-title"] == "École Exemple"


@pytest.mark.parametrize("encoding", ["identity", "gzip"])
def test_enforces_size_limit_on_wire_and_decoded_body(network, encoding):
    oversized = b"x" * (MAX_HTML_BYTES + 1)
    body = gzip.compress(oversized) if encoding == "gzip" else oversized
    network(fake_response(body=body, Content_Type="text/html", Content_Encoding=encoding))
    with pytest.raises(WebsiteUnavailable, match="1 MB"):
        fetch_page("https://school.example/")


def test_returns_clear_error_for_non_html(network):
    network(fake_response(Content_Type="application/pdf"))
    with pytest.raises(WebsiteUnavailable, match="did not return HTML"):
        fetch_page("https://school.example/prospectus.pdf")
