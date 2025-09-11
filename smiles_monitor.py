# smiles_monitor.py
# Busca Smiles (GIG -> NRT/HND), gera CSV, filtra <=170k milhas
# e notifica por Telegram a cada 3 horas

import os
import time
import re
import json
import requests
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# -----------------------
# CONFIG
# -----------------------
ORIGIN = os.getenv("ORIGIN", "GIG")
DESTINATIONS = os.getenv("DESTINATIONS", "NRT,HND").split(",")
START_DATE = os.getenv("START_DATE", "2025-09-10")   # YYYY-MM-DD
DAYS_RANGE = int(os.getenv("DAYS_RANGE", "90") or "90")  # <-- fallback seguro
INTERVAL_HOURS = int(os.getenv("INTERVAL_HOURS", "3") or "3")
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


def parse_duration_to_hours(dur: str) -> float:
    if not dur: return 9999.0
    dur = str(dur)
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", dur)
    if m:
        h = int(m.group(1) or 0)
        mm = int(m.group(2) or 0)
        return h + mm / 60.0
    return 9999.0


def save_debug_response(dest: str, date_str: str, status: int, params: dict, data: Any):
    """Salva o retorno bruto da API para debug"""
    fname = f"last_response_{dest}_{date_str}.json"
    debug = {
        "status": status,
        "params": params,
        "data": data
    }
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(debug, f, ensure_ascii=False, indent=2)
    print(f"[DEBUG] Resposta salva em {fname}")


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
        try:
            data = r.json()
        except:
            data = r.text

        save_debug_response(dest, date_str, r.status_code, params, data)

        if r.status_code == 200:
            return data
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
    if not json_data or not isinstance(json_data, dict):
        return offers

    candidates = None
    for k in ("flights", "itineraries", "offers", "data", "items"):
        v = json_data.get(k)
        if isinstance(v, list):
            candidates = v
            break
    if not candidates: return offers

    for it in candidates:
        miles = (it.get("miles") or safe_get(it, "price", "miles"))
        try:
            miles = int(re.sub(r"[^\d]", "", str(miles)))
        except:
            miles = None
        if not miles or miles > MILES_LIMIT:
            continue

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
            "duration_hours": parse_duration_to_hours(duration),
            "origin": ORIGIN,
            "destination": it.get("destination") or "?",
            "date": it.get("date") or "?"
        })
    return offers


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
            if not jsonr: 
                continue
            all_offers.extend(extract_offers(jsonr))

        if not all_offers:
            send_telegram(f"🔎 Varredura Smiles ({ORIGIN} → {dest})\n⚠️ Nenhum voo encontrado (JSON vazio).")
        else:
            send_telegram(f"🔎 Varredura Smiles ({ORIGIN} → {dest})\n✅ {len(all_offers)} voos capturados.")

if __name__ == "__main__":
    run_scan_once()
