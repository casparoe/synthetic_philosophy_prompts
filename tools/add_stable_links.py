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
arXiv asks). For LessWrong posts (--lesswrong): the revision that is current
when this runs, as a link to the post that names it
(https://www.lesswrong.com/posts/<id>/<slug>?revision=1.2.0; LessWrong keeps
every revision, and its page shows the one named), looked up through
LessWrong's GraphQL API, 50 posts a request, at its crawl delay. For entries
of the Stanford Encyclopedia of Philosophy (--sep): the entry in the newest
quarterly archive edition (or --sep-edition), if that edition has it
(https://plato.stanford.edu/archives/fall2026/entries/<entry>/; the edition's
table of contents says which entries it has). A domain that already lists a
revision of a page, a version of a paper, or an edition of an entry, keeps it,
so a rerun only adds what is missing; to move to newer revisions, remove the
old ones first.

The files are edited line by line, so their layout and comments stay as they
are: the stable_urls block goes right after the domain's urls block (or its
existing stable_urls block grows). Each file is checked afterwards to load as
before, plus exactly the new links.

    tools/add_stable_links.py --wikipedia [--dry-run]
    tools/add_stable_links.py --arxiv [--dry-run]
    tools/add_stable_links.py --lesswrong [--dry-run]
    tools/add_stable_links.py --sep [--sep-edition fall2026] [--dry-run]
    tools/add_stable_links.py --links FILE [--dry-run]

With --links, the stable links come from a file instead, one per line after
the text of the domain they go to and a tab (for links found another way, as
the arXiv papers matched to domains in 2026-10).
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
LESSWRONG_GRAPHQL = "https://www.lesswrong.com/graphql"
LESSWRONG_PER_REQUEST = 50
LESSWRONG_SPACING = 3.0  # LessWrong's crawl delay
SEP = "https://plato.stanford.edu"
SEP_SPACING = 5.0  # the SEP's crawl delay


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


def lesswrong_current_revisions(client, posts):
    """post ID as linked -> (its ID at LessWrong, slug, version of its current
    revision), for the posts LessWrong has; deleted posts, drafts, and posts
    without text are left out."""
    found = {}
    posts = sorted(posts)
    for i in range(0, len(posts), LESSWRONG_PER_REQUEST):
        batch = posts[i: i + LESSWRONG_PER_REQUEST]
        query = "{ " + " ".join(
            f'p{n}: post(input: {{selector: {{_id: "{post}"}}}}) {{ result {{ _id slug contents {{ version }} }} }}'
            for n, post in enumerate(batch)
        ) + " }"
        for attempt in range(5):
            response = client.post(LESSWRONG_GRAPHQL, json={"query": query})
            if response.status_code == 200:
                break
            time.sleep(60 * (attempt + 1))
        else:
            raise SystemExit(f"LessWrong API: {response.status_code} {response.text[:200]}")
        # a post that is gone comes back as an error for its alias, and its result as null
        data = response.json().get("data") or {}
        for n, linked in enumerate(batch):
            post = (data.get(f"p{n}") or {}).get("result")
            if post and post.get("slug") and (post.get("contents") or {}).get("version"):
                found[linked] = (post["_id"], post["slug"], post["contents"]["version"])
        time.sleep(LESSWRONG_SPACING)
        print(f"  LessWrong: {min(i + LESSWRONG_PER_REQUEST, len(posts))}/{len(posts)} posts looked up", flush=True)
    return found


def linked_name(url, prefix):
    """The rest of a link's cache key if it links a page of one kind directly
    (prefix "lesswrong:" or "sep:"), else None: a Wayback copy of the page is
    not the page."""
    key = link_cache.canonical(url)
    if key.startswith(prefix) and not link_cache.WAYBACK_RE.match(url):
        return key[len(prefix):]
    return None


def lesswrong_revision_link(post, slug, version):
    url = f"https://www.lesswrong.com/posts/{post}/{slug}?revision={version}"
    assert link_cache.stable_link(url) == ("lesswrong_revision", f"lesswrong_revision:{post}:{version}"), url
    return url


def pinned_of_kind(stable_urls, kind):
    """The pages of which a domain already lists a stable link of the kind:
    its cache key without the kind and the version (a LessWrong post's ID, an
    SEP entry's name)."""
    pinned = set()
    for url in stable_urls:
        found = link_cache.stable_link(url)
        if found and found[0] == kind:
            rest = found[1].split(":", 1)[1]
            pinned.add(rest.rsplit(":", 1)[0] if kind == "lesswrong_revision" else rest.split(":", 1)[1])
    return pinned


def sep_newest_edition(client):
    """The newest archive edition the SEP lists (like "fall2026")."""
    response = client.get(f"{SEP}/archives/")
    editions = re.findall(r'href="((?:spr|sum|fall|win)\d{4})/"', response.text)
    if response.status_code != 200 or not editions:
        raise SystemExit(f"SEP archives: {response.status_code}, no editions found")
    time.sleep(SEP_SPACING)
    return max(editions, key=lambda e: (e[-4:], ["spr", "sum", "fall", "win"].index(e[:-4])))


def sep_edition_entries(client, edition):
    """The names of the entries an SEP archive edition has, from its table of contents."""
    response = client.get(f"{SEP}/archives/{edition}/contents.html")
    entries = set(re.findall(r'href="entries/([^/"#?]+)/?"', response.text))
    if response.status_code != 200 or not entries:
        raise SystemExit(f"SEP {edition} contents: {response.status_code}, no entries found")
    time.sleep(SEP_SPACING)
    return entries


def sep_edition_link(edition, entry):
    url = f"{SEP}/archives/{edition}/entries/{entry}/"
    assert link_cache.stable_link(url) == ("sep_edition", f"sep_edition:{edition}:{entry}"), url
    return url


def insert_stable_urls(text, additions):
    """The file text with additions (domain text -> new stable links) inserted
    line by line: after the entry's stable_urls items if it has them, else
    after its urls items, as a new stable_urls block (or after the entry's
    last line if it has neither)."""
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
        new = [f"    - {url}" for url in additions[domain]]
        if block is None:  # an entry with no links yet: the block goes after its last line
            last = start
            for i in range(start + 1, end):
                if not lines[i].startswith("  ") or lines[i].lstrip().startswith("#"):
                    break
                last = i
            out_insertions[last] = ["  stable_urls:"] + new
            continue
        key, last = block
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


def lesswrong_proposer(client, entries):
    """For each domain entry, links to the current revisions of its LessWrong posts that it lacks."""
    linked = set()
    for items in entries.values():
        for entry in items:
            linked.update(filter(None, (linked_name(url, "lesswrong:") for url in entry.get("urls") or [])))
    print(f"{len(linked)} distinct LessWrong posts linked", flush=True)
    current = lesswrong_current_revisions(client, linked)
    print(f"current revisions found for {len(current)}; not found (deleted, a draft, or without text): "
          f"{len(linked) - len(current)}")

    def propose(entry):
        pinned = pinned_of_kind(entry.get("stable_urls") or [], "lesswrong_revision")
        new = []
        for url in entry.get("urls") or []:
            post = linked_name(url, "lesswrong:")
            if post not in current or current[post][0] in pinned:
                continue
            new.append(lesswrong_revision_link(*current[post]))
            pinned.add(current[post][0])
        return new

    return propose


def sep_proposer(client, entries, edition=None):
    """For each domain entry, links to its SEP entries in an archive edition
    (the newest, unless given) that it lacks, for the entries the edition has."""
    linked = set()
    for items in entries.values():
        for entry in items:
            linked.update(filter(None, (linked_name(url, "sep:") for url in entry.get("urls") or [])))
    edition = edition or sep_newest_edition(client)
    has = sep_edition_entries(client, edition)
    print(f"{len(linked)} distinct SEP entries linked; the {edition} edition has {len(has)} entries, "
          f"{len(linked & has)} of them linked; not in it: {sorted(linked - has)[:10]}", flush=True)

    def propose(entry):
        pinned = pinned_of_kind(entry.get("stable_urls") or [], "sep_edition")
        new = []
        for url in entry.get("urls") or []:
            name = linked_name(url, "sep:")
            if name not in has or name in pinned:
                continue
            new.append(sep_edition_link(edition, name))
            pinned.add(name)
        return new

    return propose


def listed_proposer(path, entries):
    """For each domain entry, the stable links that the file at path lists for
    it (lines "domain<TAB>link"; # starts a comment line), except a version of
    an arXiv paper of which the domain lists a version already."""
    wanted = collections.defaultdict(list)
    for n, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        domain, _, link = line.rpartition("\t")
        if not domain or not link_cache.stable_link(link):
            raise SystemExit(f"{path}:{n}: not a domain and a stable link: {line[:120]!r}")
        if link not in wanted[domain]:
            wanted[domain].append(link)
    known = {entry["domain"] for items in entries.values() for entry in items}
    unknown = [d for d in wanted if d not in known]
    if unknown:
        raise SystemExit(f"{path}: {len(unknown)} domains not in the domain files, e.g. {unknown[0][:80]!r}")
    print(f"{sum(map(len, wanted.values()))} links listed for {len(wanted)} domains", flush=True)

    def propose(entry):
        pinned = pinned_papers(entry.get("stable_urls") or [])
        new = []
        for link in wanted.get(entry["domain"], []):
            kind, key = link_cache.stable_link(link)
            if kind == "arxiv_version":
                paper = re.sub(r"v\d+$", "", key.split(":", 1)[1])
                if paper in pinned:
                    continue
                pinned.add(paper)
            new.append(link)
        return new

    return propose


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wikipedia", action="store_true", help="pin Wikipedia articles to their current revision")
    parser.add_argument("--arxiv", action="store_true", help="pin arXiv papers to a version (the linked one, else the latest)")
    parser.add_argument("--lesswrong", action="store_true", help="pin LessWrong posts to their current revision")
    parser.add_argument("--sep", action="store_true", help="pin SEP entries to an archive edition")
    parser.add_argument("--sep-edition", metavar="EDITION", help="that edition (like fall2026; default: the newest)")
    parser.add_argument("--links", metavar="FILE", help='add the stable links FILE lists (lines "domain<TAB>link")')
    parser.add_argument("--dry-run", action="store_true", help="look up and report, but change no file")
    args = parser.parse_args()
    if not (args.wikipedia or args.arxiv or args.lesswrong or args.sep or args.links):
        parser.error("say which links to add (--wikipedia, --arxiv, --lesswrong, --sep, --links)")
    if args.sep_edition and not re.fullmatch(r"(?:spr|sum|fall|win)\d{4}", args.sep_edition):
        parser.error(f"not an SEP edition: {args.sep_edition}")

    files = sorted(DOMAINS_DIR.glob("*.yaml"))
    entries = {path: yaml.safe_load(path.read_text()) or [] for path in files}
    with httpx.Client(headers={"User-Agent": UA}, timeout=60) as client:
        proposers = ([wikipedia_proposer(client, entries)] if args.wikipedia else []) + (
            [arxiv_proposer(client, entries)] if args.arxiv else []) + (
            [lesswrong_proposer(client, entries)] if args.lesswrong else []) + (
            [sep_proposer(client, entries, args.sep_edition)] if args.sep else []) + (
            [listed_proposer(args.links, entries)] if args.links else [])

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
