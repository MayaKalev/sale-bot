from datetime import date
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from salebot.newsletters.extractor import (ExtractionError, Extractor, Refused, SaleInfo, email_to_text,
                                           parse_end_date)

BRANDS = ["Zara", "Mango", "Castro"]


class FakeMessages:
    def __init__(self, response=None, exc=None):
        self.response, self.exc, self.calls = response, exc, []

    async def parse(self, **kw):
        self.calls.append(kw)
        if self.exc:
            raise self.exc
        return self.response


def make(response=None, exc=None):
    msgs = FakeMessages(response, exc)
    return Extractor(SimpleNamespace(messages=msgs), "claude-haiku-5-5"), msgs


def resp(info, stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, parsed_output=info)


SALE = SaleInfo(is_sale=True, brand="Zara", max_discount_pct=50, categories=["מעילים"], end_date="2026-11-29",
                headline_he="סוף עונה")


async def test_extract_ok_and_request_shape():
    ex, msgs = make(resp(SALE))
    out = await ex.extract(sender="news@zara.com", subject="SALE", body="up to 50% off",
                           received=date(2026, 11, 24), brand_names=BRANDS)
    assert out.is_sale and out.brand == "Zara"
    call = msgs.calls[0]
    assert call["model"] == "claude-haiku-5-5" and call["output_format"] is SaleInfo
    assert "<email>" in call["messages"][0]["content"] and "2026-11-24" in call["messages"][0]["content"]
    assert "temperature" not in call


async def test_unknown_brand_is_nulled():
    ex, _ = make(resp(SALE.model_copy(update={"brand": "Gucci"})))
    out = await ex.extract(sender="a@b.c", subject="", body="", received=date.today(), brand_names=BRANDS)
    assert out.brand is None


async def test_refusal():
    ex, _ = make(resp(None, stop="refusal"))
    with pytest.raises(Refused):
        await ex.extract(sender="", subject="", body="", received=date.today(), brand_names=BRANDS)


async def test_max_tokens_is_retryable():
    ex, _ = make(resp(None, stop="max_tokens"))
    with pytest.raises(ExtractionError):
        await ex.extract(sender="", subject="", body="", received=date.today(), brand_names=BRANDS)


async def test_api_error_is_retryable():
    err = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    ex, _ = make(exc=err)
    with pytest.raises(ExtractionError):
        await ex.extract(sender="", subject="", body="", received=date.today(), brand_names=BRANDS)


def test_email_to_text_strips_html():
    out = email_to_text("<html><body><h1>SALE</h1><p>עד 50% הנחה</p><img src=x></body></html>", None)
    assert "SALE" in out and "עד 50% הנחה" in out and "<" not in out


def test_parse_end_date():
    assert parse_end_date("2026-11-29") == date(2026, 11, 29)
    assert parse_end_date("soon") is None and parse_end_date(None) is None
