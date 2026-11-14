"""Formats the items collected by js/read_page.js as text for Claude.

Compact mode (default) keeps the text short:
- links are shown relative to the page's site (`-> /product-d123.htm`),
- an image link without a label is dropped when the same URL also appears with a label,
- buttons/links whose label repeats many times ("Do košíku", "Porovnat", ...) are hidden after
  the first one; they keep their number, so they can still be highlighted,
- long text lines that repeat many times (delivery notes etc.) are shown once.
A footer says what was hidden. Full mode shows everything.
"""

from collections import Counter
from urllib.parse import urlsplit

REPEAT_LIMIT = 4  # a label / line seen this many times or more counts as repeated
LONG_LINE = 25  # only text lines at least this long are deduplicated


def _short_href(href: str, page_url: str) -> str:
    if not href:
        return ""
    target, page = urlsplit(href), urlsplit(page_url)
    if target.scheme in ("http", "https") and target.netloc == page.netloc:
        rest = target.path or "/"
        if target.query:
            rest += "?" + target.query
        if target.fragment:
            rest += "#" + target.fragment
        return rest
    return href


def _element_line(item: dict, href: str) -> str:
    line = f'[{item["id"]}] {item["kind"]} "{item.get("label", "")}"{item.get("extra", "")}'
    if href:
        line += f" -> {href}"
    return line


def format_page(page: dict, full: bool = False) -> str:
    items = page.get("items") or []
    url = page.get("url", "")
    if full:
        lines = []
        for item in items:
            if item["t"] == "el":
                lines.append(_element_line(item, item.get("href", "")))
            elif item["t"] == "h":
                lines.append("#" * item["level"] + " " + item["s"])
            else:
                lines.append(item["s"])
        return "\n".join(l for i, l in enumerate(lines) if l != (lines[i - 1] if i else None))

    labelled_hrefs = {i.get("href") for i in items if i["t"] == "el" and i.get("label") and i.get("href")}
    label_counts = Counter(
        (i["kind"], i.get("label", "")) for i in items if i["t"] == "el" and i.get("label") and not i.get("href")
    )
    text_counts = Counter(i["s"] for i in items if i["t"] == "text" and len(i["s"]) >= LONG_LINE)

    lines: list[str] = []
    hidden_elements: Counter = Counter()
    hidden_text: Counter = Counter()
    shown_labels: set = set()
    shown_text: set = set()
    dropped_image_links = 0

    for item in items:
        if item["t"] == "el":
            href = item.get("href", "")
            label = item.get("label", "")
            if not label and href and href in labelled_hrefs:
                dropped_image_links += 1
                continue
            key = (item["kind"], label)
            if label and not href and label_counts[key] >= REPEAT_LIMIT:
                if key in shown_labels:
                    hidden_elements[key] += 1
                    continue
                shown_labels.add(key)
            line = _element_line(item, _short_href(href, url))
        elif item["t"] == "h":
            line = "#" * item["level"] + " " + item["s"]
        else:
            s = item["s"]
            if text_counts[s] >= REPEAT_LIMIT:
                if s in shown_text:
                    hidden_text[s] += 1
                    continue
                shown_text.add(s)
            line = s
        if not lines or lines[-1] != line:
            lines.append(line)

    notes = []
    if hidden_elements:
        parts = ", ".join(f'{kind} "{label}" ×{n}' for (kind, label), n in hidden_elements.most_common())
        notes.append(f"repeated elements hidden after the first: {parts}")
    if hidden_text:
        parts = ", ".join(f'"{s[:50]}" ×{n}' for s, n in hidden_text.most_common())
        notes.append(f"repeated lines hidden: {parts}")
    if dropped_image_links:
        notes.append(f"{dropped_image_links} unlabelled links that duplicate a labelled one")
    if notes:
        lines.append("")
        lines.append("[compact view: " + "; ".join(notes) + ". read_page(full=True) shows everything; "
                     "relative links are on " + (urlsplit(url).netloc or "this site") + "]")
    return "\n".join(lines)
