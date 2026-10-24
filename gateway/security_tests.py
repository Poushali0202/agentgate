"""The five signature checks shown on GET /security-tests (and run by pytest).

Each case runs against a fresh, isolated verifier and test key, so it never touches live traffic.
"""

import json
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from gateway.directory import Directory
from gateway.signer import BROWSER_TAG, PAYER_TAG, sign_request
from gateway.verify import Verifier

AUTHORITY = "gateway.test"
URL = f"http://{AUTHORITY}/checkout"
KEYID = "security-test-key"
BODY = json.dumps({"consumer_id": "c-test", "cart": [{"sku": "HP-100", "qty": 1}]}).encode()


def _setup():
    key = Ed25519PrivateKey.generate()
    directory = Directory()
    directory.register(KEYID, key.public_key())
    return key, Verifier(directory)


def _check(verifier, headers, body=BODY):
    return verifier.verify("POST", AUTHORITY, "/checkout", headers, body)


def case_valid():
    key, v = _setup()
    r = _check(v, sign_request(key, KEYID, "POST", URL, BODY, tag=PAYER_TAG))
    return "verified", r.identity


def case_wrong_tag():
    key, v = _setup()
    r = _check(v, sign_request(key, KEYID, "POST", URL, BODY, tag=BROWSER_TAG))
    return "invalid:wrong_tag", f"{r.identity}:{r.reason}"


def case_expired():
    key, v = _setup()
    now = int(time.time())
    r = _check(v, sign_request(key, KEYID, "POST", URL, BODY, tag=PAYER_TAG, created=now - 120, expires=now - 60))
    return "invalid:expired", f"{r.identity}:{r.reason}"


def case_replayed():
    key, v = _setup()
    headers = sign_request(key, KEYID, "POST", URL, BODY, tag=PAYER_TAG)
    _check(v, headers)
    r = _check(v, headers)
    return "invalid:replayed_nonce", f"{r.identity}:{r.reason}"


def case_tampered():
    key, v = _setup()
    headers = sign_request(key, KEYID, "POST", URL, BODY, tag=PAYER_TAG)
    tampered = BODY.replace(b'"qty": 1', b'"qty": 50')
    r = _check(v, headers, tampered)
    return "invalid:digest_mismatch", f"{r.identity}:{r.reason}"


CASES = {
    "valid": case_valid,
    "wrong_tag": case_wrong_tag,
    "expired": case_expired,
    "replayed": case_replayed,
    "tampered": case_tampered,
}


def run_all() -> list[dict]:
    results = []
    for name, fn in CASES.items():
        expected, got = fn()
        results.append({"name": name, "expected": expected, "got": got, "pass": expected == got})
    return results
