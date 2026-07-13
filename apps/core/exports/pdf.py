"""PDF rendering via weasyprint (HTML → PDF bytes).

Each module provides a Django template; this helper renders it to bytes.
"""

import os
import sys


class PdfRenderError(Exception):
    """Raised when HTML cannot be rendered to PDF bytes."""


def _ensure_macos_pango_loadable() -> None:
    """On macOS dev machines, Homebrew's Pango/Cairo libs aren't on the default
    dlopen search path. Linux (Docker/prod) resolves them via ldconfig, so this
    is a no-op there."""
    if sys.platform == "darwin" and "DYLD_LIBRARY_PATH" not in os.environ:
        for prefix in ("/opt/homebrew/lib", "/usr/local/lib"):
            if os.path.isdir(prefix):
                os.environ["DYLD_LIBRARY_PATH"] = prefix
                break


def render_pdf(html_string: str) -> bytes:
    _ensure_macos_pango_loadable()
    try:
        from weasyprint import HTML  # lazy import — needs libpango at import time
        return HTML(string=html_string).write_pdf()
    except Exception as exc:
        raise PdfRenderError(str(exc)) from exc
