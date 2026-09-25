# Player Stats DOM Notes

This is the entry point for agents investigating Biwenger player-detail HTML,
selectors, timing, and parser behavior.

## Source Files

- Clean reference notes: `docs/player_stats_dom_notes.md`
- Raw copied DOM snapshot: `docs/player_stats_html.txt`
- Current-team (squad) page notes: `docs/current_team_dom_notes.md`

The raw snapshot is intentionally preserved because Angular attributes,
component names, text placement, and class names can matter for selector work.
Do not replace the raw file with a prettified version unless a new raw snapshot
is also kept.

## Snapshot Context

- Page type: Biwenger player detail page.
- Example player in current snapshot: Mbappe.
- Captured from the visible player-detail view after opening a player from the
  Players table.
- The raw file has few lines, but at least one line is very long. Treat it as a
  large DOM blob even when `wc -l` looks small.

## Agent Workflow

Start here, not in the raw file.

1. Read this notes file first.
2. Use narrow shell searches against `docs/player_stats_html.txt`.
3. Prefer parser-assisted inspection for structural questions.
4. Only open broad raw HTML ranges when a targeted search is insufficient.
5. If the raw file grows much larger, use subagents for exploratory DOM review
   and keep the main context focused on conclusions and selector candidates.

Avoid pasting the raw DOM into chat or loading the whole file into the main
context. It can burn a lot of tokens while adding little clarity.

## Recommended Raw DOM Inspection

Use targeted searches for nearby context:

```bash
rg -o ".{0,260}Average.{0,260}" docs/player_stats_html.txt
rg -o ".{0,260}Matches played.{0,260}" docs/player_stats_html.txt
rg -o ".{0,260}data-section=\"Purchases\".{0,260}" docs/player_stats_html.txt
rg -o ".{0,260}player-detail-points.{0,260}" docs/player_stats_html.txt
```

Use component inventories before reading content:

```bash
rg -o "player-detail-[a-z-]+|player-status|player-position" docs/player_stats_html.txt | sort | uniq -c
rg -o "data-section=\"[^\"]+\"" docs/player_stats_html.txt | sort | uniq -c
rg -o "modalmenutitle=\"[^\"]+\"" docs/player_stats_html.txt | sort | uniq -c
```

Use line length checks before deciding how to inspect:

```bash
wc -l docs/player_stats_html.txt
wc -L docs/player_stats_html.txt
```

If exact DOM structure matters, use an HTML parser instead of ad hoc reading.
For example, create a temporary local script or use an interactive parser to:

- find component tags such as `player-detail-stats`;
- list descendant `.stat` nodes;
- print each stat node's text;
- list attributes like `data-section`, `title`, `aria-label`, and `href`;
- extract tables under `player-detail-points`.

Prefer parser output that is small and structured, such as:

```text
component=player-detail-stats
stat_text=8.5 Average
stat_text=31 Matches played
data_section=Purchases text=64%
data_section=Sales text=1%
data_section=Usage text=12%
```

## Useful Components

- `player-detail-header`: player identity and header metadata.
- `player-detail-info`: status and side information.
- `player-detail-stats-wrapper`: wrapper around the stats area.
- `player-detail-stats`: points, values, matches played, average, market stats.
- `player-detail-points`: match-by-match points table.
- `player-detail-next-games`: upcoming fixtures.

## App-Level Pop-Ups

Biwenger can show app-level marketing pop-ups after login or while navigating to
the app. These are not part of the player detail page, but they can block table
layout buttons and player rows, causing discovery to time out with zero players.

Known example from `docs/player_stats_html.txt`:

```html
<ng-component role="dialog" aria-modal="true">
  <button title="Close" aria-label="Close" class="close-button">×</button>
  <in-app-message>...</in-app-message>
</ng-component>
```

Useful detection selectors:

- Dialog root: `ng-component[role="dialog"][aria-modal="true"]`
- Message component: `ng-component[role="dialog"] in-app-message`
- Close button: `ng-component[role="dialog"] button.close-button`
- Accessible close fallback:
  `ng-component[role="dialog"] button[aria-label="Close"]`
- Title fallback:
  `ng-component[role="dialog"] button[title="Close"]`

Recommended scraper behavior:

1. Add a shared, safe `dismiss_app_popups_if_present()` helper.
2. Call it after login/app navigation and before table layout selection.
3. Call it again if a table/list wait times out before declaring zero rows.
4. Treat dismissal as best-effort: log whether a pop-up was dismissed, but do
   not fail if no pop-up exists.
5. Keep the helper generic for app-level dialogs, not player-specific.

## Known Selectors

Header:

- Player name: `player-detail-header h1`
- Team link: `player-detail-header team-link a`
- Team name: `player-detail-header team-link a[title]`
- Position: `player-detail-header player-position`
- Status candidates:
  - `player-detail-header h1 player-status`
  - `player-detail-info .tc player-status.with-label`
  - `player-detail-info player-status`

Stats panel:

- Panel root: `player-detail-stats`
- Current value row: `player-detail-stats tr` with text `Value`
- Minimum value row: `player-detail-stats tr` with text `Min`
- Maximum value row: `player-detail-stats tr` with text `Max`
- Matches played: `.stat` whose text contains `Matches played`
- Average: `.stat` whose text contains `Average`
- Purchases: `.stat[data-section="Purchases"]`
- Sales: `.stat[data-section="Sales"]`
- Usage: `.stat[data-section="Usage"]`

Points panel:

- Points tab content: `player-detail-points`
- Match table: `player-detail-points point-list table`
- Match rows: `player-detail-points point-list table tr`
- Round link: `td.round a[title^="Round"]`
- Match date metadata: `meta[itemprop="startDate"]`
- Points bar: `td.bar-container a.bar`
- Event spans: `td.events player-events span`

Value panel:

- Value tab: `tab[header='Value'], [role='tab']:has-text('Value')`
- Value panel root: `tab[header='Value']`
- Chart surface: `chart-js canvas, svg-chart svg, svg-chart`
- Tools: `chart-js .tools segmented-control, svg-chart-tools segmented-control`
- CSV download button: `segmented-control button:has(.icon-download)`

## Selector Lessons Learned

Avoid relying on broad Playwright text locators when the containing component is
already loaded and the stat can be read directly from that DOM root.

The previous average parser used:

```python
page.locator("player-detail-stats .stat", has_text=re.compile(r"\bAverage\b", re.I))
```

That created a repeatable ~15 second wait per player. The safer pattern is:

1. wait once for `player-detail-stats`;
2. evaluate inside that loaded root;
3. find the `.stat` whose text contains the label;
4. read the first child `div` as the value.

This keeps browser pacing unchanged while avoiding timeout-driven parsing.

## Current Timing Findings

From the headed 2-player dry run on 2026-07-18:

- Player open flow: roughly 1 second in the fast path.
- Player detail parse after the average fix: under 0.5 seconds.
- Value history scrape: roughly 1.2-1.5 seconds.
- Back-to-table: roughly 1.3 seconds.
- Match scraping can vary. One sample was 8.72 seconds for Mbappe and 1.52
  seconds for Vinicius Jr.

The next likely optimization target is match scraping. Investigate whether
`scrape_player_matches` can read the already-loaded match table in one DOM
evaluation rather than making many row-by-row Playwright locator calls.

## Parser Direction

For future scraper improvements, prefer root-level DOM extraction:

- wait for a stable component root once;
- run one scoped `evaluate` call inside that root;
- return a structured dictionary/list;
- parse types in Python;
- keep short human-ish cooldowns between players.

This is preferable to many independent locator reads because each locator call
can carry its own waiting behavior and can accidentally introduce timeout cost.
