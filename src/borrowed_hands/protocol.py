"""Wire format between client and window: one JSON object per line, one request per connection."""

import json

MAX_PAGE_CHARS = 60_000


def encode(msg: dict) -> bytes:
    return (json.dumps(msg, ensure_ascii=False) + "\n").encode()


def decode(line: bytes | str) -> dict:
    if isinstance(line, bytes):
        line = line.decode()
    msg = json.loads(line)
    if not isinstance(msg, dict):
        raise ValueError("message must be a JSON object")
    return msg


def truncate_page(text: str, limit: int = MAX_PAGE_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [truncated, {len(text) - limit} more characters]"
