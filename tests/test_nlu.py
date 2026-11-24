import pytest

from salebot.bot.nlu import Intent, extract_url, match_brands, parse_intent
from salebot.brands import SEED_BRANDS


class B:
    def __init__(self, i, seed):
        self.id, self.name, self.aliases, self.name_he = i, seed.name, list(seed.aliases), seed.name_he

    def __repr__(self):
        return self.name


BRANDS = [B(i, s) for i, s in enumerate(SEED_BRANDS, 1)]


def names(text):
    intent, rest = parse_intent(text)
    m = match_brands(rest, BRANDS)
    return intent, [b.name for b in m.brands], m.unknown


@pytest.mark.parametrize("text,intent,brands", [
    ("תעקוב אחרי זארה ומנגו", Intent.FOLLOW, ["Zara", "Mango"]),
    ("Follow Zara and Mango", Intent.FOLLOW, ["Zara", "Mango"]),
    ("תעקוב אחרי טרמינל איקס, קסטרו ופוקס", Intent.FOLLOW, ["Terminal X", "Castro", "Fox"]),
    ("עקוב אחרי אייץ׳ אנד אם", Intent.FOLLOW, ["H&M"]),
    ("follow H&M", Intent.FOLLOW, ["H&M"]),
    ("follow h & m and nike", Intent.FOLLOW, ["H&M", "Nike"]),
    ("follow nike", Intent.FOLLOW, ["Nike"]),
    ("תעקוב ונייקי", Intent.FOLLOW, ["Nike"]),
    ("תעקבי אחרי זָארָה", Intent.FOLLOW, ["Zara"]),
    ("תעקוב אחרי זרה", Intent.FOLLOW, ["Zara"]),
    ("תעקוב אחרי terminalx", Intent.FOLLOW, ["Terminal X"]),
    ("תפסיק לעקוב אחרי מנגו", Intent.UNFOLLOW, ["Mango"]),
    ("unfollow zara", Intent.UNFOLLOW, ["Zara"]),
])
def test_follow_unfollow(text, intent, brands):
    got_intent, got_brands, unknown = names(text)
    assert got_intent is intent
    assert got_brands == brands
    assert unknown == []


def test_typo_is_fuzzy_matched():
    assert names("follow castroo")[1] == ["Castro"]


def test_unknown_brand():
    intent, brands, unknown = names("תעקוב אחרי גוצ'י")
    assert intent is Intent.FOLLOW and brands == [] and unknown == ["גוצי"]


def test_mixed_known_and_unknown():
    _, brands, unknown = names("תעקוב אחרי זארה וגוצי")
    assert brands == ["Zara"] and unknown == ["וגוצי"]


@pytest.mark.parametrize("text", ["מה אני עוקב?", "מה אני עוקבת", "What am I following?", "רשימה"])
def test_list_intent(text):
    assert parse_intent(text)[0] is Intent.LIST


def test_unknown_intent():
    assert parse_intent("שלום מה נשמע")[0] is Intent.UNKNOWN


def test_extract_url():
    assert extract_url("תראה את זה https://www.zara.com/il/he/coat-p123.html).") == \
        "https://www.zara.com/il/he/coat-p123.html"
    assert extract_url("no link here") is None
