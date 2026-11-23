#!/usr/bin/env python
"""Build the CryNet project dossier as a single PDF.

Reads the chapter markdown from chapters/, renders them to one HTML file
with a self-contained stylesheet, prints it to PDF with headless Edge, then
adds PDF bookmarks and checks the result.

    python docs/dossier/build.py

Nothing here touches the firmware or the research tree; it only reads them.
"""

from __future__ import annotations

import html
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
CHAPTERS = os.path.join(HERE, "chapters")
OUT_HTML = os.path.join(HERE, "CryNet-TwoNode-Dossier.html")
OUT_PDF = os.path.join(HERE, "CryNet-TwoNode-Dossier.pdf")

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PY = sys.executable

# ---------------------------------------------------------------- markdown


def inline(text: str) -> str:
    """Inline markdown -> HTML.

    Code spans are stashed behind placeholders first, so their contents are
    never transformed *and* a bold run can wrap a code span
    (``**`foo`**``) — splitting on code spans first used to leave the
    surrounding ``**`` as literal text.
    """
    codes: list[str] = []

    def stash(m: "re.Match[str]") -> str:
        codes.append("<code>" + html.escape(m.group(1)) + "</code>")
        return "\x01%d\x02" % (len(codes) - 1)

    text = re.sub(r"`([^`]+)`", stash, text)
    text = html.escape(text)
    text = re.sub(r"&amp;([a-zA-Z]+|#\d+);", r"&\1;", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", text)
    return re.sub(r"\x01(\d+)\x02", lambda m: codes[int(m.group(1))], text)


def slug(text: str) -> str:
    s = re.sub(r"<[^>]+>", "", text)
    s = re.sub(r"[^\w\s-]", "", s.lower())
    return re.sub(r"[\s_]+", "-", s.strip())


# Only a *block-level* tag opens a raw-HTML block.  An inline tag at the
# start of a line (an <a> cross-reference, say) must stay in the paragraph
# flow: the old handler swallowed everything up to the next </p>/</div>,
# which silently ate whole sections of a chapter.
RAW_BLOCK = re.compile(
    r"^\s*</?(div|table|thead|tbody|tr|td|th|ul|ol|li|p|h[1-6]|blockquote|pre|hr|section|figure)[\s>/]"
)


def md_to_html(text: str) -> str:
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # page break directive
        if line.strip() == "<!-- PB -->":
            out.append('<div class="pagebreak"></div>')
            i += 1
            continue

        # fenced code
        if line.startswith("```"):
            lang = line[3:].strip()
            i += 1
            buf = []
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            cls = "code" + (" lang-" + re.sub(r"\W", "", lang) if lang else "")
            out.append(
                '<pre class="%s"><code>%s</code></pre>'
                % (cls, html.escape("\n".join(buf)))
            )
            continue

        # heading
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            lvl = len(m.group(1))
            txt = m.group(2).strip()
            out.append(
                '<h%d id="%s">%s</h%d>' % (lvl, slug(txt), inline(txt), lvl)
            )
            i += 1
            continue

        # horizontal rule
        if re.match(r"^\s*---+\s*$", line):
            out.append("<hr>")
            i += 1
            continue

        # table
        if line.strip().startswith("|"):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            cells = []
            for r in rows:
                if re.match(r"^\|[\s:\-|]+\|$", r):
                    continue
                parts = r.strip("|").split("|")
                cells.append([c.strip() for c in parts])
            if not cells:
                continue
            head, body = cells[0], cells[1:]
            th = "".join("<th>%s</th>" % inline(c) for c in head)
            rows_html = []
            for r in body:
                tds = "".join("<td>%s</td>" % inline(c) for c in r)
                rows_html.append("<tr>%s</tr>" % tds)
            out.append(
                '<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>'
                % (th, "".join(rows_html))
            )
            continue

        # blockquote
        if line.startswith(">"):
            buf = []
            while i < n and lines[i].startswith(">"):
                buf.append(lines[i].lstrip(">").strip())
                i += 1
            out.append(
                "<blockquote>%s</blockquote>"
                % inline(" ".join(b for b in buf if b))
            )
            continue

        # list
        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if m:
            items: list[list] = []
            while i < n:
                mm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[i])
                if mm:
                    items.append([len(mm.group(1)) // 2, mm.group(2), mm.group(3)])
                    i += 1
                    continue
                # a wrapped item: an indented continuation line belongs to
                # the item above it, not to a new paragraph
                if (items and lines[i].strip()
                        and re.match(r"^\s{2,}\S", lines[i])):
                    items[-1][2] += " " + lines[i].strip()
                    i += 1
                    continue
                if lines[i].strip() == "" and i + 1 < n and re.match(
                    r"^\s*([-*]|\d+\.)\s+", lines[i + 1]
                ):
                    i += 1
                    continue
                break
            htmlbuf: list[str] = []
            stack: list[list] = []  # [tag, li_open]
            for level, marker, txt in items:
                tag = "ol" if marker[0].isdigit() else "ul"
                while len(stack) > level + 1:
                    t, lo = stack.pop()
                    if lo:
                        htmlbuf.append("</li>")
                    htmlbuf.append("</%s>" % t)
                if len(stack) < level + 1:
                    attrs = ""
                    if tag == "ol":
                        num = int(re.match(r"(\d+)", marker).group(1))
                        if num > 1:
                            attrs = ' start="%d"' % num
                    htmlbuf.append("<%s%s>" % (tag, attrs))
                    stack.append([tag, False])
                elif stack[-1][0] != tag:
                    t, lo = stack.pop()
                    if lo:
                        htmlbuf.append("</li>")
                    htmlbuf.append("</%s>" % t)
                    htmlbuf.append("<%s>" % tag)
                    stack.append([tag, False])
                if stack[-1][1]:
                    htmlbuf.append("</li>")
                htmlbuf.append("<li>" + inline(txt))
                stack[-1][1] = True
            while stack:
                t, lo = stack.pop()
                if lo:
                    htmlbuf.append("</li>")
                htmlbuf.append("</%s>" % t)
            out.append("".join(htmlbuf))
            continue

        # raw HTML block: a line that opens with a tag
        if RAW_BLOCK.match(line):
            buf = []
            while i < n:
                buf.append(lines[i])
                i += 1
                if lines[i - 1].rstrip().endswith(("</div>", "</p>", "</table>", "</ul>")):
                    break
            out.append("\n".join(buf))
            continue

        # paragraph
        if line.strip() == "":
            i += 1
            continue
        buf = []
        while i < n and lines[i].strip() != "":
            if re.match(r"^(#{1,4})\s+", lines[i]):
                break
            if lines[i].startswith("```"):
                break
            if lines[i].strip().startswith("|"):
                break
            if re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                break
            if RAW_BLOCK.match(lines[i]):
                break
            buf.append(lines[i].strip())
            i += 1
        para = " ".join(buf)
        out.append("<p>%s</p>" % inline(para))

    return "\n".join(out)


# ------------------------------------------------------------------- pages

PAGE_TPL = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>CryNet - Two-Cot Dossier</title>
<style>
@page {
  size: A4; margin: 20mm 16mm 18mm 16mm;
  @bottom-center { content: counter(page) " / " counter(pages);
                   font-family: "Segoe UI", Arial, sans-serif; font-size: 8.5pt; color: #7c8a89; }
  @top-left { content: string(running); font-family: "Segoe UI", Arial, sans-serif;
              font-size: 8pt; color: #9aa8a7; letter-spacing:.04em; }
  @top-right { content: "CryNet - Two-Cot Dossier"; font-family: "Segoe UI", Arial, sans-serif;
               font-size: 8pt; color: #9aa8a7; }
}
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: Georgia, "Times New Roman", serif; font-size: 10.2pt; line-height: 1.52;
       color: #1b2422; margin: 0; }
h1 { string-set: running content(); font-family: "Segoe UI", Arial, sans-serif; font-size: 22pt;
     color: #0f3b3a; margin: 0 0 14pt 0; padding-bottom: 6pt; border-bottom: 2.5pt solid #2dd4bf;
     page-break-before: always; page-break-after: avoid; }
h1.no-break { page-break-before: avoid; }
h2 { font-family: "Segoe UI", Arial, sans-serif; font-size: 14pt; color: #114a48; margin: 20pt 0 7pt 0;
     page-break-after: avoid; }
h3 { font-family: "Segoe UI", Arial, sans-serif; font-size: 11.4pt; color: #1d5f5c; margin: 14pt 0 5pt 0;
     page-break-after: avoid; }
h4 { font-family: "Segoe UI", Arial, sans-serif; font-size: 10.4pt; color: #33413f; margin: 11pt 0 4pt 0;
     page-break-after: avoid; }
p { margin: 0 0 8pt 0; text-align: justify; hyphens: auto; }
ul, ol { margin: 0 0 9pt 0; padding-left: 18pt; }
li { margin: 0 0 3.5pt 0; text-align: left; }
li > ul, li > ol { margin-top: 3.5pt; }
code { font-family: Consolas, "Courier New", monospace; font-size: 8.7pt; background: #eef3f2;
       padding: 0.5pt 2.5pt; border-radius: 2pt; color: #0d3f3d; }
pre.code { background: #f4f7f6; border: 0.5pt solid #cfdbd9; border-left: 2.5pt solid #2dd4bf;
           padding: 7pt 9pt; margin: 0 0 10pt 0; overflow-wrap: break-word; white-space: pre-wrap;
           page-break-inside: avoid; }
pre.code code { background: none; padding: 0; font-size: 8.1pt; color: #17211f; }
pre.listing { background: #f7f9f9; border: 0.5pt solid #d3dedc; padding: 6pt 8pt; margin: 0 0 9pt 0;
               font-family: Consolas, "Courier New", monospace; font-size: 6.6pt; line-height: 1.30;
               white-space: pre-wrap; overflow-wrap: break-word; page-break-inside: auto; }
pre.listing .ln { color: #9fb0ae; }
h3.file { font-family: Consolas, "Courier New", monospace; font-size: 9.2pt; color: #0f3b3a;
          background: #e8f1f0; border-left: 2.5pt solid #2dd4bf; padding: 3pt 6pt; margin: 14pt 0 5pt 0; }
table { border-collapse: collapse; width: 100%; margin: 0 0 11pt 0; font-size: 8.7pt;
        page-break-inside: avoid; font-family: "Segoe UI", Arial, sans-serif; }
th { background: #0f3b3a; color: #f2f7f6; text-align: left; padding: 4pt 5pt; font-weight: 600;
     border: 0.4pt solid #0f3b3a; }
td { padding: 3.4pt 5pt; border: 0.4pt solid #cfdbd9; vertical-align: top; }
tbody tr:nth-child(even) { background: #f3f7f6; }
blockquote { border-left: 2.5pt solid #2dd4bf; background: #f2f8f7; margin: 0 0 10pt 0;
             padding: 6pt 10pt; font-size: 9.4pt; color: #24423f; }
blockquote p { margin: 0; }
hr { border: none; border-top: 0.6pt solid #cfdbd9; margin: 12pt 0; }
.pagebreak { page-break-after: always; }
a { color: #0f6f6b; text-decoration: none; }
.cover { page-break-after: always; text-align: left; }
.cover h1 { page-break-before: avoid; border: none; font-size: 30pt; color: #0f3b3a;
           margin-bottom: 3pt; padding-bottom: 2pt; }
.cover .sub { font-family: "Segoe UI", Arial, sans-serif; font-size: 12.5pt; color: #2b7a77; margin-bottom: 8pt; }
.cover .meta { font-family: "Segoe UI", Arial, sans-serif; font-size: 9.6pt; color: #4a5c5a; }
.cover .meta td { border: none; padding: 1.0pt 0; }
.cover table { font-size: 9.6pt; }
.toc { font-family: "Segoe UI", Arial, sans-serif; font-size: 9.4pt; }
.toc ol { list-style: none; padding-left: 0; }
.toc > ol > li { margin-bottom: 5pt; font-weight: 600; }
.toc ul { list-style: none; padding-left: 15pt; font-size: 8.8pt; color: #40514f;
         font-weight: 400; margin-top: 2pt; }
.toc ul li { margin-bottom: 1.6pt; }
.toc li { page-break-inside: avoid; }
.toc a { color: #16211f; display: block; position: relative; padding-right: 34pt; }
.toc ul a { color: #40514f; }
.toc .pg { position: absolute; right: 0; top: 0; width: 30pt; text-align: right;
           overflow: hidden; white-space: nowrap; color: #2b7a77;
           font-variant-numeric: tabular-nums; }
.lede { font-size: 10.4pt; color: #33423f; }
.cover p { margin-bottom: 4pt; }
.cover h2 { margin: 8pt 0 3pt 0; font-size: 12.5pt; }
.cover ul { margin-bottom: 4pt; }
.kv { font-family: "Segoe UI", Arial, sans-serif; }
.small { font-size: 8.8pt; color: #4a5c5a; }
</style></head><body>
{{BODY}}
</body></html>
"""


def build_toc(chapters: list[tuple[str, str]]) -> str:
    """chapters: list of (filename, html) - build a linked table of contents."""
    items = []
    for fname, htm in chapters:
        m = re.search(r'<h1[^>]*id="([^"]+)"[^>]*>(.*?)</h1>', htm, re.S)
        if not m:
            continue
        ident = m.group(1)
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        subs = []
        for h2m in re.finditer(
            r'<h2 id="([^"]+)">(.*?)</h2>', htm, re.S
        ):
            st = re.sub(r"<[^>]+>", "", h2m.group(2)).strip()
            subs.append(
                '<li><a href="#%s">%s<span class="pg">@@%s@@</span></a></li>'
                % (h2m.group(1), st, h2m.group(1))
            )
        subhtml = "<ul>%s</ul>" % "".join(subs) if subs else ""
        items.append(
            '<li><a href="#%s">%s<span class="pg">@@%s@@</span></a>%s</li>'
            % (ident, title, ident, subhtml)
        )
    return (
        '<div class="toc"><h1 class="no-break">Contents</h1>'
        "<ol>%s</ol></div>" % "".join(items)
    )


def listing(path: str, numbered: bool = True) -> str:
    """One source file, verbatim, as a paginated listing with line numbers."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read().replace("\r\n", "\n").rstrip("\n")
    lines = text.split("\n")
    if numbered:
        body = "\n".join(
            '<span class="ln">%4d</span>  %s' % (i + 1, html.escape(l))
            for i, l in enumerate(lines)
        )
    else:
        body = html.escape(text)
    rel = os.path.relpath(path, REPO).replace("\\", "/")
    return (
        '<h3 class="file">%s</h3>\n<p class="small">%d lines &middot; %s bytes</p>\n'
        '<pre class="listing">%s</pre>\n'
        % (html.escape(rel), len(lines), f"{os.path.getsize(path):,}", body)
    )


def build_appendix(manifest: str, title: str, anchor: str, lede: str) -> str:
    """Embed a list of files (one repo-relative path per line) verbatim."""
    p = os.path.join(CHAPTERS, manifest)
    if not os.path.exists(p):
        return ""
    # The anchor goes on the h1 itself.  A separate empty <a> element would
    # be laid out at the end of the *previous* page, so every link to it
    # would land one page short of the chapter it names.
    parts = [
        '<h1 id="%s">%s</h1>\n<p class="lede">%s</p>\n'
        % (anchor, title, lede)
    ]
    total = 0
    for raw in open(p, encoding="utf-8"):
        line = raw.strip()
        if not line or line.startswith("#!"):
            continue
        if line.startswith("#"):
            parts.append("<h2>%s</h2>\n" % html.escape(line.lstrip("#").strip()))
            continue
        fp = os.path.join(REPO, line.replace("/", os.sep))
        if not os.path.exists(fp):
            parts.append('<p class="small">missing: %s</p>\n' % html.escape(line))
            continue
        parts.append(listing(fp))
        total += 1
    parts.insert(1, '<p class="small">%d files reproduced in full.</p>\n' % total)
    return "".join(parts)


def render(page: str) -> bool:
    """Write the HTML and print it to PDF with headless Edge."""
    with open(OUT_HTML, "w", encoding="utf-8") as fh:
        fh.write(page)
    cmd = [
        EDGE,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        "--print-to-pdf=" + OUT_PDF,
        "file:///" + OUT_HTML.replace("\\", "/"),
    ]
    subprocess.run(cmd, check=False, capture_output=True)
    return os.path.exists(OUT_PDF)


def heading_lines(doc) -> list[list[tuple[float, str]]]:
    """Per page, every text line as (largest span size, normalised text).

    The contents list repeats every chapter title, so a plain text search
    finds the TOC page first.  Only a *heading* line counts: h1 is 22pt and
    h2 is 14pt, while TOC entries are 9.4pt and 8.8pt.
    """
    heads: list[list[tuple[float, str]]] = []
    for i in range(doc.page_count):
        lines: list[tuple[float, str]] = []
        for b in doc[i].get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                txt = re.sub(r"\s+", " ",
                             "".join(sp["text"] for sp in ln["spans"])).strip()
                if txt:
                    lines.append((max(sp["size"] for sp in ln["spans"]), txt))
        heads.append(lines)
    return heads


def find_heading(heads, needle: str, size_min: float, start: int, end: int):
    needle = re.sub(r"\s+", " ", needle).strip()
    if not needle:
        return None
    for pno in range(start, end):
        for size, txt in heads[pno]:
            if size > size_min and needle in txt:
                return pno
    return None


def outline(chapters, heads, npages: int):
    """Bookmark tree plus an anchor -> page map for the contents list."""
    marks: list[list] = []
    pages: dict[str, int] = {}
    start = 0
    for fname, htm in chapters:
        m = re.search(r'<h1[^>]*id="([^"]+)"[^>]*>(.*?)</h1>', htm, re.S)
        if not m:
            m2 = re.search(r"<h1[^>]*>(.*?)</h1>", htm, re.S)
            if not m2:
                continue
            ident, inner = "", m2.group(1)
        else:
            ident, inner = m.group(1), m.group(2)
        title = html.unescape(re.sub(r"<[^>]+>", "", inner).strip())
        needle = title.split("—")[0].strip()
        found = find_heading(heads, needle, 15.0, start, npages)
        if found is None:
            continue
        start = found
        marks.append([1, title, found + 1])
        if ident:
            pages[ident] = found + 1
        for h2 in re.finditer(r'<h2 id="([^"]+)">(.*?)</h2>', htm, re.S):
            st = html.unescape(re.sub(r"<[^>]+>", "", h2.group(2)).strip())
            sub = find_heading(heads, st, 12.0, found, min(found + 80, npages))
            if sub is not None:
                marks.append([2, st, sub + 1])
                pages[h2.group(1)] = sub + 1
    return marks, pages


def main() -> int:
    order_file = os.path.join(CHAPTERS, "ORDER")
    if os.path.exists(order_file):
        names = [
            l.strip()
            for l in open(order_file, encoding="utf-8")
            if l.strip() and not l.startswith("#")
        ]
    else:
        names = sorted(
            f for f in os.listdir(CHAPTERS) if f.endswith(".md")
        )

    chapters = []
    for n in names:
        p = os.path.join(CHAPTERS, n)
        with open(p, encoding="utf-8") as fh:
            htm = md_to_html(fh.read())
        m = re.match(r"^\d+", n)
        if m and not n.startswith("00"):
            anchor = "chapter-%s" % m.group(0)
            htm, nsub = re.subn(
                r'<h1([^>]*)id="[^"]*"', r'<h1\1id="%s"' % anchor, htm, count=1
            )
            if nsub == 0:  # a chapter whose h1 carries no id yet
                htm = re.sub(
                    r"<h1([^>]*)>", r'<h1\1 id="%s">' % anchor, htm, count=1
                )
            # Sub-heading anchors must be unique across the whole document.
            # Two chapters have a "## Build", two have a "## Why this chapter
            # exists", and one slug collides a third time -- and a duplicate
            # id makes the second contents row jump to the *first* heading
            # of the same name.  Prefixing with the chapter keeps every
            # contents row on its own heading.
            htm = re.sub(
                r'<h([23]) id="([^"]+)"',
                lambda mm: '<h%s id="%s-%s"' % (mm.group(1), anchor, mm.group(2)),
                htm,
            )
        chapters.append((n, htm))

    chapters.append(
        ("A-docs", build_appendix(
            "APPENDIX_DOCS",
            "Appendix A &mdash; The project record, verbatim",
            "appendix-a",
            "The repository's own documents, reproduced in full and unedited. "
            "Every D-n decision, every I-n issue, the wiring, the bill of materials, "
            "the bench runbook, the flashing guides and the handoff briefing are here "
            "exactly as they are in the tree, so that the narrative chapters can be "
            "checked against the primary record rather than taken on trust. Where a "
            "document is out of date, Chapter 18 says which one and why."))
    )
    chapters.append(
        ("B-src", build_appendix(
            "APPENDIX_SRC",
            "Appendix B &mdash; Complete first-party source listings",
            "appendix-b",
            "Every line of first-party code in the system, with line numbers, "
            "reproduced verbatim from the working tree: the hub's seven components "
            "and its application, the cot node sketch, the wearable sketch and the "
            "motor's bench sketch, the training pipeline, the evaluation scripts, "
            "the host tools and the record that guards the shipped offline images. "
            "Third-party code (TensorFlow Lite Micro, ESP-NN, NimBLE, ESP-IDF, "
            "Arduino) is not reproduced &mdash; it is fetched by the build. "
            "The 8,604-line generated model array "
            "<code>crynet_model/include/model_data.h</code> is omitted as pure "
            "data; it is regenerated from the INT8 artefact by the export cell."))
    )

    toc = build_toc(chapters[1:])
    cover = chapters[0][1] if chapters else ""
    rest = "\n".join(h for _, h in chapters[1:])
    body = cover + "\n" + toc + "\n" + rest
    page = PAGE_TPL.replace("{{BODY}}", body)

    if not os.path.exists(EDGE):
        print("edge not found at %s" % EDGE)
        return 2

    # Pass 1: print with placeholder page numbers.  The number box is a
    # fixed 30pt wide and absolutely positioned, so filling it in cannot
    # change the pagination -- pass 2 lands every heading on the same page.
    if not render(page):
        print("pdf was not produced")
        return 3

    marks: list[list] = []
    try:
        import pymupdf

        doc = pymupdf.open(OUT_PDF)
        heads = heading_lines(doc)
        marks, pages = outline(chapters, heads, doc.page_count)
        npages = doc.page_count
        doc.close()

        filled = re.sub(r"@@([a-z0-9-]+)@@",
                        lambda m: str(pages.get(m.group(1), "")), page)
        if filled != page:
            page = filled
            if not render(page):
                print("second pass failed; keeping the first")
            else:
                doc = pymupdf.open(OUT_PDF)
                if doc.page_count != npages:
                    heads = heading_lines(doc)
                    marks, _ = outline(chapters, heads, doc.page_count)
                doc.close()
        print("html  : %s (%.1f KB)" % (OUT_HTML, len(page) / 1024))
    except Exception as exc:  # pragma: no cover
        print("page-number step skipped: %s" % exc)

    # Bookmarks with real page numbers.  A 448-page document without an
    # outline is not navigable, so this is worth the extra pass.
    try:
        import pymupdf

        doc = pymupdf.open(OUT_PDF)
        if not marks:
            heads = heading_lines(doc)
            marks, _ = outline(chapters, heads, doc.page_count)
        if marks:
            doc.set_toc(marks)
        doc.set_metadata({
            "title": "CryNet - Infant Cry Detection - Two-Cot System - Full Project Dossier",
            "author": "CryNet project",
            "subject": "Complete breakdown of the CryNet two-cot system: "
                       "research, model, firmware, protocol, hardware, decisions",
            "keywords": "CryNet, ESP32, ESP-NOW, infant cry detection, TFLite Micro, two cot nodes",
        })
        doc.saveIncr()
        doc.close()
        print("pdf   : %s" % OUT_PDF)
    except Exception as exc:  # pragma: no cover
        print("bookmark step skipped: %s" % exc)

    try:
        from pypdf import PdfReader

        reader = PdfReader(OUT_PDF)
        print("pages : %d" % len(reader.pages))
        print("size  : %.1f MB" % (os.path.getsize(OUT_PDF) / 1048576))
        # pypdf's outline list counts only the *top level* of a nested tree,
        # so it under-reports the real number of bookmarks.  pymupdf's
        # get_toc() returns every entry.
        import pymupdf

        _d = pymupdf.open(OUT_PDF)
        _t = _d.get_toc()
        _d.close()
        print("marks : %d (%d top level, %d sub)"
              % (len(_t), sum(1 for b in _t if b[0] == 1),
                 sum(1 for b in _t if b[0] == 2)))
    except Exception as exc:  # pragma: no cover
        print("page count skipped: %s" % exc)

    return 0


if __name__ == "__main__":
    sys.exit(main())
