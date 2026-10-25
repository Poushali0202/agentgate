# AgentGate Apify Integration

AgentGate uses Apify's official e-commerce scraper:

```text
apify/e-commerce-scraping-tool
## Output contract (what the shopper agent reads)

Each row must carry `sku`, a **gateway store SKU** (`GET /store/products`, e.g. `HP-100`, `GC-901`). The adapter takes it from the scraper's result, and if that's missing, from the page's `data-sku` attribute. The shopper keeps only rows the store sells and always uses the store's price, so a bad row can't break checkout. Set `PRODUCTS_JSON=apify/data/products.json` once `adapter.py` has been run with a real `APIFY_API_TOKEN`. See `data/products.example.json` for the shape.

Trap pages are published by `.github/workflows/pages.yml` to `https://poushali0202.github.io/agentgate/` (an admin must set Settings → Pages → Source: GitHub Actions once). Until then, use the raw URL:
`https://raw.githubusercontent.com/Poushali0202/agentgate/main/trap-page/malicious-product.html`
