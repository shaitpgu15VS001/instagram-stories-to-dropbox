Copilot / AI agent quick instructions

- Start by reading [AGENTS.md](../AGENTS.md) and `SETUP.md` to understand project goals and environment.
- Run the test suite locally: `python -m pytest -q`.
- Validate GitHub Actions workflow YAML: `python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/sync.yml').read_text())"`.

Constraints (must follow):
- Do NOT change the storage backend selection logic in `src/main.py` unless a change is required and explained.
- State persistence: `state.json` is stored remotely under `<remote>:.instagram-sync/state.json` via `rclone`. Do not introduce `actions/cache` for `state.json`.
- Do not commit or modify `state.json` in Git.
- Use `RCLONE_CONF` secret to create `rclone.conf` in CI; do not assume a different remote.

Useful commands:
- Install deps: `python -m pip install -r requirements.txt`
- Install Playwright browsers: `playwright install --with-deps chromium`
- Run main sync locally: `python -m src.main`

If you need to change persistence/workflow, propose the change and get explicit approval before implementing.
