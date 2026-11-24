# sale-bot

A Telegram bot (Hebrew UI) that sends alerts about:

1. **Brand sales.** Write `תעקוב אחרי זארה ומנגו`, and when one of those brands sends a sale newsletter you get
   `🔥 זארה – עד 50% הנחה על מעילים וסריגים, עד יום ראשון`.
2. **Price drops.** Send a product link, and the bot replies `נשמר! המחיר הנוכחי הוא ₪399…`. If the price drops later you get
   `📉 המעיל ששמרת ירד מ־₪399 ל־₪249`.

`מה אני עוקב?` (or `/list`) shows everything you follow, with ❌ buttons to remove items.

Supported brands: Zara, Mango, H&M, Nike, Castro, Fox, Terminal X. You can name them in Hebrew or English; see `src/salebot/brands.py`.

## How it works

| | |
|---|---|
| **Newsletters** | A dedicated Gmail inbox is subscribed to brand newsletters. Every 5 minutes the bot reads unseen emails over IMAP. Claude Haiku 5.5 extracts `is_sale`, the brand, the discount %, categories (in Hebrew) and the end date. Each sale is sent once to the brand's followers. The same sale announced again within 3 days is ignored. |
| **Prices** | Every 4 hours each tracked link is fetched and its price is read from JSON-LD, then from meta tags, then from a CSS fallback. A drop of at least 1% triggers an alert. After 5 failed checks in a row the user is told and tracking stops. |

Code map: `bot/` (handlers, Hebrew `texts.py`, Hebrew/English `nlu.py`), `newsletters/` (IMAP and extraction), `prices/` (fetch, parse, check), `models.py` (SQLite through SQLAlchemy).

## Setup

1. **Telegram:** create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. **Gmail:** create a dedicated account and turn on 2-step verification. Create an **App Password** (Google Account → Security → App passwords). IMAP is on by default in Gmail.
3. **Subscribe the inbox** to the newsletters of each brand (on the brands' Israeli sites). If a brand sends from a domain that isn't listed in `brands.py`, add it there. Detection still works without it, because Claude also identifies the brand.
4. **Anthropic API key** from the [Claude Console](https://platform.claude.com).
5. Configure:
   ```bash
   cp .env.example .env   # fill in TELEGRAM_TOKEN, ANTHROPIC_API_KEY, IMAP_USER, IMAP_PASSWORD
   ```

### Run locally
```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m salebot.main
```

### Run with Docker
```bash
docker build -t salebot .
docker run -d --env-file .env -v salebot-data:/data --restart unless-stopped salebot
```

## Tests
```bash
.venv/bin/pytest
```

## Known limitations
- Sites that render prices only with JavaScript or block bots (often Zara, Mango, Nike) can fail to give a price. The bot then says so and doesn't save the link. A Playwright fetcher could later be added behind `prices/fetcher.py`.
- Brand matching is rule-based (aliases with fuzzy matching). To add a brand or nickname, edit `brands.py`. The list is synced on startup.
