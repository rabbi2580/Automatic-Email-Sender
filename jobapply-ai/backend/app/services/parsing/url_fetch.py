"""SSRF-safe, robots-aware, size/time-limited URL fetching for job pages."""
from __future__ import annotations

import ipaddress
import re
import socket
import urllib.robotparser
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import get_settings

USER_AGENT = "JobApplyAI-Fetcher/1.0 (+user-initiated; respects robots.txt)"
# Sites that forbid automated access / need login: never fetched; user is asked to paste the text.
BLOCKED_HOSTS = ("linkedin.com", "facebook.com", "fb.com", "instagram.com", "x.com", "twitter.com", "whatsapp.com", "indeed.com", "glassdoor.com")


class FetchError(Exception):
    def __init__(self, reason: str, code: str = "fetch_failed"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def _is_public_ip(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved or a.is_unspecified)


def validate_url(url: str) -> str:
    p = urlparse(url.strip())
    if p.scheme not in ("http", "https") or not p.hostname:
        raise FetchError("Only http(s) URLs are supported.", "bad_url")
    host = p.hostname.lower()
    if any(host == h or host.endswith("." + h) for h in BLOCKED_HOSTS):
        raise FetchError(
            f"{host} does not allow automated access. Please open the post and paste its text here instead.", "site_blocked"
        )
    try:
        infos = socket.getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise FetchError("The website address could not be resolved.", "dns")
    for info in infos:
        if not _is_public_ip(info[4][0]):
            raise FetchError("That address is not allowed.", "ssrf_blocked")
    return url.strip()


def _robots_allows(url: str, client: httpx.Client) -> bool:
    p = urlparse(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    try:
        r = client.get(robots_url, timeout=5)
        if r.status_code >= 400:
            return True
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(r.text.splitlines())
        return rp.can_fetch(USER_AGENT, url)
    except httpx.HTTPError:
        return True


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "tr", "section", "article", "ul", "ol"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP and tag != "head":
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("• ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and tag != "head" and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> tuple[str, str]:
    ex = _TextExtractor()
    ex.feed(html)
    text = re.sub(r"[ \t]+", " ", "".join(ex.parts))
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text, ex.title.strip()


def fetch_job_page(url: str, client: httpx.Client | None = None) -> tuple[str, str]:
    """Return (text, final_url). Follows ≤3 redirects, re-validating each hop."""
    s = get_settings()
    own = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=False, timeout=s.url_fetch_timeout_seconds)
    try:
        current = validate_url(url)
        if not _robots_allows(current, client):
            raise FetchError("The website's robots.txt does not allow automated access. Please paste the job text instead.", "robots")
        for _ in range(4):
            with client.stream("GET", current) as r:
                if r.is_redirect:
                    nxt = urljoin(current, r.headers.get("location", ""))
                    current = validate_url(nxt)
                    continue
                if r.status_code in (401, 403, 429):
                    raise FetchError("The website blocked automated access. Please paste the job text instead.", "blocked")
                if r.status_code >= 400:
                    raise FetchError(f"The page returned HTTP {r.status_code}.", "http_error")
                ctype = r.headers.get("content-type", "")
                if "html" not in ctype and "text" not in ctype:
                    raise FetchError("The link does not point to a web page. Upload the file instead.", "not_html")
                body = b""
                for chunk in r.iter_bytes():
                    body += chunk
                    if len(body) > s.url_fetch_max_bytes:
                        raise FetchError("The page is too large.", "too_large")
                text, title = html_to_text(body.decode(r.encoding or "utf-8", errors="replace"))
                if len(text) < 80:
                    raise FetchError("The page has little readable text (it may need JavaScript or a login). Please paste the job text instead.", "empty_page")
                return (f"{title}\n\n{text}" if title else text), current
        raise FetchError("Too many redirects.", "redirects")
    except httpx.HTTPError as exc:
        raise FetchError(f"Could not reach the website ({type(exc).__name__}).", "network")
    finally:
        if own:
            client.close()
