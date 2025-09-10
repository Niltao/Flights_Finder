# smiles_monitor.py
# Busca Smiles (GIG -> NRT/HND), gera CSV, filtra <=170k milhas
# e notifica por Telegram a cada 3 horas

import os
import time
import csv
import re
import requests
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# -----------------------
# CONFIG
# -----------------------
ORIGIN = os.getenv("ORIGIN", "GIG")
DESTINATIONS = os.getenv("DESTINATIONS", "NRT,HND").split(",")
START_DATE = os.getenv("START_DATE", "2025-09-10")   # YYYY-MM-DD
DAYS_RANGE = int(os.getenv("DAYS_RANGE", "90"))
INTERVAL_HOURS = int(os.getenv("INTERVAL_HOURS", "3"))  # <-- FIXO 3h
MILES_LIMIT = 170000  # <-- limite de milhas

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

API_URL = "https://api-air-flightsearch-blue.smiles.com.br/v1/airlines/search"

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "origin": "https://www.smiles.com.br",
    "referer": "https://www.smiles.com.br/",
    "user-agent": "Mozilla/5.0"
}

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
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            print("Telegram send failed:", r.status_code, r.text[:200])
    except Exception as e:
        print("Telegram send error:", e)

def extract_number_from_text(s: str) -> Optional[int]:
    if not s: return None
    s2 = re.sub(r"[^\d]", "", s)
    if not s2: return None
    try:
        return int(s2)
    except:
        return None

def parse_duration_to_hours(dur: str) -> float:
    if not dur: return 9999.0
    dur = str(dur)
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", dur)
    if m:
        h = int(m.group(1) or 0)
        mm = int(m.group(2) or 0)
        return h + mm / 60.0
    m = re.search(r"(\d+)\s*h(?:\s*(\d+)\s*m)?", dur, re.I)
    if m:
        h = int(m.group(1))
        mm = int(m.group(2) or 0)
        return h + mm / 60.0
    m = re.match(r"(\d{1,2}):(\d{2})", dur)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 60.0
    return 9999.0

# -----------------------
# Chamada API
# -----------------------
def smiles_search(origin: str, dest: str, date_str: str) -> Optional[Dict[str, Any]]:
    params = {
        "cabin": "ALL",
        "originAirportCode": origin,
        "destinationAirportCode": dest,
        "departureDate": date_str,
        "returnDate": "",
        "adults": "1",
        "children": "0",
        "infants": "0",
        "forceCongener": "false"
    }
    try:
        r = requests.get(API_URL, headers=HEADERS, params=params, timeout=30)
        if r.status_code == 200:
            return r.json()
        else:
            print(f"Smiles HTTP {r.status_code} for {origin}->{dest} {date_str}")
            return None
    except Exception as e:
        print("Request error:", e)
        return None

# -----------------------
# Extrai ofertas
# -----------------------
def safe_get(d: dict, *path):
    cur = d
    for p in path:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur

def extract_offers(json_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    offers = []
    if not json_data:
        return offers
    candidates = None
    for k in ("flights","itineraries","offers","data","items"):
        v = json_data.get(k)
        if isinstance(v, list):
            candidates = v
            break
    if not candidates: return offers

    for it in candidates:
        miles = (it.get("miles") or safe_get(it, "price", "miles"))
        try:
            miles = int(extract_number_from_text(str(miles)))
        except:
            miles = None
        if not miles or miles > MILES_LIMIT:
            continue

        taxes = safe_get(it, "miles", "taxes") or safe_get(it, "taxes")
        duration = it.get("duration") or safe_get(it, "totalDuration")
        carrier = safe_get(it, "carrier", "name") or it.get("airline")
        departure = safe_get(it, "departure") or safe_get(it, "departureTime")
        arrival = safe_get(it, "arrival") or safe_get(it, "arrivalTime")
        segments = it.get("segments") or []

        offers.append({
            "carrier": carrier or "?",
            "flight_departure": departure,
            "flight_arrival": arrival,
            "segments": len(segments) if isinstance(segments, list) else "?",
            "miles": miles,
            "taxes": taxes,
            "duration_hours": parse_duration_to_hours(duration),
            "origin": ORIGIN,
            "destination": it.get("destination") or "?",
            "date": it.get("date") or "?"
        })
    return offers

# -----------------------
# Seleções
# -----------------------
def choose_bests(offers: List[Dict[str,Any]]):
    if not offers: return {}
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
            time.sleep(0.3)
            print("Searching", ORIGIN, "->", dest, dstr)
            jsonr = smiles_search(ORIGIN, dest, dstr)
            if not jsonr: continue
            all_offers.extend(extract_offers(jsonr))

    if not all_offers:
        send_telegram("Ainda não encontrei passagens até 170k milhas.")
        return

    bests = choose_bests(all_offers)

    msgs = ["Resultado da varredura (até 170k):\n"]
    for o in all_offers:
        line = f"{o['miles']} milhas | {o.get('taxes','?')} R$ taxas | {o['duration_hours']:.1f}h | {o['origin']}→{o['destination']} em {o['date']}"
        if o == bests.get("best_miles"):
            line += "\n⚠️ Melhor milhas"
        if o == bests.get("best_duration"):
            line += "\n⚠️ Menor duração"
        msgs.append(line)

    send_telegram("\n\n".join(msgs))

# -----------------------
# Loop principal
# -----------------------
def main_loop():
    while True:
        try:
            run_scan_once()
        except Exception as e:
            print("Run error:", e)
        print(f"Sleeping for {INTERVAL_HOURS} hours...")
        time.sleep(INTERVAL_HOURS * 3600)

if __name__ == "__main__":
    run_scan_once()
