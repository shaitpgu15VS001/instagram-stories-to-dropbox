from pathlib import Path

from src.story_downloader import StoryDownloader


def main():
    sd = StoryDownloader(output_dir=Path('tmp_verify'))
    try:
        urls = sd._fetch_story_urls('israel_bidur')
        print('story_urls_count=', len(urls) if urls else 0)
        if not urls:
            raise SystemExit(1)
        url = urls[0]['u']
        print('first_url=', url[:220])
        media = sd._download_media_via_browser_context(url, timeout_seconds=60)
        print('status=', media['status'])
        print('content_type=', media['content_type'])
        print('bytes=', len(media['content']))
        print('final_url=', media['final_url'][:220])
    finally:
        sd._close_browser_context()


if __name__ == '__main__':
    main()
