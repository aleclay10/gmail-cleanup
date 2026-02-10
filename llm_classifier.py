import logging

import requests

from config import OLLAMA_URL, OLLAMA_MODEL

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Classify as IMPORTANT or UNIMPORTANT.\n"
    "IMPORTANT: real people, banks, bills, appointments, medical, legal, "
    "security alerts, deliveries.\n"
    "UNIMPORTANT: marketing, newsletters, promotions, spam, social media.\n"
    "Reply with one word only: IMPORTANT or UNIMPORTANT."
)


def check_ollama_available():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        if not any(OLLAMA_MODEL in m for m in models):
            return False, f"Model '{OLLAMA_MODEL}' not found. Available: {models}"
        return True, "OK"
    except requests.ConnectionError:
        return False, f"Cannot connect to Ollama at {OLLAMA_URL}"
    except Exception as e:
        return False, str(e)


def classify_email(from_addr, subject, snippet):
    user_msg = f"From: {from_addr} | Subject: {subject} | Preview: {snippet[:200]}"

    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 10,
                },
            },
            timeout=120,
        )
        r.raise_for_status()
        answer = r.json()["message"]["content"].strip().upper()
    except Exception as e:
        log.warning("LLM error, defaulting to important: %s", e)
        return "important"

    if "UNIMPORTANT" in answer:
        return "low_priority"
    # Safe default: anything unclear → important
    return "important"


def classify_batch(emails):
    results = {}
    for email in emails:
        classification = classify_email(
            email["from"], email["subject"], email["snippet"]
        )
        results[email["id"]] = classification
    return results
