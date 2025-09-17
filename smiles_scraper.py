import os
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright
import requests

# Configurações
ORIGIN = os.getenv("ORIGIN", "GIG")
DESTINATIONS = os.getenv("DESTINATIONS", "NRT").split(",")
START_DATE = os.getenv("START_DATE", "2025-09-10")   # YYYY-MM-DD
DAYS_RANGE = int(os.getenv("DAYS_RANGE", "1"))       # forçado p/ debug
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=15)
        print("Telegram status:", r.status_code)
    except Exception as e:
        print("Telegram error:", e)

async def run_scraper():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 1. Acessa a home
        await page.goto("https://www.smiles.com.br/home", timeout=60000)
        await page.wait_for_timeout(5000)
        html = await page.content()
        with open("debug_home.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("✅ Saved debug_home.html")

        # 2. Preenche campos e clica buscar
        try:
            await page.fill("input[name='origin']", ORIGIN)
            await page.fill("input[name='destination']", DESTINATIONS[0])
            await page.fill("input[name='departureDate']", START_DATE)
            await page.click("button:has-text('Buscar')")
            await page.wait_for_timeout(8000)
            html = await page.content()
            with open("debug_after_search.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("✅ Saved debug_after_search.html")
        except Exception as e:
            print("Erro ao preencher ou buscar:", e)

        # 3. Espera resultados
        try:
            await page.wait_for_timeout(10000)  # dá tempo para carregar
            html = await page.content()
            with open("debug_results.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("✅ Saved debug_results.html")
        except Exception as e:
            print("Erro ao capturar resultados:", e)

        await browser.close()

    send_telegram("🔎 Debug finalizado. Arquivos HTML salvos.")

if __name__ == "__main__":
    asyncio.run(run_scraper())
