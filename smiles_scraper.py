import os
import asyncio
from playwright.async_api import async_playwright
import requests

# Configurações
ORIGIN = os.getenv("ORIGIN", "GIG")
DESTINATIONS = os.getenv("DESTINATIONS", "NRT").split(",")
START_DATE = os.getenv("START_DATE", "2025-09-10")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram(text: str):
    """Envia mensagem simples para o Telegram"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram não configurado")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=15)
        print("Telegram status:", r.status_code)
    except Exception as e:
        print("Telegram error:", e)


async def run_scraper():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()

        try:
            # 1. Abre a página de passagens
            await page.goto("https://www.smiles.com.br/passagens-aereas", timeout=60000)
            await page.wait_for_timeout(5000)
            print("✅ Página carregada")

            # 2. Seleciona frame correto
            frame = None
            for f in page.frames:
                if "smiles" in f.url and "passagens" in f.url and "chat" not in f.url:
                    frame = f
                    break

            if not frame:
                print("⚠️ Nenhum frame encontrado")
                return

            print("✅ Usando frame:", frame.url)

            # 3. Preenche os campos de busca
            try:
                await frame.fill("#inputOrigin", ORIGIN)
                await frame.fill("#inputDestination", DESTINATIONS[0])
                await frame.fill("#_smilesflightsearchportlet_WAR_smilesbookingportlet_departure_date", START_DATE)
                print("✅ Campos preenchidos")
            except Exception as e:
                print("❌ Erro ao preencher campos:", e)
                return

            # 4. Clica no botão de buscar
            try:
                await frame.click("button[type='submit']", timeout=10000)
                print("✅ Cliquei no botão Buscar")
            except Exception as e:
                print("⚠️ Não achei botão Buscar:", e)

            # 5. Aguarda resultados
            await page.wait_for_timeout(10000)
            html = await frame.content()
            with open("debug_results.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("✅ Saved debug_results.html")

            await page.screenshot(path="debug_results.png", full_page=True)
            print("✅ Saved debug_results.png")

        except Exception as e:
            print("❌ Erro durante execução:", e)

        finally:
            await browser.close()

    send_telegram("🔎 Execução finalizada. Veja artifacts para os resultados.")


if __name__ == "__main__":
    asyncio.run(run_scraper())
