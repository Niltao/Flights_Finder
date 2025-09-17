import os
import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import re
import requests

ORIGIN = os.getenv("ORIGIN", "GIG")
DESTINATIONS = os.getenv("DESTINATIONS", "NRT,HND").split(",")
START_DATE = os.getenv("START_DATE", "2025-09-10")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(msg: str):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

async def scrape_flights():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        results = []

        for dest in DESTINATIONS:
            url = (
                f"https://www.smiles.com.br/emissao-com-milhas/voos?cabin=all"
                f"&originAirportCode={ORIGIN}&destinationAirportCode={dest}"
                f"&departureDate={START_DATE}&adults=1&children=0&infants=0"
            )
            print(f"🔎 Buscando: {ORIGIN} → {dest}")
            await page.goto(url, timeout=90000)

            # 1. Fecha popup se aparecer
            try:
                await page.click("button[aria-label='Fechar']", timeout=5000)
                print("✅ Popup fechado")
            except:
                print("ℹ️ Nenhum popup encontrado")

            # 2. Aceita cookies se aparecer
            try:
                await page.click("text=Aceitar", timeout=5000)
                print("✅ Cookies aceitos")
            except:
                print("ℹ️ Nenhum banner de cookies")

            # 3. Espera os cards de voo (divs)
            try:
                await page.wait_for_selector("div.ant-card, div.flight-card", timeout=90000)
            except:
                print("⚠️ Nenhum card detectado, salvando HTML para debug")
                html_fail = await page.content()
                with open(f"debug_fail_{dest}.html", "w", encoding="utf-8") as f:
                    f.write(html_fail)
                continue

            html = await page.content()
            with open(f"debug_rendered_{dest}.html", "w", encoding="utf-8") as f:
                f.write(html)

            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select("div.ant-card, div.flight-card")

            for card in cards:
                text = card.get_text(" ", strip=True)

                miles = None
                m = re.search(r"(\d[\d.]+)\s*milhas", text, re.I)
                if m:
                    miles = int(m.group(1).replace(".", ""))

                price = None
                m2 = re.search(r"R\$\s*([\d.,]+)", text)
                if m2:
                    price = m2.group(1)

                if miles:
                    results.append(
                        f"{ORIGIN}→{dest} {START_DATE} | {miles} milhas | {price or '?'}"
                    )

        await browser.close()

        if results:
            msg = "✈️ Resultados encontrados:\n" + "\n".join(results)
        else:
            msg = "⚠️ Nenhum voo encontrado."

        print(msg)
        send_telegram(msg)

if __name__ == "__main__":
    asyncio.run(scrape_flights())
