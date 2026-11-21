"""The `autostorage` command: `autostorage view`."""

import argparse
import webbrowser


def main(argv: list[str] | None = None) -> None:
    """Run the `autostorage` command."""
    parser = argparse.ArgumentParser(prog="autostorage")
    commands = parser.add_subparsers(dest="command", required=True)
    view = commands.add_parser("view", help="Open the browser GUI.")
    view.add_argument("--port", type=int, default=8765)
    view.add_argument("--no-browser", action="store_true", help="Don't open a browser.")
    args = parser.parse_args(argv)

    import uvicorn  # noqa: PLC0415 (only installed with the `gui` extra)

    from .app import create_app  # noqa: PLC0415

    url = f"http://127.0.0.1:{args.port}"
    print(f"Serving at {url}", flush=True)  # noqa: T201
    if not args.no_browser:
        webbrowser.open(url)
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port)
