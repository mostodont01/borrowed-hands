import pytest

from borrowed_hands.instruction import copy_text_for


@pytest.mark.parametrize(
    "instruction, expected",
    [
        ('Type "esperanza vr box" into the search box and press Enter.', "esperanza vr box"),
        ("Search for 'USB WiFi dongle'", "USB WiFi dongle"),
        ("Napiš „wifi usb adaptér“ do hledání", "wifi usb adaptér"),
        ("Type “tp-link” please", "tp-link"),
        ("Click the highlighted button, then click Done.", ""),
        ("If you can't find it, click Can't do it", ""),
        ('Type "first" then "second"', "first"),
    ],
)
def test_copy_text_for(instruction, expected):
    assert copy_text_for(instruction) == expected
