#!/bin/zsh
# Install what tools/arxiv_latexml.py renders arXiv sources with, into .venv
# (git-ignored): TeX Live 2025 in its final state (.venv/texlive-2025, about
# 5 GB, no documentation) and LaTeXML at a pinned commit, with its format dumps
# (.venv/latexml).
#
# Why these: no LaTeXML release gets through the LaTeX 3 kernel of a recent TeX
# Live (expl3-code.tex, which every paper using siunitx, xparse, tcolorbox and
# many more loads; LaTeXML issue #2064). The fix is on LaTeXML's master (PR
# #2759, 2026-03): `make formats` runs plain.tex and latex.ltx through LaTeXML
# once and dumps the result, which every later run loads instead. LaTeXML's
# tests use TeX Live up to 2025 (and issue #2862 reports the dump failing with
# 2026, though with this commit it worked here); and a TeX Live of its own,
# frozen, keeps the renderings reproducible, where the system's changes with
# every update. The system's TeX Live is not touched.
#
# Needs: macOS's Perl 5.34 (with its XML::LibXML), git, and Homebrew's latexml
# (`brew install latexml`), whose pure-Perl dependencies (Image::Size,
# Pod::Parser, Text::Unidecode) are copied over. Takes about half an hour.
#
#     tools/install_latexml.sh
#     # elsewhere (as tools/arxiv_latexml.py then needs to be told):
#     LATEXML_TEXLIVE=DIR LATEXML_HOME=DIR tools/install_latexml.sh
set -euo pipefail

COMMIT=0db6f47ea859391f9099e6e25e7405afad8467bf  # LaTeXML master of 2026-09-20
TLNET=https://ftp.math.utah.edu/pub/tex/historic/systems/texlive/2025/tlnet-final
REPO_ROOT=${0:A:h:h}
TEXLIVE=${LATEXML_TEXLIVE:-$REPO_ROOT/.venv/texlive-2025}
PREFIX=${LATEXML_HOME:-$REPO_ROOT/.venv/latexml}
PERL=/usr/bin/perl5.34
DEPS=/opt/homebrew/opt/latexml/libexec/lib/perl5

[[ -d $DEPS/Image && -d $DEPS/Pod && -d $DEPS/Text ]] || { echo "needs Homebrew's latexml (brew install latexml)" >&2; exit 1; }
[[ -e $PREFIX ]] && { echo "$PREFIX exists; remove it first" >&2; exit 1; }
BUILD=$(mktemp -d -t latexml-build)
trap 'rm -rf "$BUILD"' EXIT

if [[ ! -x $TEXLIVE/bin/universal-darwin/kpsewhich ]]; then
  echo "installing TeX Live 2025 into $TEXLIVE ..."
  curl -sSf -o "$BUILD/install-tl-unx.tar.gz" $TLNET/install-tl-unx.tar.gz
  curl -sSf -o "$BUILD/install-tl-unx.tar.gz.sha512" $TLNET/install-tl-unx.tar.gz.sha512
  (cd "$BUILD" && shasum -a 512 -c install-tl-unx.tar.gz.sha512 && tar xzf install-tl-unx.tar.gz)
  cat > "$BUILD/texlive.profile" <<EOF
selected_scheme scheme-full
TEXDIR $TEXLIVE
TEXMFLOCAL $TEXLIVE/texmf-local
TEXMFSYSCONFIG $TEXLIVE/texmf-config
TEXMFSYSVAR $TEXLIVE/texmf-var
TEXMFCONFIG $TEXLIVE/texmf-config
TEXMFVAR $TEXLIVE/texmf-var
TEXMFHOME $TEXLIVE/texmf-local
binary_universal-darwin 1
instopt_adjustpath 0
instopt_adjustrepo 0
instopt_letter 0
instopt_portable 1
instopt_write18_restricted 1
tlpdbopt_autobackup 0
tlpdbopt_create_formats 0
tlpdbopt_install_docfiles 0
tlpdbopt_install_srcfiles 0
tlpdbopt_desktop_integration 0
tlpdbopt_file_assocs 0
tlpdbopt_w32_multi_user 0
EOF
  "$BUILD"/install-tl-*/install-tl --no-interaction --profile="$BUILD/texlive.profile" --repository $TLNET \
    > "$BUILD/texlive.log" 2>&1 || { tail -20 "$BUILD/texlive.log" >&2; exit 1; }
fi

echo "building LaTeXML $COMMIT ..."
git -C "$BUILD" init --quiet src
git -C "$BUILD/src" fetch --quiet --depth 1 https://github.com/brucemiller/LaTeXML "$COMMIT"
git -C "$BUILD/src" checkout --quiet FETCH_HEAD
cd "$BUILD/src"
export PERL5LIB=$DEPS PATH=$TEXLIVE/bin/universal-darwin:/usr/bin:/bin
# latexml.sty (for documents that use LaTeXML's commands) goes into the prefix too
$PERL Makefile.PL INSTALL_BASE="$PREFIX" TEXMF="$PREFIX/texmf" NOMKTEXLSR > "$BUILD/configure.log"
make > "$BUILD/make.log"
echo "building the format dumps (plain.tex and latex.ltx; about half an hour) ..."
make formats > "$BUILD/formats.log" 2>&1 || { tail -20 "$BUILD/formats.log" >&2; exit 1; }
if grep -q "^Status:conversion:3" "$BUILD/formats.log"; then tail -20 "$BUILD/formats.log" >&2; exit 1; fi  # a fatal error
make install > "$BUILD/install.log"
cp -R "$DEPS/Image" "$DEPS/Pod" "$DEPS/Text" "$PREFIX/lib/perl5/"
ls "$PREFIX"/lib/perl5/LaTeXML/Engine/*_dump.pool.ltxml
echo "installed LaTeXML $COMMIT into $PREFIX, reading TeX Live 2025 in $TEXLIVE"
