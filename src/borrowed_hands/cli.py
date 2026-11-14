"""Borrowed Hands: drive the browser window from the command line."""

import argparse
import json
import sys

from borrowed_hands import __version__, client


def _print(result: dict) -> int:
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hands", description=__doc__)
    parser.add_argument("--version", action="version", version=f"hands {__version__}")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("open", help="open the window (or navigate it) to a URL")
    p.add_argument("url")
    p = sub.add_parser("say", help="show an instruction in the panel")
    p.add_argument("text")
    p.add_argument("-e", "--element", type=int, help="highlight element N from the last read")
    p = sub.add_parser("read", help="print the current page as text")
    p.add_argument("--json", action="store_true", help="print the full JSON reply")
    p.add_argument("--full", action="store_true", help="don't hide repeated elements")
    p = sub.add_parser("wait", help="wait for progress (page load, Done, reply, timeout)")
    p.add_argument("-t", "--timeout", type=float, default=50.0)
    p = sub.add_parser("navigate", help="load a URL in the open window")
    p.add_argument("url")
    sub.add_parser("close", help="close the window")
    sub.add_parser("status", help="is the window open?")
    sub.add_parser("mcp", help="run the MCP server (stdio) for Claude Code")

    args = parser.parse_args(argv)
    try:
        match args.command:
            case "open":
                return _print(client.open_window(args.url))
            case "say":
                return _print(client.say(args.text, args.element))
            case "read":
                result = client.read(args.full)
                if args.json or not result.get("ok"):
                    return _print(result)
                page = result["page"]
                print(f"{page['title']}\n{page['url']}\n\n{page['text']}")
                return 0
            case "wait":
                return _print(client.wait(args.timeout))
            case "navigate":
                return _print(client.navigate(args.url))
            case "close":
                return _print(client.close())
            case "mcp":
                from borrowed_hands import mcp_server

                mcp_server.main()
                return 0
            case "status":
                running = client.is_running()
                print("open" if running else "closed")
                return 0 if running else 1
            case _:
                parser.print_help()
                return 0
    except client.NotRunning:
        print("The window is not open. Start it with: hands open <url>", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
