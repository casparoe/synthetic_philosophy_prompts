"""Local copies of the pages that the domain links point to.

tools/build_link_cache.py fetches every URL in meta_prompt/domains/ once,
politely, and stores each page's text in link_cache/pages.sqlite; the
web_fetch tool of generate_prompt_oai.py serves those links from there
instead of the live web, so no site's rate limit caps how often links can be
shown, and long pages can be read past their first screen (offset, find).
The cache is git-ignored and never uploaded: most of the pages are under
copyright.

Pages are keyed by canonical(url), so the same page reached by another form
of its URL (http or https, with or without www, a Wayback copy of it, an
arXiv abs/pdf/html link, a forum.effectivealtruism.org link for an
ea.greaterwrong.com one) is found too.

Stable links are the exception (stable_link): links to a version of a page
that cannot change, such as a Wayback Machine capture with its full
timestamp, a Wikipedia revision, a Stanford Encyclopedia archive edition, a
revision of a LessWrong post, or a versioned arXiv paper. Each is a page of
its own: keyed by the link itself, fetched from it
(tools/build_link_cache.py), and never mapped to the live page it is a
version of, nor the live page to it. Only stable links can be attached to
link prompts (generators/attached_pages.py).
"""

import re
import sqlite3
import threading
import urllib.parse
import zlib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = REPO_ROOT / "link_cache" / "pages.sqlite"

# Characters of page text per web_fetch result, as before the cache.
PAGE_CHARS = 6000
# With find: matches shown per call, and context kept before each match.
FIND_MATCHES = 3
FIND_BEFORE = 400

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    key TEXT PRIMARY KEY,   -- canonical(url)
    url TEXT NOT NULL,      -- the URL as linked in the domain files
    status TEXT NOT NULL,   -- ok, or why there is no text (gone 404, error ...)
    method TEXT,            -- how it was fetched (wikipedia_api, greaterwrong, ...)
    title TEXT,
    author TEXT,
    site TEXT,
    published TEXT,
    license TEXT,           -- only where the source states it
    chars INTEGER,
    text BLOB,              -- zlib-compressed UTF-8
    fetched_at TEXT NOT NULL,
    note TEXT
);
"""

# Statuses of pages that are known not to exist any more: web_fetch reports
# them without trying the live site. Any other non-ok status (a timeout, a
# rate limit while building the cache) falls back to a live fetch.
GONE_PREFIX = "gone"

WAYBACK_RE = re.compile(r"^https?://web\.archive\.org/web/\d*(?:[a-z]{2}_)?/(.+)$", re.I)
# Post IDs have 17 characters, or 24 hex digits for posts imported from older
# sites (the Agent Foundations forum).
FORUM_POST_RE = re.compile(r"^/(?:posts|s/[^/]+/p)/([A-Za-z0-9]{17}|[0-9a-f]{24})(?:/|$)")
EA_FORUM_HOSTS = {"forum.effectivealtruism.org", "ea.greaterwrong.com"}
LESSWRONG_HOSTS = {"lesswrong.com", "greaterwrong.com", "alignmentforum.org"}
ARXIV_RE = re.compile(r"^/(?:abs|pdf|html)/(.+?)(?:v\d+)?(?:\.pdf)?/?$")
STACK_EXCHANGE_HOSTS = {
    "stackoverflow.com", "mathoverflow.net", "superuser.com", "serverfault.com",
    "askubuntu.com", "stackapps.com",
}
SE_QUESTION_RE = re.compile(r"^/(?:questions|q)/(\d+)(?:/|$)")
GUTENBERG_RE = re.compile(r"^/(?:ebooks|cache/epub|files)/(\d+)(?:[/.]|$)")
SEP_RE = re.compile(r"^/(?:archives/[a-z]+\d{4}/)?entries/([^/]+)/?(?:index\.html)?$")


# Stable links, by kind: the URL patterns, and how a match becomes the link's
# cache key. Extend the list to admit more kinds of stable links; the cache
# builder needs a fetcher for each kind.
STABLE_LINKS = [
    # a Wayback Machine capture, pinned to its 14-digit timestamp
    ("wayback", re.compile(r"^https://web\.archive\.org/web/(\d{14})/(https?://\S+)$"),
     lambda m: f"{m.group(1)}/{m.group(2)}"),
    # a Wikipedia revision (the "Permanent link" of a page)
    ("wikipedia_revision",
     re.compile(r"^https://([a-z][a-z-]*)\.wikipedia\.org/w/index\.php\?(?:[^#\s]*&)?oldid=(\d+)(?:&[^#\s]*)?$"),
     lambda m: f"{m.group(1)}:{m.group(2)}"),
    ("wikipedia_revision", re.compile(r"^https://([a-z][a-z-]*)\.wikipedia\.org/wiki/Special:PermanentLink/(\d+)$"),
     lambda m: f"{m.group(1)}:{m.group(2)}"),
    # an entry in a quarterly archive edition of the Stanford Encyclopedia of Philosophy
    ("sep_edition",
     re.compile(r"^https://plato\.stanford\.edu/archives/((?:spr|sum|fall|win)\d{4})/entries/([^/\s#?]+)/?$"),
     lambda m: f"{m.group(1)}:{m.group(2)}"),
    # a revision of a LessWrong post: LessWrong keeps every revision of a post,
    # and its page shows the one a ?revision= link names (the slug is free)
    ("lesswrong_revision",
     re.compile(r"^https://www\.lesswrong\.com/posts/([A-Za-z0-9]{17}|[0-9a-f]{24})/[^/?#\s]+\?revision=(\d+\.\d+\.\d+)$"),
     lambda m: f"{m.group(1)}:{m.group(2)}"),
    # one version of an arXiv paper, by its abstract link: that version's
    # source (kept by arXiv as submitted) as LaTeXML renders it, or its PDF
    # (tools/build_link_cache.py)
    ("arxiv_version",
     re.compile(r"^https://arxiv\.org/abs/((?:[a-z-]+(?:\.[A-Z]{2})?/)?\d+(?:\.\d+)?v\d+)$"),
     lambda m: m.group(1)),
]


def stable_link(url):
    """The kind of a stable link and its cache key, or None if the URL is not
    one of the STABLE_LINKS patterns."""
    url = url.strip()
    for kind, pattern, key in STABLE_LINKS:
        if m := pattern.match(url):
            return kind, f"{kind}:{key(m)}"
    return None


def canonical(url):
    """The cache key of a URL: one string per page, whatever form of the URL
    is used. Scheme, www., fragments and utm_ parameters don't count. A
    stable link is keyed by the link itself (stable_link)."""
    url = url.strip()
    if stable := stable_link(url):
        return stable[1]
    m = WAYBACK_RE.match(url)
    if m:
        url = m.group(1)
    if not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I):
        url = "https://" + url
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    host = re.sub(r"^([a-z-]+)\.m\.wikipedia\.org$", r"\1.wikipedia.org", host)
    path = urllib.parse.unquote(parts.path) or "/"

    if host in EA_FORUM_HOSTS and (m := FORUM_POST_RE.match(path)):
        return f"eaforum:{m.group(1)}"
    if host in LESSWRONG_HOSTS and (m := FORUM_POST_RE.match(path)):
        return f"lesswrong:{m.group(1)}"
    if host in ("arxiv.org", "export.arxiv.org") and (m := ARXIV_RE.match(path)):
        return f"arxiv:{m.group(1)}"
    if (host.endswith(".stackexchange.com") or host in STACK_EXCHANGE_HOSTS) and (
        m := SE_QUESTION_RE.match(path)
    ):
        return f"se:{host}:{m.group(1)}"
    if host in ("gutenberg.org", "gutenberg.pglaf.org") and (m := GUTENBERG_RE.match(path)):
        return f"gutenberg:{m.group(1)}"
    if host.endswith(".wikipedia.org") and path.startswith("/wiki/"):
        title = path[len("/wiki/"):].replace(" ", "_")
        return f"wikipedia:{host.split('.')[0]}:{title[:1].upper()}{title[1:]}"
    if host == "plato.stanford.edu" and (m := SEP_RE.match(path)):
        return f"sep:{m.group(1)}"

    path = re.sub(r"/index\.html?$", "/", path)
    if len(path) > 1:
        path = path.rstrip("/")
    query = urllib.parse.urlencode(
        [
            (k, v)
            for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
            if not k.lower().startswith("utm_")
        ]
    )
    return host + path + ("?" + query if query else "")


@dataclass
class Page:
    url: str
    status: str
    title: str | None
    author: str | None
    site: str | None
    published: str | None
    license: str | None
    text: str | None
    method: str | None = None  # how the text was fetched
    fetched_at: str | None = None

    @property
    def ok(self):
        return self.status == "ok" and self.text is not None

    @property
    def gone(self):
        return self.status.startswith(GONE_PREFIX)

    def header(self):
        fields = [
            ("Title", self.title),
            ("Author", self.author),
            ("Site", self.site),
            ("Published", self.published),
            ("License", self.license),
            ("URL", self.url),
        ]
        return [f"{name}: {value}" for name, value in fields if value]


class LinkCache:
    """Read-only access to the cache, safe to share between threads (each
    thread gets its own SQLite connection)."""

    def __init__(self, path=DEFAULT_PATH):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        self._local = threading.local()

    def _connection(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
            self._local.conn = conn
        return conn

    def get(self, url):
        """The cached Page for url, or None if the cache doesn't have it."""
        row = self._connection().execute(
            "SELECT url, status, title, author, site, published, license, text, "
            "method, fetched_at FROM pages WHERE key = ?",
            (canonical(url),),
        ).fetchone()
        if row is None:
            return None
        url, status, title, author, site, published, license_, blob, method, fetched_at = row
        text = zlib.decompress(blob).decode("utf-8") if blob is not None else None
        return Page(url, status, title, author, site, published, license_, text, method, fetched_at)

    def sizes(self):
        """Characters of text per page key, for the pages the cache has as text."""
        return dict(
            self._connection().execute(
                "SELECT key, chars FROM pages WHERE status = 'ok' AND text IS NOT NULL"
            ).fetchall()
        )

    def stats(self):
        """Pages per status."""
        return dict(
            self._connection().execute(
                "SELECT status, COUNT(*) FROM pages GROUP BY status ORDER BY 2 DESC"
            ).fetchall()
        )


def _cut(text, start, end):
    """End a slice at a line or word break near end, so words aren't split."""
    if end >= len(text):
        return len(text)
    for sep in ("\n", " "):
        cut = text.rfind(sep, start + (end - start) // 2, end)
        if cut > start:
            return cut + 1
    return end


def render(text, header, offset=0, find=None, limit=PAGE_CHARS):
    """What web_fetch returns: the header lines, then limit characters of the
    page from offset, or the passages around the first matches of find, with
    a note on how to read further when there is more."""
    head = "\n".join(header)
    head = head + "\n\n" if head else ""
    total = len(text)
    if find and find.strip():
        words = find.split()
        pattern = re.compile(r"\s+".join(re.escape(w) for w in words), re.IGNORECASE)
        matches = list(pattern.finditer(text))
        if not matches:
            return (
                f"{head}[No match for {find!r} in this page ({total} characters). "
                "Try a shorter phrase, or read the page with offset.]"
            )
        shown = []
        budget = limit
        last_end = -1
        for m in matches:
            if len(shown) == FIND_MATCHES or budget <= 0:
                break
            if m.start() < last_end:
                continue  # already inside the previous passage
            start = max(0, m.start() - FIND_BEFORE, last_end)
            nl = text.rfind("\n", start, m.start())
            if nl >= 0 and m.start() - nl < FIND_BEFORE:
                start = nl + 1
            end = _cut(text, start, min(total, start + min(budget, limit // FIND_MATCHES)))
            end = max(end, min(total, m.end()))
            shown.append((start, end))
            budget -= end - start
            last_end = end
        parts = [
            f"[{len(matches)} match{'es' if len(matches) != 1 else ''} for {find!r}; "
            f"showing {len(shown)}. The page has {total} characters.]"
        ]
        for start, end in shown:
            parts.append(
                f"[From character {start}:]\n{text[start:end].strip()}\n"
                f"[... to read on from here, call web_fetch with offset={end}]"
            )
        return head + "\n\n".join(parts)

    try:
        offset = max(0, int(float(offset or 0)))  # models sometimes send "6000" or 6000.0
    except (TypeError, ValueError):
        offset = 0
    if offset and offset >= total:
        return f"{head}[Offset {offset} is past the end of this page ({total} characters).]"
    end = _cut(text, offset, offset + limit)
    body = text[offset:end].strip()
    if offset == 0 and end >= total:
        return head + body
    note = f"[Characters {offset}-{end} of {total}."
    if end < total:
        note += (
            f" To read on, call web_fetch again with offset={end}; to jump to a "
            "passage, pass find with a word or phrase from it."
        )
    return f"{head}{body}\n{note}]"
