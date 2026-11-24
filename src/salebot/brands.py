"""Seed brand catalogue: canonical name, Hebrew display name, aliases, newsletter sender domains.

Sender domains are a starting point - verify them against real newsletter senders.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SeedBrand:
    name: str
    name_he: str
    aliases: tuple[str, ...]
    sender_domains: tuple[str, ...]


SEED_BRANDS: tuple[SeedBrand, ...] = (
    SeedBrand("Zara", "זארה", ("זארה", "זרה", "zara"), ("zara.com",)),
    SeedBrand("Mango", "מנגו", ("מנגו", "mango"), ("mango.com",)),
    SeedBrand("H&M", "H&M", ("אייץ' אנד אם", "אייץ אנד אם", "h&m", "hm", "h and m", "h & m"), ("hm.com",)),
    SeedBrand("Nike", "נייקי", ("נייקי", "נייק", "nike"), ("nike.com",)),
    SeedBrand("Castro", "קסטרו", ("קסטרו", "castro"), ("castro.com",)),
    SeedBrand("Fox", "פוקס", ("פוקס", "fox"), ("fox.co.il",)),
    SeedBrand("Terminal X", "טרמינל איקס", ("טרמינל איקס", "טרמינל x", "טרמינל", "terminal x", "terminalx"),
              ("terminalx.com",)),
)


def brand_for_sender(sender: str, brands) -> object | None:
    """Return the brand whose sender domain matches the email's From address (or a subdomain of it)."""
    domain = sender.rsplit("@", 1)[-1].strip(" >").lower()
    for b in brands:
        for d in b.sender_domains:
            if domain == d or domain.endswith("." + d):
                return b
    return None
