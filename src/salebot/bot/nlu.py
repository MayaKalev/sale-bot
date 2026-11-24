"""Lightweight Hebrew/English intent + brand parsing.

Hebrew attaches "and" (ו) to the next word ("זארה ומנגו"), so tokens that don't match are retried
without a leading ו. Aliases that genuinely start with ו still match first because exact matches win.
"""
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, Sequence

from rapidfuzz import fuzz, process

_NIQQUD = re.compile(r"[֑-ׇ]")
_QUOTES = re.compile(r"['\"`׳״’‘“”]")
_PUNCT = re.compile(r"[,.;:!?()\[\]{}/\\|\-–—_+*#…]")
_URL = re.compile(r"https?://\S+", re.IGNORECASE)

MAX_NGRAM = 3
FUZZ_CUTOFF = 85


class Intent(str, Enum):
    FOLLOW = "follow"
    UNFOLLOW = "unfollow"
    LIST = "list"
    UNKNOWN = "unknown"


# Phrases are matched on normalized text, longest first. Order matters: list > unfollow > follow.
_LIST_PHRASES = ("מה אני עוקב", "מה אני עוקבת", "אחרי מה אני עוקב", "אחרי מה אני עוקבת", "הרשימה שלי",
                 "רשימה", "what am i following", "my list", "list")
_UNFOLLOW_PHRASES = ("תפסיק לעקוב אחרי", "תפסיקי לעקוב אחרי", "הפסק לעקוב אחרי", "תפסיק לעקוב", "תפסיקי לעקוב",
                     "הפסק לעקוב", "stop following", "unfollow", "תסיר את", "תסירי את", "הסר את", "תסיר",
                     "תסירי", "הסר", "remove")
_FOLLOW_PHRASES = ("תעקוב אחרי", "תעקבי אחרי", "עקוב אחרי", "לעקוב אחרי", "תעקוב אחר", "תעקוב", "תעקבי",
                   "עקוב", "לעקוב", "follow")
_FILLERS = {"את", "אחרי", "אחר", "גם", "בבקשה", "על", "ו", "and", "please", "me", "to", "the", "also"}


def normalize(text: str) -> str:
    text = _NIQQUD.sub("", text).lower()
    text = _QUOTES.sub("", text)
    text = re.sub(r"\s*&\s*", "&", text)
    text = _PUNCT.sub(" ", text)
    return " ".join(text.split())


def _strip_phrase(norm: str, phrases: Sequence[str]) -> str | None:
    """If any phrase appears as whole words in norm, return norm with it removed."""
    for p in sorted(phrases, key=len, reverse=True):
        m = re.search(rf"(?:^|\s){re.escape(p)}(?:\s|$)", norm)
        if m:
            return " ".join((norm[: m.start()] + " " + norm[m.end():]).split())
    return None


def parse_intent(text: str) -> tuple[Intent, str]:
    """Return (intent, remaining normalized text with trigger words removed)."""
    norm = normalize(_URL.sub(" ", text))
    for intent, phrases in ((Intent.LIST, _LIST_PHRASES), (Intent.UNFOLLOW, _UNFOLLOW_PHRASES),
                            (Intent.FOLLOW, _FOLLOW_PHRASES)):
        rest = _strip_phrase(norm, phrases)
        if rest is not None:
            if intent is Intent.LIST and rest:
                continue  # "list" with extra words is probably not a list request
            return intent, rest
    return Intent.UNKNOWN, norm


class BrandLike(Protocol):
    id: int
    name: str
    aliases: list


@dataclass
class BrandMatch:
    brands: list = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)


def _alias_index(brands: Sequence[BrandLike]) -> dict[str, BrandLike]:
    index: dict[str, BrandLike] = {}
    for b in brands:
        for alias in (b.name, *b.aliases):
            index.setdefault(normalize(alias), b)
    return index


def match_brands(text: str, brands: Sequence[BrandLike]) -> BrandMatch:
    """Find brands mentioned in already-intent-stripped text."""
    index = _alias_index(brands)
    aliases = list(index)
    tokens = normalize(text).split()
    result = BrandMatch()
    seen: set[int] = set()

    def add(b: BrandLike) -> None:
        if b.id not in seen:
            seen.add(b.id)
            result.brands.append(b)

    def exact(words: list[str]) -> BrandLike | None:
        phrase = " ".join(words)
        if phrase in index:
            return index[phrase]
        if words[0].startswith("ו") and len(words[0]) > 1:
            stripped = " ".join([words[0][1:], *words[1:]])
            return index.get(stripped)
        return None

    def fuzzy(token: str) -> BrandLike | None:
        candidates = [token]
        if token.startswith("ו") and len(token) > 2:
            candidates.append(token[1:])
        for cand in candidates:
            if len(cand) < 3:
                continue
            hit = process.extractOne(cand, aliases, scorer=fuzz.ratio, score_cutoff=FUZZ_CUTOFF)
            if hit:
                return index[hit[0]]
        return None

    i = 0
    while i < len(tokens):
        if tokens[i] in _FILLERS:
            i += 1
            continue
        for n in range(min(MAX_NGRAM, len(tokens) - i), 0, -1):
            b = exact(tokens[i : i + n])
            if b:
                add(b)
                i += n
                break
        else:
            b = fuzzy(tokens[i])
            if b:
                add(b)
            else:
                result.unknown.append(tokens[i])
            i += 1
    return result


def extract_url(text: str) -> str | None:
    m = _URL.search(text)
    return m.group(0).rstrip(").,") if m else None
