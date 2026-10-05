import requests, re
h={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
s=requests.Session()
s.headers.update(h)
for url in ["https://www.viewsocials.com/profile/israel_bidur", "https://www.viewsocials.com/", "https://storynavigation.com/watch-stories"]:
    r=s.get(url, timeout=15, allow_redirects=True)
    print(url, "->", r.status_code, r.url[:100], "ctype", r.headers.get('content-type','')[:50])
    print(" len", len(r.text), "title snippet", r.text[:2000].replace("\n"," ")[:800])
    print(" cookies", list(s.cookies.keys())[:5])
    print("---")
# try to see if viewsocials has same get-user endpoint
r=s.get("https://www.viewsocials.com/profile/israel_bidur", headers={"Referer":"https://www.viewsocials.com/"}, timeout=15)
# Check for csrf
m=re.search(r'csrf-token.*?content="([^"]+)"', r.text)
print("viewsocials csrf", m.group(1)[:30] if m else "not found")
# Try api guess
for endpoint in ["/api/profile/israel_bidur","/api/stories/israel_bidur","/get-user-last-stories","/api/getStories"]:
    try:
        rr=s.post(f"https://www.viewsocials.com{endpoint}", json={"username":"israel_bidur"}, timeout=10)
        print(endpoint, rr.status_code, rr.text[:500])
    except Exception as e:
        print(endpoint, "err",e)
