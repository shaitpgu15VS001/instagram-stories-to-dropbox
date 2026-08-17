# Copilot / AI agent quick instructions

- Read [AGENTS.md](../AGENTS.md) and [SETUP.md](../SETUP.md) before making changes.
- Run the local check suite: `python -m pytest -q`.
- Validate the workflow YAML with UTF-8 encoding: `python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/sync.yml').read_text(encoding='utf-8'))"`.

## Required constraints
- Do not change the storage backend selection logic in [src/main.py](../src/main.py) unless there is a clear bug and an explanation for the change.
- Keep remote state persistence in the existing rclone pattern: `state.json` is stored under `<remote>:.instagram-sync/state.json`.
- Do not introduce `actions/cache` for `state.json`.
- Do not commit or modify `state.json` in Git.
- Use `RCLONE_CONF` in CI to create `rclone.conf`; do not assume a different remote configuration.

## Useful commands
- Install deps: `python -m pip install -r requirements.txt`
- Install browser runtime: `playwright install --with-deps chromium`
- Run the sync locally: `python -m src.main`

## Architecture notes
- The project is API-first around [src/fastdl_api.py](../src/fastdl_api.py); the DOM path in [src/story_downloader.py](../src/story_downloader.py) is preserved as fallback/reference.
- Workflow and persistence changes should be proposed and explicitly approved before implementation.
- Prefer small, targeted edits that keep the current remote state and upload model intact.
