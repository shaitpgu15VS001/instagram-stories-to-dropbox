"""Local E2E runner for a single user (no uploads, no state changes).

Saves files under `tmp_e2e/<username>/` and prints a detailed report.
"""
import os
import sys
import traceback
from pathlib import Path
from pprint import pprint

from src.story_downloader import StoryDownloader, format_taken_at_for_filename, _is_jpeg, _is_mp4

MAX_STORIES = 6
USERNAME = 'erevtov'
OUT_ROOT = Path('tmp_e2e')


def safe_mkdir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def main():
    out_dir = OUT_ROOT / USERNAME
    safe_mkdir(out_dir)
    downloader = StoryDownloader(output_dir=OUT_ROOT)

    print(f"Fetching story URLs for {USERNAME}...")
    items = downloader._fetch_story_urls(USERNAME)
    if items is None:
        print("No items returned from API/bridge")
        return 1
    total = len(items)
    print(f"Total items from API: {total}")
    to_proc = items[:MAX_STORIES]

    print(f"Processing {len(to_proc)} items (limited to {MAX_STORIES})")

    results = []
    # Ensure browser/context ready
    try:
        downloader._ensure_browser_context()
    except Exception as exc:
        print("Failed to start browser context:", exc)
        traceback.print_exc()
        return 2

    for idx, s in enumerate(to_proc, 1):
        url = s.get('u')
        ta = s.get('ta')
        kind_report = {'index': idx, 'url': url, 'ta': ta, 'chosen_kind': None}
        try:
            media = downloader._download_media_via_browser_context(url, timeout_seconds=60)
            content = media['content']
            status = media.get('status')
            content_type = media.get('content_type')
            final_url = media.get('final_url')
            # determine actual signature
            is_mp4 = _is_mp4(content)
            is_jpeg = _is_jpeg(content)
            # decide ext: prefer signature
            if is_mp4:
                ext = '.mp4'
                chosen_kind = 'video'
            elif is_jpeg:
                ext = '.jpg'
                chosen_kind = 'image'
            else:
                # fallback to header/URL heuristics
                ct = (content_type or '').lower()
                if 'video' in ct or '.mp4' in (url or '').lower():
                    ext = '.mp4'
                    chosen_kind = 'video'
                else:
                    ext = '.jpg'
                    chosen_kind = 'image'

            kind_report['chosen_kind'] = chosen_kind
            kind_report['final_url'] = final_url
            kind_report['http_status'] = status
            kind_report['content_type_header'] = content_type
            kind_report['bytes'] = len(content)

            # filename
            ts = None
            if ta:
                ts = format_taken_at_for_filename(ta)
            if not ts:
                ts = 'unknown'
            filename = f"{USERNAME}-{ts}{ext}"
            p = out_dir / filename
            p.write_bytes(content)

            # validation
            validation = None
            if ext == '.mp4':
                validation = 'mp4_signature' if is_mp4 else 'mp4_signature_missing'
            elif ext in ('.jpg', '.jpeg'):
                validation = 'jpeg_signature' if is_jpeg else 'jpeg_signature_missing'
            else:
                validation = 'unknown_format'

            kind_report.update({
                'saved_path': str(p),
                'saved_size': p.stat().st_size,
                'validation': validation,
                'detected_as_mp4': is_mp4,
                'detected_as_jpeg': is_jpeg,
            })

        except Exception as exc:
            kind_report['error'] = str(exc)
            import traceback
            traceback.print_exc()
        results.append(kind_report)

    # Close browser
    try:
        downloader._close_browser_context()
    except Exception:
        pass

    # Summarize
    print('\nE2E SUMMARY')
    print('Total items from API:', total)
    video_count = sum(1 for it in items if (it.get('u') or '').lower().find('.mp4') != -1)
    image_count = total - video_count
    print('Heuristic video count (api url contains .mp4):', video_count)
    print('Heuristic image count:', image_count)
    print('\nPer-item results (limited):')
    for r in results:
        pprint(r)

    # Provide at least 3 successful examples if available
    succ = [r for r in results if r.get('saved_path')]
    print(f"\nSuccessful downloads: {len(succ)}")
    for ex in succ[:3]:
        print('\nExample:')
        print('taken_at (raw):', ex.get('ta'))
        print('filename:', Path(ex.get('saved_path')).name)
        print('saved_size:', ex.get('saved_size'))
        print('http_status:', ex.get('http_status'))
        print('content_type_header:', ex.get('content_type_header'))
        print('validation:', ex.get('validation'))
        print('detected_as_mp4:', ex.get('detected_as_mp4'))

    return 0


if __name__ == '__main__':
    rc = main()
    sys.exit(rc)
