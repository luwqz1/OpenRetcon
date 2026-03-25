from __future__ import annotations

try:
    import typer
except ImportError:
    raise RuntimeError(
        "typer is not installed for CLI application.\n* hint: pip install saronia[cli]",
    ) from None

from retcon.cli.generate import generate_app

app = typer.Typer(
    name="retcon",
    help="OpenRetcon — OpenAPI code generation toolkit.",
    no_args_is_help=True,
)
app.add_typer(generate_app, name="generate")


def main() -> None:
    app()


__all__ = ("app", "main")
