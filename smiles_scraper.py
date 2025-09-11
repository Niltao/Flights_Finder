import asyncio
import json
from playwright.async_api import async_playwright

ORIGIN = "RIO"
DESTINATION = "HND"
DATE = "2025-09-15"

async def search_flight(origin, destination, date):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Vai direto pra busca de passagens Smiles
        await page.goto("https://www.smiles.com.br/", timeout=60000)

        # Campo Origem
        await page.wait_for_selector('input[placeholder="Digite a origem"]', timeout=60000)
        await page.fill('input[placeholder="Digite a origem"]', origin)
        await page.keyboard.press("Enter")

        # Campo Destino
        await page.wait_for_selector('input[placeholder="Digite o destino"]', timeout=60000)
        await page.fill('input[placeholder="Digite o destino"]', destination)
        await page.keyboard.press("Enter")

        # Campo Data
        await page.wait_for_selector('input[placeholder="Ida"]', timeout=60000)
        await page.fill('input[placeholder="Ida"]', date)
        await page.keyboard.press("Enter")

        # Botão Buscar
        await page.wait_for_selector('button:has-text("Buscar")', timeout=60000)
        await page.click('button:has-text("Buscar")')

        # Espera os resultados aparecerem
        await page.wait_for_selector("div.flight-card", timeout=60000)

        flights = await page.locator("div.flight-card").all_inner_texts()

        await browser.close()
        return flights

async def main():
    flights = await search_flight(ORIGIN, DESTINATION, DATE)
    print(json.dumps(flights, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
