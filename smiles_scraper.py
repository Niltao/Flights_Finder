import asyncio
import json
import requests
import os
from playwright.async_api import async_playwright

ORIGIN = os.getenv("ORIGIN", "GIG")
DESTINATION = os.getenv("DESTINATION", "HND")
DATE = os.getenv("DATE", "2025-09-15")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram não configurado.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"})
    except Exception as e:
        print("Erro Telegram:", e)

async def search_flight(origin, destination, date):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context()
        page = await context.new_page()

        print("🌍 Acessando site Smiles...")
        await page.goto("https://www.smiles.com.br/", timeout=90000)

        # salva HTML inicial para debug
        await page.screenshot(path="debug_home.png")
        with open("debug_home.html", "w", encoding="utf-8") as f:
            f.write(await page.content())

        try:
            # Espera pelo iframe de busca
            print("⌛ Esperando iframe da busca...")
            frame = await page.frame_locator("iframe").first
            await frame.locator("input[placeholder*='Digite a origem']").wait_for(timeout=60000)

            print("⌛ Preenchendo origem/destino/data...")
            await frame.fill("input[placeholder*='Digite a origem']", origin)
            await frame.fill("input[placeholder*='Digite o destino']", destination)
            await frame.fill("input[placeholder*='Ida']", date)

            print("🔎 Clicando buscar...")
            await frame.locator("button:has-text('Buscar')").click()

            # aguarda resultados
            await frame.locator("div[class*='flight-card']").first.wait_for(timeout=120000)
            flights = await frame.locator("div[class*='flight-card']").all_inner_texts()
        except Exception as e:
            print("❌ Erro ao buscar:", e)
            await page.screenshot(path="debug_error.png")
            with open("debug_error.html", "w", encoding="utf-8") as f:
                f.write(await page.content())
            flights = []

        await browser.close()
        return flights

async def main():
    flights = await search_flight(ORIGIN, DESTINATION, DATE)
    if flights:
        text = "✈️ Resultados encontrados:\n\n" + "\n\n".join(flights[:5])
        print(text)
        send_telegram(text)
    else:
        msg = "⚠️ Nenhum voo encontrado."
        print(msg)
        send_telegram(msg)

if __name__ == "__main__":
    asyncio.run(main())
