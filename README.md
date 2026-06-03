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
