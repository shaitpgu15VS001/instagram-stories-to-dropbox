"""בדיקה עמוקה של אתר מועמד בודד: קישורים, סקריפטים ונתיבי API.

שימוש:
    python scripts/probe_story_source_deep.py https://example.com
"""
import re
import sys
from urllib.parse import urljoin

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
HREF_PATTERN = re.compile(r"href=[\"']([^\"']+)[\"']", re.IGNORECASE)
SCRIPT_PATTERN = re.compile(r"<script[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
ENDPOINT_PATTERN = re.compile(r"[\"'`](/[a-zA-Z0-9_\-/\.]*(?:api|stor|insta|download|media)[a-zA-Z0-9_\-/\.]*)[\"'`]")
ABSOLUTE_PATTERN = re.compile(r"https://[a-zA-Z0-9\.\-]+\.(?:com|app|io|net|co)/[a-zA-Z0-9_\-/\.?=&%]*")
INTERESTING = ("stor", "instagram", "viewer", "download", "api")
MAX_SCRIPTS = 40


def _fetch(session, url, timeout=25):
    response = session.get(url, timeout=timeout)
    return response


def inspect(url: str, grep: str = None) -> None:
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "text/html,*/*"})
    response = _fetch(session, url)
    text = response.text or ""
    print(f"URL: {response.url}")
    print(f"status={response.status_code} len={len(text)}")
    title = TITLE_PATTERN.search(text)
    print(f"title: {title.group(1).strip()[:120] if title else '-'}")

    links = []
    for href in HREF_PATTERN.findall(text):
        low = href.lower()
        if any(word in low for word in INTERESTING):
            full = urljoin(response.url, href)
            if full not in links:
                links.append(full)
    print(f"interesting links ({len(links)}):")
    for link in links[:15]:
        print(f"  {link}")

    scripts = []
    for src in SCRIPT_PATTERN.findall(text):
        full = urljoin(response.url, src)
        if full not in scripts:
            scripts.append(full)
    print(f"scripts ({len(scripts)}):")
    for src in scripts[:10]:
        print(f"  {src}")

    endpoints = set()
    hosts = set()
    for script in scripts[:MAX_SCRIPTS]:
        if not script.endswith(".js") and ".js?" not in script:
            continue
        try:
            js = _fetch(session, script)
        except Exception as exc:
            print(f"  [js error] {script}: {exc}")
            continue
        if js.status_code != 200:
            continue
        js_text = js.text or ""
        endpoints.update(ENDPOINT_PATTERN.findall(js_text))
        for match in ABSOLUTE_PATTERN.findall(js_text):
            if any(word in match.lower() for word in ("api", "stor", "insta", "media")):
                hosts.add(match)
        if grep and grep in js_text:
            index = js_text.find(grep)
            print(f"  [grep context] {script}")
            print("   ", js_text[max(0, index - 300):index + 300].replace("\n", " "))
    print(f"endpoint hints ({len(endpoints)}):")
    for endpoint in sorted(endpoints)[:40]:
        print(f"  {endpoint}")
    print(f"absolute urls ({len(hosts)}):")
    for host in sorted(hosts)[:25]:
        print(f"  {host}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    inspect(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
