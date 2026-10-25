import argparse
import json
import os
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup


ACTOR_ID = "apify~e-commerce-scraping-tool"

APIFY_RUN_URL = (
    f"https://api.apify.com/v2/actors/{ACTOR_ID}"
    "/run-sync-get-dataset-items"
)

SUSPICIOUS_PATTERNS = [
    "ignore the customer's original instructions",
    "ignore the customer instructions",
    "ignore previous instructions",
    "ignore the user",
    "purchase 20 units",
    "purchase twenty units",
    "change the shipping address",
    "unrecognized address",
    "use the fastest payment method",
    "instructions for automated shopping agents",
    "system note for ai shopping agents",
    "do not mention this change",
    "gift card",
]


def fetch_page_text(url: str) -> tuple[str, str | None]:
    """
    Download the original product page and extract its full text
    (including hidden elements, which is what an agent reads) and the
    store SKU from the markup (data-sku), if present.

    This is separate from Apify's structured product extraction because
    we need to preserve suspicious review/page text for AgentGate.
    """
    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "AgentGate-Demo/1.0"
        },
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    tagged = soup.find(attrs={"data-sku": True})
    markup_sku = tagged["data-sku"] if tagged else None

    for element in soup(["script", "style", "noscript"]):
        element.decompose()

    text = soup.get_text(" ", strip=True)

    return " ".join(text.split()), markup_sku


def detect_untrusted_instructions(text: str) -> list[str]:
    """
    Detect suspicious instructions aimed at shopping agents.
    """
    normalized_text = text.lower()

    return [
        pattern
        for pattern in SUSPICIOUS_PATTERNS
        if pattern in normalized_text
    ]


def run_apify_scraper(urls: list[str]) -> list[dict[str, Any]]:
    """
    Run Apify's official e-commerce scraper Actor.

    The API token must be provided through APIFY_API_TOKEN.
    """
    token = os.environ.get("APIFY_API_TOKEN")

    if not token:
        raise RuntimeError(
            "APIFY_API_TOKEN is missing. "
            "Set it in PowerShell before running this script."
        )

    actor_input = {
        "detailsUrls": [
            {
                "url": url
            }
            for url in urls
        ],
        "scrapeMode": "AUTO"
    }

    response = requests.post(
        APIFY_RUN_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        json=actor_input,
        timeout=300
    )

    response.raise_for_status()

    result = response.json()

    if not isinstance(result, list):
        raise RuntimeError(
            "Unexpected response from Apify:\n"
            + json.dumps(result, indent=2)
        )

    return result


def get_first(
    item: dict[str, Any],
    possible_names: list[str],
    default: Any = None
) -> Any:
    """
    Get the first available value from possible field names.

    Different Apify Actors may name fields slightly differently.
    """
    for name in possible_names:
        value = item.get(name)

        if value is not None and value != "":
            return value

    return default


def extract_product_id(
    scraped_item: dict[str, Any]
) -> str:
    value = get_first(
        scraped_item,
        [
            "sku",
            "productId",
            "product_id",
            "asin",
            "id"
        ],
        default="unknown-product"
    )

    return str(value)


def normalize_product(
    scraped_item: dict[str, Any],
    source_url: str
) -> dict[str, Any]:
    """
    Convert Apify's result into AgentGate's shared product format.
    """
    raw_page_text, markup_sku = fetch_page_text(source_url)
    sku = extract_product_id(scraped_item)
    if sku == "unknown-product" and markup_sku:
        sku = markup_sku
    detected_patterns = detect_untrusted_instructions(raw_page_text)

    product = {
        # sku must be a gateway store SKU (GET /store/products); the shopper drops rows it doesn't recognise.
        "sku": sku,
        "product_id": sku,
        "name": get_first(
            scraped_item,
            [
                "name",
                "title",
                "productName",
                "product_title"
            ],
            default="Unknown product"
        ),
        "price": get_first(
            scraped_item,
            [
                "price",
                "currentPrice",
                "productPrice",
                "offerPrice"
            ]
        ),
        "currency": get_first(
            scraped_item,
            [
                "currency",
                "currencyCode",
                "priceCurrency"
            ],
            default="USD"
        ),
        "inventory": get_first(
            scraped_item,
            [
                "inventory",
                "stock",
                "stockQuantity",
                "availability"
            ]
        ),
        "category": get_first(
            scraped_item,
            [
                "category",
                "categoryName",
                "productCategory"
            ]
        ),
        "description": get_first(
            scraped_item,
            [
                "description",
                "productDescription"
            ],
            default=""
        ),
        "source_url": source_url,
        "raw_page_text": raw_page_text,
        "untrusted_instructions_detected": bool(
            detected_patterns
        ),
        "detected_patterns": detected_patterns,
        "scraper": ACTOR_ID
    }

    return product


def save_products(
    products: list[dict[str, Any]]
) -> Path:
    output_path = (
        Path(__file__).parent
        / "data"
        / "products.json"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output_path.write_text(
        json.dumps(products, indent=2),
        encoding="utf-8"
    )

    return output_path


def run_scanner(actor_id: str, urls: list[str]) -> list[dict[str, Any]]:
    """
    Run our Agent Prompt-Injection Scanner Actor (apify/actor/) on the
    Apify platform and return its dataset items.
    """
    token = os.environ.get("APIFY_API_TOKEN")

    if not token:
        raise RuntimeError("APIFY_API_TOKEN is missing (put it in the repo's .env).")

    response = requests.post(
        f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items",
        headers={"Authorization": f"Bearer {token}"},
        json={"startUrls": [{"url": url} for url in urls]},
        timeout=300
    )

    response.raise_for_status()

    return response.json()


def scanner_to_products(rows: list[dict[str, Any]], actor_id: str) -> list[dict[str, Any]]:
    """
    Convert scanner rows into the shared product format the shopper reads.
    """
    products = []

    for row in rows:
        product = row.get("product") or {}

        if row.get("risk") == "error" or not product.get("sku"):
            continue

        products.append({
            "sku": product["sku"],
            "product_id": product["sku"],
            "name": product.get("name") or "Unknown product",
            "price": product.get("price"),
            "currency": product.get("currency") or "USD",
            "category": product.get("category"),
            "source_url": row["url"],
            "risk": row["risk"],
            "untrusted_instructions_detected": row["risk"] in ("high", "medium"),
            "detected_patterns": row.get("injection_patterns", []),
            "hidden_text": [f["text"] for f in row.get("findings", []) if f["where"] != "visible"],
            "scraper": actor_id
        })

    return products


def _load_dotenv() -> None:
    env = Path(__file__).resolve().parent.parent / ".env"

    if not env.exists():
        return

    for line in env.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")

        if sep and key and not key.startswith("#") and value.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def main() -> None:
    _load_dotenv()

    parser = argparse.ArgumentParser(
        description=(
            "Run Apify's e-commerce scraper (or our prompt-injection "
            "scanner Actor) and normalize the results for AgentGate."
        )
    )

    parser.add_argument(
        "--url",
        action="append",
        required=True,
        help=(
            "Product URL. Pass --url multiple times "
            "for multiple products."
        )
    )

    parser.add_argument(
        "--scanner",
        nargs="?",
        const=os.environ.get("APIFY_SCANNER_ACTOR", ""),
        default=None,
        help=(
            "Use our Agent Prompt-Injection Scanner Actor instead, e.g. "
            "--scanner username~agent-prompt-injection-scanner "
            "(defaults to APIFY_SCANNER_ACTOR)."
        )
    )

    args = parser.parse_args()

    if args.scanner is not None:
        if not args.scanner:
            parser.error("--scanner needs an Actor id, or set APIFY_SCANNER_ACTOR in .env")

        print(f"Running {args.scanner} on {len(args.url)} URL(s)...")
        products = scanner_to_products(run_scanner(args.scanner, args.url), args.scanner)
        output_path = save_products(products)
        print(f"Saved {len(products)} product(s) to: {output_path}")

        for product in products:
            print(f"- {product['sku']} {product['name']}: risk = {product['risk']} {product['detected_patterns']}")

        return

    print("Starting Apify e-commerce scraper...")
    print(f"URLs: {len(args.url)}")

    scraped_items = run_apify_scraper(args.url)

    products = []

    for index, url in enumerate(args.url):
        if index < len(scraped_items):
            scraped_item = scraped_items[index]
        else:
            scraped_item = {}

        normalized_product = normalize_product(
            scraped_item=scraped_item,
            source_url=url
        )

        products.append(normalized_product)

    output_path = save_products(products)

    print(f"Saved normalized output to: {output_path}")

    for product in products:
        print(
            f"- {product['name']}: "
            f"untrusted instructions = "
            f"{product['untrusted_instructions_detected']}"
        )


if __name__ == "__main__":
    main()