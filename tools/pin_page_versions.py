#!/usr/bin/env python
"""Find a version-pinned URL for every page attached to a link batch's prompts.

The Hub gets the pages' URLs and hashes, never their text (see
generators/attached_pages.py). A live URL drifts: pages are edited, moved, or
taken down. So every attached page also gets a URL that shows the page as it was
when its text was fetched, as nearly as the source allows (version_kind):

  wikipedia_revision  the revision that was current at the fetch (index.php?oldid=),
                      from the MediaWiki API: the text the cache got
  arxiv_version       the arXiv version that was current at the fetch (abs/IDvN)
  sep_edition         the last SEP archive edition before the fetch (archives/<season>
                      <year>/entries/...), or the next one, once it is out, if the entry
                      was revised in between
  gutenberg           the ebook's page (Project Gutenberg texts rarely change)
  wayback             the Internet Archive capture nearest the fetch, for everything
                      else and as the fallback (the Wayback Machine has no SEP pages);
                      with --save, a page whose nearest capture is more than
                      SAVE_AFTER_DAYS from the fetch (or that has none) is captured now
                      with Save Page Now, which shows the page as it is now; that needs
                      an archive.org account's S3 keys (api_keys/archive_org.txt)

The results go to prompts/batch_NNN/page_versions.yaml (sha256 -> url, version_url,
version_kind, version_time, checked_at), which tools/export_hf.py joins into the
batch's link_prompts rows; a link batch is exported only once every page has an entry.
Pages that already have a version URL are skipped, so a rerun only fills gaps. The
requests are spaced out on purpose: archive.org refused this machine's connections
for a while after a probe of about fifty quick requests (2026-10-21).

    tools/pin_page_versions.py prompts/batch_073 [--save] [--limit N]
"""
import argparse
import datetime as dt
import os
import pathlib
import re
import sys
import time
import urllib.parse

import httpx
import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "generators"))
import link_cache  # noqa: E402

LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
UA = "synthetic-philosophy-prompts/0.1 (https://github.com/casparoe/synthetic_philosophy_prompts; research script)"
VERSIONS_FILE = "page_versions.yaml"
# Seconds between requests to each service.
SPACING = {"wikipedia": 1.0, "arxiv": 15.0, "sep": 5.0, "wayback": 6.0, "save": 30.0}
SAVE_AFTER_DAYS = 90
# SEP archive editions come out at the start of each season (month, day).
SEP_EDITIONS = [(3, 21, "spring"), (6, 21, "summer"), (9, 21, "fall"), (12, 21, "winter")]
SEP_REVISION_RE = re.compile(
    r"(?:substantive revision|First published)\s+\w{3}\s+(\w{3})\s+(\d{1,2}),\s+(\d{4})", re.I
)
ARXIV_VERSION_RE = re.compile(r"\[v(\d+)\]\s*(?:<[^>]+>\s*)*\w{3},\s+(\d{1,2} \w{3} \d{4} \d{2}:\d{2}:\d{2}) UTC")

_last = {}


def polite_get(client, service, url, **kwargs):
    """GET with the service's spacing between requests; retries 429/5xx and
    connection errors a few times with growing pauses."""
    for attempt in range(4):
        wait = SPACING[service] - (time.monotonic() - _last.get(service, 0))
        if wait > 0:
            time.sleep(wait)
        _last[service] = time.monotonic()
        try:
            response = client.get(url, **kwargs)
        except httpx.HTTPError as e:
            problem = e.__class__.__name__
        else:
            if response.status_code not in (429, 500, 502, 503, 504):
                return response
            problem = f"HTTP {response.status_code}"
        pause = 60 * (attempt + 1)
        print(f"  {service}: {problem}; pausing {pause} s", file=sys.stderr, flush=True)
        time.sleep(pause)
    return None


def parse_time(text):
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))


def wayback_stamp(t):
    return t.strftime("%Y%m%d%H%M%S")


def wikipedia_version(client, page):
    parts = urllib.parse.urlsplit(page["url"])
    title = urllib.parse.unquote(parts.path[len("/wiki/"):])
    fetched = parse_time(page["fetched_at"]).strftime("%Y-%m-%dT%H:%M:%SZ")
    response = polite_get(
        client, "wikipedia", f"https://{parts.hostname}/w/api.php",
        params={
            "action": "query", "format": "json", "formatversion": "2", "prop": "revisions",
            "rvprop": "ids|timestamp", "rvlimit": "1", "rvdir": "older", "rvstart": fetched,
            "titles": title, "redirects": "1",
        },
    )
    if response is None or response.status_code != 200:
        return None
    pages = response.json().get("query", {}).get("pages") or []
    revisions = pages[0].get("revisions") if pages else None
    if not revisions:
        return None
    rev = revisions[0]
    name = urllib.parse.quote(pages[0]["title"].replace(" ", "_"))
    return {
        "version_url": f"https://{parts.hostname}/w/index.php?title={name}&oldid={rev['revid']}",
        "version_kind": "wikipedia_revision",
        "version_time": rev["timestamp"],
    }


def arxiv_version(client, page, key):
    paper = key.split(":", 1)[1]
    response = polite_get(client, "arxiv", f"https://arxiv.org/abs/{paper}")
    if response is None or response.status_code != 200:
        return None
    fetched = parse_time(page["fetched_at"])
    best = None
    for number, stamp in ARXIV_VERSION_RE.findall(response.text):
        when = dt.datetime.strptime(stamp, "%d %b %Y %H:%M:%S").replace(tzinfo=dt.timezone.utc)
        if when <= fetched and (best is None or int(number) > best[0]):
            best = (int(number), when)
    if best is None:
        return None
    return {
        "version_url": f"https://arxiv.org/abs/{paper}v{best[0]}",
        "version_kind": "arxiv_version",
        "version_time": best[1].isoformat(),
    }


def sep_version(client, page, key, text):
    """The SEP archive edition closest to the fetch that holds the entry's last
    substantive revision before it: the last edition before the fetch (which
    also has the minor corrections made until then), or, if the entry was
    revised after that edition, the next one, once it is out."""
    m = None
    # The cache keeps the entry's pubinfo line ("First published ...; substantive
    # revision ...") as its published date; the last date is the latest revision.
    for m in SEP_REVISION_RE.finditer(page.get("published") or text[:3000]):
        pass
    if m is None:
        return None
    fetched = parse_time(page["fetched_at"]).date()
    editions = sorted(
        (dt.date(year, month, day), f"{season}{year}")
        for year in range(fetched.year - 1, fetched.year + 2)
        for month, day, season in SEP_EDITIONS
    )
    before = [e for e in editions if e[0] <= fetched][-1:]
    after = [e for e in editions if fetched < e[0] <= dt.date.today()][:1]
    for date, edition in before + after:
        url = f"https://plato.stanford.edu/archives/{edition}/entries/{key.split(':', 1)[1]}/"
        response = polite_get(client, "sep", url)
        if response is not None and response.status_code == 200 and m.group(0) in response.text:
            return {"version_url": url, "version_kind": "sep_edition", "version_time": date.isoformat()}
    return None  # revised after the last edition, and the next is not out yet


def wayback_version(client, page):
    """The capture nearest the fetch, among captures of the URL as shown and
    as listed."""
    fetched = parse_time(page["fetched_at"])
    best = None
    for url in dict.fromkeys([page["url"], page.get("listed_url") or page["url"]]):
        url = link_cache.WAYBACK_RE.sub(r"\1", url)
        response = polite_get(
            client, "wayback", "https://web.archive.org/cdx/search/cdx",
            params={
                "url": url, "output": "json", "fl": "timestamp,original",
                "filter": "statuscode:200", "collapse": "timestamp:6", "limit": "5000",
            },
        )
        if response is None or response.status_code != 200 or not response.text.strip():
            continue
        for stamp, original in response.json()[1:]:
            when = dt.datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=dt.timezone.utc)
            if best is None or abs(when - fetched) < abs(best[0] - fetched):
                best = (when, stamp, original)
    if best is None:
        return None
    return {
        "version_url": f"https://web.archive.org/web/{best[1]}/{best[2]}",
        "version_kind": "wayback",
        "version_time": best[0].isoformat(),
    }


ARCHIVE_KEYS = REPO / "api_keys" / "archive_org.txt"


def save_now(client, page):
    """Capture the page now with Save Page Now's API (SPN2), which needs an
    archive.org account's S3 keys in api_keys/archive_org.txt ('access:secret');
    anonymous requests fail ("Job failed", 2026-10-21). Untested: no keys yet."""
    if not ARCHIVE_KEYS.exists():
        return None
    headers = {"Authorization": "LOW " + ARCHIVE_KEYS.read_text().strip(), "Accept": "application/json"}
    wait = SPACING["save"] - (time.monotonic() - _last.get("save", 0))
    if wait > 0:
        time.sleep(wait)
    _last["save"] = time.monotonic()
    try:
        response = client.post("https://web.archive.org/save", data={"url": page["url"]}, headers=headers)
        job = response.json().get("job_id") if response.status_code == 200 else None
        for _ in range(30 if job else 0):
            time.sleep(10)
            status = client.get(f"https://web.archive.org/save/status/{job}", headers=headers).json()
            if status.get("status") == "success":
                stamp = status["timestamp"]
                when = dt.datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=dt.timezone.utc)
                return {
                    "version_url": f"https://web.archive.org/web/{stamp}/{page['url']}",
                    "version_kind": "wayback",
                    "version_time": when.isoformat(),
                    "saved": True,
                }
            if status.get("status") == "error":
                print(f"  save failed: {status.get('message')}", file=sys.stderr, flush=True)
                return None
    except (httpx.HTTPError, ValueError) as e:
        print(f"  save failed: {e!r}", file=sys.stderr, flush=True)
    return None


def find_version(client, page, text, save):
    key = link_cache.canonical(page.get("listed_url") or page["url"])
    found = None
    if key.startswith("wikipedia:"):
        found = wikipedia_version(client, page)
    elif key.startswith("arxiv:"):
        found = arxiv_version(client, page, key)
    elif key.startswith("sep:"):
        found = sep_version(client, page, key, text)
    elif key.startswith("gutenberg:"):
        found = {
            "version_url": f"https://www.gutenberg.org/ebooks/{key.split(':', 1)[1]}",
            "version_kind": "gutenberg",
            "version_time": None,
        }
    if found is None:
        found = wayback_version(client, page)
        far = found is None or abs(parse_time(found["version_time"]) - parse_time(page["fetched_at"])) > dt.timedelta(days=SAVE_AFTER_DAYS)
        if save and far:
            found = save_now(client, page) or found
    return found


def write_versions(path, versions):
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(versions, sort_keys=False, allow_unicode=True))
    os.replace(tmp, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("batch", type=pathlib.Path)
    parser.add_argument("--save", action="store_true", help="capture pages that lack a near Wayback capture")
    parser.add_argument("--limit", type=int, help="look up at most N pages this time")
    args = parser.parse_args()
    import attached_pages

    if args.save and not ARCHIVE_KEYS.exists():
        print(f"--save needs an archive.org account's S3 keys in {ARCHIVE_KEYS.relative_to(REPO)} "
              "('access:secret'); without them pages keep their nearest existing capture", flush=True)

    cfg = yaml.load((args.batch / "batch.yaml").read_text(), Loader=LOADER)
    if not cfg.get("link_prompts"):
        raise SystemExit(f"{args.batch} is not a link batch")
    store = attached_pages.SnapshotStore(REPO / cfg["snapshots"])
    pages = {}
    for meta in sorted(args.batch.glob("prompt_*.meta.yaml")):
        for page in yaml.load(meta.read_text(), Loader=LOADER).get("attached_pages") or []:
            pages.setdefault(page["sha256"], page)
    path = args.batch / VERSIONS_FILE
    versions = (yaml.load(path.read_text(), Loader=LOADER) or {}) if path.exists() else {}
    todo = [sha for sha in pages if not (versions.get(sha) or {}).get("version_url")]
    if args.limit is not None:
        todo = todo[: args.limit]
    print(f"{len(pages)} distinct pages; {len(pages) - len(todo)} done; looking up {len(todo)}", flush=True)
    with httpx.Client(headers={"User-Agent": UA}, timeout=60, follow_redirects=False) as client:
        for i, sha in enumerate(todo, 1):
            page = pages[sha]
            found = find_version(client, page, store.get(sha), args.save) or {
                "version_url": None, "version_kind": None, "version_time": None,
            }
            versions[sha] = {
                "url": page["url"],
                **found,
                "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            }
            write_versions(path, versions)
            print(f"[{i}/{len(todo)}] {found.get('version_kind') or 'NONE'} {found.get('version_url') or page['url']}", flush=True)
    kinds = {}
    for entry in versions.values():
        kinds[entry.get("version_kind") or "none"] = kinds.get(entry.get("version_kind") or "none", 0) + 1
    print("version kinds: " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    main()
