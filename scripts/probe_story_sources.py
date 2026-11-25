"""בדיקת זמינות וסימני Captcha באתרי סטוריז מועמדים.

שימוש:
    python scripts/probe_story_sources.py

הסקריפט קורא בלבד (GET) ומדפיס סיכום קצר לכל אתר:
סטטוס, אורך HTML, סימני הגנה (Turnstile/Cloudflare), ונתיבי API חשודים.
"""
import re
import sys

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

CANDIDATES = [
    "https://dolphinradar.com",
    "https://www.dolphinradar.com",
    "https://clipssaver.com",
    "https://snapgram.io",
    "https://snapgram.app",
    "https://snapgram.com",
    "https://getlurk.app",
    "https://getlurk.com",
]

GUARD_MARKERS = {
    "turnstile": "turnstile",
    "sitekey": "data-sitekey",
    "cf-challenge": "challenge-platform",
    "just-a-moment": "just a moment",
    "attention": "attention required",
    "recaptcha": "recaptcha",
    "hcaptcha": "hcaptcha",
}

API_PATTERN = re.compile(r"[\"'](/(?:api|ajax|get|stories|story)[a-zA-Z0-9_\-/\.]*)")
FORM_PATTERN = re.compile(r"<form[^>]*action=[\"']([^\"']+)[\"']", re.IGNORECASE)
INPUT_PATTERN = re.compile(r"<input[^>]*name=[\"']([^\"']+)[\"']", re.IGNORECASE)


def probe(url: str) -> dict:
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "text/html,*/*"})
    try:
        response = session.get(url, timeout=25, allow_redirects=True)
    except Exception as exc:
        return {"url": url, "error": str(exc)}
    text = response.text or ""
    lowered = text.lower()
    guards = [name for name, marker in GUARD_MARKERS.items() if marker in lowered]
    return {
        "url": url,
        "status": response.status_code,
        "final_url": response.url,
        "length": len(text),
        "guards": guards,
        "apis": sorted(set(API_PATTERN.findall(text)))[:12],
        "forms": FORM_PATTERN.findall(text)[:5],
        "inputs": sorted(set(INPUT_PATTERN.findall(text)))[:8],
    }


def main() -> int:
    for url in CANDIDATES:
        result = probe(url)
        print("=" * 70)
        print(result.get("url"))
        if result.get("error"):
            print(f"  ERROR: {result['error'][:120]}")
            continue
        print(f"  status={result['status']} final={result['final_url']} len={result['length']}")
        print(f"  guards={result['guards'] or '-'}")
        print(f"  forms={result['forms'] or '-'}")
        print(f"  inputs={result['inputs'] or '-'}")
        print(f"  api_hints={result['apis'] or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
