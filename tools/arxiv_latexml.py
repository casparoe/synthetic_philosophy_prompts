#!/usr/bin/env python3
r"""Render arXiv sources (e-prints) to HTML with LaTeXML, in a sandbox.

A versioned arXiv abstract link (https://arxiv.org/abs/<id>v<N>) is a stable
link (generators/link_cache.py): arXiv keeps the source of every version as
it was submitted, as "a permanent part of the scientific record". The page
behind such a link is that source, rendered by LaTeXML (the converter behind
arXiv's own HTML versions, which arXiv regenerates, so that they are not
stable themselves); tools/build_link_cache.py downloads the sources and takes
the text from the HTML as it does from arXiv's (arxiv_html_text). A
submission without TeX source is a PDF, and its text is the PDF's.

LaTeXML and the TeX Live it reads are pinned (tools/install_latexml.sh), so
that a source renders the same way again; the options are LATEXML_OPTIONS
and the settings in latexml_bindings/spp.sty.ltxml. A paper's \today is the
day its version was submitted.

The sources are untrusted. TeX reads any file it can name, a LaTeXML binding
(.ltxml) in a paper's directory would be run as Perl, and the rendered text
goes into prompts, which are sent to model providers. So bindings are left
out when a source is unpacked, and LaTeXML runs under sandbox-exec (macOS),
with a profile that denies the network, lets it read only its working
directory, LaTeXML, Perl, TeX Live, and the system libraries (not even the
existence of other files shows), write only its working directory, and run
only Perl, the shell, and the TeX programs; with a clean environment; within
time and memory limits. --self-test checks this: a paper that \input's a
file outside its directory, directly, through a relative path, or through a
symlink, or that asks whether the file exists, must not get it; and Perl in
the sandbox must reach neither that file nor the network, nor write outside,
nor run other programs; each probe is also run without the sandbox, where it
must succeed. Run it after a macOS, LaTeXML, or TeX Live update.

    .venv/bin/python tools/arxiv_latexml.py --self-test
    # the text of one e-print, as downloaded from arXiv
    .venv/bin/python tools/arxiv_latexml.py SOURCE_FILE
"""

import argparse
import io
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import zlib
from pathlib import Path

# LaTeXML and the TeX Live it reads, as tools/install_latexml.sh installs them
# (no LaTeXML release gets through the LaTeX 3 kernel of a recent TeX Live, and
# LaTeXML's development version not through TeX Live 2026's; see there), or
# $LATEXML_HOME and $LATEXML_TEXBIN (the directory of TeX Live's programs).
_TOOLS = Path(__file__).resolve().parents[1] / ".venv"
LATEXML_HOME = Path(os.environ.get("LATEXML_HOME") or _TOOLS / "latexml").resolve()
LATEXML_TEXBIN = os.environ.get("LATEXML_TEXBIN") or _TOOLS / "texlive-2025" / "bin" / "universal-darwin"
LATEXMLC = LATEXML_HOME / "bin" / "latexmlc"
PERL5LIB = LATEXML_HOME / "lib" / "perl5"
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
TIMEOUT = 600  # seconds LaTeXML may take for one paper (its own limit; ours is a minute more)
MAX_RSS_BYTES = 4_000_000_000  # memory it may take (checked every second)
# Limits on a source archive: what it unpacks to, and how many files it has.
MAX_UNPACKED_BYTES = 500_000_000
MAX_MEMBERS = 5000
# What LaTeXML is asked for: HTML5 with the TeX of each formula kept (as the
# alttext that arxiv_html_text uses), no images, arXiv's own preload options
# where they bear on the text (the .bbl rather than the .bib, styles that
# come with the paper loaded raw), and limits against runaway macro loops.
LATEXML_OPTIONS = [
    "--format=html5",
    "--preload=[nobibtex,localrawstyles,nobreakuntex,tokenlimit=249999999,"
    "iflimit=3599999,absorblimit=1299999,pushbacklimit=599999]latexml.sty",
    "--nodefaultresources",
    "--nographicimages",
    "--nopictureimages",
    "--nomathimages",
    "--nocomments",
    "--noinvisibletimes",
    f"--timeout={TIMEOUT}",
]
# Our own LaTeXML bindings: spp.sty.ltxml, preloaded (see there).
BINDINGS = Path(__file__).resolve().parent / "latexml_bindings"
LATEXML_OPTIONS += [f"--path={BINDINGS}", "--preload=spp.sty"]
TEX_SUFFIXES = (".tex", ".ltx", ".latex", ".TEX")
COMMON_MAIN_NAMES = ("main", "ms", "paper", "arxiv", "article", "manuscript")


class SourceError(Exception):
    """An e-print that cannot be rendered (the message is a short status)."""


def _run(command, **kwargs):
    return subprocess.run(command, capture_output=True, text=True, check=True, **kwargs).stdout.strip()


def tex_paths():
    """(directory of the TeX programs, the TeX Live tree): LATEXML_TEXBIN,
    and the tree its kpsewhich belongs to (with texmf-local)."""
    texbin = Path(LATEXML_TEXBIN).resolve()
    if not (texbin / "kpsewhich").exists():
        raise SystemExit(f"no kpsewhich in {texbin}: run tools/install_latexml.sh (or set LATEXML_TEXBIN)")
    root = Path(_run([str(texbin / "kpsewhich"), "--var-value=SELFAUTOPARENT"])).resolve()
    local = Path(_run([str(texbin / "kpsewhich"), "--var-value=TEXMFLOCAL"])).resolve()
    return texbin, root if local.is_relative_to(root) else root.parent


def perl_path():
    """The Perl to run LaTeXML with: $LATEXML_PERL, else the one latexmlc's
    first line names by its path, else macOS's (LaTeXML needs its XML::LibXML)."""
    if not LATEXMLC.exists():
        raise SystemExit(f"no LaTeXML at {LATEXML_HOME}: run tools/install_latexml.sh (or set LATEXML_HOME)")
    if os.environ.get("LATEXML_PERL"):
        return Path(os.environ["LATEXML_PERL"])
    first = LATEXMLC.read_text(errors="replace").split("\n", 1)[0]
    if re.match(r"^#!/\S*/perl[\d.]*$", first.strip()):
        return Path(first[2:].strip())
    return Path("/usr/bin/perl5.34")


def latexml_version():
    """LaTeXML's version, with the git revision of a build from its
    repository: ("LaTeXML version 0.8.8; revision 0db6f47", "0.8.8+0db6f47")."""
    env = {"PERL5LIB": str(PERL5LIB), "PATH": "/usr/bin:/bin"}
    full = _run([str(perl_path()), "-MLaTeXML", "-e", "print $LaTeXML::FULLVERSION"], env=env)
    m = re.search(r"version ([\w.]+)(?:; revision (\w+))?", full)
    return full, (m.group(1) + (f"+{m.group(2)}" if m.group(2) else "")) if m else full


_SAFE_PATH = re.compile(r"^/[A-Za-z0-9._/+-]+$")


def _sb(path):
    """A path as a sandbox-profile string (only plain characters, so nothing needs escaping)."""
    path = str(path)
    if not _SAFE_PATH.match(path):
        raise SystemExit(f"path not allowed in a sandbox profile: {path!r}")
    return f'"{path}"'


# LaTeXML asks kpsewhich for TeX's search paths through the shell (without
# it, it finds no file of TeX Live), and macOS's /bin/sh runs the shell that
# /private/var/select/sh names (bash). In the sandbox a shell can do no more
# than Perl can.
SHELL_FILES = [Path("/bin/sh"), Path("/private/var/select/sh").resolve(), Path("/private/var/select/sh")]


def sandbox_profile(work, perl, texbin, texlive):
    """The sandbox profile for a LaTeXML run in the directory work."""
    reads = [work, LATEXML_HOME, texlive, BINDINGS, Path("/Library/Perl")]
    programs = [perl, *SHELL_FILES[:2]]
    code = [LATEXML_HOME, texbin, Path("/System/Library/Perl"), Path("/Library/Perl")]
    # Directories on the way to what may be read can be looked at (stat), not listed.
    parents = sorted({p for path in [*reads, *programs, *SHELL_FILES, texbin] for p in Path(path).parents} - {Path("/")})
    lines = [
        "(version 1)",
        "(deny default)",
        '(import "system.sb")',  # the system libraries, /dev/null, the time zone, ...
        "(deny network*)",
        "(allow process-fork)",
        f"(allow process-exec {' '.join(f'(literal {_sb(p)})' for p in programs)} (subpath {_sb(texbin)}))",
        "(allow signal (target same-sandbox))",
        "(allow file-read* file-test-existence",
        *[f"  (subpath {_sb(p)})" for p in reads],
        *[f"  (literal {_sb(p)})" for p in [perl, *SHELL_FILES]],
        ")",
        "(allow file-map-executable",
        *[f"  (subpath {_sb(p)})" for p in code],
        *[f"  (literal {_sb(p)})" for p in programs],
        ")",
        "(allow file-read-metadata file-test-existence",
        *[f"  (literal {_sb(p)})" for p in parents],
        ")",
        f"(allow file-write* (subpath {_sb(work)}))",
    ]
    return "\n".join(lines) + "\n"


def sandboxed(work, command, timeout, cwd=None, extra_env=None):
    """Run command (a list; its program must be Perl or a TeX program) in
    the sandbox for work, with a clean environment. Returns the completed
    process. If it takes longer than timeout seconds, or more than
    MAX_RSS_BYTES of memory, its whole process group is killed and
    subprocess.TimeoutExpired or MemoryError raised."""
    work = Path(work).resolve()
    perl = perl_path()
    texbin, texlive = tex_paths()
    tmp = work / "tmp"
    tmp.mkdir(exist_ok=True)
    env = {
        "HOME": str(work),  # so TeX's per-user trees (TEXMFHOME, ...) are inside work
        "TMPDIR": str(tmp),
        "PATH": str(texbin),
        "PERL5LIB": str(PERL5LIB),
        "LATEXML_KPSEWHICH": str(texbin / "kpsewhich"),
        **(extra_env or {}),
    }
    profile = sandbox_profile(work, perl, texbin, texlive)
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = subprocess.Popen(
            [SANDBOX_EXEC, "-p", profile, *command],
            cwd=cwd or work, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
            start_new_session=True,
        )
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                if time.monotonic() > deadline:
                    raise subprocess.TimeoutExpired(command, timeout)
                if rss_bytes(process.pid) > MAX_RSS_BYTES:
                    raise MemoryError(f"more than {MAX_RSS_BYTES / 1e9:.0f} GB")
                time.sleep(1)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise
        out.seek(0)
        err.seek(0)
        return subprocess.CompletedProcess(
            process.args, process.returncode,
            out.read().decode(errors="replace"), err.read().decode(errors="replace"),
        )


def rss_bytes(pid):
    """Resident memory of a process (0 if it is gone)."""
    result = subprocess.run(["/bin/ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True)
    return int(result.stdout.strip() or 0) * 1024


# --- sources -------------------------------------------------------------------


def _gunzip(data, limit):
    out = zlib.decompressobj(16 + zlib.MAX_WBITS)
    result = out.decompress(data, limit + 1)
    if len(result) > limit or out.unconsumed_tail:
        raise SourceError("error source-too-large")
    return result


def source_kind(data):
    """'pdf', 'tar' or 'tex', and the bytes to use (decompressed)."""
    if data[:5] == b"%PDF-":
        return "pdf", data
    if data[:2] == b"\x1f\x8b":
        try:
            data = _gunzip(data, MAX_UNPACKED_BYTES)
        except (zlib.error, EOFError) as e:
            raise SourceError("error bad-gzip") from e
        if data[:5] == b"%PDF-":
            return "pdf", data
    if len(data) > 262 and data[257:262] == b"ustar" or _is_tar(data):
        return "tar", data
    head = data[:20000].decode("latin-1")
    if re.search(r"\\(documentclass|documentstyle|begin\s*\{document\}|input|bye)\b", head):
        return "tex", data
    if head.lstrip().startswith("%!PS"):
        raise SourceError("error postscript-only")
    raise SourceError("error unknown-source")


def _is_tar(data):
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
            return tar.next() is not None
    except tarfile.TarError:
        return False


def unpack(data, kind, into):
    """Write the source into the directory into: a tar archive's regular
    files and directories that stay inside into (within the limits), or the
    single TeX file as main.tex. LaTeXML bindings (.ltxml files) are left
    out: they are Perl, which LaTeXML would run."""
    into.mkdir(parents=True, exist_ok=True)
    if kind == "tex":
        (into / "main.tex").write_bytes(data)
        return
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
        members = []
        total = count = 0
        for member in tar:
            count += 1
            if count > MAX_MEMBERS:
                raise SourceError("error too-many-files")
            if not (member.isfile() or member.isdir()) or member.name.endswith(".ltxml"):
                continue  # no links, devices, bindings
            try:
                member = tarfile.data_filter(member, str(into))  # no absolute paths, no ..
            except tarfile.FilterError:
                continue
            total += member.size
            if total > MAX_UNPACKED_BYTES:
                raise SourceError("error source-too-large")
            members.append(member)
        try:
            tar.extractall(into, members=members, filter="data")
        except (tarfile.FilterError, OSError) as e:
            raise SourceError(f"error unpack {type(e).__name__}") from e


def _uncommented(text):
    return "\n".join(re.sub(r"(?<!\\)%.*", "", line) for line in text.split("\n"))


def main_tex(src):
    r"""The file LaTeX should be run on: the one arXiv's 00README.json names
    as toplevel, else the TeX file that starts a document (\documentclass or
    \documentstyle, preferring one with \begin{document}, one that no other
    file includes, a common name, the largest)."""
    readme = src / "00README.json"
    if readme.is_file():
        try:
            spec = json.loads(readme.read_text(errors="replace"))
            for source in spec.get("sources", []):
                if source.get("usage") == "toplevel" and (src / source.get("filename", "")).is_file():
                    return src / source["filename"]
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
    texts = {}
    for path in sorted(src.rglob("*")):
        if path.is_file() and path.suffix in TEX_SUFFIXES and path.stat().st_size < 20_000_000:
            texts[path] = _uncommented(path.read_text(errors="replace"))
    starts = [p for p, t in texts.items() if re.search(r"\\document(class|style)\b", t)]
    if not starts:
        raise SourceError("error no-main-tex")
    included = set()
    for text in texts.values():
        for name in re.findall(r"\\(?:input|include|subfile)\s*\{([^}]+)\}", text):
            included.add(Path(name.strip()).stem)

    def rank(path):
        text = texts[path]
        return (
            "\\begin{document}" in text.replace(" ", ""),
            path.stem not in included,
            path.stem.lower() in COMMON_MAIN_NAMES,
            len(text),
        )

    return max(starts, key=rank)


def render(main, work, timeout=TIMEOUT + 60, source_date=None):
    """LaTeXML's HTML for the TeX file main (inside work), and a summary of
    its log: (html or None, {"status": LaTeXML's conversion status, 0 to 3,
    "summary": its last log line, "seconds": ...}). \\today is the date
    source_date (a Unix time), if given, rather than the day of the run."""
    out = Path(work) / "out"
    out.mkdir(exist_ok=True)
    dest, logfile = out / "paper.html", out / "latexml.log"
    perl = perl_path()
    started = time.monotonic()
    try:
        sandboxed(
            work,
            [str(perl), str(LATEXMLC), *LATEXML_OPTIONS, f"--dest={dest}", f"--log={logfile}", main.name],
            timeout=timeout, cwd=main.parent,
            extra_env={"SOURCE_DATE_EPOCH": str(int(source_date))} if source_date else None,
        )
    except (subprocess.TimeoutExpired, MemoryError) as e:
        summary = "timeout" if isinstance(e, subprocess.TimeoutExpired) else "out-of-memory"
        return None, {"status": None, "summary": summary, "seconds": round(time.monotonic() - started)}
    log = logfile.read_text(errors="replace") if logfile.exists() else ""
    status = re.findall(r"^Status:conversion:(\d)", log, re.M)
    summary = [re.sub(r"\s*\(See [^)]*\)\s*$", "", line) for line in re.findall(r"^Conversion complete: (.*)$", log, re.M)]
    info = {
        "status": int(status[-1]) if status else None,
        "summary": (summary[-1] if summary else log.strip().split("\n")[-1] if log.strip() else "")[:300],
        "seconds": round(time.monotonic() - started),
    }
    html = dest.read_text(errors="replace") if dest.exists() else None
    return html, info


def eprint_html(data, source_date=None, keep_log=None):
    """The HTML for an e-print as downloaded from arXiv, or its PDF:
    ("html", html, info) or ("pdf", pdf bytes, info). Raises SourceError.
    source_date is the Unix time of the submission (for \\today); LaTeXML's
    log is copied to the path keep_log, if given."""
    kind, data = source_kind(data)
    if kind == "pdf":
        return "pdf", data, {}
    with tempfile.TemporaryDirectory(prefix="latexml-") as work:
        work = Path(work).resolve()
        src = work / "src"
        unpack(data, kind, src)
        main = main_tex(src)
        html, info = render(main, work, source_date=source_date)
        info["main"] = str(main.relative_to(src))
        if keep_log and (work / "out" / "latexml.log").exists():
            shutil.copyfile(work / "out" / "latexml.log", keep_log)
        # a fatal error (a time limit, say) can leave a document that stops part way
        if html is None or "<article" not in html or info["status"] is None or info["status"] >= 3:
            raise SourceError(f"error latexml {info.get('summary') or 'no-output'}"[:200])
        return "html", html, info


# --- self-test -----------------------------------------------------------------


PERL_PROBE = r"""
use strict; use IO::Socket::INET;
my ($probe, $outside, $home, $work) = @ARGV;
print "read the file outside:", (open(my $f, "<", $probe) ? "yes" : "no"), "\n";
print "see that it exists:", ((-e $probe) ? "yes" : "no"), "\n";
print "list its directory:", (opendir(my $d, $outside) ? "yes" : "no"), "\n";
print "list the home directory:", (opendir(my $h, $home) ? "yes" : "no"), "\n";
print "write outside:", (open(my $w, ">", "$outside/written") ? "yes" : "no"), "\n";
my $s = IO::Socket::INET->new(PeerAddr => "1.1.1.1", PeerPort => 443, Timeout => 5);
print "connect to 1.1.1.1:", ($s ? "yes" : "no"), "\n";
print "resolve a host name:", (gethostbyname("example.com") ? "yes" : "no"), "\n";
print "run curl:", (system("/usr/bin/curl", "-s", "-o", "/dev/null", "https://example.com") == 0 ? "yes" : "no"), "\n";
print "run curl from the shell:", (system("/bin/sh", "-c", "/usr/bin/curl -s -o /dev/null https://example.com") == 0 ? "yes" : "no"), "\n";
print "run osascript:", (system("/usr/bin/osascript", "-e", "return 1") == 0 ? "yes" : "no"), "\n";
print "write its work directory:", (open(my $o, ">", "$work/ok") ? "yes" : "no"), "\n";
"""
PROBE_PAPER = r"""\documentclass{article}
\begin{document}
Visible text before.

\input{PROBE}

\input{RELATIVE}

\input{link}

\IfFileExists{PROBE}{FILE-EXISTS}{FILE-ABSENT}

Euler: $e^{i\pi}+1=0$.
\end{document}
"""


def self_test():
    """Each probe runs in the sandbox, where it must fail, and without it,
    where it must succeed (else it proves nothing)."""
    failures, unproven = [], []

    def check(name, ok, detail=""):
        print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f": {detail}" if detail and not ok else ""))
        if not ok:
            failures.append(name)

    def control(name, ok):
        if not ok:
            print(f"     ({name}: not shown, since it fails without the sandbox too)")
            unproven.append(name)

    perl = perl_path()
    texbin, _ = tex_paths()
    with tempfile.TemporaryDirectory(prefix="latexml-outside-") as outside, \
            tempfile.TemporaryDirectory(prefix="latexml-") as work, \
            tempfile.TemporaryDirectory(prefix="latexml-control-") as bare:
        outside, work, bare = Path(outside).resolve(), Path(work).resolve(), Path(bare).resolve()
        secret = "SANDBOXPROBE" + secrets.token_hex(8)
        probe = outside / "probe.tex"
        probe.write_text(secret + "\n")
        src = work / "src"
        src.mkdir()
        (src / "link.tex").symlink_to(probe)
        # the three directories are siblings, so this path works from both papers
        relative = os.path.relpath(probe, src)
        (src / "main.tex").write_text(PROBE_PAPER.replace("RELATIVE", relative).replace("PROBE", str(probe)))
        shutil.copytree(src, bare / "src", symlinks=True)

        print("A paper that tries to read a file outside its directory:")
        html, info = render(src / "main.tex", work)
        check("LaTeXML renders it in the sandbox", bool(html) and "Visible text before" in html, str(info))
        check("the formula keeps its TeX", bool(html) and "e^{i\\pi}+1=0" in html)
        check("its text has nothing of the file (absolute path, relative path, symlink)", bool(html) and secret not in html)
        check("the file does not seem to exist", bool(html) and "FILE-ABSENT" in html and "FILE-EXISTS" not in html)
        subprocess.run(
            [str(perl), str(LATEXMLC), *LATEXML_OPTIONS, f"--dest={bare}/paper.html", f"--log={bare}/latexml.log", "main.tex"],
            cwd=bare / "src", env={"PERL5LIB": str(PERL5LIB), "PATH": str(texbin)}, capture_output=True, timeout=TIMEOUT,
        )
        bare_html = (bare / "paper.html").read_text() if (bare / "paper.html").exists() else ""
        control("reading the file", bare_html.count(secret) == 3)
        control("seeing that it exists", "FILE-EXISTS" in bare_html)

        plain = work / "plain"
        plain.mkdir()
        (plain / "main.tex").write_text(
            "\\documentclass{article}\n\\usepackage{keyval}\n\\begin{document}\nHello.\n\\end{document}\n")
        _, info = render(plain / "main.tex", work)
        check("a paper's packages are found in TeX Live (keyval)", info["status"] == 0, info["summary"])

        print("Perl in the sandbox, as if the paper had taken over LaTeXML:")
        args = [str(perl), "-e", PERL_PROBE, str(probe), str(outside), str(Path.home())]
        result = sandboxed(work, args + [str(work)], timeout=60)
        answers = dict(line.split(":", 1) for line in result.stdout.split("\n") if ":" in line)
        names = [line.split('"')[1].rstrip(":") for line in PERL_PROBE.split("\n") if line.startswith('print "')]
        for name in names[:-1]:
            check(f"cannot {name}", answers.get(name) == "no", answers.get(name) or result.stderr[-300:])
        check(f"can {names[-1]}", answers.get(names[-1]) == "yes", result.stderr[-300:])
        check("nothing was written outside", not (outside / "written").exists())
        bare_result = subprocess.run(args + [str(bare)], capture_output=True, text=True, timeout=60)
        bare_answers = dict(line.split(":", 1) for line in bare_result.stdout.split("\n") if ":" in line)
        for name in names[:-1]:
            control(name, bare_answers.get(name) == "yes")
    print("self-test " + (f"FAILED: {', '.join(failures)}" if failures else "passed")
          + (f" ({len(unproven)} checks not shown: {', '.join(unproven)})" if unproven else ""))
    return not failures


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", nargs="?", type=Path, help="an e-print file as downloaded from arXiv")
    parser.add_argument("--self-test", action="store_true", help="check that the sandbox holds")
    parser.add_argument("--html", action="store_true", help="print the HTML rather than the text")
    parser.add_argument("--log", type=Path, help="keep LaTeXML's log in this file")
    args = parser.parse_args()
    if args.self_test:
        sys.exit(0 if self_test() else 1)
    if not args.source:
        parser.error("give a source file, or --self-test")
    try:
        kind, content, info = eprint_html(args.source.read_bytes(), keep_log=args.log)
    except SourceError as e:
        sys.exit(str(e))
    print(json.dumps(info), file=sys.stderr)
    if kind == "pdf":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from build_link_cache import pdf_text
        print(pdf_text(content)[0])
    elif args.html:
        print(content)
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from build_link_cache import arxiv_html_text
        print(arxiv_html_text(content))


if __name__ == "__main__":
    main()
