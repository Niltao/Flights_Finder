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

WORKDIR = os.getcwd()  # diretório atual no GitHub Actions


def save_text_file(filename: str, content: str):
    """Salva texto em arquivo absoluto"""
    path = os.path.join(WORKDIR, filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ Saved {path}")
    except Exception as e:
        print(f"❌ Erro ao salvar {path}: {e}")


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
            print(f"📂 Working dir: {WORKDIR}")

            # 1. Abre a página de passagens
            await page.goto("https://www.smiles.com.br/passagens-aereas", timeout=60000)
            await page.wait_for_timeout(5000)

            # Salva HTML principal
            html = await page.content()
            save_text_file("debug_main.html", html)

            # Screenshot principal
            try:
                path = os.path.join(WORKDIR, "debug_main.png")
                await page.screenshot(path=path, full_page=True)
                print(f"✅ Saved {path}")
            except Exception as e:
                save_text_file("error_log.txt", f"Erro screenshot main: {e}")

            # 2. Seleciona frame correto
            frame = None
            for f in page.frames:
                if "smiles" in f.url and "passagens" in f.url and "chat" not in f.url:
                    frame = f
                    break

            if not frame:
                save_text_file("error_log.txt", "Nenhum frame encontrado")
                return

            print("✅ Usando frame:", frame.url)

            # 3. Preenche os campos
            await frame.fill("#inputOrigin", ORIGIN)
            await frame.fill("#inputDestination", DESTINATIONS[0])
            await frame.fill("#_smilesflightsearchportlet_WAR_smilesbookingportlet_departure_date", START_DATE)
            print("✅ Campos preenchidos")

            # 4. Buscar
            await frame.click("button[type='submit']", timeout=10000)
            print("✅ Cliquei no botão Buscar")

            # 5. Aguarda resultados
            await page.wait_for_timeout(10000)
            html = await frame.content()
            save_text_file("debug_results.html", html)

            path = os.path.join(WORKDIR, "debug_results.png")
            await page.screenshot(path=path, full_page=True)
            print(f"✅ Saved {path}")

        except Exception as e:
            save_text_file("error_log.txt", f"Erro geral: {e}")

        finally:
            await browser.close()

    send_telegram("🔎 Execução finalizada. Veja artifacts (debug_main.html, debug_results.html).")


if __name__ == "__main__":
    asyncio.run(run_scraper())
