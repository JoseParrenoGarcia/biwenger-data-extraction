# Current-Team DOM Notes

This is the entry point for agents investigating Biwenger current-team (squad)
page selectors, layout buttons, and parser behavior.

For player-detail page selectors, see `docs/player_stats_dom_notes.md` instead.

## Page Context

- Page type: Biwenger current-team / squad page.
- URL: `https://biwenger.as.com/team` (logged-in app).
- Rendered as an Angular app with custom web components.
- The squad table is the default active tab; no click is required to display it.

## Layout Controls

The page has two independent layout controls:

1. **Squad / News segmented control** (top of the squad panel):

   ```html
   <segmented-control role="tablist">
     <button type="button" class="active" role="tab"
             title="Squad" aria-selected="true">Squad</button>
     <button type="button" role="tab"
             title="News" aria-selected="false">News</button>
   </segmented-control>
   ```

   - Current selector: `segmented-control button[title='Squad']`
   - Historical selector (broken since ~Sep 22 2026):
     `segmented-control button[aria-label='Squad']` — Biwenger removed the
     `aria-label` attribute and switched to `title`.
   - The Squad tab is active by default and the table renders without clicking
     it. The scraper only scrolls it into view as a best-effort nicety. A
     missing or renamed button must not abort the run. See
     `scroll_squad_into_view()` in `scraping_biwenger/current_team/pipeline.py`.

2. **Grid / Table layout toggle** (footer filter bar):

   ```html
   <div class="layout-selector">
     <i role="button" title="Grid" aria-label="Grid" class="icon icon-hamburger"></i>
     <i role="button" title="Table" aria-label="Table" class="icon icon-table active"></i>
   </div>
   ```

   - Primary selector: `[role="button"][aria-label="Table"]`
   - Fallbacks: `[role="button"][title="Table"]`, `button:has-text("Table")`
   - The scraper skips clicking if `table.table.no-swipe tbody tr` is already
     present. See `select_table_layout()` in
     `scraping_biwenger/current_team/pipeline.py`.

## Squad Table Structure

Table root: `table.table.no-swipe`

Column order (0-indexed, via direct child td/th):

| Index | Header | Notes |
|-------|--------|-------|
| 0 | Pos. | `<player-position>` with `title`/`aria-label` |
| 1 | Team | `<a class="team" title="...">` |
| 2 | Player | `<a href="/la-liga/players/{slug}">` |
| 3 | Pts. | May contain `div.text-muted.small[title*='season points']` |
| 4 | MV | `€`-formatted market value |
| 5 | % | `<increment aria-label="€..." class="...increment|decrement|equal">` |
| 6 | Status | `<player-status aria-label="Fit|Injured|..." class="...">` |
| 7 | GP | games played this season |
| 8 | Avg. | average points |
| 9 | Home | points + `div.sub-item` with home average |
| 10 | Away | points + `div.sub-item` with away average |
| 11 | Play | home/away fixture location |
| 12 | Opponent | `<a title="..." href="/la-liga/matches/...">` |
| 13 | Form | `<player-fitness><player-points>` cells (up to 5) |
| 14 | Market | sell button / market tools |

Special row cases handled by the parser:

- **No-team players**: team cell contains `<img src=".../noteam.svg">` instead
  of an `<a class="team">` link. `team_name` is `None`.
- **Injured players in form**: `<player-fitness>` can contain `<player-status>`
  elements (injured/doubtful badges) interspersed with `<player-points>`. The
  parser filters for `player-points` only.
- **Empty form**: `<player-fitness>` may have no `<player-points>` children.
  Form values default to 0.

## Key Lessons

- The Squad segmented-control button switched from `aria-label` to `title`
  around Sep 22 2026, breaking every scheduled current-team run for 4 days.
  The scroll is now best-effort with both attribute selectors tried.
- `biwenger_current_team` is a replace-every-run table. A failed run leaves the
  previous snapshot frozen, so stale/missing players on the dashboard are the
  primary symptom of a broken current-team job.
- Always check `run_artifacts/launchd/current_team/<timestamp>/script.log` and
  `launchctl print gui/$(id -u)/com.biwenger.current-team` when the dashboard
  looks wrong.
