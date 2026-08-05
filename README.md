# daily-pulse

Personal task aggregator for Blake. Scans Fireflies, Gmail, Slack, Cowork sessions, and n8n; renders a dashboard.

**Live:** https://daily-pulse.pages.dev/

## Structure
- `index.html` — the dashboard, reads `data/tasks.json`
- `data/tasks.json` — all candidate tasks, refreshed by scheduled scan
- `data/projects.json` — project taxonomy + scope config
- (later) `data/n8n_fleet.json` — n8n workflow inventory

## Refresh cadence
- Morning scan (07:00) — writes new `tasks.json`, commits, Cloudflare auto-deploys
- EOD scan (18:00) — same

Updated by scheduled tasks. Check-off state lives in browser localStorage for v1.

## Project ledger (source of truth: Notion)

The project taxonomy and per-project state live in the Notion database
**Blake - Project Ledger**: https://app.notion.com/p/02932048d7bf455b96b3b2fc534fd405

Flow, twice a day:

1. Scan reads the Notion database -> writes `data/ledger.json`
2. `scripts/build_projects.py` -> regenerates `data/projects.json` from the ledger
3. Normal task scan + merge runs against that taxonomy
4. Scan writes per-project state back to Notion (Live tasks, Last touched,
   Recent sessions, and the narrative fields unless **Pin state** is ticked)
5. `index.html` renders a read-only Projects panel from `data/ledger.json`

### Changing the project list

Do it in Notion. Never hand-edit `data/projects.json`: it is overwritten every run.

| To do this | Do this in Notion |
|---|---|
| Add a project | New row, fill Name + Project ID |
| Rename | Edit Name (leave Project ID alone) |
| Retire | Status = Retired |
| Merge A into B | Set A to Retired, add A's Project ID to B's **Aliases** |
| Stop the scan rewriting your wording | Tick **Pin state** |

Aliases are what stop tasks orphaning when a project is retired or merged.
`build_projects.py` fails loudly on duplicate ids or colliding aliases, and warns
if a retired project has no alias route.

### Files

- `data/ledger.json` - Notion mirror. Generated. Do not hand-edit.
- `data/projects.json` - generated from ledger + scan_config. Do not hand-edit.
- `data/scan_config.json` - hand-edited. Channels in scope, excluded channels,
  dismissed patterns, aging window.
