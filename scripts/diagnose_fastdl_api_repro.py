"""Diagnostic: attempt to reproduce FastDL Stories API POSTs.

Tries two POSTs:
- minimal payload: {"username": "israel_bidur"}
- captured payload (copied fields including _s)

Prints status code and counts.
"""
import requests
import json

URL = 'https://api-wh.fastdl.app/api/v1/instagram/stories'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}

def try_post(payload):
    try:
        r = requests.post(URL, json=payload, headers=HEADERS, timeout=15)
    except Exception as e:
        print('EXCEPTION', e)
        return None
    print('status', r.status_code)
    ct = r.headers.get('Content-Type','')
    print('content-type', ct)
    try:
        j = r.json()
        if isinstance(j, dict) and 'result' in j and isinstance(j['result'], list):
            print('result_count', len(j['result']))
        else:
            print('body_keys', list(j.keys()) if isinstance(j, dict) else type(j))
    except Exception as e:
        print('json parse error', e)
        print('text snip', r.text[:500])
    return r

if __name__ == '__main__':
    print('Attempt A: minimal payload')
    try_post({'username': 'israel_bidur'})

    print('\nAttempt B: captured payload (may be stale)')
    captured = {"username":"israel_bidur","ts":1786535519065,"_ts":1785411663296,"_tsc":0,"_sv":2,"_s":"2e8c8e82c3066bd540afe620eff29b35ff4036293596a61e1ebda42aa3c3325f"}
    try_post(captured)
