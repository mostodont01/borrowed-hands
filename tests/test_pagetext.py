from borrowed_hands.pagetext import format_page

URL = "https://www.alza.cz/search?q=x"


def el(i, kind, label, href="", extra=""):
    return {"t": "el", "id": i, "kind": kind, "label": label, "href": href, "extra": extra}


def text(s):
    return {"t": "text", "s": s}


def product(n, start):
    href = f"https://www.alza.cz/product-{n}.htm"
    return [
        el(start, "link", "", href),  # image link
        el(start + 1, "button", "Porovnat"),
        el(start + 2, "link", f"Product {n}", href),
        text("Do půlnoci objednáš, ráno v AlzaBoxu máš."),
        text("Skladem"),
    ]


def page(items):
    return {"url": URL, "title": "t", "items": items}


ITEMS = [{"t": "h", "level": 1, "s": "Results"}] + [x for n in range(5) for x in product(n, 1 + n * 3)]


def test_compact_hides_repeats_and_keeps_numbers():
    out = format_page(page(ITEMS))
    assert "# Results" in out
    assert out.count('button "Porovnat"') == 2  # first one + the footer
    assert '[2] button "Porovnat"' in out
    assert out.count("Do půlnoci objednáš") == 2  # first one + the footer
    assert out.count("\nSkladem") == 5  # short lines are kept
    for n in range(5):
        assert f'"Product {n}" -> /product-{n}.htm' in out
    assert 'link ""' not in out  # image links dropped
    assert '"Porovnat" ×4' in out and "5 unlabelled links" in out
    assert "read_page(full=True)" in out


def test_full_shows_everything():
    out = format_page(page(ITEMS), full=True)
    assert out.count('button "Porovnat"') == 5
    assert "https://www.alza.cz/product-3.htm" in out
    assert "compact view" not in out


def test_other_site_links_stay_absolute():
    out = format_page(page([el(1, "link", "Slovakia", "https://www.alza.sk/x.htm")]))
    assert "-> https://www.alza.sk/x.htm" in out


def test_unlabelled_link_kept_when_unique():
    out = format_page(page([el(1, "link", "", "https://www.alza.cz/only.htm")]))
    assert '[1] link "" -> /only.htm' in out


def test_few_repeats_not_hidden():
    items = [el(i, "button", "Do košíku") for i in range(1, 4)]
    out = format_page(page(items))
    assert out.count("Do košíku") == 3 and "compact view" not in out


def test_compact_is_much_shorter():
    many = [x for n in range(30) for x in product(n, 1 + n * 3)]
    assert len(format_page(page(many))) < 0.6 * len(format_page(page(many), full=True))


def test_rating_lines_with_digits_are_kept():
    items = [x for n in range(6) for x in (text("Hodnocení: 5,0 z 5 na základě 1 recenzí"), text(f"Product {n}"))]
    assert format_page(page(items)).count("Hodnocení") == 6
