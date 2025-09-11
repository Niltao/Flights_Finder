import asyncio
import json
from playwright.async_api import async_playwright

ORIGIN = "RIO"
DESTINATION = "HND"
DATE = "2025-09-15"

async def search_flight(origin, destination, date):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context()
        page = await context.new_page()

        # Vai direto para a página de emissão de passagens
        await page.goto("https://www.smiles.com.br/emissoes", timeout=60000)

        # Campo Origem
        await page.wait_for_selector('input[name="origin"]', timeout=60000)
        await page.fill('input[name="origin"]', origin)
        await page.keyboard.press("Enter")

        # Campo Destino
        await page.wait_for_selector('input[name="destination"]', timeout=60000)
        await page.fill('input[name="destination"]', destination)
        await page.keyboard.press("Enter")

        # Campo Data de Ida
        await page.wait_for_selector('input[name="departureDate"]', timeout=60000)
        await page.fill('input[name="departureDate"]', date)
        await page.keyboard.press("Enter")

        # Botão Buscar
        await page.wait_for_selector('button[type="submit"]', timeout=60000)
        await page.click('button[type="submit"]')

        # Espera resultados
        await page.wait_for_selector("div[class*='flight-card']", timeout=60000)
        flights = await page.locator("div[class*='flight-card']").all_inner_texts()

        await browser.close()
        return flights

async def main():
    flights = await search_flight(ORIGIN, DESTINATION, DATE)
    print(json.dumps(flights, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
