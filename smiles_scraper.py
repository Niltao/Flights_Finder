import os
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright
import requests

# Config
ORIGIN = os.getenv("ORIGIN", "GIG")
DESTINATIONS = os.getenv("DESTINATIONS", "NRT,HND").split(",")
DATE = os.getenv("DATE", "2025-09-20")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram não configurado")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    if r.status_code != 200:
        print("❌ Erro ao enviar Telegram:", r.text)

async def scrape_flights():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        results = []
        for dest in DESTINATIONS:
            msg = f"🔎 Buscando: {ORIGIN} → {dest}"
            print(msg)
            send_telegram(msg)

            url = f"https://www.smiles.com.br/emissao-com-milhas?originAirportCode={ORIGIN}&destinationAirportCode={dest}&departureDate={DATE}&adults=1&children=0&infants=0&tripType=2"
            await page.goto(url, timeout=90000)

            # tenta fechar popups/cookies
            try:
                await page.locator("text=Aceitar").click(timeout=5000)
                print("✅ Banner de cookies fechado")
            except:
                print("ℹ️ Nenhum banner de cookies")

            try:
                await page.locator("button[aria-label='Fechar']").click(timeout=5000)
                print("✅ Popup fechado")
            except:
                print("ℹ️ Nenhum popup encontrado")

            # tenta encontrar cards de voos
            flights = []
            try:
                await page.wait_for_selector("div.ant-card, div.flight-card, div.result-card", timeout=60000)
                cards = await page.locator("div.ant-card, div.flight-card, div.result-card").all()
                for c in cards:
                    txt = await c.inner_text()
                    flights.append(txt.strip())
            except:
                fname = f"debug_fail_{dest}.html"
                await page.screenshot(path=f"debug_fail_{dest}.png")
                html = await page.content()
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"⚠️ Nenhum card detectado, salvando {fname}")
                send_telegram(f"⚠️ Nenhum voo detectado para {ORIGIN} → {dest}. HTML salvo como {fname}")

            if flights:
                results.extend([(dest, f) for f in flights])
                msg = f"✈️ {len(flights)} voos encontrados {ORIGIN} → {dest}"
                print(msg)
                send_telegram(msg)

        await browser.close()

        if not results:
            send_telegram("⚠️ Nenhum voo encontrado na pesquisa.")
        else:
            lines = []
            for dest, f in results[:10]:  # limitar para não estourar
                lines.append(f"➡️ {ORIGIN} → {dest}\n{f[:300]}...")
            send_telegram("\n\n".join(lines))

if __name__ == "__main__":
    asyncio.run(scrape_flights())

