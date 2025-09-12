# smiles_scraper.py
# Scraper Smiles com Playwright
# Busca passagens, salva CSV e envia resumo por Telegram

import os
import csv
import asyncio
import re
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
import requests

# -----------------------
# CONFIG
# -----------------------
ORIGIN = os.getenv("ORIGIN", "GIG")
DESTINATIONS = os.getenv("DESTINATIONS", "NRT,HND").split(",")
START_DATE = os.getenv("START_DATE", "2025-09-10")   # YYYY-MM-DD
DAYS_RANGE = int(os.getenv("DAYS_RANGE", "90"))
MILES_LIMIT = 170000

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# -----------------------
# UTILIDADES
# -----------------------
def send_telegram(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram não configurado; ignorando envio.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            print("Erro Telegram:", r.status_code, r.text[:200])
    except Exception as e:
        print("Telegram send error:", e)


def extract_number_from_text(s: str):
    if not s:
        return None
    s2 = re.sub(r"[^\d]", "", s)
    return int(s2) if s2 else None


# -----------------------
# SCRAPER
# -----------------------
async def run_scraper():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://www.smiles.com.br", timeout=60000)

        # Fecha banner de cookies
        try:
            await page.click("text=Aceitar", timeout=5000)
            print("Cookies aceitos.")
        except:
            print("Cookies não apareceram.")

        # Fecha popup inicial
        try:
            await page.click("button[aria-label='Fechar']", timeout=5000)
            print("Popup fechado.")
        except:
            print("Popup não apareceu.")

        all_rows = []

        start = datetime.fromisoformat(START_DATE).date()
        for dest in DESTINATIONS:
            for i in range(DAYS_RANGE):
                d = start + timedelta(days=i)
                dstr = d.strftime("%Y-%m-%d")

                print(f"Buscando {ORIGIN} -> {dest} em {dstr}")

                try:
                    # Preenche origem
                    await page.fill("input[placeholder='Origem']", ORIGIN)
                    await page.keyboard.press("Enter")

                    # Preenche destino
                    await page.fill("input[placeholder='Destino']", dest)
                    await page.keyboard.press("Enter")

                    # Data de ida
                    await page.fill("input[placeholder='Data de ida']", dstr)
                    await page.keyboard.press("Enter")

                    # Clica em buscar
                    await page.click("button:has-text('Buscar')")

                    # Aguarda resultados
                    await page.wait_for_selector("text=milhas", timeout=20000)

                    # Extrai resultados
                    elements = await page.locator("text=milhas").all_inner_texts()

                    for e in elements:
                        miles = extract_number_from_text(e)
                        if miles and miles <= MILES_LIMIT:
                            all_rows.append({
                                "origin": ORIGIN,
                                "destination": dest,
                                "date": dstr,
                                "miles": miles
                            })
                except Exception as e:
                    print("Erro na busca:", e)
                    continue

        await browser.close()

        # Salva CSV
        if all_rows:
            fname = f"results_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
            with open(fname, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
                writer.writeheader()
                writer.writerows(all_rows)
            print("Salvo:", fname)

            best = min(all_rows, key=lambda x: x["miles"])
            msg = f"✈️ Melhor oferta encontrada:\n{best['miles']} milhas | {best['origin']}→{best['destination']} em {best['date']}"
            send_telegram(msg)
        else:
            send_telegram("⚠️ Nenhum voo encontrado dentro do limite.")


if __name__ == "__main__":
    asyncio.run(run_scraper())
