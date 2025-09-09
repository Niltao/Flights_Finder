import os
import requests

def send_message(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    response = requests.post(url, data=payload)
    response.raise_for_status()
    return response.json()

if __name__ == "__main__":
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise ValueError("TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID não encontrados nos secrets do GitHub.")

    send_message(token, chat_id, "🚀 Teste bem-sucedido do GitHub Actions!")
    print("Mensagem enviada com sucesso!")
