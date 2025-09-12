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

        # Espera a barra de busca principal
        print("⌛ Esperando campo de origem...")
        await page.wait_for_selector("input[placeholder*='Digite a origem']", timeout=90000)
        await page.fill("input[placeholder*='Digite a origem']", origin)
        await page.keyboard.press("Enter")

        print("⌛ Esperando campo de destino...")
        await page.wait_for_selector("input[placeholder*='Digite o destino']", timeout=90000)
        await page.fill("input[placeholder*='Digite o destino']", destination)
        await page.keyboard.press("Enter")

        print("⌛ Preenchendo data...")
        await page.wait_for_selector("input[placeholder*='Ida']", timeout=90000)
        await page.fill("input[placeholder*='Ida']", date)
        await page.keyboard.press("Enter")

        # Clica em buscar
        print("🔎 Clicando em buscar...")
        await page.wait_for_selector("button:has-text('Buscar')", timeout=90000)
        await page.click("button:has-text('Buscar')")

        # Aguarda resultados
        print("⌛ Aguardando resultados...")
        try:
            await page.wait_for_selector("div[class*='flight-card']", timeout=120000)
            flights = await page.locator("div[class*='flight-card']").all_inner_texts()
        except Exception as e:
            print("❌ Nenhum resultado carregado:", e)
            await page.screenshot(path="debug_no_results.png")
            flights = []

        await browser.close()
        return flights

async def main():
    flights = await search_flight(ORIGIN, DESTINATION, DATE)
    if flights:
        text = "✈️ Resultados encontrados:\n\n" + "\n\n".join(flights[:5])  # mostra só 5 para não lotar
        print(text)
        send_telegram(text)
    else:
        msg = "⚠️ Nenhum voo encontrado."
        print(msg)
        send_telegram(msg)

if __name__ == "__main__":
    asyncio.run(main())
