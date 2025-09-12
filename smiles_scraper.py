import os
import asyncio
import time
import traceback
from playwright.async_api import async_playwright
import requests

# -------------------------
# Configurações
# -------------------------
ORIGIN = os.getenv("ORIGIN", "GIG")
DESTINATIONS = os.getenv("DESTINATIONS", "NRT").split(",")
START_DATE = os.getenv("START_DATE", "2025-10-10")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WORKDIR = os.getcwd()


# -------------------------
# Utilitários
# -------------------------
def save_text_file(filename: str, content: str):
    path = os.path.join(WORKDIR, filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ Saved {path}")
    except Exception as e:
        print(f"❌ Erro ao salvar {path}: {e}")


def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram não configurado; pulando envio")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=20)
        print("Telegram status:", r.status_code)
    except Exception as e:
        print("Erro ao enviar Telegram:", e)


async def robust_fill(frame, selector: str, value: str):
    """Preenche um campo. Se fill falhar, injeta value via evaluate()."""
    try:
        await frame.fill(selector, value, timeout=5000)
        print(f"✅ Preencheu {selector} com {value}")
        return True
    except Exception as ex:
        print(f"⚠️ fill() falhou em {selector}: {ex}")

    # fallback: usar evaluate
    try:
        await frame.evaluate(
            """arg => {
                const el = document.querySelector(arg.sel);
                if (!el) return false;
                el.value = arg.value;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
            }""",
            {"sel": selector, "value": value},
        )
        print(f"✅ Forçou {selector} com {value} via evaluate()")
        return True
    except Exception as ex:
        print(f"❌ evaluate() também falhou em {selector}: {ex}")
        return False


async def run_scraper():
    ts = time.strftime("%Y%m%d-%H%M%S")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = await browser.new_page()

            print(f"📂 Workdir: {WORKDIR}")

            # 1) Abre a página de passagens
            url = "https://www.smiles.com.br/passagens-aereas"
            await page.goto(url, timeout=60000)
            await page.wait_for_timeout(3000)

            # Salva HTML principal
            save_text_file(f"debug_main_{ts}.html", await page.content())
            await page.screenshot(path=f"debug_main_{ts}.png", full_page=True)

            # 2) Pega explicitamente o frame 0
            frame = None
            for f in page.frames:
                if f.url.startswith("https://www.smiles.com.br/passagens"):
                    frame = f
                    break
            if not frame:
                save_text_file("error_log.txt", "❌ Não achei frame de passagens (frame 0).")
                send_telegram("❌ Scraper: não achei o frame de passagens. Veja artifacts.")
                await browser.close()
                return

            print("✅ Usando frame:", frame.url)

            # 3) Preenche origem, destino e data
            await robust_fill(frame, "#inputOrigin", ORIGIN)
            await robust_fill(frame, "#inputDestination", DESTINATIONS[0])
            await robust_fill(frame, "#_smilesflightsearchportlet_WAR_smilesbookingportlet_departure_date", START_DATE)

            await page.wait_for_timeout(1500)

            # 4) Clica no botão Buscar
            try:
                await frame.click("button[type='submit']", timeout=8000)
                print("✅ Cliquei em Buscar")
            except Exception as e:
                print("⚠️ Não consegui clicar em Buscar:", e)

            # 5) Aguarda e captura resultados
            await page.wait_for_timeout(10000)
            result_html = await frame.content()
            save_text_file(f"debug_results_{ts}.html", result_html)
            await page.screenshot(path=f"debug_results_{ts}.png", full_page=True)

            # 6) Tenta extrair blocos de voos
            selectors = [
                "div[class*='flight-card']",
                ".result",
                ".fare",
                ".flight",
            ]
            flights = []
            for sel in selectors:
                try:
                    items = await frame.locator(sel).all_inner_texts()
                    if items:
                        flights.extend(items)
                        break
                except:
                    pass

            # 7) Telegram
            if flights:
                msg = f"✈️ Resultados {ORIGIN}->{DESTINATIONS[0]} ({START_DATE}):\n\n"
                msg += "\n\n".join(f.strip() for f in flights)[:3500]
                send_telegram(msg)
            else:
                send_telegram("🔎 Scraper rodou mas não achou voos. Veja artifacts.")

            await browser.close()

    except Exception as e:
        save_text_file("error_log.txt", f"Erro geral: {e}\n{traceback.format_exc()}")
        send_telegram(f"❌ Scraper erro: {e}. Veja artifacts.")


if __name__ == "__main__":
    asyncio.run(run_scraper())
