# smiles_scraper.py
# Scraper Smiles com Playwright -> retorna todos os voos encontrados
# Mostra no Telegram sempre, destacando o melhor em milhas e duração

import os
import asyncio
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from playwright.async_api import async_playwright
import requests

# -----------------------
# CONFIG
# -----------------------
ORIGIN = os.getenv("ORIGIN", "GIG")
DESTINATIONS = os.getenv("DESTINATIONS", "NRT,HND").split(",")
START_DATE = os.getenv("START_DATE", "2025-09-10")   # YYYY-MM-DD
DAYS_RANGE = int(os.getenv("DAYS_RANGE", "5"))  # pode aumentar no Actions
MILES_LIMIT = 170000  # apenas referência, não filtra

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# -----------------------
# Utils
# -----------------------
def send_telegram(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured; skipping send.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            print("Telegram send failed:", r.status_code, r.text[:200])
    except Exception as e:
        print("Telegram send error:", e)


def parse_miles(text: str) -> Optional[int]:
    if not text:
        return None
    m = re.sub(r"[^\d]", "", text)
    return int(m) if m else None


def parse_duration(text: str) -> float:
    if not text:
        return 9999.0
    h, m = 0, 0
    match = re.search(r"(\d+)\s*h", text)
    if match:
        h = int(match.group(1))
    match = re.search(r"(\d+)\s*m", text)
    if match:
        m = int(match.group(1))
    return h + m / 60.0


def choose_bests(offers: List[Dict[str, Any]]):
    if not offers:
        return {}
    return {
        "best_miles": min(offers, key=lambda x: x.get("miles", 10**12)),
        "best_duration": min(offers, key=lambda x: x.get("duration_hours", 1e9)),
    }


# -----------------------
# Scraper Playwright
# -----------------------
async def fetch_day(origin: str, dest: str, date_str: str) -> List[Dict[str, Any]]:
    url = f"https://www.smiles.com.br/emissao-com-milhas/voo-listagem?originAirportCode={origin}&destinationAirportCode={dest}&departureDate={date_str}&adults=1&children=0&infants=0&cabin=all"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(url, timeout=60000)

        # aceitar cookies e fechar popups se existirem
        try:
            await page.locator("button#onetrust-accept-btn-handler").click(timeout=5000)
        except:
            pass
        try:
            await page.locator("button[aria-label='Fechar']").click(timeout=5000)
        except:
            pass

        await page.wait_for_timeout(5000)

        offers = []
        cards = await page.locator("div.flight-card").all()
        for card in cards:
            try:
                miles_text = await card.locator(".price span").first.text_content()
                miles = parse_miles(miles_text)
                duration_text = await card.locator(".duration").text_content()
                duration = parse_duration(duration_text)
                airline = await card.locator(".airline-name").text_content()
                if miles:
                    offers.append({
                        "carrier": airline or "?",
                        "miles": miles,
                        "duration_hours": duration,
                        "origin": origin,
                        "destination": dest,
                        "date": date_str
                    })
            except:
                continue

        await browser.close()
        return offers


async def run_scan_once():
    start = datetime.fromisoformat(START_DATE).date()
    all_offers: List[Dict[str, Any]] = []

    for dest in DESTINATIONS:
        for i in range(DAYS_RANGE):
            d = start + timedelta(days=i)
            dstr = d.strftime("%Y-%m-%d")
            print("Searching", ORIGIN, "->", dest, dstr)
            try:
                offers = await fetch_day(ORIGIN, dest, dstr)
                all_offers.extend(offers)
            except Exception as e:
                print("Error fetching:", e)

    if not all_offers:
        send_telegram("Nenhum voo encontrado na pesquisa (site pode ter bloqueado ou alterado layout).")
        return

    bests = choose_bests(all_offers)

    msgs = [f"🔎 Varredura Smiles ({ORIGIN} → {','.join(DESTINATIONS)})\nLimite de referência: {MILES_LIMIT:,} milhas\n"]
    for o in all_offers:
        line = f"{o['miles']:,} milhas | {o['duration_hours']:.1f}h | {o['origin']}→{o['destination']} em {o['date']}"
        if o == bests.get("best_miles"):
            line += "\n⚠️ Melhor milhas"
        if o == bests.get("best_duration"):
            line += "\n⚠️ Menor duração"
        msgs.append(line)

    send_telegram("\n\n".join(msgs))


if __name__ == "__main__":
    asyncio.run(run_scan_once())
