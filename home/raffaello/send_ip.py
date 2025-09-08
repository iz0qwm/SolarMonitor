#!/usr/bin/env python3
import requests
import subprocess

# --- CONFIG ---
BOT_TOKEN = "<BOT_TOKEN>"
CHAT_ID = "Chat_ID"
# Una volta creato il bot ottieni il Chat ID con:
# https://api.telegram.org/bot<IL_TUO_BOT_TOKEN>/getUpdates

PORT = 8088

def get_ip():
    # prende il primo IP non di loopback
    result = subprocess.check_output("hostname -I", shell=True)
    ip = result.decode("utf-8").strip().split()[1]
    return ip

def send_message(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

if __name__ == "__main__":
    ip = get_ip()
    send_message(f"🌐 Raspberry disponibile su: http://{ip}:{PORT}")

