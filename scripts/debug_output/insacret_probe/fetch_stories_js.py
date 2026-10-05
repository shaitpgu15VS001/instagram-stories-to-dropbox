import requests, re
headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
# fetch the chunk js
url="https://insacret.org/_next/static/chunks/pages/stories/%5Busername%5D-c11afc8aba09979b.js"
r=requests.get(url, headers=headers, timeout=15)
print("status", r.status_code, "len", len(r.text))
text=r.text
# save
open("scripts/debug_output/insacret_probe/stories_chunk.js","w",encoding="utf-8").write(text)
# search for keywords
for kw in ["fetch(","axios","/api","stories","profile","israel_bidur","token","csrf","instagram","media","cloudflare","turnstile","fx.js","9x43"]:
    if kw.lower() in text.lower():
        idx=text.lower().find(kw.lower())
        print(f"\n--- {kw} ---")
        print(text[max(0,idx-800):idx+1500][:2000])
# also fetch fx.js and 9x
for u in ["https://insacret.org/fx.js","https://insacret.org/9x43Iaq6G.js"]:
    rr=requests.get(u, headers=headers, timeout=15)
    print(f"\n=== {u} status {rr.status_code} len {len(rr.text)} ===")
    print(rr.text[:3000])
    open(f"scripts/debug_output/insacret_probe/{u.split('/')[-1]}","w",encoding="utf-8").write(rr.text)
