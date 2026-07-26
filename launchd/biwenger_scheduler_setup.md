# Biwenger launchd Scheduler Setup

This is the supported macOS scheduling path for the repo.

Use:

- `bash_scripts/run_players.sh` for the headed player scraper
- `bash_scripts/run_current_team.sh` for the headed current-team scraper
- `launchd/com.biwenger.players.plist.example` and
  `launchd/com.biwenger.current-team.plist.example` as the source templates

The active LaunchAgent plist files live under:

```bash
~/Library/LaunchAgents
```

These jobs are designed for a stable local checkout with a prepared project
virtualenv at `.venv/bin/python`.

## Important behavior

- These are **LaunchAgents**, not daemons, so they run in your logged-in user
  session and can open a headed Chromium window.
- The Mac should be logged in when the job runs.
- The repo path should stay stable. The LaunchAgent plist points to an absolute
  script path inside the repo.
- Use a scheduler checkout outside `Documents/`, for example
  `~/Code/biwenger-data-extraction`. The July 26, 2026 smoke test showed macOS
  privacy restrictions can block LaunchAgent execution from
  `~/Documents/GitHub/...` with `Operation not permitted`.
- Scheduler scripts write their own wrapper log under:

```bash
run_artifacts/launchd/<job_name>/<timestamp>/script.log
```

- Player runs still write their real scrape artifacts under:

```bash
run_artifacts/player_runs/<run_id>/
```

## One-time local preparation

From the repo root:

```bash
chmod +x bash_scripts/biwenger_job_lib.sh
chmod +x bash_scripts/run_players.sh
chmod +x bash_scripts/run_current_team.sh
chmod +x bash_scripts/run_scraping_players.sh
chmod +x bash_scripts/dev_run_scraping_players.sh
```

## Create the active LaunchAgent plist files

These commands copy the repo templates into the active user LaunchAgents folder
and replace the placeholder repo path with the current checkout path.

From the repo root:

```bash
mkdir -p "$HOME/Library/LaunchAgents"
cp launchd/com.biwenger.players.plist.example "$HOME/Library/LaunchAgents/com.biwenger.players.plist"
cp launchd/com.biwenger.current-team.plist.example "$HOME/Library/LaunchAgents/com.biwenger.current-team.plist"
python3 - <<'PY'
from pathlib import Path

repo = Path.cwd()
launch_agents = Path.home() / "Library" / "LaunchAgents"
for name in ("com.biwenger.players.plist", "com.biwenger.current-team.plist"):
    path = launch_agents / name
    path.write_text(
        path.read_text().replace(
            "/ABSOLUTE/PATH/TO/biwenger-data-extraction",
            str(repo),
        )
    )
PY
```

## Validate the plist files

```bash
plutil -lint "$HOME/Library/LaunchAgents/com.biwenger.players.plist"
plutil -lint "$HOME/Library/LaunchAgents/com.biwenger.current-team.plist"
```

## Load the jobs

For fresh load:

```bash
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.biwenger.players.plist" 2>/dev/null || true
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.biwenger.current-team.plist" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.biwenger.players.plist"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.biwenger.current-team.plist"
```

## Manually trigger the jobs

These are the best smoke tests before trusting the schedule:

```bash
launchctl kickstart -k "gui/$(id -u)/com.biwenger.players"
launchctl kickstart -k "gui/$(id -u)/com.biwenger.current-team"
```

## Check loaded status

```bash
launchctl print "gui/$(id -u)/com.biwenger.players" | egrep 'state =|program =|last exit code ='
launchctl print "gui/$(id -u)/com.biwenger.current-team" | egrep 'state =|program =|last exit code ='
```

## Test safely with limited players

Before enabling a real production scrape, edit the active player plist and add:

```xml
<key>EnvironmentVariables</key>
<dict>
  <key>BIWENGER_UPLOAD_BATCH_SIZE</key>
  <string>10</string>
  <key>BIWENGER_RETRY_TOP_PLAYERS</key>
  <string>400</string>
  <key>BIWENGER_MAX_PLAYER_PAGES</key>
  <string>1</string>
  <key>BIWENGER_MAX_PLAYERS</key>
  <string>2</string>
</dict>
```

Then reload and kickstart again.

## Useful environment variables for the player job

These can be set in the player plist under `EnvironmentVariables`:

- `BIWENGER_UPLOAD_BATCH_SIZE`
- `BIWENGER_RETRY_TOP_PLAYERS`
- `BIWENGER_MAX_PLAYER_PAGES`
- `BIWENGER_MAX_PLAYERS`
- `BIWENGER_PLAYER_SLUG`
- `BIWENGER_RESUME_CHECKPOINT`
- `BIWENGER_DRY_RUN=1`
- `BIWENGER_DEBUG_LOG=1`
- `BIWENGER_RUN_RETENTION_DAYS=7`
- `BIWENGER_NOTIFY=0` to disable macOS notifications

## Unload the jobs

```bash
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.biwenger.players.plist"
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.biwenger.current-team.plist"
```

## Remove the jobs completely

```bash
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.biwenger.players.plist" 2>/dev/null || true
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.biwenger.current-team.plist" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/com.biwenger.players.plist"
rm -f "$HOME/Library/LaunchAgents/com.biwenger.current-team.plist"
```

## Troubleshooting

- If the job fails immediately, check:

```bash
tail -n 200 /tmp/biwenger.players.launchd.stdout.log
tail -n 200 /tmp/biwenger.players.launchd.stderr.log
find run_artifacts/launchd -maxdepth 3 -name script.log | tail
```

- If the browser does not appear, confirm the job was loaded as a
  **LaunchAgent** under your user session, not as a system daemon.
- If the script cannot find Python, rebuild the repo virtualenv and confirm
  `.venv/bin/python` exists.
- If the wrapper log shows Python import or syntax failures, confirm the
  scheduler checkout uses the same Python major/minor version as the main repo.
  The validated setup on July 26, 2026 used Python `3.13`.
