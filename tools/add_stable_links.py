#!/usr/bin/env python
"""Add stable versions of the domains' links to meta_prompt/domains, under stable_urls.

A link prompt can attach only stable links (generators/link_cache.py,
STABLE_LINKS), and the domains' links are mostly to live pages. This adds,
next to a domain's live links, a stable version of each, under the domain's
stable_urls. The live links stay in urls, where they serve as the
meta-prompt's inspiration links; only link prompts use stable_urls. Nothing is
mapped between the two: tools/build_link_cache.py fetches every stable link
from the link itself.

For Wikipedia articles (--wikipedia): the revision that is current when this
runs, as a permanent link (https://en.wikipedia.org/w/index.php?title=...&oldid=...,
with the title the article has after redirects). For arXiv papers (--arxiv):
the version the link names, else the latest, as its abstract link
(https://arxiv.org/abs/<id>v<N>; the arXiv API says which version is the
latest, for 100 papers a request, at most one request every three seconds as
arXiv asks). A domain that already lists a revision of a page, or a version of
a paper, keeps it, so a rerun only adds what is missing; to move to newer
revisions, remove the old ones first.

The files are edited line by line, so their layout and comments stay as they
are: the stable_urls block goes right after the domain's urls block (or its
existing stable_urls block grows). Each file is checked afterwards to load as
before, plus exactly the new links.

    tools/add_stable_links.py --wikipedia [--dry-run]
    tools/add_stable_links.py --arxiv [--dry-run]
"""
import argparse
import collections
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "generators"))
import link_cache  # noqa: E402

DOMAINS_DIR = REPO / "meta_prompt" / "domains"
UA = "synthetic-philosophy-prompts/0.1 (https://github.com/casparoe/synthetic_philosophy_prompts; research script)"
WIKI_RE = re.compile(r"^https://([a-z][a-z-]*)\.wikipedia\.org/wiki/([^?#\s]+)$")
TITLES_PER_REQUEST = 50  # the API's limit for titles in one query
SPACING = 1.0  # seconds between API requests
# Characters a title keeps unencoded in a permanent link (spaces become underscores).
TITLE_SAFE = "()_,-.:!*'/;@$~"
# An arXiv link, with the paper's identifier and the version it names, if any.
ARXIV_LINK_RE = re.compile(
    r"^https?://(?:www\.|export\.)?arxiv\.org/(?:abs|pdf|html)/"
    r"((?:[a-z-]+(?:\.[A-Z]{2})?/)?\d+(?:\.\d+)?)(v\d+)?(?:\.pdf)?/?$"
)
ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_PER_REQUEST = 100
ARXIV_SPACING = 3.0  # arXiv's terms for its API: at most one request every three seconds
ATOM = {"a": "http://www.w3.org/2005/Atom"}


def wikipedia_revisions(client, lang, titles):
    """title as linked -> (title after redirects, current revision ID), for
    the titles that are articles; missing pages are left out."""
    found = {}
    titles = sorted(titles)
    for i in range(0, len(titles), TITLES_PER_REQUEST):
        batch = titles[i: i + TITLES_PER_REQUEST]
        for attempt in range(5):
            response = client.get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={
                    "action": "query", "prop": "revisions", "rvprop": "ids", "titles": "|".join(batch),
                    "redirects": 1, "format": "json", "formatversion": 2, "maxlag": 5,
                },
            )
            data = response.json() if response.status_code == 200 else {}
            if data.get("error", {}).get("code") == "maxlag" or response.status_code >= 500:
                time.sleep(10 * (attempt + 1))
                continue
            break
        if "query" not in data:
            raise SystemExit(f"Wikipedia API: {response.status_code} {str(data)[:200]}")
        query = data["query"]
        normalized = {n["from"]: n["to"] for n in query.get("normalized", [])}
        redirects = {r["from"]: r["to"] for r in query.get("redirects", [])}
        pages = {p["title"]: p for p in query.get("pages", [])}
        for title in batch:
            final = normalized.get(title, title)
            final = redirects.get(final, final)
            page = pages.get(final)
            if page and page.get("revisions") and not page.get("missing") and page.get("ns") == 0:
                found[title] = (final, page["revisions"][0]["revid"])
        time.sleep(SPACING)
        print(f"  {lang}: {min(i + TITLES_PER_REQUEST, len(titles))}/{len(titles)} titles looked up", flush=True)
    return found


def permanent_link(lang, title, revid):
    url = f"https://{lang}.wikipedia.org/w/index.php?title={urllib.parse.quote(title.replace(' ', '_'), safe=TITLE_SAFE)}&oldid={revid}"
    assert link_cache.stable_link(url) == ("wikipedia_revision", f"wikipedia_revision:{lang}:{revid}"), url
    return url


def pinned_titles(stable_urls):
    """(lang, title) of the Wikipedia revisions a domain already lists."""
    pinned = set()
    for url in stable_urls:
        kind = link_cache.stable_link(url)
        if kind and kind[0] == "wikipedia_revision":
            parts = urllib.parse.urlsplit(url)
            title = urllib.parse.parse_qs(parts.query).get("title", [None])[0]
            if title:
                pinned.add((parts.hostname.split(".")[0], title.replace("_", " ")))
    return pinned


def arxiv_latest_versions(client, papers):
    """paper identifier -> its latest version ("v3"), for the papers arXiv has."""
    found = {}
    papers = sorted(papers)
    for i in range(0, len(papers), ARXIV_PER_REQUEST):
        batch = papers[i: i + ARXIV_PER_REQUEST]
        for attempt in range(5):
            response = client.get(ARXIV_API, params={"id_list": ",".join(batch), "max_results": len(batch)})
            if response.status_code == 200 and response.text.lstrip().startswith("<?xml"):
                break
            time.sleep(30 * (attempt + 1))
        else:
            raise SystemExit(f"arXiv API: {response.status_code} {response.text[:200]}")
        for entry in ET.fromstring(response.text).findall("a:entry", ATOM):
            link = entry.findtext("a:id", "", ATOM)
            if m := re.search(r"/abs/(.+?)(v\d+)$", link):
                found[m.group(1)] = m.group(2)
        time.sleep(ARXIV_SPACING)
        print(f"  arXiv: {min(i + ARXIV_PER_REQUEST, len(papers))}/{len(papers)} papers looked up", flush=True)
    return found


def arxiv_abstract_link(paper, version):
    url = f"https://arxiv.org/abs/{paper}{version}"
    assert link_cache.stable_link(url) == ("arxiv_version", f"arxiv_version:{paper}{version}"), url
    return url


def pinned_papers(stable_urls):
    """The arXiv papers of which a domain already lists a version."""
    papers = set()
    for url in stable_urls:
        kind = link_cache.stable_link(url)
        if kind and kind[0] == "arxiv_version":
            papers.add(re.sub(r"v\d+$", "", kind[1].split(":", 1)[1]))
    return papers


def insert_stable_urls(text, additions):
    """The file text with additions (domain text -> new stable links) inserted
    line by line: after the entry's stable_urls items if it has them, else
    after its urls items, as a new stable_urls block."""
    lines = text.split("\n")
    starts = [i for i, line in enumerate(lines) if line.startswith("- domain:")]
    out_insertions = {}  # line index -> lines to insert after it
    entries = yaml.safe_load(text) or []
    for entry_index, start in enumerate(starts):
        domain = entries[entry_index]["domain"]
        if domain not in additions:
            continue
        end = starts[entry_index + 1] if entry_index + 1 < len(starts) else len(lines)
        block = None  # index of the last item line of the block to extend
        for key in ("stable_urls", "urls"):
            head = next((i for i in range(start, end) if lines[i] == f"  {key}:"), None)
            if head is None:
                continue
            last = head
            for i in range(head + 1, end):
                if lines[i].startswith("    - "):
                    last = i
                else:
                    break
            block = (key, last)
            break
        if block is None:
            raise SystemExit(f"{domain[:60]!r}: no urls block to put stable_urls after")
        key, last = block
        new = [f"    - {url}" for url in additions[domain]]
        out_insertions[last] = new if key == "stable_urls" else ["  stable_urls:"] + new
    result = []
    for i, line in enumerate(lines):
        result.append(line)
        result.extend(out_insertions.get(i, []))
    return "\n".join(result)


def wikipedia_proposer(client, entries):
    """For each domain entry, the permanent links of its Wikipedia articles that it lacks."""
    wanted = collections.defaultdict(set)  # lang -> titles
    for items in entries.values():
        for entry in items:
            for url in entry.get("urls") or []:
                if m := WIKI_RE.match(url):
                    wanted[m.group(1)].add(urllib.parse.unquote(m.group(2)))
    print(f"{sum(map(len, wanted.values()))} distinct Wikipedia articles linked", flush=True)
    revisions = {}
    for lang, titles in wanted.items():
        for title, found in wikipedia_revisions(client, lang, titles).items():
            revisions[(lang, title)] = found
    missing = sum(map(len, wanted.values())) - len(revisions)
    print(f"current revisions found for {len(revisions)}; not an article (missing, or not in the main namespace): {missing}")

    def propose(entry):
        pinned = pinned_titles(entry.get("stable_urls") or [])
        new = []
        for url in entry.get("urls") or []:
            m = WIKI_RE.match(url)
            found = m and revisions.get((m.group(1), urllib.parse.unquote(m.group(2))))
            if not found or (m.group(1), found[0]) in pinned:
                continue
            new.append(permanent_link(m.group(1), *found))
            pinned.add((m.group(1), found[0]))
        return new

    return propose


def arxiv_proposer(client, entries):
    """For each domain entry, the abstract links of the versions of its arXiv papers that it lacks."""
    linked = set()
    unversioned = set()
    for items in entries.values():
        for entry in items:
            for url in entry.get("urls") or []:
                if m := ARXIV_LINK_RE.match(url):
                    linked.add(m.group(1))
                    if not m.group(2):
                        unversioned.add(m.group(1))
    print(f"{len(linked)} distinct arXiv papers linked, {len(unversioned)} of them without a version", flush=True)
    latest = arxiv_latest_versions(client, unversioned)
    print(f"latest versions found for {len(latest)}; not found: {len(unversioned) - len(latest)}")

    def propose(entry):
        pinned = pinned_papers(entry.get("stable_urls") or [])
        new = []
        for url in entry.get("urls") or []:
            m = ARXIV_LINK_RE.match(url)
            version = m and (m.group(2) or latest.get(m.group(1)))
            if not version or m.group(1) in pinned or link_cache.stable_link(url):
                continue  # (a link that is itself stable can be attached as it is)
            new.append(arxiv_abstract_link(m.group(1), version))
            pinned.add(m.group(1))
        return new

    return propose


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wikipedia", action="store_true", help="pin Wikipedia articles to their current revision")
    parser.add_argument("--arxiv", action="store_true", help="pin arXiv papers to a version (the linked one, else the latest)")
    parser.add_argument("--dry-run", action="store_true", help="look up and report, but change no file")
    args = parser.parse_args()
    if not (args.wikipedia or args.arxiv):
        parser.error("say which links to add stable versions of (--wikipedia, --arxiv)")

    files = sorted(DOMAINS_DIR.glob("*.yaml"))
    entries = {path: yaml.safe_load(path.read_text()) or [] for path in files}
    with httpx.Client(headers={"User-Agent": UA}, timeout=60) as client:
        proposers = ([wikipedia_proposer(client, entries)] if args.wikipedia else []) + (
            [arxiv_proposer(client, entries)] if args.arxiv else [])

    added = changed_files = 0
    for path, items in entries.items():
        additions = {}
        for entry in items:
            new = []
            for propose in proposers:
                new += [link for link in propose(entry) if link not in new and link not in (entry.get("stable_urls") or [])]
            if new:
                additions[entry["domain"]] = new
        if not additions:
            continue
        text = path.read_text()
        new_text = insert_stable_urls(text, additions)
        # the file must load as before, plus exactly the new links
        expected = [
            {**entry, "stable_urls": (entry.get("stable_urls") or []) + additions[entry["domain"]]}
            if entry["domain"] in additions else entry
            for entry in items
        ]
        if yaml.safe_load(new_text) != expected:
            raise SystemExit(f"{path}: the edited file does not load as expected; nothing written")
        added += sum(map(len, additions.values()))
        changed_files += 1
        if not args.dry_run:
            path.write_text(new_text)
    print(f"{'would add' if args.dry_run else 'added'} {added} stable links in {changed_files} files")


if __name__ == "__main__":
    main()
