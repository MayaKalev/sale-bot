import pytest

from salebot.prices.parser import parse_price_value, parse_product


@pytest.mark.parametrize("raw,expected", [
    ("399", 399.0), ("399.00", 399.0), ("₪1,299.90", 1299.9), ("1.299,90", 1299.9), ("249,90", 249.9),
    ("1,299", 1299.0), (179.9, 179.9), ("₪ 59", 59.0), ("", None), ("free", None), (0, None),
])
def test_parse_price_value(raw, expected):
    assert parse_price_value(raw) == expected


@pytest.mark.parametrize("name,price,currency,title,source", [
    ("product_jsonld.html", 399.0, "ILS", "מעיל צמר ארוך", "jsonld"),
    ("product_jsonld_graph.html", 149.9, "ILS", "סווטשירט קפוצ'ון", "jsonld"),
    ("product_aggregate.html", 1299.9, "ILS", "ג'ינס סקיני", "jsonld"),
    ("product_meta.html", 59.9, "ILS", "חולצת טי בייסיק - קסטרו", "meta"),
    ("product_fallback.html", 179.9, "ILS", "שמלת מידי", "fallback"),
])
def test_parse_product(fixture_text, name, price, currency, title, source):
    info = parse_product(fixture_text(name))
    assert info is not None
    assert (info.price, info.currency, info.title, info.source) == (price, currency, title, source)


def test_parse_product_none(fixture_text):
    assert parse_product(fixture_text("product_none.html")) is None
