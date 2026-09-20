"""Harness CLI entry point."""

from __future__ import annotations

import typer

from harness_cli.commands.build import build
from harness_cli.commands.deploy import deploy
from harness_cli.commands.dev import dev
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
app.command(name="dev")(dev)
app.command(name="deploy")(deploy)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
