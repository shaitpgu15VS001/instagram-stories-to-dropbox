# AGENTS — project quick-start for AI coding agents

This repo is a Python automation project that downloads public Instagram stories, stores them in a remote target via rclone, and keeps duplicate state remotely under the configured remote.

## Start here
- Install dependencies: `python -m pip install -r requirements.txt`
- Optional browser setup: `playwright install --with-deps chromium`
- Local run: `python -m src.main`
- Test suite: `python -m pytest -q`
- Workflow YAML validation: `python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/sync.yml').read_text(encoding='utf-8'))"`

## Key files
- [src/main.py](src/main.py): entry point, username loading, orchestration
- [src/clipssaver_api.py](src/clipssaver_api.py): primary stories source (ClipSaver token + stories API)
- [src/insta_stories_api.py](src/insta_stories_api.py): secondary stories source (insta-stories.io fallback)
- [src/fastdl_api.py](src/fastdl_api.py): last-resort FastDL stories API and response parsing
- [src/story_downloader.py](src/story_downloader.py): downloader flow and archived DOM fallback; do not change unless a specific issue is identified
- [src/state_manager.py](src/state_manager.py): uploaded-state tracking and duplicate prevention
- [src/partition.py](src/partition.py): split users into parallel parts; reads `USERS_PER_PART.txt`
- [src/state_merge.py](src/state_merge.py): merge part state artifacts into one `state.json` with integrity check
- [src/state_restore.py](src/state_restore.py): restore the freshest remote `state.json` by ModTime (avoids stale copies)
- [USERS_PER_PART.txt](USERS_PER_PART.txt): how many users per parallel part (default 80)
- [src/rclone_uploader.py](src/rclone_uploader.py): remote upload path via rclone
- [.github/workflows/sync.yml](.github/workflows/sync.yml): CI workflow (setup → matrix parts → artifacts → merge → single retry pass) and remote-state persistence

## Project conventions
- Keep the source order in [src/story_downloader.py](src/story_downloader.py) `_fetch_story_urls`: ClipSaver first, then insta-stories.io, then FastDL. Returning `None` means "source failed"; an empty list means "no active stories".
- Keep one ClipSaver client/token per run (`StoryDownloader._get_clipssaver_api`) and the preflight token check (`ensure_story_source_ready` called from `main`) — GitHub Actions IP gets 403 after ~110 token requests.
- Parallel parts: each part runs with `PART_INDEX`/`PART_TOTAL` (set by the workflow matrix) against a FULL restored state and uploads its state as an artifact; the `merge` job unions artifacts into `state.json` (dedup by `pre_download_id`, integrity check: entry count must not drop). Do not make parts write the shared remote `state.json` directly.
- Users per part is controlled by `USERS_PER_PART.txt` (or the `users_per_part` dispatch input); default 80. Keep `max-parallel: 2`. Raising to 4 caused 37 ClipSaver 503s (server overload) vs 7 at 2 — do not raise again without evidence it won't overload the source.
- Transient failures: `ClipSaverAPI` exposes `last_retry_after`; `_fetch_from_clipssaver` retries up to 3 times for transient errors only (honoring `retry_after`), not for blocks/unknown status. Each part writes `retry-users-partN.txt` (transient failures only, never `USER_NOT_FOUND`); the workflow `retry` job runs ONE extra pass via `USERNAMES_OVERRIDE` — do not let it generate another retry list (avoid infinite loops).
- Keep the existing API-first FastDL flow in [src/fastdl_api.py](src/fastdl_api.py). The DOM logic in [src/story_downloader.py](src/story_downloader.py) is preserved for fallback/reference, not as the automatic path.
- Do not change the storage backend selection logic in [src/main.py](src/main.py) unless a real bug requires it and the rationale is explained.
- Keep state persistence aligned with the workflow: `state.json` is restored and uploaded under `<remote>:.instagram-sync/state.json` using rclone. Do not introduce `actions/cache` for `state.json`.
- Do not commit or modify `state.json` in Git.
- Use `RCLONE_CONF` to create `rclone.conf` in CI; do not assume a different remote or auth mechanism.
- If you need to touch storage, state, or workflow behavior, read [.github/workflows/sync.yml](.github/workflows/sync.yml) first and explain the change before implementing it.

## Read these docs when needed
- [SETUP.md](SETUP.md)
- [USAGE.md](USAGE.md)
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- [docs/FASTDL_GUIDE.md](docs/FASTDL_GUIDE.md)
- [docs/FASTDL_STORIES_ARCHITECTURE.md](docs/FASTDL_STORIES_ARCHITECTURE.md)

## Guardrails
- Prefer small, targeted changes.
- Preserve backward compatibility for file names, folder layout, and user input formats unless the docs are updated in the same change.
- Keep automation robust against missing secrets or empty state; do not add broad architecture changes without a clear justification.
- When a bug is found, validate it with the smallest real test or reproduction before patching.
