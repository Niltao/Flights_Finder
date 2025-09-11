# smiles_scraper.py
import asyncio
import json
import requests
import os
import time
import traceback
from typing import Tuple, Optional
from playwright.async_api import async_playwright, Page, Frame

# ----------------------------
# CONFIGURAÇÕES
# ----------------------------
ORIGIN = os.getenv("ORIGIN", "RIO")
DESTINATION = os.getenv("DESTINATION", "HND")
DATE = os.getenv("DATE", "2025-09-15")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Timeout total (segundos) para encontrar inputs/frames
FIND_TIMEOUT = 60


# ----------------------------
# UTILIDADES TELEGRAM
# ----------------------------
def send_telegram(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram não configurado; pulando envio.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            print("❌ Falha ao enviar Telegram:", r.status_code, r.text[:400])
    except Exception as e:
        print("❌ Erro ao enviar Telegram:", e)


def send_telegram_image(image_path: str, caption: str = "") -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram não configurado; pulando envio de imagem.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        with open(image_path, "rb") as f:
            files = {"photo": f}
            data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption}
            r = requests.post(url, data=data, files=files, timeout=60)
            if r.status_code != 200:
                print("❌ Falha ao enviar imagem:", r.status_code, r.text[:400])
    except Exception as e:
        print("❌ Erro ao enviar imagem:", e)


# ----------------------------
# HELPERS PARA BUSCA DE SELECTORS EM FRAMES
# ----------------------------
async def _element_visible_in_frame(frame: Frame, selector: str) -> bool:
    try:
        el = await frame.query_selector(selector)
        if not el:
            return False
        # is_visible pode lançar em alguns frames cross-origin; envolver em try
        try:
            return await el.is_visible()
        except Exception:
            return True
    except Exception:
        return False


async def find_frame_and_selector(page: Page, selectors: list, timeout: int = FIND_TIMEOUT) -> Tuple[Optional[Frame], Optional[str]]:
    """
    Procura por qualquer selector listado primeiro no page e depois em cada frame.
    Retorna (frame_like, selector) onde frame_like pode ser o `page` (tem métodos semelhantes)
    ou um Frame real.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        # Tente no page principal
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    try:
                        if await el.is_visible():
                            print(f"Encontrado selector {sel} no page principal")
                            return page, sel
                    except Exception:
                        return page, sel
            except Exception:
                pass

        # Tente em todos os frames
        frames = page.frames
        for f in frames:
            for sel in selectors:
                try:
                    if await _element_visible_in_frame(f, sel):
                        print(f"Encontrado selector {sel} no frame: {f.url}")
                        return f, sel
                except Exception:
                    pass

        await asyncio.sleep(1)
    return None, None


# ----------------------------
# SCRAPER RESILIENTE
# ----------------------------
async def search_flight(origin: str, destination: str, date: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context()
        page = await context.new_page()

        print("Abrindo https://www.smiles.com.br/emissoes ...")
        await page.goto("https://www.smiles.com.br/emissoes", timeout=60000)

        # Seletores possíveis (vários tries para tolerância a mudanças)
        origin_selectors = [
            'input[name="origin"]',
            'input[placeholder*="Origem"]',
            'input[aria-label*="Origem"]',
            'input[id*="origin"]',
            'input[placeholder*="De onde"]'
        ]
        destination_selectors = [
            'input[name="destination"]',
            'input[placeholder*="Destino"]',
            'input[aria-label*="Destino"]',
            'input[id*="destination"]'
        ]
        date_selectors = [
            'input[name="departureDate"]',
            'input[placeholder*="Ida"]',
            'input[aria-label*="Ida"]',
            'input[id*="departureDate"]'
        ]
        search_button_selectors = [
            'button[type="submit"]',
            'button:has-text("Buscar")',
            'button:has-text("Pesquisar")'
        ]
        result_selectors = [
            "div[class*='flight-card']",
            "div[class*='result']",
            "ul[class*='results']",
            ".search-results"
        ]

        # Encontrar frame / selector para Origem
        frame_or_page, origin_sel = await find_frame_and_selector(page, origin_selectors, timeout=FIND_TIMEOUT)
        if not frame_or_page:
            await _save_debug(page, prefix="no_origin_found")
            await browser.close()
            raise RuntimeError("Campo Origem não encontrado (debug salvo)")

        # Preencher origem
        print(f"Preenchendo origem usando selector {origin_sel} ...")
        try:
            await frame_or_page.fill(origin_sel, origin)
            # pressionar ENTER no campo
            try:
                await frame_or_page.press(origin_sel, "Enter")
            except Exception:
                pass
        except Exception as e:
            print("Erro ao preencher origem:", e)

        # Encontrar e preencher destino (tenta no mesmo frame antes de re-procurar)
        dest_sel = None
        try:
            # se o mesmo frame contém destino
            for s in destination_selectors:
                if await _element_visible_in_frame(frame_or_page, s):
                    dest_sel = s
                    break
        except Exception:
            dest_sel = None

        if not dest_sel:
            frame_or_page, dest_sel = await find_frame_and_selector(page, destination_selectors, timeout=FIND_TIMEOUT)
            if not frame_or_page:
                await _save_debug(page, prefix="no_destination_found")
                await browser.close()
                raise RuntimeError("Campo Destino não encontrado (debug salvo)")

        print(f"Preenchendo destino usando selector {dest_sel} ...")
        try:
            await frame_or_page.fill(dest_sel, destination)
            try:
                await frame_or_page.press(dest_sel, "Enter")
            except Exception:
                pass
        except Exception as e:
            print("Erro ao preencher destino:", e)

        # Encontrar e preencher data
        date_sel = None
        try:
            for s in date_selectors:
                if await _element_visible_in_frame(frame_or_page, s):
                    date_sel = s
                    break
        except Exception:
            date_sel = None

        if not date_sel:
            frame_or_page, date_sel = await find_frame_and_selector(page, date_selectors, timeout=FIND_TIMEOUT)
            if not frame_or_page:
                await _save_debug(page, prefix="no_date_found")
                await browser.close()
                raise RuntimeError("Campo Data não encontrado (debug salvo)")

        print(f"Preenchendo data usando selector {date_sel} ...")
        try:
            await frame_or_page.fill(date_sel, date)
            try:
                await frame_or_page.press(date_sel, "Enter")
            except Exception:
                pass
        except Exception as e:
            print("Erro ao preencher data:", e)

        # Clicar no botão buscar (tenta vários seletores)
        clicked = False
        for sel in search_button_selectors:
            try:
                if await _element_visible_in_frame(frame_or_page, sel):
                    print(f"Clicando botão de busca com selector {sel}")
                    await frame_or_page.click(sel)
                    clicked = True
                    break
            except Exception:
                pass

        if not clicked:
            # tentar achar o botão em toda a página/frames
            frame_btn, btn_sel = await find_frame_and_selector(page, search_button_selectors, timeout=15)
            if frame_btn and btn_sel:
                print(f"Clicando botão de busca com selector {btn_sel} em frame {getattr(frame_btn, 'url', 'page')}")
                await frame_btn.click(btn_sel)
                clicked = True

        if not clicked:
            print("⚠️ Não foi possível clicar no botão Buscar; salvando debug.")
            await _save_debug(page, prefix="no_click_button")
            await browser.close()
            raise RuntimeError("Botão Buscar não encontrado/clicável (debug salvo)")

        # Esperar resultados (procura em page e em frames)
        print("Aguardando resultados...")
        deadline = time.time() + FIND_TIMEOUT
        flights = []
        while time.time() < deadline:
            # procurar por qualquer seletor de resultado nos frames
            for sel in result_selectors:
                # page
                try:
                    locs = await page.locator(sel).all_inner_texts()
                    if locs:
                        flights = locs
                        break
                except Exception:
                    pass
                # frames
                for f in page.frames:
                    try:
                        locs = await f.locator(sel).all_inner_texts()
                        if locs:
                            flights = locs
                            break
                    except Exception:
                        pass
                if flights:
                    break
            if flights:
                break
            await asyncio.sleep(1)

        await browser.close()
        return flights


# salva debug: screenshot + html principal + frames content
async def _save_debug(page: Page, prefix: str = "debug"):
    try:
        img_path = f"{prefix}_page.png"
        html_path = f"{prefix}_page.html"
        print("Salvando screenshot em", img_path)
        await page.screenshot(path=img_path, full_page=True)
        content = await page.content()
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(content)

        # salvar conteúdo dos frames (quando possível)
        for i, f in enumerate(page.frames):
            try:
                fname = f"{prefix}_frame_{i}.html"
                print("Salvando frame", i, "url=", f.url)
                cont = await f.content()
                with open(fname, "w", encoding="utf-8") as ff:
                    ff.write(f"<!-- frame url: {f.url} -->\n")
                    ff.write(cont)
            except Exception as e:
                print("Não foi possível salvar conteúdo do frame", i, ":", e)

        # tentar enviar ao Telegram (se configurado)
        try:
            send_telegram("⚠️ Debug salvo automaticamente (ver arquivos).")
            send_telegram_image(img_path, caption="Debug screenshot")
        except Exception as e:
            print("Falha ao enviar debug pro Telegram:", e)

    except Exception as ex:
        print("Erro ao salvar debug:", ex)
        traceback.print_exc()


# ----------------------------
# MAIN
# ----------------------------
async def main():
    try:
        flights = await search_flight(ORIGIN, DESTINATION, DATE)
        if flights:
            # limitar tamanho da mensagem
            joined = "\n\n".join(flights)
            msg = f"✈️ Resultados para {ORIGIN} → {DESTINATION} em {DATE}:\n\n{joined}"
            # truncar para evitar limite do Telegram (4096)
            if len(msg) > 3800:
                msg = msg[:3800] + "\n\n...(resultado truncado)"
            print(msg)
            send_telegram(msg)
        else:
            print("Nenhum voo encontrado.")
            send_telegram(f"⚠️ Nenhum voo encontrado para {ORIGIN}->{DESTINATION} em {DATE}.")
    except Exception as e:
        print("Erro durante execução:", e)
        traceback.print_exc()
        # tentar salvar debug e enviar
        try:
            # a rotina de debug precisa do page, mas se não foi possível, apenas notifica
            send_telegram(f"❌ Erro no scraper: {e}")
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
