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
- [src/fastdl_api.py](src/fastdl_api.py): API-first FastDL story discovery and response parsing
- [src/story_downloader.py](src/story_downloader.py): downloader flow and archived DOM fallback; do not change unless a specific issue is identified
- [src/state_manager.py](src/state_manager.py): uploaded-state tracking and duplicate prevention
- [src/rclone_uploader.py](src/rclone_uploader.py): remote upload path via rclone
- [.github/workflows/sync.yml](.github/workflows/sync.yml): CI workflow and remote-state persistence

## Project conventions
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
