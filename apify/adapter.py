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
]


def fetch_page_text(url: str) -> str:
    """
    Download the original product page and extract visible text.

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

    for element in soup(["script", "style", "noscript"]):
        element.decompose()

    text = soup.get_text(" ", strip=True)

    return " ".join(text.split())


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
    raw_page_text = fetch_page_text(source_url)
    detected_patterns = detect_untrusted_instructions(raw_page_text)

    product = {
        "product_id": extract_product_id(scraped_item),
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run Apify's e-commerce scraper and "
            "normalize the results for AgentGate."
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

    args = parser.parse_args()

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