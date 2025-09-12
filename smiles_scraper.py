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


async def save_file(filename: str, content: str):
    """Salva conteúdo em arquivo de debug"""
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ Saved {filename} (cwd={os.getcwd()})")
    except Exception as e:
        print(f"❌ Erro ao salvar {filename}: {e}")


async def run_scraper():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()

        try:
            # 1. Abre a página de passagens
            await page.goto("https://www.smiles.com.br/passagens-aereas", timeout=60000)
            await page.wait_for_timeout(5000)

            # Salva HTML principal
            html = await page.content()
            await save_file("debug_main.html", html)

            # Salva screenshot principal
            try:
                await page.screenshot(path="debug_main.png", full_page=True)
                print("✅ Saved debug_main.png")
            except Exception as e:
                print("⚠️ Erro ao salvar screenshot principal:", e)

            # 2. Lista frames disponíveis
            frames_info = []
            for i, f in enumerate(page.frames):
                frames_info.append(f"{i}: {f.url}")
                try:
                    cont = await f.content()
                    await save_file(f"debug_frame_{i}.html", cont)
                except Exception as e:
                    print(f"⚠️ Não consegui salvar frame {i}: {e}")

            await save_file("debug_frames.txt", "\n".join(frames_info))

            # 3. Escolhe frame principal de passagens
            frame = None
            for f in page.frames:
                if "smiles" in f.url and "passagens" in f.url and "chat" not in f.url and "smooch" not in f.url:
                    frame = f
                    break

            if not frame:
                print("⚠️ Nenhum frame de busca encontrado. Veja debug_frames.txt.")
                return

            print("✅ Usando frame:", frame.url)

            # 4. Salva inputs do frame
            inputs = await frame.query_selector_all("input")
            inputs_data = []
            for i, inp in enumerate(inputs):
                try:
                    attrs = await frame.evaluate(
                        """el => {
                            let atts = {};
                            for (let a of el.attributes) { atts[a.name] = a.value; }
                            return atts;
                        }""",
                        inp
                    )
                    inputs_data.append(f"Input {i}: {attrs}")
                except:
                    inputs_data.append(f"Input {i}: erro ao ler atributos")

            await save_file("debug_inputs.txt", "\n".join(inputs_data))

            # 5. Screenshot da página
            try:
                await page.screenshot(path="debug_results.png", full_page=True)
                print("✅ Saved debug_results.png")
            except Exception as e:
                print("⚠️ Erro ao salvar debug_results.png:", e)

        except Exception as e:
            print("❌ Erro durante execução:", e)

        finally:
            await browser.close()

    send_telegram("🔎 Execução finalizada. Veja artifacts (debug_main.html, debug_inputs.txt, etc).")


if __name__ == "__main__":
    asyncio.run(run_scraper())
