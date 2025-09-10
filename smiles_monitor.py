import os
import requests
from datetime import datetime, timedelta

# -----------------------
# Configurações vindas do GitHub Secrets
# -----------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ORIGIN = os.getenv("ORIGIN", "GIG")  # aeroporto de origem
DESTINATIONS = os.getenv("DESTINATIONS", "MIA,JFK,ORD").split(",")  # destinos separados por vírgula
START_DATE = os.getenv("START_DATE", "2025-09-01")  # data inicial YYYY-MM-DD
DAYS_RANGE = int(os.getenv("DAYS_RANGE", "30"))  # quantidade de dias a partir da inicial

# Limite de milhas configurável via Secrets
MILES_LIMIT = int(os.getenv("MILES_LIMIT", "170000"))


# -----------------------
# Funções auxiliares
# -----------------------
def send_telegram(message: str):
    """Envia mensagem para o Telegram"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram não configurado.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Erro ao enviar para o Telegram: {e}")


def search_flights(origin, destination, date):
    """Consulta voos na API da Smiles"""
    url = (
        "https://api-airlines-prd.smiles.com.br/v1/airlines/search"
        f"?originAirportCode={origin}&destinationAirportCode={destination}"
        f"&departureDate={date}&adults=1&tripType=2&cabinType=all"
    )
    try:
        response = requests.get(url, timeout=20)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Erro API {response.status_code} em {origin} -> {destination} {date}")
            return None
    except Exception as e:
        print(f"Erro na requisição: {e}")
        return None


# -----------------------
# Processamento
# -----------------------
def process_results():
    """Busca voos, filtra e envia para o Telegram"""
    start_date = datetime.strptime(START_DATE, "%Y-%m-%d")

    for destination in DESTINATIONS:
        valid_flights = []
        best_flight = None

        for i in range(DAYS_RANGE):
            date = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
            data = search_flights(ORIGIN, destination, date)

            if not data or "items" not in data:
                continue

            for item in data["items"]:
                miles = item.get("miles", 9999999)
                money = item.get("money", 0.0)

                flight_info = {
                    "date": date,
                    "destination": destination,
                    "miles": miles,
                    "money": money,
                }

                # guarda o melhor voo (mesmo acima do limite)
                if not best_flight or miles < best_flight["miles"]:
                    best_flight = flight_info

                # guarda apenas voos dentro do limite
                if miles <= MILES_LIMIT:
                    valid_flights.append(flight_info)

        # mensagem de abertura com o limite usado
        header_msg = f"🔎 *Varredura Smiles* ({ORIGIN} → {destination})\nLimite configurado: *{MILES_LIMIT:,} milhas*\n"

        # envia voos dentro do limite
        if valid_flights:
            msg = header_msg + "\n✈️ *Voos encontrados abaixo do limite:*\n\n"
            for f in valid_flights:
                msg += (
                    f"📅 {f['date']} - {f['miles']:,} milhas "
                    f"+ R${f['money']:.2f}\n"
                )
            send_telegram(msg)
        else:
            send_telegram(header_msg + "\n⚠️ Nenhum voo abaixo do limite encontrado.")

        # envia também a melhor opção geral
        if best_flight:
            msg = (
                f"⭐ *Melhor encontrada (independente do limite)*\n"
                f"{ORIGIN} → {best_flight['destination']}\n"
                f"📅 {best_flight['date']} - {best_flight['miles']:,} milhas "
                f"+ R${best_flight['money']:.2f}"
            )
            send_telegram(msg)


# -----------------------
# Execução
# -----------------------
if __name__ == "__main__":
    process_results()
