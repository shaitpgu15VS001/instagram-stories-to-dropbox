import requests, re
headers={"User-Agent":"Mozilla/5.0"}
r=requests.get("https://storynavigation.com/js/app.js?id=e11233d6e7dff598dd94", headers=headers, timeout=15)
print(r.text[:20000])
# also search for get-user
if "get-user" in r.text:
    idx=r.text.find("get-user")
    print(r.text[idx-1000:idx+2000])
else:
    print("no get-user in app.js")
    # maybe in assets js
r2=requests.get("https://storynavigation.com/assets/js/index.js", headers=headers, timeout=15)
print("\n=== index.js len", len(r2.text))
print(r2.text[:10000])
if "get-user" in r2.text:
    print("found in index.js")
