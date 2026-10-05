import requests, re, base64, json, urllib.parse, pathlib, time
OUT = pathlib.Path("scripts/debug_output/viewsocials_probe")
headers_base={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def do_session_test(run_id):
    print(f"\n=== RUN {run_id} ===")
    s = requests.Session()
    s.headers.update(headers_base)
    # 1 GET user page
    url = "https://storynavigation.com/user/israel_bidur"
    r = s.get(url, timeout=20)
    print(f"GET {url} -> {r.status_code} len {len(r.text)}")
    # extract userId
    m = re.search(r'"id"\s*:\s*(\d+)', r.text)
    if m:
        user_id = int(m.group(1))
        print(f"found user_id {user_id}")
    else:
        # try profile-page prop
        m2 = re.search(r'user-info-prop.*?id.*?:(\d+)', r.text)
        print("user_id not found via first regex")
        user_id=None
        # fallback to known
        user_id=508790485
    # extract csrf meta (not needed for xsrf but check)
    m_csrf = re.search(r'<meta name="csrf-token" content="([^"]+)">', r.text)
    if m_csrf:
        print(f"csrf meta {m_csrf.group(1)[:20]}...")
    # cookies
    print("cookies:", list(s.cookies.keys()))
    # find XSRF token
    xsrf_cookie = None
    for c in s.cookies:
        if c.name == "XSRF-TOKEN":
            xsrf_cookie = c.value
            print(f"XSRF cookie raw len {len(xsrf_cookie)} val {xsrf_cookie[:100]}...")
    # need to url-decode
    if xsrf_cookie:
        xsrf_decoded = urllib.parse.unquote(xsrf_cookie)
        print(f"decoded xsrf len {len(xsrf_decoded)} {xsrf_decoded[:100]}...")
    else:
        print("NO XSRF cookie!")
        return None
    # try POST
    api = "https://storynavigation.com/get-user-last-stories"
    payload = {"userName":"israel_bidur","isPrivate":"","instagramUserId":user_id}
    headers_post = {
        "Referer": url,
        "Origin": "https://storynavigation.com",
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json, text/plain, */*",
        "X-XSRF-TOKEN": xsrf_decoded,
        "X-CSRF-TOKEN": m_csrf.group(1) if m_csrf else ""
    }
    # also try x-xsrf-token lower
    # requests will automatically send cookies
    rr = s.post(api, json=payload, headers=headers_post, timeout=20)
    print(f"POST -> {rr.status_code} ctype {rr.headers.get('content-type')} body len {len(rr.text)}")
    print(rr.text[:3000])
    if rr.status_code==200:
        try:
            j=rr.json()
            print(f"found {len(j.get('lastStories',[]))} stories")
            # decode one
            if j.get('lastStories'):
                first=j['lastStories'][0]
                print("first keys", first.keys())
                print("type", first.get('type'), "id", first.get('id'))
                # decode URLs
                for k in ['url','thumbnailUrl','videoUrl']:
                    if first.get(k):
                        decoded = base64.b64decode(first[k]).decode()
                        print(f"{k} decoded -> {decoded[:250]}")
                # try download via cdn.storynavigation.com
                # for image: use thumbnailUrl via cdn
                thumb_b64=first.get('thumbnailUrl')
                if thumb_b64:
                    decoded_thumb=base64.b64decode(thumb_b64).decode()
                    cdn_url = "https://cdn.storynavigation.com/?" + thumb_b64
                    print(f"cdn_url: {cdn_url[:200]}")
                    # try fetch cdn url
                    rthumb = s.get(cdn_url, headers={"Referer": url}, timeout=15)
                    print(f"GET cdn thumb -> {rthumb.status_code} ctype {rthumb.headers.get('content-type')} len {len(rthumb.content)}")
                    # also try direct instagram url (may fail)
                    r_direct = requests.get(decoded_thumb, headers=headers_base, timeout=10)
                    print(f"GET direct thumb -> {r_direct.status_code} {r_direct.headers.get('content-type','')[:50]} len {len(r_direct.content) if r_direct.status_code==200 else 0}")
                # if video, test stories-cdn.fun
                if first.get('type')=='video' and first.get('videoUrl'):
                    video_b64=first.get('videoUrl')
                    decoded_video=base64.b64decode(video_b64).decode()
                    print(f"video decoded preview {decoded_video[:300]}")
                    fun_url="https://stories-cdn.fun/"+video_b64
                    print(f"fun url {fun_url[:200]}")
                    # we won't fetch large video fully, just head
                    try:
                        rh = s.head(fun_url, timeout=15, allow_redirects=True)
                        print(f"HEAD fun -> {rh.status_code} headers {dict(list(rh.headers.items())[:5])}")
                    except Exception as e:
                        print("head fun error",e)
                # save json
                (OUT / f"replay_run_{run_id}.json").write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")
                return j
        except Exception as e:
            print("json parse error",e)
    else:
        print("POST failed")
    return None

for i in range(1,4):
    do_session_test(i)
    time.sleep(2)

# also test without xsrf token (should be 419)
print("\n=== Negative test without xsrf ===")
s=requests.Session()
s.headers.update(headers_base)
s.get("https://storynavigation.com/user/israel_bidur", timeout=15)
rr=s.post("https://storynavigation.com/get-user-last-stories", json={"userName":"israel_bidur","isPrivate":"","instagramUserId":508790485}, headers={"Referer":"https://storynavigation.com/user/israel_bidur","Content-Type":"application/json"}, timeout=15)
print(f"without xsrf -> {rr.status_code} {rr.text[:500]}")

# also test with wrong userId
print("\n=== Test with generic username existence check ===")
# try fetching user not exist flow?
