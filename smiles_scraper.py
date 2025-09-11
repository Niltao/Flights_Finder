import os
import json
import asyncio
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
import requests

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

ORIGIN = os.getenv("ORIGIN", "GIG")
DESTINATIONS = os.getenv("DESTINATIONS", "HND,NRT").split(",")
START_DATE = os.getenv("START_DATE", datetime.now().strftime("%Y-%m-%d"))
DAYS_RANGE = int(os.getenv("DAYS_RANGE", "30"))
LIMIT = int(os.getenv("LIMIT", "170000"))  # limite em milhas


async def search_flight(origin, destination, date, page):
    url = "https://www.smiles.com.br/emissao"  # página de busca
    await page.goto(url, timeout=60000)

    # Seleciona campos de origem, destino e data
    await page.fill('input[name="origin"]', origin)
    await page.fill('input[name="destination"]', destination)
    await page.fill('input[name="departureDate"]', date)

    # Clica no botão de busca
    await page.click('button[type="submit"]')
    await page.wait_for_timeout(10000)  # aguarda resultados carregarem

    # Captura os preços exibidos
    prices = []
    items = await page.query_selector_all("span[class*=price]")
    for item in items:
        text = await item.inner_text()
        try:
            val = int(text.replace(".", "").replace(",", "").strip())
            prices.append(val)
        except:
            continue

    return prices if prices else None


async def run():
    results = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        start_date = datetime.strptime(START_DATE, "%Y-%m-%d")

        for dest in DESTINATIONS:
            all_prices = []
            for i in range(DAYS_RANGE):
                date = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
                prices = await search_flight(ORIGIN, dest, date, page)
                if prices:
                    all_prices.extend([(date, p) for p in prices])

            if all_prices:
                best = min(all_prices, key=lambda x: x[1])
                results[dest] = {"best": best, "all": all_prices}
            else:
                results[dest] = {"best": None, "all": []}

        await browser.close()

    # salva resposta
    with open("last_response.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # envia para o Telegram
    for dest, data in results.items():
        header = f"🔎 Varredura Smiles ({ORIGIN} → {dest})\nLimite configurado: {LIMIT:,} milhas"
        if data["best"] is None:
            message = f"{header}\n⚠️ Nenhum voo encontrado."
        else:
            best_date, best_price = data["best"]
            if best_price <= LIMIT:
                message = f"{header}\n✅ Melhor voo: {best_price:,} milhas em {best_date}"
            else:
                message = f"{header}\n⚠️ Nenhum voo abaixo do limite.\nℹ️ Melhor encontrado: {best_price:,} milhas em {best_date}"

        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": message},
        )


if __name__ == "__main__":
    asyncio.run(run())
