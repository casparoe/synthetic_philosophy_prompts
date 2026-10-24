#!/usr/bin/env python3
"""Fetch the pages behind the domain links into the local link cache.

Every URL in meta_prompt/domains/*.yaml is fetched once, and its text goes
into link_cache/pages.sqlite, where the web_fetch tool of
generators/generate_prompt_oai.py finds it (see generators/link_cache.py).
The cache is git-ignored and must never be uploaded: most of the pages are
under copyright. Pages already cached, or known to be gone, are skipped, so
rerun this after adding links; failed fetches are retried on each run.

Sites are fetched in parallel, each one request at a time: robots.txt is
obeyed and crawl delays are honoured. Where a site has an API that gives
cleaner text than its pages, that is used: Wikipedia (TextExtracts), Stack
Exchange (api.stackexchange.com, 100 questions with all their answers per
request; a question missing there comes from its Wayback copy), Substack
(/api/v1/posts), LessWrong and the EA Forum (their GraphQL APIs, ten posts
per request; for the EA Forum that of forum-bots.effectivealtruism.org, its
read-only mirror for bots, since the Forum itself puts scripts behind a
Cloudflare challenge and ea.greaterwrong.com allows only a few requests a
minute).
Project Gutenberg books come from the PGLAF mirror, since gutenberg.org bans
automated access; arXiv papers (the abstract page, then the HTML or PDF full
text) at arxiv.org's crawl delay of 15 seconds.

Stable links (link_cache.stable_link) are fetched from the link itself and
from nothing else: a Wayback Machine capture as archived (its raw id_ form,
and only if the archive has a capture at exactly that timestamp), with rules
for the pages of the forums, Stack Exchange, and Substack, whose text the
generic extraction gets wrong; a Wikipedia revision as Wikipedia renders that
revision (through its API, since its robots.txt bars scripts from the
permanent-link pages themselves); an SEP archive edition's page; one version
of an arXiv paper (its abstract link) as that version's source rendered by
LaTeXML in a sandbox (tools/arxiv_latexml.py), with title, authors, date, and
license from the version's abstract page. A version whose source is only a
PDF, or that LaTeXML cannot render, is skipped (status "skipped pdf-only" or
"skipped latexml"), never taken from its PDF; skipped versions are not tried
again unless asked (--redo-skipped). These come from export.arxiv.org, the copy of arXiv
that arXiv sets aside for programmatic access ("We ask that users intent on
harvesting use the dedicated site export.arxiv.org",
https://info.arxiv.org/help/bulk_data.html; arxiv.org's robots.txt bars
/src, and export.arxiv.org's turns away all crawlers), one request at a time,
after any arxiv.org requests (arXiv asks for one connection at a time). The
sources are kept in link_cache/arxiv_source, so another rendering of them
needs no download.

Usage:
    # everything not yet cached; runs for hours, so start it detached
    caffeinate -i .venv/bin/python tools/build_link_cache.py >> link_cache/build.log 2>&1
    # a trial: two pages of each site
    .venv/bin/python tools/build_link_cache.py --limit 2
    # what is cached, and the pages that failed
    .venv/bin/python tools/build_link_cache.py --status
    .venv/bin/python tools/build_link_cache.py --failures > failures.tsv
    # arXiv versions skipped before, again (after a LaTeXML update, say)
    .venv/bin/python tools/build_link_cache.py --kinds arxiv_version --redo-skipped
"""

import argparse
import functools
import hashlib
import html as htmllib
import io
import json
import logging
import re
import sqlite3
import sys
import threading
import time
import urllib.parse
import urllib.robotparser
import zlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx
import lxml.html
import trafilatura
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "generators"))
import link_cache  # noqa: E402

UA = (
    "synthetic-philosophy-prompts/0.1 "
    "(https://github.com/casparoe/synthetic_philosophy_prompts; research script)"
)
DOMAINS_DIR = REPO_ROOT / "meta_prompt" / "domains"
THIN_CHARS = 300  # text shorter than this is noted as thin
GUTENBERG_MIRROR = "https://gutenberg.pglaf.org"
# A Stack Exchange API filter (made with /filters/create) that returns
# questions with their bodies and all their answers.
SE_FILTER = "!20aKG._8Oscv*6djs8Pgm"
# EA Forum posts published from this date on are under CC BY 4.0.
EA_FORUM_CC_BY_SINCE = "2022-12-01"
# The forums' GraphQL APIs: the EA Forum's read-only mirror for bots and
# agents (its robots.txt asks for one request a second) and LessWrong's own
# (crawl delay 3); and the posts asked for per request.
FORUM_GRAPHQL = {
    "eaforum": "https://forum-bots.effectivealtruism.org/graphql",
    "lesswrong": "https://www.lesswrong.com/graphql",
}
FORUM_BATCH = 10
# Licences stated site-wide, for the header of their pages.
HOST_LICENSES = {"gwern.net": "CC0", "standardebooks.org": "Public domain"}
# Ordinary web pages: trafilatura's guess at the author is often wrong (a
# commenter, the reviewed book's authors, "Posted on"), so it is kept only if
# it looks like a name (see plausible_author), never for these hosts, and
# replaced for these single-author sites.
NO_AUTHOR_HOSTS = {"lesswrong.com", "ndpr.nd.edu"}
HOST_AUTHORS = {"gwern.net": "Gwern Branwen", "readthesequences.com": "Eliezer Yudkowsky"}
NOT_AUTHORS = {
    "authors", "author", "posted on", "name", "people", "staff", "admin",
    "administrator", "editor", "editors", "the editors", "guest", "guest author",
    "bmj", "blogger", "anonymous", "unknown",
}
SITE_NAMES = {
    "aeon.co": "Aeon", "psyche.co": "Psyche", "iep.utm.edu": "Internet Encyclopedia of Philosophy",
    "mathworld.wolfram.com": "Wolfram MathWorld", "econtalk.org": "EconTalk",
}
WIKIPEDIA_TAIL = (
    "See also", "Notes", "References", "Further reading", "External links",
    "Bibliography", "Sources", "Citations", "Footnotes", "Works cited",
    "Notes and references", "References and notes", "Explanatory notes",
)
# Seconds between two requests to one site, at least (robots.txt may ask for more).
DELAYS = {
    "wikipedia": 0.1,
    "eaforum": 2.0,  # ten posts per request
    "lesswrong": 3.0,  # ten posts per request
    "se": 2.0,
    "wayback": 10.0,  # a burst of quick requests gets connections refused for a while
    "gutenberg": 2.0,
    "sep": 5.0,
    "arxiv": 15.0,
    # export.arxiv.org: HTTP 429 or "Rate exceeded." at a request every 2 to 5 seconds (2026-10-22); on
    # 2026-10-24, for sources (/src), every few minutes even at one request a minute (arXiv tightened its
    # per-IP limits in 2026 and publishes no numbers)
    "arxiv_version": 30.0,
    "substack": 1.0,
    "web": 1.0,
}

# After a 429 from export.arxiv.org: ten minutes, then twenty, then forty (its throttle lasts twenty
# minutes or more).
ARXIV_LIMITED_WAIT = 600.0

logging.getLogger("trafilatura").setLevel(logging.CRITICAL)
logging.getLogger("pypdf").setLevel(logging.CRITICAL)


def log(message):
    print(f"{datetime.now().strftime('%H:%M:%S')} {message}", flush=True)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_links():
    """{cache key: URL} for every link in the domain files."""
    links = {}
    for path in sorted(DOMAINS_DIR.glob("*.yaml")):
        for entry in yaml.safe_load(path.read_text()) or []:
            for url in (entry.get("urls") or []) + (entry.get("stable_urls") or []):
                links.setdefault(link_cache.canonical(url), url)
    return links


def kind_of(key):
    """wikipedia, eaforum, lesswrong, se, gutenberg, sep, arxiv, substack or web."""
    head = key.split("/", 1)[0]
    if ":" in head:
        return head.split(":", 1)[0]
    if re.match(r"^[^/]+/p/[^/]+$", key):
        return "substack"  # every /p/<slug> link in the domain files is a Substack post
    return "web"


# Stable kinds share the group (and so the pace) of the site they come from.
SERVICE_OF = {"wikipedia_revision": "wikipedia", "sep_edition": "sep"}
# Groups that must not run at the same time as another: they run after it, in its thread.
AFTER = {"arxiv_version": "arxiv"}


def group_of(key):
    """Requests within a group go out one at a time."""
    kind = kind_of(key)
    if kind == "web":
        return "web:" + key.split("/", 1)[0]
    if kind in ("wikipedia", "wikipedia_revision"):
        return "wikipedia:" + key.split(":")[1]
    return SERVICE_OF.get(kind, kind)


# --- storage -----------------------------------------------------------------


class Store:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False, timeout=120)  # other runs may write too
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(link_cache.SCHEMA)
        self.lock = threading.Lock()
        self.pending = 0
        self.committed_at = time.monotonic()

    def statuses(self):
        with self.lock:
            return dict(self.conn.execute("SELECT key, status FROM pages"))

    def thin_keys(self):
        with self.lock:
            return {k for (k,) in self.conn.execute("SELECT key FROM pages WHERE note LIKE '%thin%'")}

    def put(self, key, url, status, method=None, text=None, title=None, author=None,
            site=None, published=None, license=None, note=None):
        if text is not None:
            text = text.strip()
            if not text:
                text, status = None, "empty"
            elif len(text) < THIN_CHARS:
                note = "; ".join(filter(None, [note, "thin"]))
        blob = zlib.compress(text.encode("utf-8"), 6) if text is not None else None
        row = (
            key, url, status, method, clean(title), clean(author), clean(site),
            clean(published), license, len(text) if text else None, blob, now(), note,
        )
        with self.lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO pages (key, url, status, method, title, author, "
                "site, published, license, chars, text, fetched_at, note) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                row,
            )
            self.pending += 1
            if self.pending >= 50 or time.monotonic() - self.committed_at > 20:
                self.commit()

    def commit(self):
        self.conn.commit()
        self.pending = 0
        self.committed_at = time.monotonic()

    def close(self):
        with self.lock:
            self.commit()
        self.conn.close()


def clean(value):
    if value is None:
        return None
    value = re.sub(r"\s+", " ", htmllib.unescape(str(value))).strip()
    return value or None


# --- fetching ----------------------------------------------------------------


class Site:
    """Requests to one site: one at a time, at least delay seconds apart,
    backing off on rate limits and server errors."""

    def __init__(self, name, delay, limited_wait=None):
        self.name = name
        self.delay = self.base_delay = delay
        self.limited_wait = limited_wait  # seconds after a first rate limit (doubling); default a minute more each time
        self.max_delay = max(60.0, delay)
        self.next_at = 0.0
        self.streak = 0  # successes since the last slow-down
        self.client = httpx.Client(
            headers={"User-Agent": UA},
            timeout=httpx.Timeout(60.0, connect=20.0),
            follow_redirects=True,
        )

    def slow_down(self, delay):
        """Honour a crawl delay (up to two minutes)."""
        self.base_delay = max(self.base_delay, min(delay, 120.0))
        self.delay = max(self.delay, self.base_delay)

    def request(self, method, url, tries=4, **kwargs):
        for attempt in range(tries):
            pause = self.next_at - time.monotonic()
            if pause > 0:
                time.sleep(pause)
            try:
                response = self.client.request(method, url, **kwargs)
            except httpx.HTTPError:
                self.next_at = time.monotonic() + self.delay + 30 * (attempt + 1)
                if attempt == tries - 1:
                    raise
                continue
            self.next_at = time.monotonic() + self.delay
            limited = response.status_code == 429 or rate_limit_page(response)
            if limited or response.status_code >= 500:
                self.streak = 0
                if limited:
                    self.delay = min(self.delay * 1.2, self.max_delay)
                wait = retry_after(response) or (
                    self.limited_wait * 2 ** attempt if limited and self.limited_wait else 60 * (attempt + 1))
                self.next_at = time.monotonic() + max(wait, self.delay)
                if attempt < tries - 1:
                    log(f"{self.name}: HTTP {response.status_code} for {url}, waiting {wait:.0f} s")
                    continue
            else:
                # after a slow-down, speed up again gradually
                self.streak += 1
                if self.streak >= 50 and self.delay > self.base_delay:
                    self.delay = max(self.base_delay, self.delay / 1.2)
                    self.streak = 0
            return response

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)


def rate_limit_page(response):
    """GreaterWrong serves its 'Too many requests' page with status 200;
    export.arxiv.org answers just "Rate exceeded."."""
    body = response.content.lower() if len(response.content) < 4000 else b""
    return (
        (response.status_code == 200 and b"too many requests" in body)
        or body.strip() == b"rate exceeded."
    )


def retry_after(response):
    try:
        return min(float(response.headers.get("retry-after", "")), 900.0)
    except ValueError:
        return None


class Robots:
    """robots.txt of each host, read once, through the host's own Site."""

    def __init__(self):
        self.cache = {}
        self.lock = threading.Lock()

    def check(self, site, url):
        """Whether url may be fetched, and the largest crawl delay the host asks for."""
        host = urllib.parse.urlsplit(url).netloc
        with self.lock:
            entry = self.cache.get(host)
        if entry is None:
            parser = urllib.robotparser.RobotFileParser()
            lines, delay = [], 0.0
            try:
                response = site.get(f"https://{host}/robots.txt", tries=2)
                if response.status_code in (401, 403):
                    parser.disallow_all = True
                elif response.status_code == 200:
                    lines = response.text.splitlines()
            except httpx.HTTPError:
                pass
            parser.parse(lines)
            for line in lines:
                if m := re.match(r"(?i)\s*crawl-delay\s*:\s*([\d.]+)", line):
                    delay = max(delay, float(m.group(1)))
            entry = (parser, delay)
            with self.lock:
                self.cache[host] = entry
        parser, delay = entry
        site.slow_down(delay)
        return parser.can_fetch(UA, url)


def http_failure(response):
    if response.status_code in (404, 410):
        return {"status": f"gone {response.status_code}"}
    return {"status": f"error {response.status_code}"}


# --- text extraction ---------------------------------------------------------

BLOCK_TAGS = (
    "p", "div", "section", "article", "blockquote", "pre", "table", "tr", "ul",
    "ol", "dl", "dt", "dd", "figure", "figcaption", "header", "footer", "aside",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr",
)


def html_to_text(root):
    """Plain text of an HTML element or fragment, keeping paragraph breaks,
    headings (as #), list items (-), table cells (|) and quotations (>)."""
    if isinstance(root, str):
        if not root.strip():
            return ""
        root = lxml.html.fragment_fromstring(source_text(root, keep_space=True), create_parent="div")
    for el in root.xpath(".//script|.//style|.//noscript|.//svg|.//button|.//form|.//comment()"):
        el.drop_tree()
    # Line breaks in the HTML source are just spaces (except in <pre>), and
    # control characters go: lxml refuses to set text that has them.
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        in_pre = any(a.tag == "pre" for a in el.iterancestors())
        if el.text:
            el.text = source_text(el.text, keep_space=in_pre or el.tag == "pre")
        if el.tail:
            el.tail = source_text(el.tail, keep_space=in_pre)
    for el in root.xpath(".//br"):
        el.tail = "\n" + (el.tail or "")
    for el in root.xpath(".//h1|.//h2|.//h3|.//h4|.//h5|.//h6"):
        el.text = "\n\n" + "#" * int(el.tag[1]) + " " + (el.text or "")
    for el in root.xpath(".//li"):
        el.text = "- " + (el.text or "")
        el.tail = "\n" + (el.tail or "")
    for el in root.xpath(".//td|.//th"):
        el.tail = " | " + (el.tail or "")
    for el in root.xpath(".//blockquote"):
        for p in el.xpath(".//p") or [el]:
            p.text = "> " + (p.text or "")
    for el in root.iter(*BLOCK_TAGS):
        el.tail = "\n\n" + (el.tail or "")
    return tidy(root.text_content())


def source_text(text, keep_space):
    """Text from the HTML source without the characters XML forbids (control
    characters, noncharacters, lone surrogates), whitespace collapsed unless
    keep_space."""
    text = re.sub(r"[\x00-\x08\x0e-\x1f\ufffe\uffff\ud800-\udfff]", "", text)
    text = re.sub(r"[\x0b\x0c]", "\n", text)
    return text if keep_space else re.sub(r"\s+", " ", text)


def tidy(text):
    text = text.replace("\r\n", "\n").replace(" ", " ")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def pdf_text(content, max_pages=400):
    import pypdf  # only needed here

    reader = pypdf.PdfReader(io.BytesIO(content))
    pages = []
    for page in reader.pages[:max_pages]:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 -- a broken page shouldn't lose the rest
            pages.append("")
    title = None
    try:
        title = (reader.metadata or {}).get("/Title")
    except Exception:  # noqa: BLE001
        pass
    text = tidy("\n\n".join(pages))
    # Some PDFs (TeX with Type 3 fonts) extract as glyph codes like /x54/x68:
    # mostly not letters, and useless.
    visible = sum(not c.isspace() for c in text)
    if visible and sum(c.isalpha() for c in text) / visible < 0.6:
        text = ""
    return text, (str(title) if title else None)


def page_text(html, url):
    """Main text (Markdown-ish) and metadata of an ordinary web page; the
    date only from the page's markup or URL, not guessed from its text."""
    text = trafilatura.extract(
        html, url=url, output_format="markdown", include_comments=False,
        include_tables=True,
    )
    meta = trafilatura.extract_metadata(html, default_url=url, extensive=False)
    if meta is None:
        return text, {}
    host = (urllib.parse.urlsplit(url).hostname or "").removeprefix("www.")
    title = meta.title
    # A page whose title is just the site's name (IEP's): use its heading.
    heading = re.match(r"# (.+)\n", (text or "") + "\n")
    if heading and (not title or heading.group(1).strip().lower() not in title.lower()):
        title = heading.group(1).strip()
    if title:
        title = re.sub(r"[*_`]{2,}|`", "", title)
    published = meta.date
    if published and published.endswith("-01-01"):
        published = None  # a bare year, usually a copyright line
    author = None if host in NO_AUTHOR_HOSTS else plausible_author(meta.author)
    site = SITE_NAMES.get(host) or (meta.sitename if meta.sitename not in (None, "Blogger") else None)
    return text, {
        "title": title, "author": HOST_AUTHORS.get(host, author), "site": site,
        "published": published,
    }


# Where blogs keep a post's text (Blogger's post-body, WordPress's
# entry-content), for the pages trafilatura extracts nothing from.
CONTENT_XPATHS = [
    f"//div[contains(concat(' ', normalize-space(@class), ' '), ' {name} ')]"
    for name in ("post-body", "entry-content", "post-content", "article-content")
] + ["//article", "//main"]


def container_text(html):
    """The text of the page's main content container, without its share
    buttons, or None if it has no such container with much text."""
    doc = lxml.html.fromstring(html)
    for xpath in CONTENT_XPATHS:
        found = doc.xpath(xpath)
        if not found:
            continue
        root = found[0]
        for el in root.xpath(".//*[contains(@class, 'share') or contains(@class, 'social')]"):
            el.drop_tree()
        text = html_to_text(root)
        if len(text) >= THIN_CHARS:
            return text
    return None


def plausible_author(name):
    name = clean(name)
    if (
        not name or len(name) > 60 or ";" in name or re.search(r"\d", name)
        or name.lower() in NOT_AUTHORS or name.lower().startswith(("about the author", "posted", "by "))
    ):
        return None
    return name


def first(values):
    return next((v for v in values if v), None)


def first_el(nodes):
    """The first of a list of elements, or None (an lxml element without
    children counts as false, so first() would skip it)."""
    return nodes[0] if len(nodes) else None


def person_name(citation_name):
    """'Weirich, Paul' -> 'Paul Weirich'."""
    if "," in citation_name:
        last, first_names = citation_name.split(",", 1)
        return f"{first_names.strip()} {last.strip()}".strip()
    return citation_name.strip()


# --- the sources ---------------------------------------------------------------


def fetch_wikipedia(site, robots, key, url):
    _, lang, title = key.split(":", 2)
    params = {
        "action": "query", "prop": "extracts", "explaintext": 1,
        "exsectionformat": "wiki", "titles": title, "redirects": 1,
        "format": "json", "formatversion": 2, "maxlag": 5,
    }
    for _ in range(4):
        response = site.get(f"https://{lang}.wikipedia.org/w/api.php", params=params)
        if response.status_code != 200:
            return http_failure(response)
        data = response.json()
        if data.get("error", {}).get("code") == "maxlag":
            time.sleep(10)
            continue
        break
    else:
        return {"status": "error maxlag"}
    if "error" in data:
        return {"status": "error api", "note": data["error"].get("code")}
    page = data["query"]["pages"][0]
    if page.get("missing") or page.get("invalid"):
        return {"status": "gone missing"}
    text = page.get("extract") or ""
    tail = re.search(
        r"^==\s*(?:" + "|".join(map(re.escape, WIKIPEDIA_TAIL)) + r")\s*==\s*$", text, re.M
    )
    if tail:
        text = text[: tail.start()]
    return {
        "status": "ok", "method": "wikipedia_api", "title": page.get("title"),
        "site": "Wikipedia", "text": text,
    }


FORUM_POST_FIELDS = "title postedAt htmlBody user { displayName } coauthors { displayName }"


def forum_record(post, forum):
    """The record of a LessWrong or EA Forum post from the forum's GraphQL API."""
    authors = [post.get("user") or {}] + (post.get("coauthors") or [])
    published = (post.get("postedAt") or "")[:10] or None
    license_ = None
    if forum == "eaforum" and published and published >= EA_FORUM_CC_BY_SINCE:
        license_ = "CC BY 4.0"
    return {
        "status": "ok", "method": f"{forum}_graphql", "title": post.get("title"),
        "author": ", ".join(a["displayName"] for a in authors if a.get("displayName")) or None,
        "site": "EA Forum" if forum == "eaforum" else "LessWrong",
        "published": published, "license": license_,
        "text": html_to_text(post.get("htmlBody") or ""),
    }


def run_forum(forum, jobs, store, robots, progress):
    """Posts of a forum (eaforum or lesswrong), FORUM_BATCH per request (one
    aliased post query each), from its GraphQL API."""
    site = Site(forum, DELAYS[forum])
    endpoint = FORUM_GRAPHQL[forum]
    allowed = robots.check(site, endpoint)  # and take its crawl delay
    for i in range(0, len(jobs), FORUM_BATCH):
        chunk = jobs[i: i + FORUM_BATCH]
        failure, data, errors = None, {}, {}
        if not allowed:
            failure = "robots"
        else:
            query = "{ " + " ".join(
                f'p{n}: post(input: {{selector: {{_id: "{key.split(":", 1)[1]}"}}}}) '
                f"{{ result {{ {FORUM_POST_FIELDS} }} }}"
                for n, (key, _) in enumerate(chunk)
            ) + " }"
            try:
                response = site.request("POST", endpoint, json={"query": query})
                if response.status_code != 200:
                    failure = http_failure(response)["status"]
                else:
                    body = response.json()
                    data = body.get("data") or {}
                    errors = {
                        (e.get("path") or [None])[0]: e.get("message", "")
                        for e in body.get("errors") or []
                    }
            except (httpx.HTTPError, ValueError) as e:
                failure = f"error {type(e).__name__}"
        for n, (key, url) in enumerate(chunk):
            post = ((data.get(f"p{n}") or {}).get("result")) if not failure else None
            if failure:
                record = {"status": failure}
            elif post:
                try:
                    record = forum_record(post, forum)
                except Exception as e:  # noqa: BLE001 -- one bad post shouldn't stop the rest
                    record = {"status": f"error {type(e).__name__}", "note": str(e)[:200]}
            elif errors.get(f"p{n}") == "app.missing_document":
                record = {"status": "gone missing"}
            else:
                record = {"status": "error api", "note": (errors.get(f"p{n}") or "no result")[:200]}
            store.put(key, url, **record)
            progress.add(forum, record["status"])


def gutenberg_record(raw, method):
    """A book's record from its plain text (or the text of its HTML edition):
    the part between Project Gutenberg's START and END lines, and the title,
    author and release date from its header."""
    raw = raw.replace("\r\n", "\n")
    start = re.search(r"^\*\*\* ?START OF (?:THE|THIS) PROJECT GUTENBERG.*$", raw, re.M | re.I)
    end = re.search(r"^\*\*\* ?END OF (?:THE|THIS) PROJECT GUTENBERG.*$", raw, re.M | re.I)
    header = raw[: start.start()] if start else ""
    body = raw[start.end(): end.start() if end else len(raw)] if start else raw

    def field(name):
        m = re.search(rf"^{name}:\s*(.+)$", header, re.M | re.I)
        return m.group(1).strip() if m else None

    released = field("Release date")
    if released:
        released = re.sub(r"\s*\[e(?:Book|Text) #\d+\]", "", released, flags=re.I).strip()
        released = f"this Project Gutenberg edition released {released}"
    # Public domain unless the header says otherwise (a few books are
    # copyrighted with permission); unknown without a header.
    public = bool(header) and not re.search(r"copyright(?!\s+laws)", header, re.I)
    return {
        "status": "ok", "method": method, "title": field("Title"),
        "author": field("Author"), "site": "Project Gutenberg", "published": released,
        "license": "Public domain in the USA" if public else None,
        "text": re.sub(r"\n{3,}", "\n\n", body).strip(),
    }


def fetch_gutenberg(site, robots, key, url):
    """A book from the PGLAF mirror: its plain text; if that is missing or
    only a stub pointing at another format, the HTML edition; failing both,
    the best of the files in the book's directory (HTML edition, plain text,
    TeX source, PDF)."""
    number = key.split(":", 1)[1]
    digits = "/".join(number[:-1]) if len(number) > 1 else "0"
    epub = f"{GUTENBERG_MIRROR}/cache/epub/{number}/pg{number}"
    folder = f"{GUTENBERG_MIRROR}/{digits}/{number}/"

    def get(target):
        if not robots.check(site, target):
            return None
        response = site.get(target)
        return response if response.status_code == 200 else None

    def links(page):
        return re.findall(r'href="([^"?/][^"]*)"', page.text) if page is not None else []

    def from_folder(files):
        """Records from the files of the book's directory, best formats first."""
        if f"{number}-h/" in files:
            page = get(f"{folder}{number}-h/{number}-h.htm")
            body = lxml.html.fromstring(page.content).xpath("//body") if page is not None else []
            if body:
                yield gutenberg_record(html_to_text(body[0]), "gutenberg_mirror_html")
        for name in sorted(f for f in files if f.endswith(".txt")):
            page = get(folder + name)
            if page is not None:
                yield gutenberg_record(page.content.decode("utf-8", errors="replace"), "gutenberg_mirror")
        if f"{number}-t/" in files:
            for name in [f for f in links(get(f"{folder}{number}-t/")) if f.endswith(".tex")][:1]:
                page = get(f"{folder}{number}-t/{name}")
                if page is not None:
                    yield gutenberg_record(page.content.decode("utf-8", errors="replace"), "gutenberg_mirror_tex")
        for name in sorted(f for f in files if f.endswith(".pdf")):
            page = get(folder + name)
            if page is not None:
                text, title = pdf_text(page.content)
                pdf_record = gutenberg_record(text, "gutenberg_mirror_pdf")
                pdf_record["title"] = pdf_record["title"] or title
                yield pdf_record

    record = None
    page = get(epub + ".txt")
    if page is not None:
        record = gutenberg_record(page.content.decode("utf-8", errors="replace"), "gutenberg_mirror")
    if record is None or len(record["text"]) < 2000:
        page = get(epub + "-images.html")
        if page is not None:
            body = lxml.html.fromstring(page.content).xpath("//body")
            if body:
                html_record = gutenberg_record(html_to_text(body[0]), "gutenberg_mirror_html")
                if record is None or len(html_record["text"]) > len(record["text"]):
                    record = html_record
    if record is None or len(record["text"]) < 2000:
        for candidate in from_folder(links(get(folder))):
            if record is None or len(candidate["text"]) > len(record["text"]):
                record = candidate
            if len(record["text"]) >= 2000:
                break
    return record or {"status": "error mirror 404"}


def fetch_sep(site, robots, key, url):
    slug = key.split(":", 1)[1]
    return sep_record(site, robots, f"https://plato.stanford.edu/entries/{slug}/", "sep")


def fetch_sep_edition(site, robots, key, url):
    """An entry in an SEP archive edition, from the edition's own page."""
    _, edition, slug = key.split(":", 2)
    return sep_record(site, robots, f"https://plato.stanford.edu/archives/{edition}/entries/{slug}/", "sep_edition")


def sep_record(site, robots, target, method):
    if not robots.check(site, target):
        return {"status": "robots"}
    response = site.get(target)
    if response.status_code != 200:
        return http_failure(response)
    doc = lxml.html.fromstring(response.text)

    def part(div_id):
        found = doc.xpath(f"//div[@id='{div_id}']")
        return found[0] if found else None

    pubinfo = part("pubinfo")
    sections = []
    for div_id in ("preamble", "toc", "main-text", "bibliography"):
        el = part(div_id)
        if el is not None:
            text = html_to_text(el)
            sections.append(("Contents\n\n" + text) if div_id == "toc" else text)
    authors = [person_name(m.get("content", "")) for m in doc.xpath("//meta[@name='citation_author']")]
    return {
        "status": "ok", "method": method, "title": first(h.text_content() for h in doc.xpath("//h1")),
        "author": ", ".join(a for a in authors if a) or None,
        "site": "Stanford Encyclopedia of Philosophy",
        "published": pubinfo.text_content() if pubinfo is not None else None,
        "text": "\n\n".join(sections),
    }


def license_name(href):
    if not href:
        return None
    if m := re.search(r"creativecommons\.org/(?:licenses|publicdomain)/([a-z-]+)/([\d.]+)", href):
        code, version = m.groups()
        return f"CC0 {version}" if code == "zero" else f"CC {code.upper()} {version}"
    if "nonexclusive-distrib" in href:
        return "arXiv non-exclusive license to distribute"
    return None


def ltx_class(name):
    """An XPath test for an element with the class name (LaTeXML's ltx_...)."""
    return f"contains(concat(' ', @class, ' '), ' {name} ')"


def arxiv_html_text(html):
    """The text of LaTeXML's HTML (arXiv's, or ours): formulas as their TeX,
    footnotes in brackets where they are marked ("[Footnote 2: ...]"), without
    the table of contents or the names of macros LaTeXML did not know."""
    doc = lxml.html.fromstring(html)
    article = doc.xpath("//article") or [doc]
    root = article[0]
    for nav in root.xpath(".//nav"):  # LaTeXML's table of contents
        nav.drop_tree()
    for error in root.xpath(f".//*[{ltx_class('ltx_ERROR')}]"):
        error.drop_tree()  # keeps the tail
    # A note is its mark, then its content, which repeats the mark: "form¹¹The contrast ..."
    for note in root.xpath(f".//*[{ltx_class('ltx_note')}]"):
        marks = note.xpath(f"./*[{ltx_class('ltx_note_mark')}]")
        mark = marks[0].text_content().strip() if marks else ""
        content = note.xpath(f".//*[{ltx_class('ltx_note_content')}]")
        bracket = lxml.html.Element("span")
        footnote = "ltx_role_footnote" in (note.get("class") or "").split()
        bracket.text = f" [Footnote {mark}: " if footnote and mark else " [Note: "
        if content:
            body = content[0]
            for el in body.xpath(f".//*[{ltx_class('ltx_note_mark')} or {ltx_class('ltx_tag_note')}]"):
                el.drop_tree()
            body.tail = "]"
            bracket.append(body)
        else:
            bracket.text += "]"
        bracket.tail = note.tail
        note.getparent().replace(note, bracket)
    for math in root.xpath(".//math"):
        alt = math.get("alttext")
        span = lxml.html.Element("span")
        span.text = f"${alt}$" if alt else math.text_content()
        span.tail = math.tail
        math.getparent().replace(math, span)
    return html_to_text(root)


def fetch_arxiv(site, robots, key, url):
    paper = key.split(":", 1)[1]
    target = f"https://arxiv.org/abs/{paper}"
    if not robots.check(site, target):
        return {"status": "robots"}
    response = site.get(target)
    if response.status_code != 200:
        return http_failure(response)
    doc = lxml.html.fromstring(response.text)

    def meta(name):
        return [m.get("content") for m in doc.xpath(f"//meta[@name='{name}']")]

    abstract = first(meta("citation_abstract")) or ""
    published = first(meta("citation_date"))
    full, method = None, "arxiv_abs"
    html_link = first(
        a.get("href") for a in doc.xpath("//a[contains(@href, '/html/')]")
        if "arxiv.org/html/" in (a.get("href") or "")
    )
    if html_link and robots.check(site, html_link):
        page = site.get(html_link)
        if page.status_code == 200 and "<article" in page.text:
            full, method = arxiv_html_text(page.text), "arxiv_html"
    if not full:
        pdf = first(meta("citation_pdf_url")) or f"https://arxiv.org/pdf/{paper}"
        if robots.check(site, pdf):
            page = site.get(pdf)
            if page.status_code == 200 and page.content[:5] == b"%PDF-":
                full, method = pdf_text(page.content)[0], "arxiv_pdf"
    text = f"Abstract: {tidy(abstract)}" + (f"\n\n{full}" if full else "")
    return {
        "status": "ok", "method": method, "title": first(meta("citation_title")),
        "author": ", ".join(person_name(a) for a in meta("citation_author")) or None,
        "site": "arXiv", "published": published.replace("/", "-") if published else None,
        "license": license_name(
            first(a.get("href") for a in doc.xpath("//div[contains(@class, 'abs-license')]//a"))
        ),
        "text": text,
    }


def fetch_substack(site, robots, key, url):
    host = urllib.parse.urlsplit(url).netloc
    slug = key.split("/p/", 1)[1]
    api_url = f"https://{host}/api/v1/posts/{slug}"
    if not robots.check(site, api_url):
        return fetch_web(site, robots, key, url)
    response = site.get(api_url)
    if response.status_code != 200 or "json" not in response.headers.get("content-type", ""):
        return fetch_web(site, robots, key, url)
    post = response.json()
    root = lxml.html.fragment_fromstring(post.get("body_html") or "<p></p>", create_parent="div")
    for el in root.xpath(
        ".//*[contains(@class, 'subscription-widget') or contains(@class, 'button-wrapper') "
        "or contains(@class, 'captioned-button') or contains(@class, 'image-link-expand')]"
    ):
        el.drop_tree()
    text = html_to_text(root)
    subtitle = (post.get("subtitle") or "").strip()
    if subtitle.strip(".… "):  # Astral Codex Ten's subtitles are just "..."
        text = f"{subtitle}\n\n{text}"
    authors = [b.get("name") for b in post.get("publishedBylines") or [] if b.get("name")]
    return {
        "status": "ok", "method": "substack_api", "title": post.get("title"),
        "author": ", ".join(authors) or None, "site": f"{host.removeprefix('www.')} (Substack)",
        "published": (post.get("post_date") or "")[:10] or None,
        "note": "paywalled, preview only" if post.get("audience") == "only_paid" else None,
        "text": text,
    }


def fetch_web(site, robots, key, url, include_comments=False):
    if not robots.check(site, url):
        return {"status": "robots"}
    response = site.get(url)
    if response.status_code != 200:
        return http_failure(response)
    host = urllib.parse.urlsplit(str(response.url)).hostname or ""
    host = host.removeprefix("www.")
    if response.content[:5] == b"%PDF-" or "pdf" in response.headers.get("content-type", ""):
        text, title = pdf_text(response.content)
        return {
            "status": "ok", "method": "pdf", "title": title, "site": host,
            "license": HOST_LICENSES.get(host), "text": text,
        }
    html = response.text
    text, fields = page_text(html, str(response.url))
    method = "html"
    if len(text or "") < THIN_CHARS:
        fallback = container_text(html)
        if fallback and len(fallback) > len(text or ""):
            text, method = fallback, "html_container"
    if include_comments and text:
        with_comments = trafilatura.extract(
            html, url=str(response.url), output_format="markdown", include_comments=True,
        )
        text = with_comments or text
    return {
        "status": "ok", "method": method, "text": text or "", "license": HOST_LICENSES.get(host),
        **{k: v for k, v in fields.items() if v},
        "site": fields.get("site") or host,
    }


# --- stable links ------------------------------------------------------------------

WIKIPEDIA_DROP = (
    "mw-editsection", "reference", "infobox", "navbox", "vertical-navbox", "sidebar", "hatnote",
    "reflist", "references", "thumb", "metadata", "ambox", "noprint", "mw-empty-elt",
    "shortdescription", "toc",
)


def fetch_wikipedia_revision(site, robots, key, url):
    """A Wikipedia revision as Wikipedia renders it (action=parse with its
    oldid), without edit links, reference markers and lists, infoboxes,
    navigation boxes, images, and the sections from WIKIPEDIA_TAIL on."""
    _, lang, revid = key.split(":", 2)
    params = {
        "action": "parse", "oldid": revid, "prop": "text|revid", "format": "json",
        "formatversion": 2, "disableeditsection": 1, "disabletoc": 1, "maxlag": 5,
    }
    for _ in range(4):
        response = site.get(f"https://{lang}.wikipedia.org/w/api.php", params=params)
        if response.status_code != 200:
            return http_failure(response)
        data = response.json()
        if data.get("error", {}).get("code") == "maxlag":
            time.sleep(10)
            continue
        break
    else:
        return {"status": "error maxlag"}
    if "error" in data:
        code = data["error"].get("code")
        return {"status": "gone missing" if code in ("nosuchrevid", "missingtitle") else "error api", "note": code}
    parsed = data["parse"]
    if str(parsed.get("revid")) != revid:
        return {"status": "error api", "note": f"got revision {parsed.get('revid')}"}
    root = lxml.html.fragment_fromstring(parsed["text"], create_parent="div")
    for el in root.xpath(
        " | ".join(f".//*[contains(concat(' ', normalize-space(@class), ' '), ' {c} ')]" for c in WIKIPEDIA_DROP)
        + " | .//figure | .//style | .//*[@id='toc']"
    ):
        if el.getparent() is not None:
            el.drop_tree()
    # Cut at the first tail section ("See also", "References", ...): its heading
    # (or the div that wraps it) and everything after it.
    top = root[0] if len(root) == 1 and root[0].tag == "div" else root
    tail = False
    for child in list(top):
        heading = child if child.tag == "h2" else first_el(child.xpath(".//h2"))
        if heading is not None and heading.text_content().strip() in WIKIPEDIA_TAIL:
            tail = True
        if tail:
            top.remove(child)
    return {
        "status": "ok", "method": "wikipedia_revision", "title": parsed.get("title"),
        "site": "Wikipedia", "note": f"revision {revid}", "text": html_to_text(root),
    }


ARXIV_EXPORT = "https://export.arxiv.org"
LATEXML_WORKERS = 3  # papers rendered at once
# a version in the abstract page's submission history: "[v2] Tue, 8 Aug 2023 23:47:28 UTC (1,029 KB)"
ARXIV_HISTORY_RE = r"\[v{n}\]\s+\w{{3}}, (\d{{1,2}} \w{{3}} \d{{4}} \d\d:\d\d:\d\d) UTC"


def arxiv_version_metadata(site, version):
    """Title, authors, date and license of one version of an arXiv paper,
    from its abstract page, and the time it was submitted (or a failure)."""
    response = site.get(f"{ARXIV_EXPORT}/abs/{version}")
    if response.status_code != 200:
        return http_failure(response), None
    doc = lxml.html.fromstring(response.text)

    def meta(name):
        return [m.get("content") for m in doc.xpath(f"//meta[@name='{name}']")]

    if not meta("citation_title"):
        return {"status": "error no-abstract-page"}, None  # a rate-limit reply, say
    history = " ".join(" ".join(doc.xpath("//div[contains(@class, 'submission-history')]//text()")).split())
    submitted = None
    if m := re.search(ARXIV_HISTORY_RE.format(n=version.rsplit("v", 1)[1]), history):
        submitted = datetime.strptime(m.group(1), "%d %b %Y %H:%M:%S").replace(tzinfo=timezone.utc)
    published = first(meta("citation_date"))
    record = {
        "status": "ok", "site": "arXiv", "title": first(meta("citation_title")),
        "author": ", ".join(person_name(a) for a in meta("citation_author")) or None,
        "published": submitted.date().isoformat() if submitted else published and published.replace("/", "-"),
        "license": license_name(
            first(a.get("href") for a in doc.xpath("//div[contains(@class, 'abs-license')]//a"))
        ),
    }
    return record, submitted


def arxiv_version_source(site, version, directory):
    """The source of one version as arXiv serves it (gzipped tar or TeX, or
    a PDF), from directory if it was downloaded before, else downloaded and
    kept there; or None and a failure."""
    stem = version.replace("/", "_")
    kept = sorted(p for p in directory.glob(stem + ".*") if not p.name.endswith(".part"))
    if kept:
        return kept[0].read_bytes(), None
    response = site.get(f"{ARXIV_EXPORT}/src/{version}")
    if response.status_code != 200:
        return None, http_failure(response)
    if rate_limit_page(response) or not response.content:
        return None, {"status": "error rate-limited"}
    name = re.findall(r'filename="?([^";]+)', response.headers.get("content-disposition", ""))
    m = re.search(r"(\.tar\.gz|\.[A-Za-z]+)$", name[0]) if name else None  # arXiv-2601.08850v1.tar.gz
    suffix = m.group(1) if m else ".bin"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (stem + suffix)
    partial = path.with_name(path.name + ".part")
    partial.write_bytes(response.content)
    partial.rename(path)
    return response.content, None


def arxiv_render(source, submitted, latexml, log_path):
    """A version's page, from its source as LaTeXML renders it (in the
    sandbox): (text, method, "ok", note); or (None, None, "skipped ...", note)
    if the source is only a PDF, or LaTeXML cannot render it. LaTeXML's log
    goes to log_path."""
    import arxiv_latexml

    sha = hashlib.sha256(source).hexdigest()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        kind, content, info = arxiv_latexml.eprint_html(
            source, source_date=submitted.timestamp() if submitted else None, keep_log=log_path
        )
    except arxiv_latexml.SourceError as e:
        return None, None, "skipped latexml", f"source {sha}; {latexml[0]}; {e}"
    if kind == "pdf":
        return None, None, "skipped pdf-only", f"source {sha} is a PDF"
    text = arxiv_html_text(content)
    note = (f"source {sha}; {latexml[0]}; main file {info['main']}; "
            f"LaTeXML status {info['status']} in {info['seconds']} s: {info['summary']}")
    if len(text) < 1500:
        return None, None, "skipped latexml", note + f"; only {len(text)} characters"
    return text, f"arxiv_latexml {latexml[1]}", "ok", note


def run_arxiv_versions(jobs, store, robots, progress, site=None):
    """Versioned arXiv abstract links (see the module docstring): the
    abstract pages and sources are fetched one at a time, and the sources
    rendered LATEXML_WORKERS at a time meanwhile; a version LaTeXML cannot
    render is skipped."""
    import concurrent.futures

    import arxiv_latexml

    site = site or Site("arxiv_version", DELAYS["arxiv_version"], limited_wait=ARXIV_LIMITED_WAIT)
    try:
        latexml = arxiv_latexml.latexml_version()
        arxiv_latexml.tex_paths()
    except SystemExit as e:  # no LaTeXML or TeX Live: leave the versions for a later run
        log(f"arxiv_version: {e}; {len(jobs)} versions skipped")
        return
    directory = store.path.parent / "arxiv_source"
    logs = store.path.parent / "arxiv_logs"  # LaTeXML's, one per version
    log(f"arxiv_version: {len(jobs)} versions, rendered with {latexml[0]}")

    def finish(key, url, record, outcome):
        text, method, status, note = outcome
        if status == "ok":
            record = {**record, "method": method, "text": text}
        else:
            record = {**record, "status": status}
        store.put(key, url, **{**record, "note": note})
        progress.add("arxiv_version", record["status"])

    with concurrent.futures.ThreadPoolExecutor(LATEXML_WORKERS) as pool:
        pending = {}

        def settle(block):
            done, _ = concurrent.futures.wait(
                pending, timeout=None if block else 0, return_when=concurrent.futures.FIRST_COMPLETED
            )
            for future in done:
                key, url, record = pending.pop(future)
                try:
                    outcome = future.result()
                except Exception as e:  # noqa: BLE001 -- one bad paper shouldn't stop the rest
                    outcome = None, None, f"error {type(e).__name__}", str(e)[:300]
                finish(key, url, record, outcome)

        for key, url in jobs:
            version = key.split(":", 1)[1]
            try:
                record, submitted = arxiv_version_metadata(site, version)
                source = None
                if record["status"] == "ok":
                    source, failure = arxiv_version_source(site, version, directory)
                    record = failure or record
            except Exception as e:  # noqa: BLE001
                record, source = {"status": f"error {type(e).__name__}", "note": str(e)[:200]}, None
            if source is None:
                store.put(key, url, **record)
                progress.add("arxiv_version", record["status"])
            else:
                log_path = logs / (version.replace("/", "_") + ".log")
                pending[pool.submit(arxiv_render, source, submitted, latexml, log_path)] = (key, url, record)
            settle(block=len(pending) >= 2 * LATEXML_WORKERS)
        while pending:
            settle(block=True)


FORUM_SITES = {
    "lesswrong.com": "LessWrong", "forum.effectivealtruism.org": "EA Forum",
    "alignmentforum.org": "AI Alignment Forum",
}


def forum_page(html, host, url):
    """A LessWrong, Alignment Forum, or EA Forum post page (ForumMagnum): the
    post's body, without the comments. The classic pages have it in
    #postContent; the redesigned ones (the EA Forum's in 2026, a Next.js app)
    only in their flight data (flight_post_html)."""
    doc = lxml.html.fromstring(html)

    def meta(name):
        return [m.get("content") for m in doc.xpath(f"//meta[@name='{name}']")]

    body = first_el(doc.xpath("//*[@id='postContent']"))
    if body is not None:
        text = html_to_text(body)
        stamp = first(doc.xpath("//*[contains(@class, 'PostsPageDate-date')]//time/@datetime"))
    else:
        post = link_cache.FORUM_POST_RE.match(urllib.parse.urlsplit(url).path)
        fragment = flight_post_html(html, post.group(1)) if post else None
        if not fragment:
            return None
        text = html_to_text(fragment)
        stamp = first(meta("citation_publication_date"))
    published = stamp[:10].replace("/", "-") if stamp else None
    license_ = "CC BY 4.0" if host == "forum.effectivealtruism.org" and published and published >= EA_FORUM_CC_BY_SINCE else None
    return {
        "method": "forum", "title": first(meta("citation_title")),
        "author": ", ".join(a for a in meta("citation_author") if a) or None,
        "site": FORUM_SITES.get(host), "published": published, "license": license_, "text": text,
    }


def flight_post_html(html, post_id):
    """The post's HTML from a Next.js page's flight data (the
    self.__next_f.push chunks): the object with the post's _id points from
    its "contents" to a text row (id:T<hex byte length>,<html>)."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', html, re.S)
    if not chunks:
        return None
    try:
        payload = "".join(json.loads(f'"{c}"') for c in chunks)
    except ValueError:
        return None
    m = re.search(
        r'"_id":"%s".{0,20000}?"contents":\{"_id":"[^"]*","html":"\$([0-9a-f]+)"' % re.escape(post_id),
        payload, re.S,
    )
    if not m:
        return None
    data = payload.encode("utf-8")
    row = re.search(rb"(?<![0-9a-f])" + m.group(1).encode() + rb":T([0-9a-f]+),", data)
    if not row:
        return None
    return data[row.end(): row.end() + int(row.group(1), 16)].decode("utf-8", "replace")


def greaterwrong_page(html, host):
    doc = lxml.html.fromstring(html)
    body = doc.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), ' post-body ')]")
    if not body:
        return None
    return {
        "method": "greaterwrong", "title": first(h.text_content().strip() for h in doc.xpath("//h1")),
        "site": "EA Forum" if host.startswith("ea.") else "LessWrong", "text": html_to_text(body[0]),
    }


def se_page(html, host):
    """A Stack Exchange question page: the question and its answers (the
    accepted one first, then by score), each with its score, author, and
    date, as the API version gives them (se_text); no comments."""
    doc = lxml.html.fromstring(html)
    question = first_el(doc.xpath("//div[@id='question']"))
    if question is None:
        return None

    def post(el):
        """Text, author, day, and score of a question or an answer; its
        author signs last (an editor's signature can come first)."""
        body = first_el(el.xpath(".//div[contains(@class, 's-prose') or contains(@class, 'post-text')]"))
        sigs = el.xpath(".//div[contains(@class, 'post-signature')]")
        sig = sigs[-1] if sigs else None
        name = day = None
        if sig is not None:
            name = first(a.text_content().strip() for a in sig.xpath(".//div[contains(@class, 'user-details')]//a"))
            day = first(sig.xpath(".//span[contains(@class, 'relativetime')]/@title"))
        return (html_to_text(body) if body is not None else ""), name, (day or "")[:10], el.get("data-score") or "0"

    text, asker, asked, score = post(question)
    parts = [f"Question (score {score}, asked {asked}{' by ' + asker if asker else ''}):\n\n{text}"]
    answers = doc.xpath("//div[@data-answerid]")
    answers.sort(key=lambda a: ("accepted-answer" not in (a.get("class") or ""), -int(a.get("data-score") or 0)))
    for answer in answers:
        text, name, day, score = post(answer)
        flags = f"score {score}" + (", accepted" if "accepted-answer" in (answer.get("class") or "") else "")
        parts.append(f"Answer{' by ' + name if name else ''} ({flags}, {day}):\n\n{text}")
    title = first_el(doc.xpath("//h1//a"))
    if title is None:
        title = first_el(doc.xpath("//h1"))
    if sum(len(part) for part in parts) < THIN_CHARS + 100:
        return None  # markup this rule does not know; the generic extraction may
    return {
        "method": "stackexchange_page", "title": title.text_content().strip() if title is not None else None,
        "site": host, "published": asked or None, "author": asker, "text": "\n\n".join(parts),
    }


def substack_page(html, host):
    """A Substack post page: the post's body without subscription widgets."""
    doc = lxml.html.fromstring(html)
    body = first_el(doc.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), ' available-content ')]"))
    if body is None:
        return None
    for el in body.xpath(
        ".//*[contains(@class, 'subscription-widget') or contains(@class, 'button-wrapper') "
        "or contains(@class, 'captioned-button') or contains(@class, 'image-link-expand')]"
    ):
        el.drop_tree()
    text = html_to_text(body)
    subtitle = first(h.text_content().strip() for h in doc.xpath("//h3[contains(@class, 'subtitle')]"))
    if subtitle and subtitle.strip(".… "):
        text = f"{subtitle}\n\n{text}"
    published = first(doc.xpath("//meta[@property='article:published_time']/@content"))
    if not published and (m := re.search(r'"datePublished":"(\d{4}-\d\d-\d\d)', html)):
        published = m.group(1)  # newer pages give the date only in their JSON-LD
    return {
        "method": "substack", "title": first(h.text_content().strip() for h in doc.xpath("//h1[contains(@class, 'post-title')]")),
        "author": first(doc.xpath("//meta[@name='author']/@content")),
        "site": f"{host} (Substack)", "published": published[:10] if published else None, "text": text,
    }


def archived_page(response, url):
    """The text and metadata of a page as the Wayback Machine archived it
    (response is the raw capture of url): the site rules above where they
    apply, else the generic extraction of fetch_web."""
    host = (urllib.parse.urlsplit(url).hostname or "").lower().removeprefix("www.")
    if response.content[:5] == b"%PDF-" or "pdf" in response.headers.get("content-type", ""):
        text, title = pdf_text(response.content)
        return {"method": "pdf", "title": title, "site": host, "license": HOST_LICENSES.get(host), "text": text}
    html = response.text
    record = None
    if host in FORUM_SITES:
        record = forum_page(html, host, url)
    elif host.endswith("greaterwrong.com"):
        record = greaterwrong_page(html, host)
    elif host.endswith(".stackexchange.com") or host in link_cache.STACK_EXCHANGE_HOSTS:
        record = se_page(html, host)
    elif "available-content" in html and "substack" in html:
        record = substack_page(html, host)
    if record is not None and len(record.get("text") or "") < THIN_CHARS:
        record = None  # the site rule found too little; try the generic extraction
    if record is None:
        text, fields = page_text(html, url)
        method = "html"
        if len(text or "") < THIN_CHARS:
            fallback = container_text(html)
            if fallback and len(fallback) > len(text or ""):
                text, method = fallback, "html_container"
        record = {"method": method, "text": text or "", "license": HOST_LICENSES.get(host),
                  **{k: v for k, v in fields.items() if v}}
        record["site"] = fields.get("site") or host
    return record


def fetch_wayback(site, robots, key, url):
    """A Wayback Machine capture: the page as archived (the raw id_ form,
    without the archive's banner and rewritten links), and only if the
    archive has a capture at exactly the link's timestamp; it redirects to
    the nearest capture otherwise."""
    stamp, original = key.split(":", 1)[1].split("/", 1)
    raw = f"https://web.archive.org/web/{stamp}id_/{original}"
    if not robots.check(site, raw):
        return {"status": "robots"}
    response = site.get(raw)
    if response.status_code != 200:
        return http_failure(response)
    got = re.search(r"/web/(\d{14})", str(response.url))
    if not got or got.group(1) != stamp:
        return {"status": "gone no-capture", "note": f"the archive redirects to {got.group(1) if got else 'another page'}"}
    record = archived_page(response, original)
    record["method"] = "wayback_" + record["method"]
    return {"status": "ok", **record}


def se_text(question):
    def who(post):
        name = (post.get("owner") or {}).get("display_name")
        return f" by {htmllib.unescape(name)}" if name else ""

    def day(post):
        return datetime.fromtimestamp(post["creation_date"], timezone.utc).date().isoformat()

    parts = [
        f"Question (score {question.get('score', 0)}, asked {day(question)}{who(question)}):\n\n"
        + html_to_text(question.get("body") or "")
    ]
    answers = sorted(
        question.get("answers") or [],
        key=lambda a: (not a.get("is_accepted"), -a.get("score", 0)),
    )
    for answer in answers:
        flags = f"score {answer.get('score', 0)}" + (", accepted" if answer.get("is_accepted") else "")
        parts.append(
            f"Answer{who(answer)} ({flags}, {day(answer)}):\n\n" + html_to_text(answer.get("body") or "")
        )
    return "\n\n".join(parts), day(question)


def run_stack_exchange(jobs, store, robots, progress):
    """Questions 100 at a time from the API; any it lacks from the Wayback Machine."""
    api = Site("api.stackexchange.com", DELAYS["se"])
    wayback = Site("web.archive.org", DELAYS["wayback"])
    by_host = defaultdict(list)
    for key, url in jobs:
        by_host[key.split(":")[1]].append((key, url))
    for host, items in sorted(by_host.items(), key=lambda kv: -len(kv[1])):
        api_site = host.removesuffix(".stackexchange.com") if host.endswith(".stackexchange.com") else host.split(".")[0]
        for i in range(0, len(items), 100):
            chunk = items[i: i + 100]
            ids = ";".join(key.split(":")[2] for key, _ in chunk)
            try:
                response = api.get(
                    f"https://api.stackexchange.com/2.3/questions/{ids}",
                    params={"site": api_site, "filter": SE_FILTER, "pagesize": 100},
                )
                data = response.json()
            except (httpx.HTTPError, ValueError) as e:
                log(f"se: {host} chunk {i}: {e!r}")
                continue
            if "error_id" in data:
                log(f"se: API error {data.get('error_id')} {data.get('error_message')}; stopping")
                return
            if data.get("backoff"):
                api.next_at = max(api.next_at, time.monotonic() + float(data["backoff"]))
            found = {str(q["question_id"]): q for q in data.get("items", [])}
            for key, url in chunk:
                question = found.get(key.split(":")[2])
                if question is not None:
                    text, asked = se_text(question)
                    owner = (question.get("owner") or {}).get("display_name")
                    record = {
                        "status": "ok", "method": "stackexchange_api",
                        "title": question.get("title"), "author": owner, "site": host,
                        "published": asked, "text": text,
                    }
                else:
                    original = link_cache.WAYBACK_RE.match(url)
                    original = original.group(1) if original else url
                    try:
                        record = fetch_web(
                            wayback, robots, key, f"https://web.archive.org/web/2026id_/{original}",
                            include_comments=True,
                        )
                        record["method"] = "wayback"
                        record["site"] = host
                    except httpx.HTTPError as e:
                        record = {"status": f"error {type(e).__name__}"}
                store.put(key, url, **record)
                progress.add("se", record["status"])
            log(f"se: {host} {min(i + 100, len(items))}/{len(items)} (quota left {data.get('quota_remaining')})")


FETCHERS = {
    "wikipedia": fetch_wikipedia,
    "gutenberg": fetch_gutenberg,
    "sep": fetch_sep,
    "arxiv": fetch_arxiv,
    "substack": fetch_substack,
    "web": fetch_web,
    # stable links
    "wayback": fetch_wayback,
    "wikipedia_revision": fetch_wikipedia_revision,
    "sep_edition": fetch_sep_edition,
}
# Kinds fetched many pages per request, each by its own loop.
RUNNERS = {
    "se": run_stack_exchange,
    "eaforum": functools.partial(run_forum, "eaforum"),
    "lesswrong": functools.partial(run_forum, "lesswrong"),
    "arxiv_version": run_arxiv_versions,
}


class Progress:
    def __init__(self, totals):
        self.totals = totals
        self.done = defaultdict(Counter)
        self.lock = threading.Lock()

    def add(self, group, status):
        with self.lock:
            self.done[group][status.split()[0]] += 1
            n = sum(self.done[group].values())
        if n % 200 == 0:
            log(f"{group}: {n}/{self.totals[group]} {dict(self.done[group])}")

    def summary(self):
        with self.lock:
            overall = Counter()
            for counts in self.done.values():
                overall.update(counts)
            n = sum(overall.values())
        return f"{n}/{sum(self.totals.values())} done {dict(overall)}"


def run_group(name, jobs, store, robots, progress):
    kind = name.split(":", 1)[0]
    try:
        if kind in RUNNERS:
            RUNNERS[kind](jobs, store, robots, progress)
            return
        site = Site(name, DELAYS[kind])
        for key, url in jobs:
            try:
                # a group can mix kinds of one site (sep and sep_edition, ...)
                record = FETCHERS[kind_of(key)](site, robots, key, url)
            except Exception as e:  # noqa: BLE001 -- one bad page shouldn't stop the site
                record = {"status": f"error {type(e).__name__}", "note": str(e)[:200]}
            store.put(key, url, **record)
            progress.add(name, record["status"])
    finally:
        log(f"{name}: finished {dict(progress.done[name])}")


# --- reports -------------------------------------------------------------------


def print_status(db, links):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = conn.execute("SELECT key, status, chars FROM pages").fetchall()
    by_key = {k: (s, c) for k, s, c in rows}
    table = defaultdict(Counter)
    chars = 0
    for key in links:
        status, n = by_key.get(key, ("not fetched", 0))
        table[kind_of(key)][status.split()[0]] += 1
        chars += n or 0
    print(f"{len(links)} linked pages; cache {db} ({db.stat().st_size / 1e6:.0f} MB, "
          f"{len(rows)} rows, {chars / 1e6:.0f} M characters of linked text)")
    statuses = sorted({s for c in table.values() for s in c})
    print("kind".ljust(11) + "".join(s.rjust(13) for s in statuses))
    for kind, counts in sorted(table.items(), key=lambda kv: -sum(kv[1].values())):
        print(kind.ljust(11) + "".join(str(counts.get(s, 0)).rjust(13) for s in statuses))


def print_failures(db, links):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    print("status\tnote\tchars\turl")
    for key, url, status, note, chars in conn.execute(
        "SELECT key, url, status, note, chars FROM pages "
        "WHERE status != 'ok' OR note LIKE '%thin%' ORDER BY status, key"
    ):
        if key in links:
            print(f"{status}\t{note or ''}\t{chars or 0}\t{url}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=link_cache.DEFAULT_PATH)
    parser.add_argument("--kinds", help="only these kinds, comma-separated: " + ", ".join([*FETCHERS, *RUNNERS]))
    parser.add_argument("--hosts", help="only these hosts (of web and substack links), comma-separated")
    parser.add_argument("--limit", type=int, help="at most this many pages per site (for a trial)")
    parser.add_argument("--first", type=Path, metavar="FILE",
                        help="fetch the links FILE lists first, in its order (a URL per line, or domain<TAB>URL)")
    parser.add_argument("--redo-thin", action="store_true", help="fetch pages with thin text again")
    parser.add_argument("--redo-skipped", action="store_true",
                        help="try the arXiv versions skipped before again (after a LaTeXML update, say)")
    parser.add_argument("--status", action="store_true", help="report what is cached and exit")
    parser.add_argument("--failures", action="store_true", help="list pages without usable text and exit")
    args = parser.parse_args()

    links = load_links()
    if args.status or args.failures:
        (print_status if args.status else print_failures)(args.db, links)
        return

    store = Store(args.db)
    done = store.statuses()
    redo = store.thin_keys() if args.redo_thin else set()
    finished = ("ok", "gone") + (() if args.redo_skipped else ("skipped",))
    todo = {k: u for k, u in links.items() if k in redo or not done.get(k, "").startswith(finished)}
    if args.kinds:
        kinds = set(args.kinds.split(","))
        todo = {k: u for k, u in todo.items() if kind_of(k) in kinds}
    if args.hosts:
        hosts = {h.removeprefix("www.") for h in args.hosts.split(",")}
        todo = {k: u for k, u in todo.items() if k.split("/", 1)[0] in hosts}
    first = {}
    if args.first:
        for line in args.first.read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                first.setdefault(link_cache.canonical(line.rpartition("\t")[2]), len(first))
    groups = defaultdict(list)
    for key, url in sorted(todo.items(), key=lambda kv: (first.get(kv[0], len(first)), kv[0])):
        groups[group_of(key)].append((key, url))
    if args.limit:
        groups = {g: jobs[: args.limit] for g, jobs in groups.items()}
    totals = {g: len(jobs) for g, jobs in groups.items()}
    log(f"{len(links)} linked pages, {sum(totals.values())} to fetch in {len(groups)} groups: "
        + ", ".join(f"{g} {n}" for g, n in sorted(totals.items(), key=lambda kv: -kv[1])[:12]))

    progress = Progress(totals)
    robots = Robots()

    def run_groups(names):
        for g in names:
            run_group(g, groups[g], store, robots, progress)

    # A group in AFTER runs after the group it names, in that group's thread.
    chains = {g: [g] for g in groups if not (g in AFTER and AFTER[g] in groups)}
    for g, before in AFTER.items():
        if g in groups and before in groups:
            chains[before].append(g)
    threads = [
        threading.Thread(target=run_groups, args=(names,), name=names[0], daemon=True)
        for names in chains.values()
    ]
    for t in threads:
        t.start()
    last = time.monotonic()
    while any(t.is_alive() for t in threads):
        time.sleep(5)
        if time.monotonic() - last > 600:
            log(progress.summary() + f"; {sum(t.is_alive() for t in threads)} sites still running")
            last = time.monotonic()
            with store.lock:
                store.commit()
    store.close()
    log("finished: " + progress.summary())


if __name__ == "__main__":
    main()
