# AgentGate × Apify

Apify does two jobs in AgentGate:

1. **Defense, with our own Actor.** The [Agent Prompt-Injection Scanner](https://console.apify.com/actors/UvgMeMy3H8U9N78ft) (`tangy_taste_poy~agent-prompt-injection-scanner`, source in [`actor/`](actor/)) scans the pages a shopping agent is about to read. It flags instructions hidden from humans but aimed at AI agents, and extracts the page's product data. It's the first line of defense: it flags the poisoned page *before* the agent reads it. If an agent is fooled anyway, the gateway catches the purchase at checkout.
2. **Product data for the shopper agent.** The scanner's output, or Apify's official e-commerce scraper (`apify~e-commerce-scraping-tool`), is normalized into `data/products.json`, which the shopper reads through `PRODUCTS_JSON`.

## Run it

```bash
# from the repo root; APIFY_API_TOKEN comes from .env
.venv/bin/python apify/adapter.py --scanner tangy_taste_poy~agent-prompt-injection-scanner \
  --url https://raw.githubusercontent.com/Poushali0202/agentgate/main/trap-page/safe-product.html \
  --url https://raw.githubusercontent.com/Poushali0202/agentgate/main/trap-page/malicious-product.html
```

Output from a real run on the Apify platform:

```
- HP-100 Studio Wireless Headphones: risk = low []
- HP-100 Studio Wireless Headphones: risk = high ['addresses_ai_agent', 'conceal_from_user', 'gift_card_push', 'override_instructions', 'quantity_override', 'redirect_shipping']
```

Without `--scanner`, the adapter runs Apify's e-commerce scraper and its own phrase check instead.

## The Actor

- **Detects** hidden text (the `hidden` attribute, inline and stylesheet `display:none` / `visibility:hidden` / zero opacity or font size / off-screen / `clip` / 1-px boxes, `aria-hidden`), HTML comments, and injection phrasing: overriding the user's instructions, addressing AI agents, concealing from the user, redirected shipping, quantity and payment overrides, gift cards.
- **Outputs** one dataset item per page: `risk` (high / medium / low / error), `findings` (where, how it was hidden, the text, matched patterns) and `product` (`sku`, name, price, currency, category from JSON-LD).
- **Crawls** with Crawlee (`crawl: true`, the default). Give it one storefront URL and it follows same-host links up to `maxPages`, scanning every page it finds.
- **Develop:** `cd actor && apify run`, or run `pytest apify/actor/tests` from the repo root. **Deploy:** `cd actor && apify push`.

## Storefront guard (in the gateway)

The merchant's own pages get scanned too: a hacked review widget or a malicious marketplace listing can poison them. An hourly Apify Schedule runs the scanner over `STOREFRONT_URLS`. The gateway's `GET /storefront-scan` pulls the latest successful run (pull, because a laptop gateway isn't reachable from Apify). The dashboard's **Storefront scan** panel shows any page hiding instructions for AI agents, with the hidden text and how it was hidden. **Scan now** calls `POST /storefront-scan/run`.

## Output contract (what the shopper agent reads)

Each row in `data/products.json` carries `sku`, a **gateway store SKU** (`GET /store/products`, e.g. `HP-100`, `GC-901`). The shopper keeps only rows the store sells, de-duplicated, and always uses the store's price, so a bad row can't break checkout. Rows from the scanner also carry `risk`, `detected_patterns` and `hidden_text`.

## Trap pages

`trap-page/` is published by `.github/workflows/pages.yml` to `https://poushali0202.github.io/agentgate/` once a repo admin sets Settings → Pages → Source: GitHub Actions. Until then, use the raw URLs above.
