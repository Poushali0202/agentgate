"""Rehearse the ASI:One demo by driving the real Shopper and Guardian handler code, minus Agentverse transport.

Shopper.shop() and Guardian.handle()/deliver() are the functions the chat protocol calls; a fake Context records
what each agent would send to the human. The gateway, signing, webhook listener and Guardian token are all real.

    # a gateway whose challenge webhook points at this rehearsal's listener (port 8011):
    CHALLENGE_WEBHOOK_URL=http://127.0.0.1:8011/challenge .venv/bin/uvicorn gateway.app:app --port 8010
    GATEWAY_URL=http://localhost:8010 .venv/bin/python -m agents.rehearse

Uses .env for GUARDIAN_TOKEN, ANTHROPIC_API_KEY, TRAP_PAGE_URL, PRODUCTS_JSON. Registers its own key
("rehearsal-shopper"), so it never collides with the real Shopper's key.
"""

import os

os.environ.setdefault("SHOPPER_KEYID", "rehearsal-shopper")
os.environ.setdefault("SHOPPER_CHALLENGE_WAIT_S", "45")

import asyncio  # noqa: E402
import logging  # noqa: E402
import sys  # noqa: E402

import httpx  # noqa: E402

from agents.common import consumer_id_for  # noqa: E402
from agents.guardian import agent as guardian  # noqa: E402  (before the Shopper, which drops GUARDIAN_TOKEN)
from agents.guardian import webhook  # noqa: E402
from agents.shopper import agent as shopper  # noqa: E402
from agents.shopper.intent import MODEL  # noqa: E402

HUMAN = "agent1qrehearsalhuman0000000000000000000000000000000000000000"
GW = os.environ.get("GATEWAY_URL", "http://localhost:8010")


class Storage(dict):
    def set(self, k, v):
        self[k] = v


class Ctx:
    def __init__(self, name):
        self.name, self.sent, self.storage = name, [], Storage()
        self.logger = logging.getLogger(name)

    async def send(self, to, msg):
        text = " ".join(getattr(c, "text", "") for c in getattr(msg, "content", []) if getattr(c, "text", None))
        if text:
            self.sent.append(text)
            print(f"   [{self.name} → human] " + text.replace("\n", "\n" + " " * 21))


async def pump_guardian(gctx, seconds, until_card=True):
    for _ in range(seconds):
        await asyncio.sleep(1)
        before = len(gctx.sent)
        await guardian.deliver(gctx)
        if until_card and len(gctx.sent) > before:
            return True
    return False


async def main():
    logging.basicConfig(level=logging.WARNING)
    print(f"intent model: {MODEL} | gateway: {GW} | consumer: {consumer_id_for(HUMAN)}")
    webhook.configure(guardian.GUARDIAN_TOKEN)
    webhook.start(8011)
    await guardian.load_names()
    sctx, gctx = Ctx("shopper"), Ctx("guardian")

    print("\n① Human says hi to the Guardian (it learns who to ask)")
    print("   [guardian → human] " + (await guardian.handle(gctx, "hi"))[:80] + "…")
    gctx.storage.set("owner", HUMAN)

    print("\n② Human → Shopper: \"buy me wireless headphones under $200\"")
    print("   [shopper → human] " + (await shopper.shop(sctx, HUMAN, "buy me wireless headphones under $200")).replace("\n", " | "))

    print("\n③ Simulator scalper swarm runs on the same gateway (its challenges must NOT reach this human)")
    async with httpx.AsyncClient() as c:
        await c.post(f"{GW}/sim/run/scalper")
    shown = await pump_guardian(gctx, 4)
    print(f"   Guardian showed the human {'A SIM CARD (wrong!)' if shown else 'nothing (correct)'}")

    print("\n④ Shopper restarted with HIJACK=1, human asks for headphones again")
    os.environ["HIJACK"] = "1"
    task = asyncio.create_task(shopper.shop(sctx, HUMAN, "buy me headphones"))
    got_card = await pump_guardian(gctx, 40)
    if not got_card:
        print("   ✗ no Guardian card arrived")
        task.cancel()
        sys.exit(1)

    print("\n⑤ Human → Guardian: \"deny\"")
    print("   [guardian → human] " + await guardian.handle(gctx, "deny"))
    print("   [shopper → human] " + (await task).replace("\n", " | "))

    async with httpx.AsyncClient() as c:
        ev = (await c.get(f"{GW}/events", params={"limit": 300})).json()
    mine = [e for e in reversed(ev) if e["consumer_id"] == consumer_id_for(HUMAN)]
    print("\nGateway log for this human:")
    for e in mine:
        print(f"   {e['decision']:9} risk {e['risk_score']:3}  {e['cart'][0]['sku']} ×{e['cart'][0]['qty']}  {e['reasons']}")


asyncio.run(main())
