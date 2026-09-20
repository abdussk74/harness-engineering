"""Harness CLI entry point."""

from __future__ import annotations

import typer

from harness_cli.commands.doctor import doctor

app = typer.Typer(
    name="harness",
    help="Zero-ops control plane for A2A agents.",
    no_args_is_help=True,
)


@app.callback()
def _callback() -> None:
    """Zero-ops control plane for A2A agents.

    A dedicated callback keeps Typer in subcommand mode (`harness doctor`)
    instead of collapsing to a single implicit command while `doctor` is
    still the only one registered.
    """


app.command(name="doctor")(doctor)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
