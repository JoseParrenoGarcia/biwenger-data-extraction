# macOS LaunchAgent Scheduler Guide

This repo uses macOS LaunchAgents plus repo-owned shell scripts for local
scheduled Biwenger scraping.

Use LaunchAgents instead of cron because the scraper runs best in a logged-in
macOS user session and can show notifications.

## Supported Jobs

The scheduler is intentionally split into separate jobs:

- current team: `bash_scripts/run_current_team.sh`
- players: `bash_scripts/run_players.sh`

There is no combined full-pipeline scheduler script. If both jobs are needed,
schedule both or run the two scripts manually.

## Script Behavior

Both scripts:

- derive the repo root from their own location;
- require `.venv/bin/python` and fail clearly if it is missing;
- run headed Chromium by default;
- send start/success/failure macOS notifications when `osascript` is available;
- create timestamped scheduler logs under `run_artifacts/launchd/`;
- delete scheduler log folders older than 7 days by default.

Player runs also create the normal checkpoint bundle under:

```text
run_artifacts/player_runs/<run_id>/
```

That folder remains the main recovery/debug artifact for player scraping.

## macOS Privacy Note

The current local repo path is under:

```text
/Users/joseparreno/Documents/GitHub/biwenger-data-extraction
```

macOS can block LaunchAgents from executing scripts, Python interpreters, or log
paths under `Documents` unless the relevant process has privacy permission. A
manual LaunchAgent probe in this repo showed:

- direct script execution from `Documents` can fail with exit code `126`;
- LaunchAgent stdout/stderr paths inside the repo can fail before the job runs;
- Python launched from launchd can hit `Operation not permitted` when importing
  from a repo under `Documents`.

The cleanest long-term fix is to keep scheduled repos outside protected folders,
for example under `~/Developer/` or `~/GitHub/`. The other option is granting
the relevant terminal/shell/Python process Full Disk Access in macOS System
Settings.

The plist examples write launchd's early stdout/stderr to `/tmp` for this
reason. Once the scraper starts successfully, the repo scripts still create the
normal timestamped logs under `run_artifacts/launchd/`.

## Production Commands

Current team:

```bash
bash bash_scripts/run_current_team.sh
```

Players:

```bash
bash bash_scripts/run_players.sh
```

The player script defaults to:

```bash
.venv/bin/python -m scraping_biwenger.get_player_stats \
  --headed \
  --upload-batch-size 10 \
  --retry-top-players 150 \
  --run-retention-days 7
```

## Safe Manual Scheduler Test

Before enabling the daily player LaunchAgent, validate the same script with only
two players:

```bash
BIWENGER_MAX_PLAYER_PAGES=1 BIWENGER_MAX_PLAYERS=2 bash bash_scripts/run_players.sh
```

Equivalent Make target:

```bash
make scheduler-test-players-2
```

This is a real write-capable scheduler-shaped run. Use it only when writing to
Supabase is acceptable.

For a no-write test:

```bash
BIWENGER_DRY_RUN=1 BIWENGER_MAX_PLAYER_PAGES=1 BIWENGER_MAX_PLAYERS=2 bash bash_scripts/run_players.sh
```

## Useful Environment Variables

These can be set in the shell before running a script, or inside a LaunchAgent
`EnvironmentVariables` block.

| Variable | Applies to | Default | Purpose |
| --- | --- | --- | --- |
| `BIWENGER_NOTIFY` | both | `1` | Set `0` to disable macOS notifications. |
| `BIWENGER_DRY_RUN` | both | `0` | Set `1` to skip Supabase writes. |
| `BIWENGER_RUN_RETENTION_DAYS` | both | `7` | Days to retain timestamped scheduler logs. |
| `BIWENGER_UPLOAD_BATCH_SIZE` | players | `10` | Players between live Supabase batch uploads. |
| `BIWENGER_RETRY_TOP_PLAYERS` | players | `150` | Retry first-pass failures for top N players. |
| `BIWENGER_MAX_PLAYER_PAGES` | players | unset | Limit player table pages. |
| `BIWENGER_MAX_PLAYERS` | players | unset | Limit player details scraped. |
| `BIWENGER_PLAYER_SLUG` | players | unset | Scrape one player by slug. |
| `BIWENGER_DEBUG_LOG` | players | `0` | Set `1` to include DEBUG timing records. |

## Install A LaunchAgent

1. Copy the example plist:

   ```bash
   cp launchd/com.biwenger.players.plist.example \
     ~/Library/LaunchAgents/com.biwenger.players.plist
   ```

2. Edit the copied plist and replace every
   `/ABSOLUTE/PATH/TO/biwenger-data-extraction` placeholder with the repo's
   absolute path.

   From the repo root, this prints the value to use:

   ```bash
   pwd
   ```

3. Validate the plist:

   ```bash
   plutil -lint ~/Library/LaunchAgents/com.biwenger.players.plist
   ```

4. Load it:

   ```bash
   launchctl unload ~/Library/LaunchAgents/com.biwenger.players.plist 2>/dev/null || true
   launchctl load ~/Library/LaunchAgents/com.biwenger.players.plist
   ```

5. Trigger it manually without waiting for the schedule:

   ```bash
   launchctl start com.biwenger.players
   ```

The included examples run daily at 10:00.

## Temporary 2-Player LaunchAgent Test

To test launchd wiring without a full player run, add this block inside the
players plist before loading it:

```xml
<key>EnvironmentVariables</key>
<dict>
  <key>BIWENGER_MAX_PLAYER_PAGES</key>
  <string>1</string>
  <key>BIWENGER_MAX_PLAYERS</key>
  <string>2</string>
</dict>
```

Remove that block before enabling the full production schedule.

## Inspect Jobs

List Biwenger jobs:

```bash
launchctl list | grep biwenger
```

Inspect a job:

```bash
launchctl print gui/$(id -u)/com.biwenger.players | egrep 'path =|program =|last exit|state ='
```

Run now:

```bash
launchctl start com.biwenger.players
```

Unload:

```bash
launchctl unload ~/Library/LaunchAgents/com.biwenger.players.plist
```

Remove:

```bash
launchctl remove com.biwenger.players 2>/dev/null || true
rm -f ~/Library/LaunchAgents/com.biwenger.players.plist
```

## Logs

Launchd stdout/stderr paths in the plist are stable files under `/tmp` used to
catch early startup failures before repo logging starts:

```text
/tmp/biwenger.players.launchd.stdout.log
/tmp/biwenger.players.launchd.stderr.log
/tmp/biwenger.current-team.launchd.stdout.log
/tmp/biwenger.current-team.launchd.stderr.log
```

The repo scripts create timestamped logs here:

```text
run_artifacts/launchd/current_team/<timestamp>/script.log
run_artifacts/launchd/players/<timestamp>/script.log
```

Player scraper run artifacts are separate:

```text
run_artifacts/player_runs/<run_id>/run.log
```

If a player run needs to be replayed without Biwenger:

```bash
.venv/bin/python -m scraping_biwenger.get_player_stats --upload-checkpoint run_artifacts/player_runs/<run_id>
```

## Notification Check

Notifications appear under Script Editor on macOS. Test them once with:

```bash
osascript -e 'display notification "Testing notifications" with title "Biwenger"'
```

If no popup appears, enable notifications for Script Editor in System Settings.

## Common Failure Modes

- Missing venv: create `.venv` and run `make install`.
- Plist has placeholders: replace all `/ABSOLUTE/PATH/TO/...` values.
- Script not executable: run `chmod +x bash_scripts/run_players.sh`.
- Launchd exit code `126`: check script executable bit and macOS privacy
  permissions. If the repo is under `Documents`, move it outside `Documents` or
  grant Full Disk Access.
- Launchd exit code `78` with empty logs: check `StandardOutPath` and
  `StandardErrorPath`; paths under protected folders can fail before the command
  runs.
- Browser or Biwenger failure: inspect the timestamped scheduler log and the
  player run folder.
