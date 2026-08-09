import json
import sys
from pathlib import Path
# ensure project root on sys.path so `src` can be imported
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import story_downloader as sd
from src.logger import logger

logger.set_level('debug')

P = Path(__file__).resolve().parents[1] / 'playwright_israel_bidur.json'
if not P.exists():
    print('playwright_israel_bidur.json not found at', P)
    raise SystemExit(1)

data = json.loads(P.read_text(encoding='utf-8'))
# data is a list of runs; each run has 'items' list; build sequence of counts
counts = []
for run in data:
    items = run.get('items') or []
    counts.append(len(items))
if not counts:
    print('no runs/items in the JSON')
    raise SystemExit(1)

# compress counts to a sequence where each iteration shows how many items are observed
# we'll simulate that initial counts[0] is initial, and then later counts may increase
# For safety, make a monotonic sequence by taking max so far
seq = []
maxc = 0
for c in counts:
    if c > maxc:
        maxc = c
    seq.append(maxc)
# Ensure at least two steps
if len(seq) < 2:
    seq = [seq[0], seq[0]]

print('Simulated counts sequence:', seq)

class FakePage:
    def __init__(self, counts):
        self.counts = counts
        self.idx = 0

    def evaluate(self, js):
        s = js.strip()
        # length / metrics check - return a metrics dict similar to real page.evaluate
        if 'document.querySelectorAll' in s and '.length' in s:
            return {'count': self.counts[self.idx], 'winY': 0, 'docH': 1000, 'bodyH': 1000, 'container': None}
        # check for found_last
        if "return items.length > 0" in s:
            return self.counts[self.idx] > 0
        # scrollIntoView simulation
        if 'scrollIntoView' in s:
            # simulate that scrolling will cause the next step to have more items if possible
            if self.idx + 1 < len(self.counts):
                before = {'winY': 0, 'docH': 1000, 'bodyH': 1000}
                self.idx += 1
                after = {'winY': 100, 'docH': 2000, 'bodyH': 2000}
                return {'before': before, 'after': after}
            return None
        # map collection
        if '.map(li' in s or 'map(li =>' in s:
            n = self.counts[self.idx]
            items = []
            for i in range(n):
                items.append({'u': f'https://fastdl/item/{i}', 'x': float(i * 10), 'y': float((i // 3) * 100), 't': '', 'txt': ''})
            return items
        # default dict for metrics
        if 'return {count' in s:
            return {'count': self.counts[self.idx], 'winY': 0, 'docH': 1000, 'bodyH': 1000, 'container': None}
        return None

    def wait_for_timeout(self, ms):
        return None


page = FakePage(seq)
items = sd._collect_items_with_scroll(page, max_scrolls=10, wait_ms=100)
print('Final collected items:', len(items))
for i, it in enumerate(items[:10]):
    print(i, it.get('u'))
