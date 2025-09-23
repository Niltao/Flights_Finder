# seats_monitor.py
# Busca via Seats.aero (GIG -> NRT/HND), filtra <=170k milhas
# e notifica por Telegram a cada execução (via GitHub Actions)

import os
import requests
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# -----------------------
# CONFIG
# -----------------------
ORIGIN = os.getenv("ORIGIN", "GRU")
DESTINATIONS = os.getenv("DESTINATIONS", "NRT,HND").split(",")
START_DATE = os.getenv("START_DATE", "2025-09-10")  # YYYY-MM-DD
DAYS_RANGE = int(os.getenv("DAYS_RANGE", "90"))
MILES_LIMIT = 170000  # limite de milhas fixo

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SEATS_API = "https://seats.aero/api/search"

# -----------------------
# UTILIDADES
# -----------------------
def send_telegram(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured; skipping send.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=20)
        if r.status_code != 200:
            print("Telegram send failed:", r.status_code, r.text[:200])
    except Exception as e:
        print("Telegram send error:", e)

def search_seats(origin: str, dest: str, date_str: str) -> Optional[List[Dict[str, Any]]]:
    url = f"{SEATS_API}/{origin}/{dest}/{date_str}"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            return r.json().get("flights", [])
        else:
            print(f"Seats.aero HTTP {r.status_code} for {origin}->{dest} {date_str}")
            return None
    except Exception as e:
        print("Seats.aero error:", e)
        return None

# -----------------------
# Seleção
# -----------------------
def choose_bests(offers: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not offers:
        return {}
    bests = {
        "best_miles": min(offers, key=lambda x: x.get("miles", 10**12)),
        "best_duration": min(offers, key=lambda x: x.get("duration_hours", 1e9)),
    }
    return bests

# -----------------------
# Run único
# -----------------------
def run_scan_once():
    start = datetime.fromisoformat(START_DATE).date()
    all_offers = []

    for dest in DESTINATIONS:
        for i in range(DAYS_RANGE):
            d = start + timedelta(days=i)
            dstr = d.strftime("%Y-%m-%d")

            print(f"🔎 Searching {ORIGIN} -> {dest} {dstr}")
            results = search_seats(ORIGIN, dest, dstr)
            if not results:
                continue

            for f in results:
                miles = f.get("miles")
                if not miles or miles > MILES_LIMIT:
                    continue

                offer = {
                    "origin": ORIGIN,
                    "destination": dest,
                    "date": dstr,
                    "carrier": f.get("airline") or "?",
                    "miles": miles,
                    "cash": f.get("cash_price"),
                    "duration_hours": f.get("duration_hours", 0),
                    "stops": f.get("stops", 0),
                }
                all_offers.append(offer)

    if not all_offers:
        send_telegram(f"🔎 Varredura Seats.aero ({ORIGIN}→{','.join(DESTINATIONS)})\n⚠️ Nenhum voo encontrado até {MILES_LIMIT:,} milhas.")
        return

    bests = choose_bests(all_offers)

    msgs = [f"🔎 Varredura Seats.aero ({ORIGIN}→{','.join(DESTINATIONS)})\nLimite configurado: {MILES_LIMIT:,} milhas\n"]

    for o in all_offers:
        line = f"{o['miles']:,} milhas | {o.get('cash','?')} US$ | {o['duration_hours']:.1f}h | {o['stops']} escalas | {o['origin']}→{o['destination']} em {o['date']}"
        if o == bests.get("best_miles"):
            line += "\n⚠️ Melhor em milhas"
        if o == bests.get("best_duration"):
            line += "\n⚠️ Menor duração"
        msgs.append(line)

    send_telegram("\n\n".join(msgs))

# -----------------------
# MAIN
# -----------------------
if __name__ == "__main__":
    run_scan_once()

