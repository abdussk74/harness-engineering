"""Harness CLI entry point."""

from __future__ import annotations

import typer

from harness_cli.commands.build import build
from harness_cli.commands.doctor import doctor

app = typer.Typer(
    name="harness",
    help="Zero-ops control plane for A2A agents.",
    no_args_is_help=True,
)


@app.callback()
def _callback() -> None:
    """Zero-ops control plane for A2A agents."""


app.command(name="doctor")(doctor)
app.command(name="build")(build)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
