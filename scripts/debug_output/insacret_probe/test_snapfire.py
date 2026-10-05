import requests, json, pathlib
headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36","Accept":"application/json","Content-Type":"application/json","Origin":"https://insacret.org","Referer":"https://insacret.org/en/stories/israel_bidur"}
url="https://igstories.snapfirecdn.com/v2/stories"
payloads=[
    {"username":"israel_bidur"},
    {"username":"israel_bidur","turnstile":"dummy"},
    {"username":"israel_bidur","turnstile":""},
    {"username":"israel_bidur","turnstile":None},
]

for p in payloads:
    try:
        r=requests.post(url, json=p, headers=headers, timeout=15)
        print(f"payload {p} -> {r.status_code} {r.headers.get('content-type')} {r.text[:3000]}")
        print("headers", dict(list(r.headers.items())[:6]))
    except Exception as e:
        print(f"payload {p} error {e}")
    print("---")

# also try with session that first gets insacret page to get cookies?
s=requests.Session()
s.headers.update({"User-Agent":"Mozilla/5.0"})
r=s.get("https://insacret.org/en/stories/israel_bidur", timeout=15)
print("GET insacret cookies", list(s.cookies.keys()))
# try with those cookies
try:
    r2=s.post(url, json={"username":"israel_bidur","turnstile":"test"}, headers={"Accept":"application/json","Content-Type":"application/json","Origin":"https://insacret.org","Referer":"https://insacret.org/en/stories/israel_bidur"}, timeout=15)
    print(f"with cookies -> {r2.status_code} {r2.text[:3000]}")
except Exception as e:
    print(e)
