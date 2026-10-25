"""Apify Actor: scan pages for instructions hidden from humans but aimed at AI shopping agents.

Uses Crawlee's BeautifulSoupCrawler. With `crawl` on, it follows links on the same host from each start URL,
up to `maxPages`, so one storefront URL scans every product page behind it.
"""

from apify import Actor
from crawlee.crawlers import BeautifulSoupCrawler, BeautifulSoupCrawlingContext

from .scan import analyze


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        urls = [s["url"] for s in actor_input.get("startUrls", []) if isinstance(s, dict) and s.get("url")]
        if not urls:
            await Actor.fail(status_message="Input needs at least one start URL.")
            return
        crawl = bool(actor_input.get("crawl", False))
        max_pages = int(actor_input.get("maxPages", 50))

        counts = {"high": 0, "medium": 0, "low": 0}
        crawler = BeautifulSoupCrawler(max_requests_per_crawl=max_pages if crawl else len(urls), max_request_retries=2)

        @crawler.router.default_handler
        async def handle(context: BeautifulSoupCrawlingContext) -> None:
            row = analyze(str(context.soup), context.request.loaded_url or context.request.url)
            counts[row["risk"]] += 1
            Actor.log.info(f"{row['risk'].upper():6} {row['url']}  patterns={row['injection_patterns']}")
            await Actor.push_data(row)
            if crawl:
                await context.enqueue_links(strategy="same-hostname")

        @crawler.failed_request_handler
        async def failed(context, error: Exception) -> None:
            Actor.log.warning(f"Could not fetch {context.request.url}: {error}")
            await Actor.push_data({"url": context.request.url, "risk": "error", "error": str(error)})

        await crawler.run(urls)
        scanned = sum(counts.values())
        await Actor.set_status_message(
            f"Scanned {scanned} page(s): {counts['high']} hide instructions aimed at AI agents, {counts['medium']} suspicious.")
