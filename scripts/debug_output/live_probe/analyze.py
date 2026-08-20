#!/usr/bin/env python3
import json
from pathlib import Path

d = json.load(open(r'scripts\debug_output\live_probe\live_probe_report.json', encoding='utf-8'))
lines = []
for u in d['users']:
    lines.append('===== ' + u['username'] + ' =====')
    lines.append('REQ: ' + json.dumps(u['stories_request'], ensure_ascii=False))
    lines.append('RESP: ' + json.dumps(u['stories_response'], ensure_ascii=False))
    lines.append('SUMMARY: ' + json.dumps(u['response_summary'], ensure_ascii=False))
    evs = [s for s in u['steps'] if s['event'] in ('request', 'response', 'requestfailed', 'stories_tab_clicked')]
    lines.append('STEPS: ' + json.dumps(evs, ensure_ascii=False))
    lines.append('DOM_ALL: ' + json.dumps(u['dom_observations'], ensure_ascii=False))
    lines.append('')
Path('scripts/debug_output/live_probe/analysis.txt').write_text('\n'.join(lines), encoding='utf-8')
print('written')