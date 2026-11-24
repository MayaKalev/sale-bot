from datetime import date

import pytest

from salebot.bot import texts

TODAY = date(2026, 11, 24)  # Tuesday


@pytest.mark.parametrize("value,expected", [(399, "₪399"), (399.0, "₪399"), (249.9, "₪249.90"),
                                            (1299.5, "₪1,299.50"), (20, "₪20")])
def test_format_price(value, expected):
    assert texts.format_price(value) == expected


def test_format_price_other_currency():
    assert texts.format_price(50, "USD") == "$50"


@pytest.mark.parametrize("end,expected", [
    (None, ""), (date(2026, 11, 23), ""), (date(2026, 11, 24), "עד היום"), (date(2026, 11, 25), "עד מחר"),
    (date(2026, 11, 29), "עד יום ראשון"), (date(2026, 11, 28), "עד שבת"), (date(2026, 11, 27), "עד יום שישי"),
    (date(2026, 12, 15), "עד 15.12"),
])
def test_format_until(end, expected):
    assert texts.format_until(end, TODAY) == expected


def test_join_he():
    assert texts.join_he([]) == ""
    assert texts.join_he(["זארה"]) == "זארה"
    assert texts.join_he(["זארה", "מנגו"]) == "זארה ומנגו"
    assert texts.join_he(["קסטרו", "פוקס", "טרמינל איקס"]) == "קסטרו, פוקס וטרמינל איקס"


def test_sale_alert():
    msg = texts.sale_alert("זארה", 50, "סוף עונה", ["מעילים", "סריגים"], date(2026, 11, 29), TODAY)
    assert msg == "🔥 <b>זארה – עד 50% הנחה</b> על מעילים וסריגים, עד יום ראשון"


def test_sale_alert_no_pct_uses_headline_and_escapes():
    msg = texts.sale_alert("H&M", None, "1+1 על <הכל>", [], None, TODAY)
    assert msg == "🔥 <b>H&amp;M – 1+1 על &lt;הכל&gt;</b>"


def test_price_drop():
    msg = texts.price_drop("המעיל ששמרת", 399, 249, "ILS", "https://x.co/a?b=1&c=2")
    assert msg == "📉 <b>המעיל ששמרת ירד מ־₪399 ל־₪249</b>\nhttps://x.co/a?b=1&amp;c=2"


def test_price_drop_default_title():
    assert texts.DEFAULT_PRODUCT_TITLE in texts.price_drop(None, 100, 80, "ILS", "u")


def test_templates_format_cleanly():
    texts.START.format(brands="x")
    texts.UNKNOWN_BRANDS.format(names="a", brands="b")
    texts.SAVED.format(price="₪1")
