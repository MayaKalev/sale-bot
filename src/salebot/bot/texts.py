"""All user-facing strings (Hebrew). Messages are sent with parse_mode=HTML, so every value is escaped."""
from datetime import date
from html import escape

# Monday=0 ... Sunday=6
_DAYS_HE = ("שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון")

START = (
    "היי! 👋 אני בוט ההנחות שלך.\n\n"
    "• כתבו <b>תעקוב אחרי זארה ומנגו</b> ואשלח לכם התראה כשיש מבצע.\n"
    "• שלחו לי <b>קישור למוצר</b> ואעדכן כשהמחיר שלו יורד.\n"
    "• <b>מה אני עוקב?</b> – הרשימה שלכם, עם אפשרות להסיר.\n\n"
    "מותגים נתמכים: {brands}"
)
HELP = START
FOLLOWED = "מעולה! מעכשיו אעדכן אותך על מבצעים ב־{brands}."
ALREADY_FOLLOWING = "כבר עוקבים אחרי {brands}."
UNFOLLOWED = "הפסקתי לעקוב אחרי {brands}."
NOT_FOLLOWING = "לא עקבת אחרי {brands}."
UNKNOWN_BRANDS = "לא הכרתי את: {names}.\nהמותגים שאני מכיר: {brands}"
NO_BRANDS_GIVEN = "איזה מותג? לדוגמה: <b>תעקוב אחרי קסטרו ופוקס</b>\nהמותגים שאני מכיר: {brands}"
DIDNT_UNDERSTAND = "לא הבנתי 🙈 אפשר לכתוב <b>תעקוב אחרי זארה</b>, לשלוח קישור למוצר, או <b>מה אני עוקב?</b>"

CHECKING_LINK = "בודק את המחיר… ⏳"
SAVED = "נשמר! המחיר הנוכחי הוא {price}, אעדכן אותך אם הוא יורד."
ALREADY_TRACKING = "המוצר הזה כבר ברשימה שלך (מחיר אחרון: {price})."
CANT_READ_PRICE = "לא הצלחתי לקרוא מחיר מהאתר הזה כרגע 😕 לא שמרתי את הקישור."

LIST_EMPTY = "את/ה עדיין לא עוקב/ת אחרי כלום. כתבו <b>תעקוב אחרי זארה</b> או שלחו קישור למוצר."
LIST_HEADER = "<b>הנה מה שאני עוקב עבורך</b> (לחצו ❌ כדי להסיר):"
LIST_BRANDS = "🏷️ <b>מותגים:</b> {brands}"
LIST_PRODUCTS = "🛍️ <b>מוצרים:</b>"
LIST_PRODUCT_LINE = "{i}. {title} – {price}"
REMOVED_BRAND = "הוסר: {name}"
REMOVED_PRODUCT = "המוצר הוסר מהמעקב."
REMOVED_ALREADY = "כבר הוסר."

SALE_ALERT = "🔥 <b>{brand} – {headline}</b>{categories}{until}"
PRICE_DROP = "📉 <b>{title} ירד מ־{old} ל־{new}</b>\n{url}"
DEFAULT_PRODUCT_TITLE = "המוצר ששמרת"
TRACKING_STOPPED = "לא הצלחתי לבדוק את המחיר של {title} כבר כמה פעמים, אז הפסקתי לעקוב אחריו.\n{url}"


def format_price(value: float, currency: str = "ILS") -> str:
    """₪399, ₪249.90 – drop .00, keep two decimals otherwise."""
    symbol = {"ILS": "₪", "USD": "$", "EUR": "€", "GBP": "£"}.get(currency.upper(), currency.upper() + " ")
    num = f"{value:,.0f}" if round(value, 2) == int(value) else f"{value:,.2f}"
    return f"{symbol}{num}"


def join_he(items: list[str]) -> str:
    """'א', 'א וב', 'א, ב וג' (Hebrew 'and' attaches to the last word)."""
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " ו" + items[-1]


def format_until(end: date | None, today: date) -> str:
    if end is None or end < today:
        return ""
    delta = (end - today).days
    if delta == 0:
        return "עד היום"
    if delta == 1:
        return "עד מחר"
    if delta <= 6:
        day = _DAYS_HE[end.weekday()]
        return "עד שבת" if day == "שבת" else f"עד יום {day}"
    return f"עד {end.day}.{end.month}"


def sale_alert(brand_he: str, discount_pct: int | None, headline_he: str, categories: list[str],
               end: date | None, today: date) -> str:
    headline = f"עד {discount_pct}% הנחה" if discount_pct else (headline_he or "מבצע")
    cats = join_he([escape(c) for c in categories[:4]])
    until = format_until(end, today)
    return SALE_ALERT.format(
        brand=escape(brand_he),
        headline=escape(headline),
        categories=f" על {cats}" if cats else "",
        until=f", {until}" if until else "",
    )


def price_drop(title: str | None, old: float, new: float, currency: str, url: str) -> str:
    return PRICE_DROP.format(
        title=escape(shorten(title) if title else DEFAULT_PRODUCT_TITLE),
        old=format_price(old, currency),
        new=format_price(new, currency),
        url=escape(url),
    )


def shorten(text: str, limit: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
