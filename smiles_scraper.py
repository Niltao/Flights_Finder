import asyncio
import json
import requests
import os
from playwright.async_api import async_playwright

ORIGIN = os.getenv("ORIGIN", "RIO")
DESTINATION = os.getenv("DESTINATION", "HND")
DATE = os.getenv("DATE", "2025-09-15")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram não configurado.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"})

async def search_flight(origin, destination, date):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context()
        page = await context.new_page()

        # 1) Abre a página inicial
        await page.goto("https://www.smiles.com.br/", timeout=60000)

        # 2) Clica no menu "Passagens Aéreas"
        await page.wait_for_selector('a[href*="passagens-aereas"], a:has-text("Passagens")', timeout=60000)
        await page.click('a[href*="passagens-aereas"], a:has-text("Passagens")')

        # 3) Espera os campos carregarem
        await page.wait_for_selector('input[name="origin"], input[placeholder*="Origem"]', timeout=60000)
        await page.fill('input[name="origin"], input[placeholder*="Origem"]', origin)
        await page.keyboard.press("Enter")

        await page.wait_for_selector('input[name="destination"], input[placeholder*="Destino"]', timeout=60000)
        await page.fill('input[name="destination"], input[placeholder*="Destino"]', destination)
        await page.keyboard.press("Enter")

        await page.wait_for_selector('input[name="departureDate"], input[placeholder*="Ida"]', timeout=60000)
        await page.fill('input[name="departureDate"], input[placeholder*="Ida"]', date)
        await page.keyboard.press("Enter")

        # 4) Buscar
        await page.wait_for_selector('button[type="submit"], button:has-text("Buscar")', timeout=60000)
        await page.click('button[type="submit"], button:has-text("Buscar")')

        # 5) Capturar resultados
        await page.wait_for_selector("div[class*='flight-card']", timeout=60000)
        flights = await page.locator("div[class*='flight-card']").all_inner_texts()

        await browser.close()
        return flights

async def main():
    flights = await search_flight(ORIGIN, DESTINATION, DATE)
    if flights:
        text = "✈️ Resultados:\n\n" + "\n\n".join(flights)
        print(text)
        send_telegram(text)
    else:
        print("Nenhum voo encontrado.")
        send_telegram("⚠️ Nenhum voo encontrado.")

if __name__ == "__main__":
    asyncio.run(main())
