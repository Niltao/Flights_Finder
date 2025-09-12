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

            # Salva HTML principal
            html = await page.content()
            with open("debug_main.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("✅ Saved debug_main.html")

            # Salva screenshot
            await page.screenshot(path="debug_main.png", full_page=True)

            # 2. Lista frames disponíveis
            frames_info = []
            for i, f in enumerate(page.frames):
                frames_info.append(f"{i}: {f.url}")
                try:
                    content = await f.content()
                    with open(f"debug_frame_{i}.html", "w", encoding="utf-8") as ff:
                        ff.write(content)
                except Exception as e:
                    print(f"⚠️ Não consegui salvar frame {i}: {e}")

            with open("debug_frames.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(frames_info))
            print("✅ Frames salvos em debug_frames.txt")

            # 3. Escolhe um frame de busca (ignora chat/about:blank)
            frame = None
            for f in page.frames:
                if "smiles" in f.url and "chat" not in f.url and "smooch" not in f.url and "about:" not in f.url:
                    frame = f
                    break

            if not frame:
                print("⚠️ Nenhum frame de busca encontrado. Veja debug_frames.txt.")
                return

            print("✅ Usando frame:", frame.url)

            # 4. Preenche os campos dentro do frame de passagens
            frame_html = await frame.content()
            with open("debug_passagens_frame.html", "w", encoding="utf-8") as f:
                f.write(frame_html)
            print("✅ Saved debug_passagens_frame.html")
    
            # Seletores alternativos
            origin_selectors = [
                "input[name='origin']",
                "input[placeholder*='Origem']",
                "input[aria-label*='Origem']",
                "input[id*='origin']",
                "input[type='text']"
            ]
            dest_selectors = [
                "input[name='destination']",
                "input[placeholder*='Destino']",
                "input[aria-label*='Destino']",
                "input[id*='destination']",
                "input[type='text']"
            ]
            date_selectors = [
                "input[name='departureDate']",
                "input[placeholder*='Ida']",
                "input[aria-label*='Ida']",
                "input[id*='departureDate']"
            ]
    
            async def safe_fill(selectors, value):
                for sel in selectors:
                    try:
                        await frame.fill(sel, value, timeout=5000)
                        print(f"✅ Preencheu {value} em {sel}")
                        return True
                    except:
                        pass
                print(f"⚠️ Nenhum seletor funcionou para {value}")
                return False
    
            await safe_fill(origin_selectors, ORIGIN)
            await safe_fill(dest_selectors, DESTINATIONS[0])
            await safe_fill(date_selectors, START_DATE)
    
            # Botão Buscar
            try:
                await frame.click("button:has-text('Buscar')", timeout=10000)
                print("✅ Cliquei no botão Buscar")
            except:
                print("⚠️ Não achei botão Buscar")


            # 5. Salva HTML após buscar
            result_html = await frame.content()
            with open("debug_results.html", "w", encoding="utf-8") as f:
                f.write(result_html)
            await frame.screenshot(path="debug_results.png", full_page=True)
            print("✅ Saved debug_results.html and debug_results.png")

        except Exception as e:
            print("❌ Erro durante execução:", e)

        finally:
            await browser.close()

    send_telegram("🔎 Execução finalizada. Veja artifacts (debug_main.html, debug_frames.txt, debug_results.html).")


if __name__ == "__main__":
    asyncio.run(run_scraper())

