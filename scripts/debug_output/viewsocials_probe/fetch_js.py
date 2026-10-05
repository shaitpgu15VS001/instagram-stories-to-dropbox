import requests, pathlib, re, base64, json
headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
# fetch socialstory.js
url="https://storynavigation.com/js/socialstory.js?v63"
r=requests.get(url, headers=headers, timeout=15)
print("status",r.status_code, "len",len(r.text))
out=pathlib.Path("scripts/debug_output/viewsocials_probe/socialstory.js")
out.write_text(r.text, encoding="utf-8")
print(r.text[:8000])

# also fetch user page raw via requests to see if userId visible
url2="https://storynavigation.com/user/israel_bidur"
r2=requests.get(url2, headers=headers, timeout=15)
print("\n=== user page status",r2.status_code)
# search for instagramUserId in text
if "508790485" in r2.text:
    idx=r2.text.find("508790485")
    print(r2.text[idx-1000:idx+1000][:2000])
else:
    print("not found 508 in requests fetch")
    # check for other hints
    for kw in ["instagramUserId","userName","get-user","israel_bidur"]:
        if kw in r2.text:
            print("found",kw)
            idx=r2.text.find(kw)
            print(r2.text[idx-500:idx+1000][:1500])

# now try direct API replay tests
print("\n=== API replay tests ===")
api="https://storynavigation.com/get-user-last-stories"
# payloads to try
payloads=[
 {"userName":"israel_bidur","isPrivate":"","instagramUserId":508790485},
 {"userName":"israel_bidur"},
 {"userName":"israel_bidur","instagramUserId":508790485},
 {"userName":"israel_bidur","isPrivate":""},
]
for p in payloads:
    try:
        rr=requests.post(api, json=p, headers={**headers,"Referer":"https://storynavigation.com/user/israel_bidur","Origin":"https://storynavigation.com","Content-Type":"application/json;charset=UTF-8"}, timeout=15)
        print(f"payload {p} -> {rr.status_code} {rr.headers.get('content-type')} {rr.text[:3000]}")
    except Exception as e:
        print("error",e)

# decode one story URL
# from earlier network capture we have base64 urls
sample_b64="aHR0cHM6Ly9zY29udGVudC1zamM2LTEuY2RuaW5zdGFncmFtLmNvbS92L3Q1MS43MTg3OC0xNS83ODc2ODI0NDhfMTc1Mjk0NDA2MjQwODA0MV83MDI3NDc2MTY5MDMxMTI2NDMzX24uanBnP3N0cD1kc3QtanBnX2UxNV90dDYmX25jX2NhdD0xMDgmY2I9MzBhNjg4ZjctMWE1YTM2MjQmaWdfY2FjaGVfa2V5PU16azNNamczTmpBd09URTNORGN6TlRjMU1nJTNEJTNELjMtY2NiNy01LWNiMzBhNjg4ZjctMWE1YTM2MjQmY2NiPTctNSZfbmNfc2lkPTU4Y2RhZCZlZmc9ZXlKMlpXNWpiMlJsWDNSaFp5STZJbE5VVDFKWkxuaHdhV1J6TGpZME1DNXpaSEl1ZG1sa1pXOWZaR1ZtWVhWc2RGOWpiM1psY2w5bWNtRnRaUzVETXlKOSZfbmNfb2hjPVEtT2hmTWxlZ2p3UTdrTnZ3SGgzLWw0Jl9uY19vYz1BZHBOcHd6Y3RTNEU2SW1wVHZwVXhWSHdYZTE0anRGaVB0NThiZXdtTnhOZEFUZ21rc3JnZ3J1MG5zLTBINzEtN3hZJl9uY19hZD16LW0mX25jX2NpZD0wJl9uY196dD0yMyZfbmNfaHQ9c2NvbnRlbnQtc2pjNi0xLmNkbmluc3RhZ3JhbS5jb20mX25jX2dpZD1hTnZ6RFRuZkF6ZGdhSU9XQXdYdlRBJl9uY19zcz03YTIyZSZvaD0wMF9BUUV1NEdEQXFNYkVvUjZ2V3ktOUhjZ0tuQWZTNHY1SkhSVkstTmg3cll1czN3Jm9lPTZBOTczNTIz"
print("\ndecode sample", base64.b64decode(sample_b64).decode()[:1000])
