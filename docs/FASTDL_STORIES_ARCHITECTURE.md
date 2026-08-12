FASTDL Stories: API-first architecture and DOM fallback
=====================================================

Purpose
-------
This document explains how FastDL Stories are discovered and downloaded in this
project. It is written for a developer or an automated agent with no prior
knowledge of the investigation that produced the code.

API (preferred discovery path)
------------------------------
- Endpoint: `POST https://api-wh.fastdl.app/api/v1/instagram/stories`
- Typical request: JSON body containing at least `{"username": "<user>"}`.
  Observed browser requests can include additional signed fields such as
  `ts`, `_ts`, `_tsc`, `_sv`, and `_s`. A Playwright browser bridge that captures
  the real page-generated request is the most reliable way to obtain this.
  Callers should still be prepared to fall back if the API rejects the request.
- Response shape: observed as JSON with a top-level `result` array. Each item
  is an object that commonly contains one or more of:
  - `image_versions2.candidates` -> candidate objects with `url`, `url_wrapped`, `url_downloadable`
  - `video_versions` -> list of video candidate objects with same keys
  - top-level `url_downloadable` / `url_wrapped`
- Download URL: prefer `url_downloadable` or `url_wrapped` (often a proxied
  URL at `media.fastdl.app/get?...`). These proxied URLs often include
  `__sig` and `__expires` query parameters and are ephemeral.
- Detection: inspect `video_versions` vs `image_versions2` or file extension to
  classify `video` vs `image`.
- Ephemeral URLs: do NOT persist proxied URLs into `state.json`. Use them
  immediately. If a proxied URL expires, re-request the Stories API for fresh
  URLs. Avoid re-requesting per-item; prefer re-requesting the API once and
  reuse the new set.

DOM (fallback and maintenance knowledge)
---------------------------------------
- Where to find the DOM code: `src/story_downloader.py` includes the Playwright
  based collector. It remains the canonical fallback and all related functions
  and selectors are preserved.
- Key selectors and elements:
  - Story list items: `.profile-media-list__item`
  - Download buttons: `.button__download`
  - Story timestamp/meta: `.media-content__meta-time`
- Scrolling: `_collect_items_with_scroll(page, ...)` performs repeated
  `scrollIntoView()` on the last `.profile-media-list__item` and samples the
  DOM to detect new items. It intentionally logs debug info and preserves
  container analysis (overflowY detection) to assist future debugging.
- Extraction: the DOM collector returns objects with `u` (download href), `t`
  (timestamp) and `txt` (text parsed from metadata). The downloader continues
  to use `extract_pre_download_id()` to map `u` to a pre-download id for state
  deduplication.
- Observed behaviors to keep in mind:
  - The API often returns more items than the DOM initially renders (example:
    API returned ~35 items while DOM showed 6 in a capture).
  - DOM lazy-loading/virtualization means scrolling doesn't always reveal all
    items; DOM may be incomplete compared to API.
  - Download URLs from API match those observable from the DOM; both lead to
    proxied `media.fastdl.app/get` URLs.

Important findings (observed facts vs heuristics)
-------------------------------------------------
- Observed facts:
  - In our capture, API returned 35 Stories while DOM showed 6.
  - Media proxy URLs contain `__sig`/`__expires` and are ephemeral.
  - GETs of proxied media worked in our checks without cookies or special headers.

- Heuristics / not guaranteed:
  - API may accept minimal payloads; in some cases signatures may be present.
  - The exact set of fields in each Story object may vary; always defensively
    parse.

Debug / investigation assets
---------------------------
- Playwright runner and network capture: `scripts/debug_fastdl_israel.py` — run
  to reproduce a viewer session and capture network responses.
- Focused browser bridge: `scripts/debug_fastdl_api_bridge.py` — captures the
  real signed POST to `/api/v1/instagram/stories` and confirms download URLs
  from the API response.
- API-only feasibility test: `scripts/debug_api_only_stories.py` — parses a
  captured run `scripts/debug_fastdl_israel.json` and performs limited GETs on
  sample proxied URLs (saves partial files in `scripts/debug_api_only/`).
- Other helpers: `scripts/debug_fastdl_story_response.py`, `scripts/debug_fastdl_full_network.py`.

Each script contains a one-line description at top explaining its purpose.

Integration note:
- The production downloader now prefers the API-first path through
  `src/fastdl_api.py` using browser-signed Stories API capture.
- If the API path fails or returns zero usable items, the DOM extraction logic
  remains preserved in `src/story_downloader.py::_fetch_story_urls` and
  `src/story_downloader.py::_collect_items_with_scroll`, but it is not executed
  automatically from the API-first flow.

How the downloader now works (summary)
-------------------------------------
- Primary flow: `story_downloader` uses an API-first approach via
  `src/fastdl_api.py`:
  - `FastDLStoriesAPI.fetch_stories(username)` attempts to POST to the
    Stories API and returns normalized items (download URLs + kind).
  - If this call returns items, the downloader uses them as the source of
    truth for downloads.
- Fallback flow: if the API call fails or returns unexpected shape, the
  existing Playwright-based DOM collector runs unchanged and provides a
  recovery path.

Testing guidance
----------------
Run the focused API-only script against existing captures to validate parsing and
download behavior:

```bash
python -m scripts.debug_api_only_stories
```

When adding automated tests, prefer unit tests for `src/fastdl_api.py` parsing
logic using recorded captures (no live network required).

Security and privacy
--------------------
- Do not commit `state.json` containing persisted upload state.
- Do not commit any captured signed URLs, cookies, or tokens.

Maintenance notes
-----------------
- If API changes, the maintainer should first check `scripts/debug_fastdl_israel.py`
  to capture a fresh API response and then update parsing logic in
  `src/fastdl_api.py`.
- Preserve DOM collector; only change API parsing when confident.

*** End of document ***
