# smiles_monitor.py
# Worker para Render: busca Smiles (GIG -> NRT/HND) em janela fixa,
# gera CSV, calcula filtros e notifica por Telegram a cada 6 horas.

import os
import time
import csv
import json
import re
import requests
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# -----------------------
# CONFIG via ENV VARIABLES
# -----------------------
ORIGIN = os.getenv("ORIGIN", "GIG")
DESTINATIONS = os.getenv("DESTINATIONS", "NRT,HND").split(",")
START_DATE = os.getenv("START_DATE", "2025-09-10")   # YYYY-MM-DD
DAYS_RANGE = int(os.getenv("DAYS_RANGE", "90"))
INTERVAL_HOURS = int(os.getenv("INTERVAL_HOURS", "6"))

MAX_MILES = int(os.getenv("MAX_MILES", "170000"))   # 🔥 novo limite

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# API endpoint observado (pode mudar ao longo do tempo)
API_URL = "https://api-air-flightsearch-blue.smiles.com.br/v1/airlines/search"

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "origin": "https://www.smiles.com.br",
    "referer": "https://www.smiles.com.br/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
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
    """
    Suporta formatos comuns: 'PT15H30M' (ISO), '15h 30m', '15:30', '15h30'
    Retorna horas (float).
    """
    if not dur: return 9999.0
    dur = str(dur)
    # ISO like PT15H30M
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", dur)
    if m:
        h = int(m.group(1) or 0)
        mm = int(m.group(2) or 0)
        return h + mm / 60.0
    # patterns like "15h 30m"
    m = re.search(r"(\d+)\s*h(?:ou?r)?(?:\s*(\d+)\s*m)?", dur, re.I)
    if m:
        h = int(m.group(1))
        mm = int(m.group(2) or 0)
        return h + mm / 60.0
    # hh:mm
    m = re.match(r"(\d{1,2}):(\d{2})", dur)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 60.0
    # fallback: try to find numbers
    nums = re.findall(r"\d+", dur)
    if len(nums) >= 2:
        return int(nums[0]) + int(nums[1]) / 60.0
    return 9999.0

# -----------------------
# Chamada à API Smiles
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
            # save debug body occasionally
            return None
    except Exception as e:
        print("Request error:", e)
        return None

# -----------------------
# Extrai ofertas de um JSON
# -----------------------
def extract_offers(json_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    offers = []
    if not json_data:
        return offers
    # procurar por campos típicos
    candidates = None
    for k in ("flights","itineraries","offers","data","items"):
        v = json_data.get(k)
        if isinstance(v, list):
            candidates = v
            break
    if not candidates:
        # fallback: tentar procurar estruturas dentro do JSON
        return offers

    for it in candidates:
        # tentativa direta por chaves comuns
        miles = None
        taxes = None
        price_cash = None
        duration = None
        carrier = None
        departure = None
        arrival = None
        segments = None

        # buscas comuns
        miles = (it.get("miles") or safe_get(it, "price", "miles") or safe_get(it, "miles", "amount"))
        taxes = (safe_get(it, "miles", "taxes") or safe_get(it, "taxes") or safe_get(it, "price", "taxes"))
        price_cash = (safe_get(it, "price", "amount") or safe_get(it, "amount") or it.get("priceAmount"))
        duration = it.get("duration") or safe_get(it, "totalDuration") or safe_get(it, "durationText")
        carrier = safe_get(it, "carrier", "name") or safe_get(it, "airline", "name") or it.get("marketingCarrier") or it.get("airline")
        departure = safe_get(it, "departure") or safe_get(it, "departureTime") or safe_get(it, "depart")
        arrival = safe_get(it, "arrival") or safe_get(it, "arrivalTime") or safe_get(it, "arrive")
        segments = it.get("segments") or safe_get(it, "legs") or []

        # normalize numbers
        try:
            miles = int(miles) if isinstance(miles, (int, float, str)) and extract_number_from_text(str(miles)) else None
        except:
            miles = None
        try:
            taxes = float(taxes) if isinstance(taxes, (int, float, str)) and extract_number_from_text(str(taxes)) else None
        except:
            taxes = None
        try:
            price_cash = float(price_cash) if isinstance(price_cash, (int, float, str)) and extract_number_from_text(str(price_cash)) else None
        except:
            price_cash = None

        # duration in hours
        dur_hours = parse_duration_to_hours(duration)

        if miles is None:
            # fallback: procurar numeros no item
            for k,v in flatten_numbers(it):
                if re.search(r"mile", k, re.I) or re.search(r"miles", k, re.I):
                    miles = int(v)
                    break
        if miles is None:
            continue

        offers.append({
            "carrier": carrier or "?",
            "flight_departure": departure,
            "flight_arrival": arrival,
            "segments": len(segments) if isinstance(segments, list) else "?",
            "miles": miles,
            "taxes": taxes,
            "price_cash": price_cash,
            "duration_hours": dur_hours,
            "raw": it
        })
    return offers

def safe_get(d: dict, *path):
    cur = d
    for p in path:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur

def flatten_numbers(node: Any) -> List[Tuple[str, float]]:
    out = []
    def rec(n, path):
        if isinstance(n, dict):
            for k,v in n.items():
                rec(v, path + [k])
        elif isinstance(n, list):
            for i,v in enumerate(n):
                rec(v, path + [str(i)])
        else:
            if isinstance(n, (int,float)):
                out.append((".".join(path), float(n)))
            elif isinstance(n,str):
                for m in re.findall(r"\d+[.,]?\d*", n):
                    val = float(m.replace(",","."))
                    out.append((".".join(path), val))
    rec(node, [])
    return out

# -----------------------
# Seleções / métricas
# -----------------------
def choose_bests(offers: List[Dict[str,Any]]):
    if not offers: return {}
    # 1) menor milhas
    best_miles = min(offers, key=lambda x: x.get("miles", 10**12))
    # 2) menor taxa em dinheiro (quando disponível)
    offers_with_tax = [o for o in offers if isinstance(o.get("taxes"), (int,float))]
    best_tax = min(offers_with_tax, key=lambda x: x["taxes"]) if offers_with_tax else None
    # 3) menor duração
    best_duration = min(offers, key=lambda x: x.get("duration_hours", 1e9))
    # 4) custo-benefício (milhas por hora) -> menor é melhor
    best_cb = min(offers, key=lambda x: (x.get("miles", 1e12) / max(0.1, x.get("duration_hours", 0.1))))
    return {
        "best_miles": best_miles,
        "best_tax": best_tax,
        "best_duration": best_duration,
        "best_costbenefit": best_cb
    }

# -----------------------
# Main scan loop (um run)
# -----------------------
def run_scan_once():
    start = datetime.fromisoformat(START_DATE).date()
    all_rows = []
    for dest in DESTINATIONS:
        for i in range(DAYS_RANGE):
            d = start + timedelta(days=i)
            dstr = d.strftime("%Y-%m-%d")
            # polite sleep small
            time.sleep(0.3)
            print("Searching", ORIGIN, "->", dest, dstr)
            jsonr = smiles_search(ORIGIN, dest, dstr)
            if not jsonr:
                continue
            offers = extract_offers(jsonr)
            for o in offers:
                row = {
                    "origin": ORIGIN,
                    "destination": dest,
                    "date": dstr,
                    "carrier": o["carrier"],
                    "segments": o["segments"],
                    "miles": o["miles"],
                    "taxes": o.get("taxes"),
                    "price_cash": o.get("price_cash"),
                    "duration_hours": o["duration_hours"]
                }
                all_rows.append(row)
    # save CSV
    if all_rows:
        fname = f"results_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
        with open(fname, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            writer.writeheader()
            writer.writerows(all_rows)
        print("Saved", fname)
    else:
        print("No rows collected.")

    # compute bests overall
    bests = {}
    if all_rows:
        # convert to offers form for selectors
        offers = []
        for r in all_rows:
            offers.append({
                "carrier": r["carrier"],
                "miles": r["miles"],
                "taxes": r["taxes"],
                "price_cash": r["price_cash"],
                "duration_hours": r["duration_hours"],
                "origin": r["origin"],
                "destination": r["destination"],
                "date": r["date"],
                "segments": r["segments"]
            })
        bests = choose_bests(offers)

    # prepare Telegram message
    msgs = []
    def format_offer(label, b):
        warn = " ⚠️" if b["miles"] and b["miles"] > MAX_MILES else ""
        return f"{label}{warn}: {b['miles']} milhas | {b.get('taxes','?')}R$ taxas | {b['duration_hours']:.1f}h | {b['origin']}→{b['destination']} em {b['date']}"
    
    if bests.get("best_miles"):
        msgs.append(format_offer("🟢 Menor milhas", bests["best_miles"]))
    if bests.get("best_tax"):
        b = bests["best_tax"]
        warn = " ⚠️" if b["miles"] and b["miles"] > MAX_MILES else ""
        msgs.append(f"🔵 Menor taxa{warn}: {b['taxes']} R$ | {b['miles']} milhas | {b['origin']}→{b['destination']} em {b['date']}")
    if bests.get("best_duration"):
        msgs.append(format_offer("⏱️ Menor duração", bests["best_duration"]))
    if bests.get("best_costbenefit"):
        b = bests["best_costbenefit"]
        cb = b['miles']/max(0.1,b['duration_hours'])
        warn = " ⚠️" if b["miles"] and b["miles"] > MAX_MILES else ""
        msgs.append(f"🟣 Melhor custo-benefício (milhas/h){warn}: {cb:.1f} | {b['miles']} milhas | {b['duration_hours']:.1f}h | {b['origin']}→{b['destination']} em {b['date']}")

# -----------------------
# Scheduler (loop principal para RUN em Render worker)
# -----------------------
def main_loop():
    while True:
        try:
            run_scan_once()
        except Exception as e:
            print("Run error:", e)

        # sleep until next run
        print(f"Sleeping for {INTERVAL_HOURS} hours...")
        time.sleep(INTERVAL_HOURS * 3600)

if __name__ == "__main__":
    run_scan_once()






