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

        # Acessa o site da Smiles
        await page.goto("https://www.smiles.com.br/", timeout=60000)

        # Garante que o botão de "Passagens Aéreas" esteja presente e clica
        await page.wait_for_selector('a[href*="passagens-aereas"]', timeout=60000)
        await page.click('a[href*="passagens-aereas"]')

        # Agora espera o formulário carregar
        await page.wait_for_selector('input[placeholder*="Origem"]', timeout=60000)

        # Campo Origem
        await page.fill('input[placeholder*="Origem"]', origin)
        await page.keyboard.press("Enter")

        # Campo Destino
        await page.wait_for_selector('input[placeholder*="Destino"]', timeout=60000)
        await page.fill('input[placeholder*="Destino"]', destination)
        await page.keyboard.press("Enter")

        # Campo Data (Ida)
        await page.wait_for_selector('input[placeholder*="Ida"]', timeout=60000)
        await page.fill('input[placeholder*="Ida"]', date)
        await page.keyboard.press("Enter")

        # Botão Buscar
        await page.wait_for_selector('button:has-text("Buscar")', timeout=60000)
        await page.click('button:has-text("Buscar")')

        # Espera os resultados carregarem
        await page.wait_for_selector("div.flight-card", timeout=60000)

        flights = await page.locator("div.flight-card").all_inner_texts()

        await browser.close()
        return flights

async def main():
    flights = await search_flight(ORIGIN, DESTINATION, DATE)
    print(json.dumps(flights, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
