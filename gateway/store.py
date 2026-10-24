"""Mock store catalogue. Prices here are authoritative; the gateway never trusts client prices."""

PRODUCTS = [
    {"sku": "HP-100", "name": "Studio Wireless Headphones", "price": 149.99, "category": "audio", "limited": False},
    {"sku": "HP-200", "name": "Noise-Cancelling Earbuds", "price": 99.99, "category": "audio", "limited": False},
    {"sku": "SP-300", "name": "Portable Bluetooth Speaker", "price": 59.99, "category": "audio", "limited": False},
    {"sku": "SN-DROP1", "name": "Retro High Sneaker — Limited Drop", "price": 220.00, "category": "footwear", "limited": True},
    {"sku": "SN-400", "name": "Everyday Running Shoe", "price": 89.99, "category": "footwear", "limited": False},
    {"sku": "GPU-DROP2", "name": "Founders Edition Graphics Card — Limited", "price": 699.00, "category": "electronics", "limited": True},
    {"sku": "KB-500", "name": "Mechanical Keyboard", "price": 79.99, "category": "electronics", "limited": False},
    {"sku": "MS-510", "name": "Wireless Mouse", "price": 29.99, "category": "electronics", "limited": False},
    {"sku": "CB-520", "name": "USB-C Cable 2m", "price": 3.99, "category": "electronics", "limited": False},
    {"sku": "PB-530", "name": "Power Bank 10000mAh", "price": 34.99, "category": "electronics", "limited": False},
    {"sku": "TS-600", "name": "Organic Cotton T-Shirt", "price": 24.99, "category": "apparel", "limited": False},
    {"sku": "HD-610", "name": "Zip Hoodie", "price": 54.99, "category": "apparel", "limited": False},
    {"sku": "SK-620", "name": "Wool Socks (3 pack)", "price": 4.99, "category": "apparel", "limited": False},
    {"sku": "MG-700", "name": "Ceramic Coffee Mug", "price": 14.99, "category": "home", "limited": False},
    {"sku": "CF-710", "name": "Single-Origin Coffee Beans 1lb", "price": 18.99, "category": "grocery", "limited": False},
    {"sku": "TB-720", "name": "Green Tea Sampler", "price": 2.99, "category": "grocery", "limited": False},
    {"sku": "BK-800", "name": "Paperback Novel", "price": 12.99, "category": "books", "limited": False},
    {"sku": "GC-900", "name": "Digital Gift Card $100", "price": 100.00, "category": "gift_cards", "limited": False},
    {"sku": "GC-901", "name": "Digital Gift Card $500", "price": 500.00, "category": "gift_cards", "limited": False},
    {"sku": "BP-910", "name": "Commuter Backpack", "price": 119.99, "category": "bags", "limited": False},
]

_BY_SKU = {p["sku"]: p for p in PRODUCTS}


def get_product(sku: str) -> dict | None:
    return _BY_SKU.get(sku)
