import json
import os
import re
import sys
import time
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright
import requests

STATUS_URL = "https://status.ankama.com/"
WEBHOOK_URL = "https://discord.com/api/webhooks/1493557013794259064/sV18egi6XwbLBArEgqfd__GzT616Rw4rSK0rurO0S4X7DvlZqbPdGvGQFl76sv9ef8jQ"
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))
STATE_FILE = "blair_status_state.json"
TARGET_NAME = "Blair"
SINGLE_RUN = os.getenv("SINGLE_RUN", "0") == "1"

STATUS_PATTERNS = [
    ("operational", ["operational", "online", "up", "available", "ok", "running", "🟢"]),
    ("degraded", ["degraded", "partial outage", "slow", "unstable", "🟡"]),
    ("maintenance", ["maintenance", "down for maintenance", "🔧"]),
    ("major_outage", ["major outage", "outage", "offline", "down", "unavailable", "🔴"]),
]

def get_page_with_browser():
    print("📱 Navigation...", flush=True)
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
        return {"found": False, "status": "not_found"}

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

def send_webhook(content, color=3447003):
    if not WEBHOOK_URL:
        raise RuntimeError("WEBHOOK_URL manquant")

    payload = {
        "username": "Blair Status Watcher",
        "embeds": [{
            "title": "🚨 Statut Blair",
            "description": content,
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
    }
    r = requests.post(WEBHOOK_URL, json=payload, timeout=20)
    print(f"Discord: {r.status_code}", flush=True)
    r.raise_for_status()

def color_for(status):
    return {
        "operational": 5763719,
        "degraded": 16763904,
        "maintenance": 16098851,
        "major_outage": 15548997,
        "unknown": 9807270,
        "not_found": 10197915,
    }.get(status, 9807270)

def format_blair_message(current):
    status = current.get("status", "unknown")

    if not current["found"]:
        return "❓ **Blair** introuvable dans la liste DOFUS Touch"

    emoji = (
        "🟢" if status == "operational"
        else "🟡" if status == "degraded"
        else "🔧" if status == "maintenance"
        else "🔴" if status == "major_outage"
        else "❓"
    )

    return f"{emoji} **Blair** : **{status}**\n*Vérifié sur status.ankama.com*"

def run_once(notify_on_first_run=False):
    html = get_page_with_browser()
    current = extract_blair_status(html)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"[{now}] {format_blair_message(current)}", flush=True)

    state = load_state()
    previous_status = state.get("status")

    if previous_status is None:
        save_state(current)
        if notify_on_first_run:
            send_webhook(
                format_blair_message(current),
                color_for(current.get("status", "unknown"))
            )
        return

    if current.get("status") != previous_status:
        msg = f"**Changement détecté !**\n{format_blair_message(current)}"
        send_webhook(msg, color_for(current.get("status", "unknown")))
        save_state(current)
    else:
        print("✅ Pas de changement", flush=True)
        save_state(current)

def main():
    if not WEBHOOK_URL:
        raise RuntimeError("❌ WEBHOOK_URL manquant - Ajoutez-le dans GitHub Secrets")

    # TEST GITHUB ACTIONS - à commenter/supprimer après validation
    if os.getenv("GITHUB_ACTIONS", "").lower() == "true":
        print("🧪 MODE TEST GITHUB ACTIONS", flush=True)
        send_webhook("🚀 **TEST GitHub Actions OK** - Script + webhook fonctionnels !", 5763719)
        return

    if len(sys.argv) > 1 and sys.argv[1] == "0":
        run_once(True)
    elif SINGLE_RUN:
        print("🔄 Exécution unique (GitHub Actions)", flush=True)
        run_once()
    else:
        print("👀 Surveillance 24/24 démarrée", flush=True)
        while True:
            try:
                run_once()
                time.sleep(CHECK_INTERVAL)
            except KeyboardInterrupt:
                print("🛑 Arrêt demandé", flush=True)
                break
            except Exception as e:
                print(f"❌ Erreur: {e}", flush=True)
                time.sleep(60)

if __name__ == "__main__":
    main()
