# macOS LaunchAgent (plist) — Quickstart & Troubleshooting Guide

This doc shows how we set up a **test LaunchAgent** that fires every minute and shows a **macOS notification** (popup). It’s the same pattern you’ll use to schedule your Biwenger scrapers.

---

## What’s a LaunchAgent (and a `.plist`)?

- **launchd** is macOS’s built-in scheduler/service manager (think “macOS-native cron + services”).
- A **LaunchAgent** is a job that runs **in your logged-in user session** (so it can show popups, use GUI-ish tools, etc.).
- Each job is defined by a small **property list** file (`.plist`) in `~/Library/LaunchAgents/`.
- The plist contains keys like:
  - `Label`: the job’s unique name (used with `launchctl start <Label>`).
  - `ProgramArguments`: the exact command to run (as an **array**, no shell expansion unless you explicitly call a shell).
  - `StartInterval` or `StartCalendarInterval`: when to run.
  - `RunAtLoad`: run once immediately after being loaded.
  - `StandardOutPath`/`StandardErrorPath`: where stdout/stderr go.

> **Why LaunchAgent over cron?** Agents run with your GUI session, so **macOS notifications work**. Cron often runs in a headless context and can’t show popups.

---

## Folder locations (very important)

- **Your user agents (use this):** `~/Library/LaunchAgents/`  
  (`~` expands to `/Users/<yourname>`)
- **System-wide agents (not for this use):** `/Library/LaunchAgents/` (requires admin; runs for all users)

Open your user LaunchAgents folder in Finder:
```bash
open ~/Library/LaunchAgents
```

---

## Step-by-step: Create a minimal popup job

### 0) Enable notifications for Script Editor (once)
`osascript` notifications appear under **Script Editor** in System Settings.
1. Run this in Terminal:
   ```bash
   osascript -e 'display notification "Testing notifications" with title "Biwenger"'
   ```
2. Go to **System Settings → Notifications**, find **Script Editor**, and enable notifications (Banner/Alert).

### 1) Create a simple script in `~/bin`
Avoid Documents-folder privacy restrictions by using `~/bin`.

```bash
mkdir -p "$HOME/bin"
nano "$HOME/bin/notify_test.sh"
```

Paste:
```bash
#!/usr/bin/env bash
set -euo pipefail
/usr/bin/osascript -e 'display notification "Job ran at '"$(/bin/date)"'" with title "Biwenger Cron"'
/bin/echo "notified at $(/bin/date)"
```

Make it executable & test:
```bash
chmod +x "$HOME/bin/notify_test.sh"
"$HOME/bin/notify_test.sh"
```

### 2) Create the LaunchAgent plist
```bash
nano ~/Library/LaunchAgents/com.biwenger.notify.test.plist
```

Paste **exactly**:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.biwenger.notify.test</string>

  <key>ProgramArguments</key>
  <array>
    <string>/Users/joseparreno/bin/notify_test.sh</string>
  </array>

  <key>RunAtLoad</key><true/>
  <key>StartInterval</key><integer>60</integer>

  <key>StandardOutPath</key><string>/Users/joseparreno/notify_stdout.log</string>
  <key>StandardErrorPath</key><string>/Users/joseparreno/notify_stderr.log</string>
</dict></plist>
```

Validate XML:
```bash
plutil -lint ~/Library/LaunchAgents/com.biwenger.notify.test.plist
```

### 3) Load and trigger it
```bash
launchctl unload ~/Library/LaunchAgents/com.biwenger.notify.test.plist 2>/dev/null
launchctl load   ~/Library/LaunchAgents/com.biwenger.notify.test.plist
launchctl start  com.biwenger.notify.test
```

### 4) Verify it’s running
```bash
# Shows loaded jobs — middle column is the LAST EXIT CODE (0 = success)
launchctl list | grep biwenger

# Inspect the job (path, program, last exit code)
launchctl print gui/$(id -u)/com.biwenger.notify.test | egrep 'path =|program =|last exit|state ='
```
Expect:
- `path = /Users/.../com.biwenger.notify.test.plist`
- `program = /Users/.../bin/notify_test.sh`
- `last exit code = 0` after a good run

### 5) Check logs (optional)
```bash
tail -n +1 ~/notify_stdout.log ~/notify_stderr.log
```
- `stdout` shows `notified at …`
- `stderr` should be empty (clear with `: > ~/notify_stderr.log`)

### 6) Stop / remove
```bash
# Stop / unload
launchctl unload ~/Library/LaunchAgents/com.biwenger.notify.test.plist

# Fully remove (unload + delete)
launchctl remove com.biwenger.notify.test 2>/dev/null
rm -f ~/Library/LaunchAgents/com.biwenger.notify.test.plist
```

---

## Common pitfalls & fixes

**Exit code meanings in `launchctl list`:**
- `-    0` → last run **succeeded**
- `-   78` → **EX_CONFIG** (bad plist/command)
- `-  126` → **Operation not permitted / not executable**

**“Operation not permitted” (126):**
- Don’t run agents from **Documents** (privacy restrictions).
- Use `~/bin`, ensure exec + shebang:
  ```bash
  head -1 ~/bin/notify_test.sh   # expect: #!/usr/bin/env bash
  chmod +x ~/bin/notify_test.sh
  ```
- If downloaded, clear quarantine:
  ```bash
  xattr -d com.apple.quarantine ~/bin/notify_test.sh 2>/dev/null || true
  ```

**AppleScript error `(-2741)` (quote issues):**
- Use a simple one-liner:
  ```bash
  /usr/bin/osascript -e 'display notification "Job ran at '"$(/bin/date)"'" with title "Biwenger Cron"'
  ```
- Or pass args via heredoc:
  ```bash
  /usr/bin/osascript - "$title" "$message" <<'APPLESCRIPT'
  on run argv
    display notification (item 2 of argv) with title (item 1 of argv)
  end run
  APPLESCRIPT
  ```

**I don’t see popups:**
- Enable **System Settings → Notifications → Script Editor** (Banner/Alert).
- Confirm with:
  ```bash
  osascript -e 'display notification "Hello" with title "Biwenger"'
  ```

**Two plists loaded with different labels:**
```bash
launchctl list | grep biwenger
launchctl remove com.biwenger.test 2>/dev/null
rm -f ~/Library/LaunchAgents/com.biwenger.test.plist
```

**Validate the active job:**
```bash
launchctl print gui/$(id -u)/com.biwenger.notify.test | egrep 'path =|program =|last exit'
```

---

## Log-only probe (no popups)

Useful to isolate launchd issues from notification issues.

**Script:**
```bash
cat > ~/bin/notify_probe.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
/bin/echo "probe at $(/bin/date)" >> "$HOME/notify_probe.log"
SH
chmod +x ~/bin/notify_probe.sh
```

**Temporarily point the plist to the probe:**
```xml
<key>ProgramArguments</key>
<array>
  <string>/Users/joseparreno/bin/notify_probe.sh</string>
</array>
```

Reload/run and confirm `~/notify_probe.log` updates.

---

## Production notes (for scrapers)

- Keep a wrapper script in `~/bin` or your repo that:
  1) sets env (e.g., `export PYTHONPATH=...`),  
  2) runs your scraper,  
  3) sends success/failure notification.
- Use **one** canonical plist per job label (e.g., `com.biwenger.scraper.news`).
- Prefer `ProgramArguments` with an absolute path to your script. If you need shell features, wrap them in the script or use:
  ```xml
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>/absolute/path/to/your_script.sh</string>
  </array>
  ```

---

## TL;DR (known-good files)

**`~/bin/notify_test.sh`**
```bash
#!/usr/bin/env bash
set -euo pipefail
/usr/bin/osascript -e 'display notification "Job ran at '"$(/bin/date)"'" with title "Biwenger Cron"'
/bin/echo "notified at $(/bin/date)"
```

**`~/Library/LaunchAgents/com.biwenger.notify.test.plist`**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.biwenger.notify.test</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/joseparreno/bin/notify_test.sh</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>StartInterval</key><integer>60</integer>
  <key>StandardOutPath</key><string>/Users/joseparreno/notify_stdout.log</string>
  <key>StandardErrorPath</key><string>/Users/joseparreno/notify_stderr.log</string>
</dict></plist>
```

**Load & run:**
```bash
plutil -lint ~/Library/LaunchAgents/com.biwenger.notify.test.plist
launchctl load  ~/Library/LaunchAgents/com.biwenger.notify.test.plist
launchctl start com.biwenger.notify.test
```

---

## Handy commands

```bash
# Open user LaunchAgents folder
open ~/Library/LaunchAgents

# Validate a plist file
plutil -lint ~/Library/LaunchAgents/<file>.plist

# Load / unload / remove
launchctl load   ~/Library/LaunchAgents/<file>.plist
launchctl unload ~/Library/LaunchAgents/<file>.plist
launchctl remove <Label>

# Run now (don’t wait for schedule)
launchctl start <Label>

# List jobs (middle column is last exit code)
launchctl list | grep <partial-label>

# Inspect a specific job
launchctl print gui/$(id -u)/<Label> | egrep 'path =|program =|last exit|state ='

# Follow logs
tail -f ~/notify_stdout.log ~/notify_stderr.log
```

