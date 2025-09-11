import asyncio
import json
import requests
from playwright.async_api import async_playwright
import os

# ======================
# CONFIGURAÇÕES
# ======================
ORIGIN = "RIO"
DESTINATION = "HND"
DATE = "2025-09-15"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ======================
# FUNÇÃO TELEGRAM
# ======================
def send_telegram(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram não configurado; pulando envio.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            print("❌ Telegram send failed:", r.status_code, r.text[:200])
    except Exception as e:
        print("❌ Telegram send error:", e)


# ======================
# SCRAPER
# ======================
async def search_flight(origin, destination, date):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context()
        page = await context.new_page()

        # Vai direto para a página de emissão
        await page.goto("https://www.smiles.com.br/emissoes", timeout=60000)

        # Espera iframe carregar
        await page.wait_for_selector("iframe", timeout=60000)
        iframe_element = await page.query_selector("iframe")
        frame = await iframe_element.content_frame()

        # Origem
        await frame.wait_for_selector('input[name="origin"], input[placeholder*="Origem"]', timeout=60000)
        await frame.fill('input[name="origin"], input[placeholder*="Origem"]', origin)
        await frame.keyboard.press("Enter")

        # Destino
        await frame.wait_for_selector('input[name="destination"], input[placeholder*="Destino"]', timeout=60000)
        await frame.fill('input[name="destination"], input[placeholder*="Destino"]', destination)
        await frame.keyboard.press("Enter")

        # Data
        await frame.wait_for_selector('input[name="departureDate"], input[placeholder*="Ida"]', timeout=60000)
        await frame.fill('input[name="departureDate"], input[placeholder*="Ida"]', date)
        await frame.keyboard.press("Enter")

        # Botão Buscar
        await frame.wait_for_selector('button[type="submit"], button:has-text("Buscar")', timeout=60000)
        await frame.click('button[type="submit"], button:has-text("Buscar")')

        # Resultados
        await frame.wait_for_selector("div[class*='flight-card']", timeout=60000)
        flights = await frame.locator("div[class*='flight-card']").all_inner_texts()

        await browser.close()
        return flights


# ======================
# MAIN
# ======================
async def main():
    flights = await search_flight(ORIGIN, DESTINATION, DATE)

    if flights:
        result_text = "\n\n".join(flights)
        print(result_text)
        send_telegram(f"✈️ Resultados encontrados:\n\n{result_text}")
    else:
        print("Nenhum voo encontrado.")
        send_telegram("⚠️ Nenhum voo encontrado na pesquisa.")


if __name__ == "__main__":
    asyncio.run(main())
