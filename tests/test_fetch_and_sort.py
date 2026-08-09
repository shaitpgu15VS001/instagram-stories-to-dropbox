from datetime import datetime, timezone

from src import story_downloader as sd


def test_sort_by_timestamp_absolute_and_relative():
    # absolute timestamps (dd.mm.yyyy, HH:MM:SS)
    a = {'u': 'u1', 't': '01.01.2020, 00:00:00', 'txt': ''}
    b = {'u': 'u2', 't': '02.01.2020, 00:00:00', 'txt': ''}
    c = {'u': 'u3', 't': '', 'txt': '5 minutes'}  # relative
    items = [b, c, a]
    sorted_items = sd._sort_items_chronologically(items)
    # oldest first -> a, b, c (c parsed to recent time, goes to end)
    assert [it['u'] for it in sorted_items][:2] == ['u1', 'u2']


class FakePage:
    def __init__(self, counts):
        # counts: list of integers returned by successive length checks
        self.counts = counts
        self.idx = 0
        self._length_called = 0

    def evaluate(self, js):
        s = js.strip()
        if 'return {count' in s or ('document.querySelectorAll' in s and 'winY' in s):
            # return a metrics dict
            return {'count': self.counts[self.idx], 'winY': 0, 'docH': 1000, 'bodyH': 1000, 'container': None}
        if 'document.querySelectorAll' in s and '.length' in s:
            # first time return initial count, subsequent calls return final count
            self._length_called += 1
            if self._length_called == 1:
                return self.counts[0]
            return self.counts[-1]
        if 'scrollIntoView' in s:
            # simulate loading more items after a scroll
            if self.idx + 1 < len(self.counts):
                self.idx += 1
                return True
            return False
        # map collection
        if 'map(li' in s or 'map(li =>' in s:
            # return the current (final) count as the loaded number of items
            n = self.counts[-1]
            items = []
            for i in range(n):
                items.append({'u': f'https://fastdl/item/{i}', 'x': float(i * 10), 'y': float((i // 3) * 100), 't': '', 'txt': ''})
            return items
        return None

    def wait_for_timeout(self, ms):
        return None


def test_collect_items_after_scroll():
    # simulate initial 6 items, after first scroll 10 items
    page = FakePage([6, 10])
    items = sd._collect_items_with_scroll(page, max_scrolls=5, wait_ms=0)
    assert len(items) == 10
    assert items[0]['u'] == 'https://fastdl/item/0'
    assert items[-1]['u'] == 'https://fastdl/item/9'
