from __future__ import annotations

import typer

from retcon.cli.generate import generate_app

app = typer.Typer(
    name="retcon",
    help="OpenRetcon — OpenAPI code generation toolkit.",
    no_args_is_help=True,
)
app.add_typer(generate_app, name="generate")


def main() -> None:
    app()


if __name__ == "__main__":
    main()


__all__ = ("app", "main")
