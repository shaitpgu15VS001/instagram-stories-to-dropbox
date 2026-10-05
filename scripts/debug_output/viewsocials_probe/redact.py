import pathlib, re
probe_dir = pathlib.Path('scripts/debug_output/viewsocials_probe')
for p in probe_dir.glob('*.json'):
    text = p.read_text(encoding='utf-8', errors='ignore')
    orig = text
    text = re.sub(r'eyJpdiI[^"\s]+', '[REDACTED_XSRF]', text)
    text = re.sub(r'"value"\s*:\s*"eyJ[^"]+"', '"value": "[REDACTED]"', text)
    text = re.sub(r'x-xsrf-token"\s*:\s*"[^"]+"', '"x-xsrf-token": "[REDACTED]"', text, flags=re.I)
    text = re.sub(r'laravel_session.*?"[^"]+"', '"laravel_session": "[REDACTED]"', text, flags=re.I)
    text = re.sub(r'__cf_bm.*?"[^"]+"', '"__cf_bm": "[REDACTED]"', text)
    if text != orig:
        p.write_text(text, encoding='utf-8')
        print(f'redacted {p.name}')
    else:
        print(f'no change {p.name}')
for p in probe_dir.glob('*.html'):
    t = p.read_text(encoding='utf-8')
    t2 = re.sub(r'<meta name="csrf-token" content="[^"]+"', '<meta name="csrf-token" content="[REDACTED]"', t)
    if t2 != t:
        p.write_text(t2, encoding='utf-8')
        print(f'redacted html {p.name}')
