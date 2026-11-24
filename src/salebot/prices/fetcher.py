import asyncio
import logging

import httpx

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
}


class FetchError(Exception):
    pass


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=20)


async def fetch_html(client: httpx.AsyncClient, url: str, retries: int = 2) -> str:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await client.get(url)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise FetchError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            return resp.text
        except (httpx.HTTPError, FetchError) as e:
            last = e
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500:
                break  # 403/404 won't fix themselves
            await asyncio.sleep(2 * (attempt + 1))
    raise FetchError(f"{url}: {last}")
