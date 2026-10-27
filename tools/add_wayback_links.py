#!/usr/bin/env python
"""Add Wayback Machine captures of the domains' links to some sites, as stable links.

A link prompt can attach only stable links (generators/link_cache.py,
STABLE_LINKS), and a Wayback Machine capture pinned to its timestamp
(https://web.archive.org/web/<14 digits>/<url>) is one. For each page on the
given sites that a domain links to (under urls): posts (/p/<slug> paths, as
on Substack), or with --any-path every page but a site's home page (PDFs
aside), and with the site "stackexchange" the questions of every Stack
Exchange site (a link to a Wayback copy that names no capture stands for the
page it copies), this looks up the captures of that same URL in the Wayback
Machine's index and fetches the newest that was archived as an HTML page with
status 200, in its raw id_ form, as tools/build_link_cache.py fetches a
Wayback link. The capture is kept if its text matches the page as cached from
the live site or its API (link_cache/pages.sqlite): at least MIN_COVERAGE of
the live text's word 8-grams must be in it, and it must not be more than
MAX_RATIO times as long. One that fails gives way to the next newest, up to
--tries captures per page. Pages whose live text is far outside the length a
page must have to be attached (generators/attached_pages.py) are passed over.
A kept capture's link goes into the domain's stable_urls, as
tools/add_stable_links.py puts links there; its text is in the link cache
already, under the capture's own key, so the link needs no further fetching.
Every capture fetched is cached, kept or not, and a rerun fetches none again.
Live links stay under urls; nothing maps between them and the captures.

The Wayback Machine limits scripts (HTTP 429, and an hour's block of the IP
for one that keeps going), so this goes slowly: the index (the CDX server) is
read a page of about 5,000 captures at a time, one page a minute, and
the pages are kept in link_cache/wayback_index/, so a rerun reads none again
(the URLs of a page it will not give are looked up one by one instead); with
--exact, and always for Stack Exchange, each page's captures are looked up by
themselves, one page every 20 seconds, which suits a few hundred pages of a
large site; captures are fetched one every 20 seconds. After a 429 it waits
ten minutes, after a server error three; after a failed connection two
minutes, and an hour if the next one fails too. A run over a few thousand
pages takes a day or more, so start it detached. Each run writes its report
(report_<time>.tsv) and the links it added (additions_<time>.tsv) next to the
index pages.

    tools/add_wayback_links.py --site benthams.substack.com --site www.overcomingbias.com [--dry-run] [--limit N]
    tools/add_wayback_links.py --site gwern.net --site slatestarcodex.com --any-path --exact
    tools/add_wayback_links.py --site stackexchange --tries 2
"""
import argparse
import re
import sqlite3
import sys
import time
import urllib.parse
import zlib
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import httpx
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "generators"))
sys.path.insert(0, str(REPO / "tools"))
import link_cache  # noqa: E402
from attached_pages import MAX_PAGE_CHARS, MIN_PAGE_CHARS  # noqa: E402
import build_link_cache as blc  # noqa: E402
from add_stable_links import DOMAINS_DIR, insert_stable_urls  # noqa: E402

CDX = "https://web.archive.org/cdx/search/cdx"
FIELDS = "urlkey,timestamp,original,statuscode,mimetype,digest,length"
INDEX_PACE = 60.0  # seconds between two requests for index pages
LOOKUP_PACE = 20.0  # seconds between two index lookups of a single URL
CAPTURE_PACE = 20.0  # seconds between two capture fetches
LIMITED_WAIT = 600.0  # after a 429
SERVER_ERROR_WAIT = 180.0  # after a server error (the index server often answers 503 under load)
RETRY_WAIT = 120.0  # after a failed connection
BLOCKED_WAIT = 3600.0  # after a second one in a row: the archive's block lasts an hour
SHINGLE = 8  # words per shingle in the text comparison
MIN_COVERAGE = 0.9  # share of the live text's shingles the capture must have
MAX_RATIO = 2.0  # the capture's length (in words) at most this times the live text's (embedded tweets add text)
POST_RE = re.compile(r"^/p/[^/?#]+$")
# A question's page on a Stack Exchange site (the site "stackexchange" stands for all of them).
QUESTION_RE = re.compile(r"^/questions/\d+(?:/[^/?#]*)?$")


class Wayback:
    """Requests to web.archive.org, one at a time and slowly. It stands in for
    build_link_cache's Site (get and slow_down), with longer waits."""

    def __init__(self, pace):
        self.pace = pace
        self.next_at = 0.0
        self.failures = 0  # failed connections in a row
        self.client = httpx.Client(
            headers={"User-Agent": blc.UA}, timeout=httpx.Timeout(180.0, connect=30.0), follow_redirects=True,
        )

    def slow_down(self, delay):
        self.pace = max(self.pace, min(delay, 120.0))

    def get(self, url, tries=4, **kwargs):
        for attempt in range(tries):
            time.sleep(max(0.0, self.next_at - time.monotonic()))
            try:
                response = self.client.get(url, **kwargs)
            except httpx.HTTPError as e:
                # one failed connection is usually a glitch; two in a row look like the archive's block
                self.failures += 1
                wait = RETRY_WAIT if self.failures == 1 else BLOCKED_WAIT
                blc.log(f"web.archive.org: {type(e).__name__} ({str(e)[:100]}); waiting {wait / 60:.0f} min")
                self.next_at = time.monotonic() + wait
                if attempt == tries - 1:
                    raise
                continue
            self.failures = 0
            self.next_at = time.monotonic() + self.pace
            if response.status_code == 429 or response.status_code >= 500:
                wait = LIMITED_WAIT if response.status_code == 429 else SERVER_ERROR_WAIT
                blc.log(f"web.archive.org: HTTP {response.status_code}; waiting {wait / 60:.0f} min")
                self.next_at = time.monotonic() + wait
                if attempt < tries - 1:
                    continue
            return response


def index_folder(directory, prefix):
    folder = directory / re.sub(r"[^A-Za-z0-9.-]+", "_", prefix).strip("_")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def index_lines(wayback, directory, prefix):
    """Every index line (FIELDS) for URLs starting with prefix (host and path,
    no scheme), a page at a time, each page kept in directory; and the urlkey
    ranges (first, last; inclusive) of the pages the index would not give
    (it answers some heavy pages with 503 again and again), whose URLs are
    then looked up one by one (exact_lines)."""
    folder = index_folder(directory, prefix)
    count = folder / "pages.txt"
    if not count.exists():
        response = wayback.get(CDX, params={"url": prefix, "matchType": "prefix", "showNumPages": "true"})
        if response.status_code != 200:
            raise SystemExit(f"Wayback index: HTTP {response.status_code} for {prefix}")
        count.write_text(response.text.strip() + "\n")
    pages = int(count.read_text())
    lines, gaps = [], []
    gap_from = None  # the last urlkey before a run of pages not read
    failed = 0  # pages in a row the index would not give; after two, no more are asked for
    for page in range(pages):
        path = folder / f"page_{page:04d}.txt"
        if not path.exists():
            response = None
            if failed < 2:
                try:
                    response = wayback.get(
                        CDX, params={"url": prefix, "matchType": "prefix", "page": page, "fl": FIELDS}, tries=2)
                except httpx.HTTPError:
                    response = None
            if response is None or response.status_code != 200:
                failed += 1
                if response is not None:
                    blc.log(f"Wayback index: HTTP {response.status_code} for {prefix} page {page + 1}/{pages}; "
                            "its URLs will be looked up one by one")
                if gap_from is None:
                    gap_from = lines[-1].split(" ")[0] if lines else ""
                continue
            failed = 0
            path.write_text(response.text)
            blc.log(f"Wayback index: {prefix} page {page + 1}/{pages}")
        page_lines = path.read_text().splitlines()
        if gap_from is not None:
            gaps.append((gap_from, page_lines[0].split(" ")[0] if page_lines else "\uffff"))
            gap_from = None
        lines += page_lines
    if gap_from is not None:
        gaps.append((gap_from, "\uffff"))
    return lines, gaps


def exact_lines(wayback, directory, prefix, url):
    """The index lines of one URL (any scheme, with or without www.), kept
    in directory; None if the index would not answer."""
    folder = index_folder(directory, prefix) / "exact"
    folder.mkdir(exist_ok=True)
    path = folder / (re.sub(r"[^A-Za-z0-9.-]+", "_", urlkey(url)) + ".txt")
    if not path.exists():
        try:
            response = wayback.get(CDX, params={"url": url.split("://", 1)[-1], "fl": FIELDS}, tries=2)
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        path.write_text(response.text)
    return path.read_text().splitlines()


def urlkey(url):
    """The index's key for a URL (SURT form, as the CDX server writes it),
    without a trailing slash."""
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    return trimmed(",".join(reversed(host.split("."))) + ")" + parts.path.lower())


def trimmed(key):
    """An index key without its path's trailing slash (a page is captured with and without one)."""
    return key[:-1] if key.endswith("/") and not key.endswith(")/") else key


def captures_by_key(lines):
    """urlkey -> [(timestamp, original)] of the captures archived as HTML pages with status 200, newest first."""
    found = defaultdict(set)
    for line in lines:
        fields = line.split(" ")
        if len(fields) == 7 and fields[3] == "200" and fields[4] == "text/html":
            found[trimmed(fields[0])].add((fields[1], fields[2]))
    return {key: sorted(caps, reverse=True) for key, caps in found.items()}


def stack_exchange(host):
    return host.endswith(".stackexchange.com") or host in link_cache.STACK_EXCHANGE_HOSTS


def linked_page(url, sites, any_path):
    """For a domain's link: (site, URL of the page to look for) if it links one
    of the sites; the URL is None if the link is not to a page this looks for.
    Pages are posts (/p/<slug>, as on Substack), with any_path any page but a
    site's home page (PDFs aside), and on Stack Exchange questions. A link to
    a Wayback copy that is not pinned to a capture stands for the page it
    copies. None for other links, and for stable links, which need no
    capture."""
    if link_cache.stable_link(url):
        return None
    wayback = link_cache.WAYBACK_RE.match(url)
    page = wayback.group(1) if wayback else url
    parts = urllib.parse.urlsplit(page)
    host = (parts.hostname or "").lower().removeprefix("www.")
    if "stackexchange" in sites and stack_exchange(host):
        ok = QUESTION_RE.match(parts.path) and not parts.query and not parts.fragment
        return "stackexchange", page if ok else None
    site = next((s for s in sites if host == s.removeprefix("www.")), None)
    if site is None:
        return None
    ok = not parts.query and not parts.fragment and (
        POST_RE.match(parts.path)
        or (any_path and parts.path not in ("", "/") and not parts.path.lower().endswith(".pdf")))
    return site, page if ok else None


def shingles(text):
    words = re.findall(r"\w+", text.lower())
    return {tuple(words[i: i + SHINGLE]) for i in range(max(1, len(words) - SHINGLE + 1))}, len(words)


def compare(live, capture):
    """(share of the live text's shingles in the capture, capture length / live length, in words)."""
    a, a_words = shingles(live)
    b, b_words = shingles(capture)
    return len(a & b) / max(1, len(a)), b_words / max(1, a_words)


def archived(link):
    """The cache key of the page a pinned capture link archives (None for other links)."""
    stable = link_cache.stable_link(link)
    if stable and stable[0] == "wayback":
        return link_cache.canonical(stable[1].split(":", 1)[1].split("/", 1)[1])
    return None


def cached_text(conn, key):
    row = conn.execute("SELECT status, text, note FROM pages WHERE key = ?", (key,)).fetchone()
    if not row or row[0] != "ok" or row[1] is None:
        return None, None
    return zlib.decompress(row[1]).decode("utf-8"), row[2] or ""


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", action="append", required=True,
                        help="host of the pages (repeatable; stackexchange: the questions of every Stack Exchange site)")
    parser.add_argument("--any-path", action="store_true",
                        help="any page of the sites but their home pages and PDFs, not only /p/<slug> posts")
    parser.add_argument("--exact", action="store_true",
                        help="look up each page's captures by itself rather than reading the site's index "
                             "(always so for stackexchange)")
    parser.add_argument("--db", type=Path, default=link_cache.DEFAULT_PATH)
    parser.add_argument("--index-dir", type=Path, help="where the index pages are kept (default: next to the db)")
    parser.add_argument("--tries", type=int, default=3, help="captures tried per page, newest first")
    parser.add_argument("--limit", type=int, help="at most this many pages per site (for a trial)")
    parser.add_argument("--dry-run", action="store_true", help="fetch and compare, but change no domain file")
    args = parser.parse_args()
    sites = [s.lower() for s in args.site]
    index_dir = args.index_dir or args.db.parent / "wayback_index"

    # the pages the domains link to
    files = sorted(DOMAINS_DIR.glob("*.yaml"))
    entries = {path: yaml.safe_load(path.read_text()) or [] for path in files}
    posts = defaultdict(dict)  # site -> {link as the domains have it: URL of the page}, in file order
    other = Counter()
    for items in entries.values():
        for entry in items:
            for url in entry.get("urls") or []:
                found = linked_page(url, sites, args.any_path)
                if found is None:
                    continue
                site, page = found
                if page is None:
                    other[site] += 1
                else:
                    posts[site].setdefault(url, page)
    for site in sites:
        blc.log(f"{site}: {len(posts[site])} pages linked" + (f" (and {other[site]} other links, left alone)" if other[site] else ""))

    store = blc.Store(args.db)
    robots = blc.Robots()
    index = Wayback(INDEX_PACE)
    lookups = Wayback(LOOKUP_PACE)
    fetcher = Wayback(CAPTURE_PACE)
    conn = sqlite3.connect(args.db, timeout=600)
    statuses = store.statuses()
    index_dir.mkdir(parents=True, exist_ok=True)
    run = datetime.now().strftime("%Y%m%d-%H%M")
    report = open(index_dir / f"report_{run}.tsv", "w")  # link, capture link, coverage, ratio, verdict
    kept = {}  # link as the domains have it -> capture link
    for site in sites:
        if args.exact or site == "stackexchange":
            prefix, captures, gaps = site, {}, [("", "￿")]  # every page looked up by itself
        else:
            prefix = site.removeprefix("www.") + ("/" if args.any_path else "/p/")
            lines, gaps = index_lines(index, index_dir, prefix)
            captures = captures_by_key(lines)
        todo = list(posts[site].items())
        todo = todo[: args.limit] if args.limit else todo
        tally = Counter()
        for n, (url, page) in enumerate(todo, 1):
            live, note = cached_text(conn, link_cache.canonical(url))
            if live is None or "paywalled" in note:
                tally["no live text" if live is None else "paywalled"] += 1
                continue
            if not 0.9 * MIN_PAGE_CHARS <= len(live) <= 1.1 * MAX_PAGE_CHARS:
                tally["too short or too long to attach"] += 1  # a capture of it could not be attached either
                continue
            if any(first <= urlkey(page) <= last for first, last in gaps):
                found = exact_lines(lookups, index_dir, prefix, page)
                if found is None:
                    tally["index lookup failed"] += 1  # a rerun tries again
                    continue
                captures.update(captures_by_key(found))
            options = captures.get(urlkey(page), [])
            verdict = "no capture" if not options else "no match"
            for stamp, original in options[: args.tries]:
                link = f"https://web.archive.org/web/{stamp}/{original}"
                kind, key = link_cache.stable_link(link) or (None, None)
                if kind != "wayback":
                    continue
                status = statuses.get(key)
                if status != "ok" and not (status or "").startswith("gone"):
                    try:
                        record = blc.fetch_wayback(fetcher, robots, key, link)
                    except Exception as e:  # noqa: BLE001 -- one bad capture shouldn't stop the run
                        record = {"status": f"error {type(e).__name__}", "note": str(e)[:200]}
                    store.put(key, link, **record)  # errors too, as build_link_cache does; they are retried
                    store.commit()
                    statuses[key] = status = record["status"]
                if status != "ok":
                    report.write(f"{url}\t{link}\t\t\t{status}\n")
                    verdict = "capture failed" if verdict == "no match" else verdict
                    continue
                capture, _ = cached_text(conn, key)
                coverage, ratio = compare(live, capture or "")
                ok = coverage >= MIN_COVERAGE and ratio <= MAX_RATIO
                report.write(f"{url}\t{link}\t{coverage:.3f}\t{ratio:.2f}\t{'kept' if ok else 'rejected'}\n")
                if ok:
                    kept[url] = link
                    verdict = "kept"
                    break
                verdict = "no match"
            if not options:
                report.write(f"{url}\t\t\t\tno capture\n")
            tally[verdict] += 1
            report.flush()
            if n % 50 == 0:
                blc.log(f"{site}: {n}/{len(todo)} pages, {dict(tally)}")
        blc.log(f"{site}: done, {dict(tally)}")
    store.close()

    # the domain files as they are now (they may have changed during the run):
    # each kept capture next to its live link, unless the domain lists a
    # capture of that post already
    added = changed = 0
    listed = []  # "domain<TAB>capture link", as tools/add_stable_links.py --links reads them
    for path in files:
        text = path.read_text()
        items = yaml.safe_load(text) or []
        additions = {}
        for entry in items:
            have = {archived(u) for u in entry.get("stable_urls") or []}
            new = []
            for url in entry.get("urls") or []:
                if url in kept and link_cache.canonical(url) not in have:
                    new.append(kept[url])
                    have.add(link_cache.canonical(url))
            if new:
                additions[entry["domain"]] = new
                listed += [f"{entry['domain']}\t{link}" for link in new]
        if not additions:
            continue
        new_text = insert_stable_urls(text, additions)
        expected = [
            {**entry, "stable_urls": (entry.get("stable_urls") or []) + additions[entry["domain"]]}
            if entry["domain"] in additions else entry
            for entry in items
        ]
        if yaml.safe_load(new_text) != expected:
            raise SystemExit(f"{path}: the edited file does not load as expected; nothing written")
        added += sum(map(len, additions.values()))
        changed += 1
        if not args.dry_run:
            path.write_text(new_text)
    (index_dir / f"additions_{run}.tsv").write_text("".join(line + "\n" for line in listed))
    blc.log(f"{'would add' if args.dry_run else 'added'} {added} capture links in {changed} files "
            f"({len(kept)} pages kept; listed in {index_dir / f'additions_{run}.tsv'})")


if __name__ == "__main__":
    main()
