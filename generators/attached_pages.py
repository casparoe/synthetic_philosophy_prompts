"""Web pages attached to a prompt: what a link prompt's answering model reads.

A link prompt (every prompt of a link batch, see generate_prompt_oai.py
--link-prompts) comes with one to three web pages that the asker shares. The
prompt text gives their URLs, and the model that answers sees each page's text
in the user message, ahead of the prompt (render_message). Nothing is fetched
at answer time and no tools are offered, so a response is still a single
completion. The generating model sees the pages in the meta-prompt in the same
form, so it writes the prompt against exactly the text the answering model
will read.

The pages are the domains' linked pages as the link cache holds them
(generators/link_cache.py). Because the cache can be re-crawled, the text a
prompt is written against is frozen when the prompt is sampled: the snapshot
store (link_cache/snapshots.sqlite, git-ignored and never uploaded, like the
cache) keeps every text ever attached, under the SHA-256 of its UTF-8 bytes,
and is only ever added to. The prompt's sidecar lists the pages under
attached_pages (the URL as shown, title, author, site, date, license, when and
how the text was fetched, its length, and the hash); the hash ties a prompt,
its responses, and the text together. The store is the only exact copy of
these texts, so it needs a backup.
"""

import hashlib
import random
import re
import sqlite3
import threading
import urllib.parse
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import link_cache

DEFAULT_SNAPSHOTS = link_cache.REPO_ROOT / "link_cache" / "snapshots.sqlite"

# How a page is shown to the models (render_page); batch.yaml and run.yaml
# record it, so that a later format can be told apart.
PAGE_FORMAT = "page-v1"
# Pages with less text make poor material; a prompt's pages together may have
# at most MAX_TOTAL_CHARS characters (about 15,000 tokens).
MIN_PAGE_CHARS = 1500
MAX_TOTAL_CHARS = 60000
# How many pages a link prompt comes with, and how often; several pages come
# from the same domain, so that they can be compared.
PAGES_PER_PROMPT = {1: 0.75, 2: 0.2, 3: 0.05}
# Instruction groups left out of link samples: quote_inclusion asks for a
# prompt built around a verbatim passage, which the attached page replaces.
LINK_SKIPPED_GROUPS = {"quote_inclusion"}

# Licenses under which the dataset (CC BY 4.0) may carry a reworking of a
# whole page: CC BY without NC, ND, or SA; CC0; public domain.
OPEN_LICENSE_RE = re.compile(r"^(?:CC BY \d|CC0\b|Public domain)", re.I)

# Mirrors whose text the cache holds for pages better known by another address.
MIRRORS = {
    "ea.greaterwrong.com": "forum.effectivealtruism.org",
    "greaterwrong.com": "www.lesswrong.com",
    "www.greaterwrong.com": "www.lesswrong.com",
}

HEADER_FIELDS = [
    ("Title", "title"),
    ("Author", "author"),
    ("Site", "site"),
    ("Published", "published"),
    ("License", "license"),
]


def text_sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def open_license(license):
    """Whether a page's license lets the dataset carry a reworking of the
    whole page (a translation, a rewrite): CC BY without NC, ND, or SA, CC0,
    or public domain."""
    return bool(license and OPEN_LICENSE_RE.match(license.strip()))


def display_url(url):
    """The URL a user would paste for a linked page: the original address
    rather than a Wayback copy of it, and the EA Forum's or LessWrong's own
    address rather than GreaterWrong's mirror (whose text the cache holds)."""
    m = link_cache.WAYBACK_RE.match(url)
    if m:
        url = m.group(1)
        if not re.match(r"^https?://", url, re.I):
            url = "https://" + url
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    if host in MIRRORS and link_cache.FORUM_POST_RE.match(parts.path):
        return urllib.parse.urlunsplit(("https", MIRRORS[host], parts.path, parts.query, ""))
    return url


class SnapshotStore:
    """The frozen texts of attached pages, under the SHA-256 of their UTF-8
    bytes. Texts are only ever added, so a hash always returns the text it
    was stored with. Safe to share between threads (one SQLite connection per
    thread); opened read-only unless writable."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS snapshots (
        sha256 TEXT PRIMARY KEY,  -- of the text's UTF-8 bytes
        chars INTEGER NOT NULL,
        text BLOB NOT NULL,       -- zlib-compressed UTF-8
        stored_at TEXT NOT NULL   -- when the text was first stored
    );
    """

    def __init__(self, path=DEFAULT_SNAPSHOTS, writable=False):
        self.path = Path(path)
        self.writable = writable
        if writable:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, timeout=60)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(self.SCHEMA)
            conn.close()
        elif not self.path.exists():
            raise FileNotFoundError(self.path)
        self._local = threading.local()

    def _connection(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            mode = "rw" if self.writable else "ro"
            conn = sqlite3.connect(f"file:{self.path}?mode={mode}", uri=True, timeout=60)
            self._local.conn = conn
        return conn

    def put(self, text):
        """Store text unless it is stored already; return its hash."""
        if not self.writable:
            raise PermissionError(f"{self.path} is open read-only")
        sha = text_sha256(text)
        conn = self._connection()
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO snapshots VALUES (?, ?, ?, ?)",
                (
                    sha,
                    len(text),
                    zlib.compress(text.encode("utf-8"), 9),
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
        return sha

    def get(self, sha):
        """The text stored under sha; KeyError if there is none. The text is
        checked against the hash, so a damaged store fails loudly."""
        row = self._connection().execute(
            "SELECT text FROM snapshots WHERE sha256 = ?", (sha,)
        ).fetchone()
        if row is None:
            raise KeyError(sha)
        text = zlib.decompress(row[0]).decode("utf-8")
        if text_sha256(text) != sha:
            raise ValueError(f"{self.path}: the text stored under {sha} does not match the hash")
        return text

    def missing(self, shas):
        """Those of the hashes that the store lacks."""
        conn = self._connection()
        return [
            sha
            for sha in shas
            if conn.execute("SELECT 1 FROM snapshots WHERE sha256 = ?", (sha,)).fetchone() is None
        ]


@dataclass
class Candidate:
    """A page that can be attached: a URL as listed under a domain, and the
    length of its cached text."""

    url: str
    chars: int


def eligible_pages(components, cache):
    """domain -> the domain's linked pages that can be attached: cached as
    text of MIN_PAGE_CHARS to MAX_TOTAL_CHARS characters, one Candidate per
    page (two URLs of one page count once), in file order. Domains without
    such pages are left out."""
    sizes = cache.sizes()
    eligible = {}
    for domain in components.domains:
        seen, pages = set(), []
        for url in components.domain_urls.get(domain, []):
            key = link_cache.canonical(url)
            chars = sizes.get(key)
            if key in seen or chars is None or not MIN_PAGE_CHARS <= chars <= MAX_TOTAL_CHARS:
                continue
            seen.add(key)
            pages.append(Candidate(url, chars))
        if pages:
            eligible[domain] = pages
    return eligible


def draw_pages(domains, eligible, rng=random):
    """Pick a link prompt's pages: one of the given domains that has eligible
    pages, a number of pages from PAGES_PER_PROMPT, then that many of the
    domain's eligible pages at random, skipping any that would take the total
    past MAX_TOTAL_CHARS (so a domain with few or long pages can yield fewer).
    Returns (domain, candidates), or None if no domain has eligible pages."""
    usable = [d for d in domains if eligible.get(d)]
    if not usable:
        return None
    domain = rng.choice(usable)
    wanted = rng.choices(list(PAGES_PER_PROMPT), weights=list(PAGES_PER_PROMPT.values()))[0]
    chosen, total = [], 0
    for candidate in rng.sample(eligible[domain], len(eligible[domain])):
        if len(chosen) == wanted:
            break
        if total + candidate.chars <= MAX_TOTAL_CHARS:
            chosen.append(candidate)
            total += candidate.chars
    return domain, chosen


def page_record(url, page, text, sha):
    """What a prompt's sidecar records about one attached page: the URL as
    shown (display_url) and as listed under the domain, the header fields,
    when and how the cache fetched the text, its length, and its hash."""
    return {
        "url": display_url(url),
        "listed_url": url,
        "title": page.title,
        "author": page.author,
        "site": page.site,
        "published": page.published,
        "license": page.license,
        "fetched_at": page.fetched_at,
        "fetch_method": page.method,
        "chars": len(text),
        "sha256": sha,
    }


def attach(sample, eligible, cache, store, rng=random):
    """Make a sample into a link sample: draw its pages (draw_pages), freeze
    their texts into the store, and narrow the sample to them. domains_offered
    becomes the pages' domain alone, without inspiration links, the groups in
    LINK_SKIPPED_GROUPS are dropped, and attached_pages lists the pages.
    Returns the new sample and the pages' texts, or None if no offered domain
    has a usable page (draw another sample then)."""
    drawn = draw_pages(sample["domains_offered"], eligible, rng)
    if drawn is None:
        return None
    domain, candidates = drawn
    records, texts = [], []
    for candidate in candidates:
        page = cache.get(candidate.url)
        text = page.text.strip() if page is not None and page.ok else ""
        if not text or "</page>" in text:
            return None  # can't be shown as a page; rare enough to redraw
        records.append(page_record(candidate.url, page, text, store.put(text)))
        texts.append(text)
    linked = dict(sample)
    linked["domains_offered"] = [domain]
    linked["domain_urls"] = [[]]
    linked["additional_instructions"] = {
        name: text
        for name, text in sample["additional_instructions"].items()
        if name not in LINK_SKIPPED_GROUPS
    }
    linked["attached_pages"] = records
    return linked, texts


def render_page(record, text):
    """One page the way the models see it (PAGE_FORMAT page-v1): a <page>
    element carrying the URL, then the title, author, site, date, and
    license where known, a blank line, and the text."""
    url = record["url"].replace('"', "%22")
    lines = [f"{name}: {record[key]}" for name, key in HEADER_FIELDS if record.get(key)]
    head = "\n".join(lines) + "\n\n" if lines else ""
    return f'<page url="{url}">\n{head}{text}\n</page>'


def render_blocks(records, store):
    """The rendered pages of a sample's attached_pages, from the store."""
    return [render_page(r, store.get(r["sha256"])) for r in records]


def render_message(records, texts, prompt_text):
    """The user message of a link prompt: its pages, then the prompt."""
    return "\n\n".join([*(render_page(r, t) for r, t in zip(records, texts)), prompt_text])


URL_RE = re.compile(r"https?://[^\s<>\"'`]+")
TRAILING_PUNCTUATION = ".,;:!?*”’»"


def _strip_one(url):
    """The URL without its last character if that is punctuation around or
    after a URL in prose or Markdown (a final period, a closing parenthesis
    that the URL did not open), else None."""
    if url and url[-1] in TRAILING_PUNCTUATION:
        return url[:-1]
    if url.endswith(")") and url.count(")") > url.count("("):
        return url[:-1]
    if url.endswith("]") and url.count("]") > url.count("["):
        return url[:-1]
    return None


def urls_in(text):
    """The http(s) URLs in a text, without the punctuation that ends a
    sentence or closes a parenthesis, bracket, or quotation around a URL; a
    closing parenthesis that the URL opened itself (as in Wikipedia titles)
    is kept."""
    urls = []
    for m in URL_RE.finditer(text):
        url = m.group(0)
        while (shorter := _strip_one(url)) is not None:
            url = shorter
        urls.append(url)
    return urls


def url_problem(prompt_text, records):
    """Why a link prompt's URLs don't fit its pages, or None. The prompt must
    give the URL of every page it comes with (any form of it that
    link_cache.canonical maps to the same page) and no other URL, since the
    answering model can open nothing else. A URL counts as a page's if it
    matches with or without the punctuation after it, since a title can end
    in some (Wikipedia's Scared_Straight!)."""
    pages = {link_cache.canonical(r["url"]) for r in records}
    found, others = set(), []
    for m in URL_RE.finditer(prompt_text):
        url, keys = m.group(0), []
        while url is not None:
            keys.append(link_cache.canonical(url))
            shortest, url = url, _strip_one(url)
        matched = [key for key in keys if key in pages]
        if matched:
            found.add(matched[0])
        else:
            others.append(shortest)
    missing = [r["url"] for r in records if link_cache.canonical(r["url"]) not in found]
    if missing:
        return f"the prompt lacks the URL of an attached page ({missing[0]})"
    if others:
        return f"the prompt has a URL of a page that is not attached ({others[0]})"
    return None
