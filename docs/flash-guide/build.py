#!/usr/bin/env python
"""Print the offline flashing guide to PDF with headless Edge.

    python docs/flash-guide/build.py

The guide is one hand-written HTML file; this script only prints it.  The same
pipeline as docs/dossier/build.py, minus the markdown, the contents list and
the bookmarks -- the guide is short enough to navigate without an outline.
"""

from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "CryNet-Offline-Flashing-Guide.html")
OUT_PDF = os.path.join(HERE, "CryNet-Offline-Flashing-Guide.pdf")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def main() -> int:
    if not os.path.exists(EDGE):
        print("edge not found at %s" % EDGE)
        return 2
    subprocess.run(
        [EDGE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
         "--print-to-pdf=" + OUT_PDF, "file:///" + SRC.replace("\\", "/")],
        check=False, capture_output=True)
    if not os.path.exists(OUT_PDF):
        print("pdf was not produced")
        return 3
    try:
        from pypdf import PdfReader
        print("pdf   : %s (%.1f MB, %d pages)"
              % (OUT_PDF, os.path.getsize(OUT_PDF) / 1048576,
                 len(PdfReader(OUT_PDF).pages)))
    except ImportError:
        print("pdf   : %s" % OUT_PDF)
    return 0


if __name__ == "__main__":
    sys.exit(main())
