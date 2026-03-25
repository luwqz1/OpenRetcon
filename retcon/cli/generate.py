from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

generate_app = typer.Typer(
    name="generate",
    help="Generate client code from an OpenAPI schema.",
    no_args_is_help=True,
)


def _read_schema(source: str) -> bytes:
    if source.startswith("http://") or source.startswith("https://"):
        try:
            import urllib.request

            with urllib.request.urlopen(source) as resp:  # noqa: S310
                return resp.read()
        except Exception as exc:
            typer.echo(f"error: failed to fetch {source!r}: {exc}", err=True)
            raise typer.Exit(1) from exc

    path = Path(source)

    if not path.exists():
        typer.echo(f"error: file not found: {path}", err=True)
        raise typer.Exit(1)

    return path.read_bytes()


def _write_files(files: dict[str, str], output_dir: Path) -> None:
    for rel_path, content in files.items():
        dest = output_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        typer.echo(f"  wrote {dest}")


@generate_app.command("python")
def generate_python(
    schema: Annotated[
        str,
        typer.Argument(
            metavar="SCHEMA",
            help="Path to a local OpenAPI JSON file, or an HTTP(S) URL.",
        ),
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            metavar="DIR",
            help="Directory to write the generated files into. Defaults to current path + /api directory.",
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("./api"),
    api_module_name: Annotated[
        str,
        typer.Option(
            "--api",
            "-a",
            metavar="NAME",
            help="Name for the API endpoint variable and module file. Defaults to output directory name or 'api'.",
        ),
    ] = "api",
    fmt: Annotated[
        bool,
        typer.Option(
            "--fmt/--no-fmt",
            help="Run ruff import-sorting and formatting on generated files (requires ruff).",
        ),
    ] = True,
) -> None:
    """Generate a Python (saronia controllers + msgspex models) from SCHEMA."""

    try:
        from retcon.generators.python import PythonGenerator
        from retcon.schema.pipeline import run_generation_pipeline
    except ImportError as exc:
        typer.echo(
            f'error: Python generator dependencies are not installed.\nInstall them with:  pip install "openretcon[py]"\n\n{exc}',
            err=True,
        )
        raise typer.Exit(1) from exc

    if not schema.endswith(".json") and not schema.endswith(".yaml"):
        typer.echo("Only json or yaml schema supported.")
        raise typer.Exit(1)

    raw = _read_schema(schema)

    try:
        result = run_generation_pipeline(
            raw,
            PythonGenerator(fmt=fmt, module_name=api_module_name),
            document_type="json" if schema.endswith(".json") else "yaml",
        )
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc

    output.mkdir(parents=True, exist_ok=True)
    typer.echo(f"Generating Python client → {output}/")
    _write_files(result.files, output)
    typer.echo(f"Done. {len(result.files)} file(s) written.")


@generate_app.command("rust")
def generate_rust(
    schema: Annotated[
        str,
        typer.Argument(
            metavar="SCHEMA",
            help="Path to a local OpenAPI JSON file, or an HTTP(S) URL.",
        ),
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            metavar="DIR",
            help="Directory to write the generated files into.",
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    fmt: Annotated[
        bool,
        typer.Option(
            "--fmt/--no-fmt",
            help="Run rust formatter on generated files.",
        ),
    ] = True,
) -> None:
    """(WIP) Generate a Rust controllers and models from SCHEMA."""

    from retcon.generators.rust import RustGenerator
    from retcon.schema.pipeline import run_generation_pipeline

    raise NotImplementedError


__all__ = ("generate_app",)
