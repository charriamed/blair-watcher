import json
import os
import re
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright
import requests

STATUS_URL = "https://status.ankama.com/"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
STATE_FILE = "blair_status_state.json"
TARGET_NAME = "Blair"

STATUS_PATTERNS = [
    ("operational", ["operational", "online", "up", "available", "ok", "running", "🟢"]),
    ("degraded", ["degraded", "partial outage", "slow", "unstable", "🟡"]),
    ("maintenance", ["maintenance", "down for maintenance", "🔧"]),
    ("major_outage", ["major outage", "outage", "offline", "down", "unavailable", "🔴"]),
]

def get_page_with_browser():
    print("📱 Navigation vers status.ankama.com...", flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        page = browser.new_page()
        page.goto(STATUS_URL, wait_until="networkidle")
        page.get_by_text("DOFUS Touch", exact=True).click()
        page.wait_for_timeout(3000)
        content = page.content()
        browser.close()
        return content

def normalize_spaces(text):
    return re.sub(r"\s+", " ", text).strip()

def infer_status(window_text):
    low = window_text.lower()
    for label, needles in STATUS_PATTERNS:
        for needle in needles:
            if needle in low:
                return label, needle
    return "unknown", None

def extract_blair_status(html):
    compact = normalize_spaces(re.sub(r"<[^>]+>", " ", html))
    idx = compact.lower().find(TARGET_NAME.lower())

    if idx == -1:
        return {
            "found": False,
            "status": "not_found",
            "snippet": None,
            "matched": None,
        }

    start = max(0, idx - 200)
    end = min(len(compact), idx + 300)
    snippet = compact[start:end]
    status, matched = infer_status(snippet)

    return {
        "found": True,
        "status": status,
        "snippet": snippet,
        "matched": matched,
    }

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def color_for(status):
    return {
        "operational": 5763719,
        "degraded": 16763904,
        "maintenance": 16098851,
        "major_outage": 15548997,
        "unknown": 9807270,
        "not_found": 10197915,
    }.get(status, 9807270)

def emoji_for(status):
    return {
        "operational": "🟢",
        "degraded": "🟡",
        "maintenance": "🔧",
        "major_outage": "🔴",
        "unknown": "❓",
        "not_found": "❔",
    }.get(status, "❓")

def format_status_label(status):
    labels = {
        "operational": "Opérationnel",
        "degraded": "Dégradé",
        "maintenance": "Maintenance",
        "major_outage": "Panne majeure",
        "unknown": "Inconnu",
        "not_found": "Introuvable",
    }
    return labels.get(status, status)

def format_blair_message(current, previous_status=None):
    status = current.get("status", "unknown")
    emoji = emoji_for(status)
    status_label = format_status_label(status)

    if not current.get("found"):
        base = "❔ **Blair** introuvable dans la liste DOFUS Touch"
    else:
        base = f"{emoji} **Blair** : **{status_label}**"

    if previous_status is None:
        prefix = "🆕 **Premier relevé**\n"
    elif previous_status != status:
        previous_label = format_status_label(previous_status)
        prefix = f"🚨 **Changement détecté**\nAncien statut : **{previous_label}**\nNouveau statut : **{status_label}**\n"
    else:
        prefix = "ℹ️ **Aucun changement**\n"

    return f"{prefix}{base}\n*Vérifié sur status.ankama.com*"

def send_webhook(content, color=3447003):
    if not WEBHOOK_URL:
        print("ℹ️ WEBHOOK_URL absent : envoi Discord ignoré", flush=True)
        return

    payload = {
        "username": "Blair Status Watcher",
        "embeds": [{
            "title": "Statut du serveur Blair",
            "description": content,
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
    }

    r = requests.post(WEBHOOK_URL, json=payload, timeout=20)
    print(f"Discord: {r.status_code}", flush=True)
    r.raise_for_status()

def run_once():
    html = get_page_with_browser()
    current = extract_blair_status(html)
    current["checked_at"] = datetime.now(timezone.utc).isoformat()

    previous = load_state()
    previous_status = previous.get("status")

    print(f"Statut actuel: {current.get('status')}", flush=True)
    if previous_status is None:
        print("Aucun état précédent trouvé", flush=True)
    else:
        print(f"Statut précédent: {previous_status}", flush=True)

    message = format_blair_message(current, previous_status)

    # Laisse cette ligne active si tu veux envoyer à Discord :
    send_webhook(message, color_for(current.get("status", "unknown")))

    # Si tu veux désactiver Discord temporairement, commente la ligne au-dessus.

    save_state(current)

def main():
    run_once()

if __name__ == "__main__":
    main()
