"""Apify Actor: scan product pages for instructions hidden from humans but aimed at AI shopping agents."""

import httpx
from apify import Actor

from .scan import analyze

USER_AGENT = "Mozilla/5.0 (compatible; AgentPromptInjectionScanner/0.1; +https://github.com/Poushali0202/agentgate)"


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        urls = [s["url"] for s in actor_input.get("startUrls", []) if isinstance(s, dict) and s.get("url")]
        if not urls:
            await Actor.fail(status_message="Input needs at least one start URL.")
            return

        flagged = 0
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as http:
            for url in urls:
                try:
                    response = await http.get(url)
                    response.raise_for_status()
                except httpx.HTTPError as e:
                    Actor.log.warning(f"Could not fetch {url}: {e}")
                    await Actor.push_data({"url": url, "risk": "error", "error": str(e)})
                    continue
                row = analyze(response.text, str(response.url))
                flagged += row["risk"] == "high"
                Actor.log.info(f"{row['risk'].upper():6} {url}  patterns={row['injection_patterns']}")
                await Actor.push_data(row)

        await Actor.set_status_message(f"Scanned {len(urls)} page(s); {flagged} hide instructions aimed at AI agents.")
