"""CLI test helpers."""

from __future__ import annotations

import re

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def squeeze(text: str) -> str:
    """Strips ANSI escape codes and collapses whitespace, so substring
    checks don't depend on the environment's terminal/color detection.

    Typer/Rich renders CLI errors in a bordered box, word-wrapped to the
    detected terminal width and, in some environments (observed on a
    GitHub Actions runner but not locally), with ANSI styling applied
    per-token — splitting a flag like "--push" into separately-styled
    "-" and "-push" runs, e.g. "\\x1b[1m-\\x1b[0m\\x1b[1m-push\\x1b[0m".
    That breaks a plain substring check even though the rendered text
    reads identically; passing NO_COLOR to the CliRunner's invoke() env
    only suppressed color, not the bold/dim styling causing the split.
    Stripping ANSI codes first, then normalizing whitespace, makes the
    check robust to both wrap width and styling differences.
    """
    return " ".join(_ANSI_ESCAPE.sub("", text).split())
