"""A signed shopper on the command line, for testing the gateway without the Fetch.ai agent.

    python -m gateway.cli_shopper --sku HP-100
    python -m gateway.cli_shopper --sku GC-901 --qty 2 --ship-to "77 Unknown Rd" --scenario hijacked
    python -m gateway.cli_shopper --sku HP-100 --unsigned

Registers its key, does a signed /browse, then a signed /checkout. On challenge, polls until the Guardian answers.
"""

import argparse
import json
import os
import sys
import time

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from gateway.signer import BROWSER_TAG, PAYER_TAG, public_jwk, sign_request

KEY_DIR = "gateway/data/cli_keys"


def load_key(keyid: str) -> Ed25519PrivateKey:
    """One persistent key per keyid, so the same CLI 'agent' keeps its identity (and history) across runs."""
    path = os.path.join(KEY_DIR, f"{keyid}.pem")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)
    key = Ed25519PrivateKey.generate()
    os.makedirs(KEY_DIR, exist_ok=True)
    with open(path, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return key


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gateway", default="http://localhost:8000")
    ap.add_argument("--keyid", default="cli-shopper")
    ap.add_argument("--consumer", default="c-cli")
    ap.add_argument("--sku", default="HP-100")
    ap.add_argument("--qty", type=int, default=1)
    ap.add_argument("--card", default="card_cli_1")
    ap.add_argument("--ship-to", default="1 Main St, San Francisco")
    ap.add_argument("--scenario", default=None, help="ground-truth label for the dashboard")
    ap.add_argument("--unsigned", action="store_true", help="send checkout with no signature")
    ap.add_argument("--wait", type=float, default=120, help="seconds to wait for a challenge to resolve")
    args = ap.parse_args()

    g = args.gateway.rstrip("/")
    key = load_key(args.keyid)
    with httpx.Client(timeout=10) as http:
        http.post(f"{g}/directory/keys", json=public_jwk(key.public_key(), args.keyid)).raise_for_status()

        url = f"{g}/browse"
        r = http.get(url, params={"consumer_id": args.consumer, "q": ""},
                     headers=sign_request(key, args.keyid, "GET", url, tag=BROWSER_TAG))
        print(f"browse    {r.status_code}  {len(r.json()) if r.is_success else r.text}")

        order = {"consumer_id": args.consumer, "card_fp": args.card, "ship_to": args.ship_to,
                 "cart": [{"sku": args.sku, "qty": args.qty}]}
        body = json.dumps(order).encode()
        url = f"{g}/checkout"
        headers = {"Content-Type": "application/json"}
        if not args.unsigned:
            headers.update(sign_request(key, args.keyid, "POST", url, body, tag=PAYER_TAG))
        if args.scenario:
            headers["X-AgentGate-Scenario"] = args.scenario
        r = http.post(url, content=body, headers=headers)
        out = r.json()
        print(f"checkout  {r.status_code}  {out['decision']}  "
              f"score={out.get('risk_score', '-')}  reasons={out.get('reasons', '-')}  latency={out.get('latency_ms', '-')}ms")

        if out["decision"] != "challenge":
            return 0 if out["decision"] == "allow" else 1

        cid = out["challenge_id"]
        print(f"challenge {cid}: waiting for the Guardian (POST {g}/challenge/{cid}/resolve)")
        deadline = time.time() + args.wait
        while time.time() < deadline:
            status = http.get(f"{g}/challenge/{cid}").json()
            if status["status"] != "pending":
                print(f"resolved  {status['status']}  reasons={status['reasons']}")
                return 0 if status["status"] == "allow" else 1
            time.sleep(1)
        print("still pending")
        return 2


if __name__ == "__main__":
    sys.exit(main())
