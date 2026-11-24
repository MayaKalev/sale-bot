"""Read a product's current price from its HTML.

Order: JSON-LD Product/Offer -> meta/microdata price tags -> conservative CSS-class fallback.
"""
import json
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup


@dataclass
class ProductInfo:
    price: float
    currency: str
    title: str | None
    source: str  # "jsonld" | "meta" | "fallback"


_CURRENCY_SYMBOLS = {"₪": "ILS", "ש\"ח": "ILS", "ש״ח": "ILS", "$": "USD", "€": "EUR", "£": "GBP"}


def parse_price_value(raw) -> float | None:
    """'₪1,299.90' -> 1299.9, '1.299,90' -> 1299.9, '399' -> 399.0, 249 -> 249.0"""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw > 0 else None
    s = re.sub(r"[^\d.,]", "", str(raw))
    if not s or not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = f"{head.replace(',', '')}.{tail}" if len(tail) in (1, 2) else s.replace(",", "")
    elif s.count(".") > 1:
        head, _, tail = s.rpartition(".")
        s = f"{head.replace('.', '')}.{tail}" if len(tail) in (1, 2) else s.replace(".", "")
    try:
        value = float(s)
    except ValueError:
        return None
    return value if value > 0 else None


def _iter_nodes(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _iter_nodes(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_nodes(v)


def _is_type(node: dict, name: str) -> bool:
    t = node.get("@type")
    return t == name or (isinstance(t, list) and name in t)


def _offer_price(offers) -> tuple[float | None, str | None]:
    candidates = offers if isinstance(offers, list) else [offers]
    best: tuple[float | None, str | None] = (None, None)
    for o in candidates:
        if not isinstance(o, dict):
            continue
        raw = o.get("price")
        if raw in (None, ""):
            raw = o.get("lowPrice")
        if raw in (None, "") and isinstance(o.get("priceSpecification"), (dict, list)):
            spec = o["priceSpecification"]
            spec = spec[0] if isinstance(spec, list) and spec else spec
            raw = spec.get("price") if isinstance(spec, dict) else None
        price = parse_price_value(raw)
        if price is not None and (best[0] is None or price < best[0]):
            best = (price, o.get("priceCurrency"))
    return best


def _from_jsonld(soup: BeautifulSoup) -> ProductInfo | None:
    for script in soup.find_all("script", type="application/ld+json"):
        text = script.string or script.get_text() or ""
        try:
            data = json.loads(text, strict=False)
        except (json.JSONDecodeError, ValueError):
            continue
        for node in _iter_nodes(data):
            if _is_type(node, "Product") and "offers" in node:
                price, currency = _offer_price(node["offers"])
                if price is not None:
                    name = node.get("name")
                    return ProductInfo(price, (currency or "ILS").upper(), name if isinstance(name, str) else None,
                                       "jsonld")
    return None


def _meta(soup: BeautifulSoup, *keys: str) -> str | None:
    for key in keys:
        tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key}) \
            or soup.find(attrs={"itemprop": key})
        if tag is None:
            continue
        value = tag.get("content") or tag.get_text(strip=True)
        if value:
            return value
    return None


def _from_meta(soup: BeautifulSoup) -> tuple[float, str] | None:
    raw = _meta(soup, "product:price:amount", "og:price:amount", "price")
    price = parse_price_value(raw)
    if price is None:
        return None
    currency = _meta(soup, "product:price:currency", "og:price:currency", "priceCurrency") or "ILS"
    return price, currency.upper()


def _from_fallback(soup: BeautifulSoup) -> tuple[float, str] | None:
    """Look in elements whose class names mention a final/sale price, then any 'price' class, for a ₪ amount."""
    for selector in ('[class*="final-price"], [class*="sale-price"], [class*="special-price"], [class*="price--sale"]',
                     '[class*="price"]'):
        for el in soup.select(selector)[:30]:
            text = el.get_text(" ", strip=True)
            m = re.search(r"(₪|ש[\"״]ח)\s*([\d.,]+)|([\d.,]+)\s*(₪|ש[\"״]ח)", text)
            if m:
                price = parse_price_value(m.group(2) or m.group(3))
                if price is not None:
                    return price, "ILS"
    return None


def _title(soup: BeautifulSoup) -> str | None:
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return og["content"].strip()
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return None


def parse_product(html: str) -> ProductInfo | None:
    soup = BeautifulSoup(html, "html.parser")
    info = _from_jsonld(soup)
    if info:
        info.title = info.title or _title(soup)
        return info
    for source, finder in (("meta", _from_meta), ("fallback", _from_fallback)):
        found = finder(soup)
        if found:
            return ProductInfo(found[0], found[1], _title(soup), source)
    return None
