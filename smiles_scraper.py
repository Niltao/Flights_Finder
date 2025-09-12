import os
import asyncio
import time
import traceback
from playwright.async_api import async_playwright, TimeoutError as PWTimeoutError
import requests

# -------------------------
# Configurações (env vars)
# -------------------------
ORIGIN = os.getenv("ORIGIN", "GIG")
DESTINATIONS = os.getenv("DESTINATIONS", "NRT").split(",")
START_DATE = os.getenv("START_DATE", "2025-10-10")  # exemplo
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


def save_bytes_file(filename: str, bts: bytes):
    path = os.path.join(WORKDIR, filename)
    try:
        with open(path, "wb") as f:
            f.write(bts)
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


# -------------------------
# Helpers Playwright
# -------------------------
async def robust_fill(frame, selector: str, value: str, try_fill_timeout=5000) -> bool:
    """
    Tenta preencher com frame.fill(). Se falhar (visibilidade / timeout),
    usa frame.evaluate(...) passando um objeto único para forçar o value e disparar events.
    Retorna True se conseguiu, False caso contrário.
    """
    try:
        await frame.fill(selector, value, timeout=try_fill_timeout)
        # tenta ENTER para selecionar autocomplete
        try:
            await frame.press(selector, "Enter", timeout=500)
        except Exception:
            pass
        print(f"✅ Preencheu via fill() {selector} <- {value}")
        return True
    except Exception as ex:
        print(f"⚠️ fill() falhou para {selector}: {ex} — tentando via evaluate()")

    # evaluate — usar um único argumento (obj)
    try:
        await frame.evaluate(
            """arg => {
                const sel = arg.sel;
                const value = arg.value;
                const el = document.querySelector(sel);
                if (!el) return false;
                // tornar visível caso esteja escondido (tentativa)
                try {
                    el.style.display = '';
                } catch(e){}
                el.value = value;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                // tentar focus/blur para disparar listeners
                try { el.focus(); el.blur(); } catch(e){}
                return true;
            }""",
            {"sel": selector, "value": value},
        )
        print(f"✅ Preencheu via evaluate() {selector} <- {value}")
        # tentar ENTER também
        try:
            await frame.press(selector, "Enter", timeout=500)
        except Exception:
            pass
        return True
    except Exception as ex:
        print(f"❌ evaluate() também falhou para {selector}: {ex}")
        return False


async def robust_click(frame, selectors):
    """
    Tenta clicar em uma lista de seletores até um funcionar.
    Retorna True se clicou em algum, False caso contrário.
    """
    for sel in selectors:
        try:
            await frame.click(sel, timeout=5000)
            print(f"✅ Clique em {sel}")
            return True
        except Exception as ex:
            print(f"⚠️ click() falhou em {sel}: {ex}")
    # tentativa via evaluate para forçar click (quando botão não é "clicável" direto)
    try:
        await frame.evaluate(
            """sel => {
                const el = document.querySelector(sel);
                if (el) { el.click(); return true; }
                return false;
            }""",
            selectors[0] if selectors else "button[type='submit']",
        )
        print("✅ Clique via evaluate() executado")
        return True
    except Exception as ex:
        print("❌ Clique via evaluate() falhou:", ex)
        return False


# -------------------------
# Rotina principal
# -------------------------
async def run_scraper():
    ts = time.strftime("%Y%m%d-%H%M%S")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = await browser.new_page()

            print(f"📂 Workdir: {WORKDIR}")

            # 1) Abre a home / passagens
            url = "https://www.smiles.com.br/passagens-aereas"
            print("Abrindo:", url)
            await page.goto(url, timeout=60000)
            await page.wait_for_timeout(3500)

            # Salva HTML + screenshot principal
            try:
                html = await page.content()
                save_text_file(f"debug_main_{ts}.html", html)
            except Exception as e:
                save_text_file("error_log.txt", f"Erro ao salvar main html: {e}\n{traceback.format_exc()}")

            try:
                screenshot_path = os.path.join(WORKDIR, f"debug_main_{ts}.png")
                await page.screenshot(path=screenshot_path, full_page=True)
                print("✅ Saved", screenshot_path)
            except Exception as e:
                save_text_file("error_log.txt", f"Erro ao salvar main screenshot: {e}\n{traceback.format_exc()}")

            # 2) Salva frames e procura o frame de passagens
            frames_info = []
            for i, f in enumerate(page.frames):
                frames_info.append(f"{i}: {f.url}")
                try:
                    cont = await f.content()
                    save_text_file(f"debug_frame_{i}_{ts}.html", cont)
                except Exception as e:
                    print(f"⚠️ Não consegui salvar frame {i}: {e}")

            save_text_file(f"debug_frames_{ts}.txt", "\n".join(frames_info))
            print("Frames listados:", frames_info)

            # 3) escolher o frame que contém o formulário
            frame = None
            for f in page.frames:
                if "passagens" in f.url and "chat" not in f.url:
                    frame = f
                    break
            if not frame:
                # se não encontrar, pegar o primeiro que tem inputs
                for f in page.frames:
                    try:
                        cnt = await f.query_selector_all("input")
                        if cnt:
                            frame = f
                            break
                    except Exception:
                        pass

            if not frame:
                save_text_file("error_log.txt", "Nenhum frame apropriado encontrado.")
                await browser.close()
                send_telegram("❌ Scraper: nenhum frame encontrado. Confira artifacts.")
                return

            print("✅ Usando frame:", getattr(frame, "url", "<frame>"))

            # 4) Seletores conhecidos (detectados no debug_inputs anteriormente)
            origin_sel = "#inputOrigin"
            dest_sel = "#inputDestination"
            date_sel = "#_smilesflightsearchportlet_WAR_smilesbookingportlet_departure_date"

            # 5) Preencher origem/destino/data (robusto)
            ok_o = await robust_fill(frame, origin_sel, ORIGIN)
            ok_d = await robust_fill(frame, dest_sel, DESTINATIONS[0])
            ok_date = await robust_fill(frame, date_sel, START_DATE)

            if not (ok_o and ok_d):
                save_text_file("error_log.txt", f"Não foi possível preencher Origem/Destino (ok_o={ok_o}, ok_d={ok_d})")
                # prosseguir mesmo assim, para salvar debug
            if not ok_date:
                save_text_file("error_log.txt", "Não foi possível preencher a Data com os métodos tentados.")

            # Aguardar pequenas animações / sugestões
            await page.wait_for_timeout(1200)

            # 6) clicar no botão Buscar (tenta variações)
            clicked = await robust_click(frame, ["button[type='submit']", "button:has-text('Buscar')", "button:has-text('Pesquisar')"])
            if not clicked:
                save_text_file("error_log.txt", "Botão Buscar não foi clicado.")

            # 7) Esperar resultados — procurar por selectors comuns
            result_selectors = [
                "div[class*='flight-card']",
                ".search-results",
                ".results",
                "ul.results",
                ".result",
                ".fare",
                ".flight"
            ]

            flights_texts = []
            deadline = time.time() + 25
            while time.time() < deadline and not flights_texts:
                # checar no próprio frame
                for sel in result_selectors:
                    try:
                        items = await frame.locator(sel).all_inner_texts()
                        if items:
                            flights_texts.extend(items)
                            break
                    except Exception:
                        pass
                # checar na page (alguns resultados aparecem fora do frame)
                if not flights_texts:
                    for sel in result_selectors:
                        try:
                            items = await page.locator(sel).all_inner_texts()
                            if items:
                                flights_texts.extend(items)
                                break
                        except Exception:
                            pass
                if flights_texts:
                    break
                await asyncio.sleep(1)

            # 8) salvar resultado do frame e screenshot final
            try:
                res_html = await frame.content()
                save_text_file(f"debug_results_{ts}.html", res_html)
            except Exception as e:
                save_text_file("error_log.txt", f"Erro ao salvar resultado HTML: {e}\n{traceback.format_exc()}")

            try:
                final_screenshot = os.path.join(WORKDIR, f"debug_results_{ts}.png")
                await page.screenshot(path=final_screenshot, full_page=True)
                print("✅ Saved", final_screenshot)
            except Exception as e:
                save_text_file("error_log.txt", f"Erro ao salvar screenshot final: {e}\n{traceback.format_exc()}")

            # 9) enviar Telegram com resultados (ou aviso)
            if flights_texts:
                # compactar e truncar para evitar limites do Telegram
                joined = "\n\n".join([t.strip() for t in flights_texts])[:3800]
                msg = f"✈️ Resultados {ORIGIN}->{DESTINATIONS[0]} em {START_DATE}:\n\n{joined}"
                send_telegram(msg)
            else:
                send_telegram("🔎 Scraper rodou mas não encontrou voos. Veja artifacts (debug_results_*.html, debug_frames_*.txt).")

            await browser.close()

    except Exception as e:
        # erro fatal
        save_text_file("error_log.txt", f"Erro geral: {e}\n{traceback.format_exc()}")
        send_telegram(f"❌ Erro no scraper: {e}. Veja error_log.txt nos artifacts.")


if __name__ == "__main__":
    asyncio.run(run_scraper())
