"""Helpers for instructions shown in the panel (no Qt)."""

import re

# "text", „text“, “text”, «text», 'text' (single quotes only at word edges, so "can't" is ignored)
_QUOTED = re.compile(r'"([^"]+)"|„([^“”"]+)[“”"]|“([^”]+)”|«([^»]+)»|(?<!\w)\'([^\']+)\'(?!\w)')

STATUS_FOR_EVENT = {
    "page_loaded": "✓ Page change detected, Claude is on it",
    "done": "✓ Done sent to Claude",
    "cant": "✓ Sent to Claude",
    "reply": "✓ Reply sent to Claude",
}


def copy_text_for(instruction: str) -> str:
    """What the Copy button copies: the first quoted part of the instruction, if any."""
    m = _QUOTED.search(instruction)
    if not m:
        return ""
    return next(g for g in m.groups() if g is not None).strip()
