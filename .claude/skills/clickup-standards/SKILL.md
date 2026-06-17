---
name: clickup-standards
description: ProcessSmith ClickUp operating standards — structure, descriptions, attachments, statuses, and safe-write rules for Steve's Agent Management workspace. Use whenever creating, updating, organizing, or attaching anything in ClickUp (tasks, subtasks, company records, engagements, artifacts, comments), or when reviewing/cleaning the workspace.
---

# ClickUp Standards (ProcessSmith / Agent Management)

## Access — in this order
1. **Native ClickUp MCP connector** (works for workspace 90141038349 as of 2026-06-11) — full read/write incl. attachments and comments.
2. Zapier SDK scripts in `processsmith-systems/tools/` — fallback only. Known silent failures: stale hardcoded connection IDs (look up the connection by title, currently "Steve Rea"); `task` action **silently ignores** `parent_id` — real nesting requires the **`subtask`** action; SDK swallows stdout on errors — scripts must write progress to a file.
3. Never the browser for data ops; never ask Steve to paste API keys.

## Key IDs
- Workspace/team `90141038349`, space "AI Consulting Business" `90144653218`
- CRM folder `90149897798` (Companies `901417067407`), Client Delivery folder `90149383674` (Audit Pipeline `901416937485`, Audit Intake Inbox `901416937482`)

## Structure (one client = exactly two anchors)
- **Company record** in CRM > Companies — permanent hub, never moves. Rich profile: what they do, region, size, people (names/roles/contacts), systems & hard constraints, compliance context, "why they'd buy" pain summary, links to engagements + source records. Mark unknowns `[NEEDS: ...]`.
- **Engagement parent task** in Audit Pipeline — `"[Company] — AI Efficiency Audit"`. One row per engagement; everything else is a **subtask** of it (Intake, Discovery Interview, Post-Interview Review, Workflow Map, Audit Report, Proposal/SOW). Cross-link company ↔ engagement both directions.
- **Audit Intake Inbox** = raw landing zone only; file arrivals into an engagement promptly.
- Meeting naming convention (enables transcript auto-grab): `ProcessSmith Discovery — [Company] — YYYY-MM-DD`.

## Descriptions = index, not archive
Short: what it is, 3-6 key facts, where it came from, links. Full content lives in **attachments**, not description prose. Never paste transcripts into task text. Status/stage belongs in the status field, not in description prose. Journals/updates go in **comments**, not descriptions.

## Attachments — Steve's hard rule
**Only PDF, Word (.docx), Excel (.xlsx), or images (jpg/png).** Never .md, .json, code, or raw text files — convert first (deliverables → DOCX via the docx skill; data → XLSX). Keep the editable .md/source in the repo's gitignored `delivery/clients/<client>/` folder. GitHub is connected to ClickUp — link PRs/commits instead of attaching code.

### Generating Word/Excel deliverables
- Build .docx with **python-docx** (`py -3.13`), **not** a hand-rolled docx-js markdown parser. The markdown-parser route produces files that pass loose validators but Word rejects as "unreadable content." Reference implementation: `processsmith-systems/tools/md-to-docx-pydocx.py`.
- Tables must use **content-proportional column widths with a fixed layout** — set `w:tblLayout` `type="fixed"` and a width on **every** cell. Without it Word redistributes columns badly (e.g. a 1-char "#" column hogging the page).
- **Verify before delivering — validators passing ≠ Word opening.** Download the file back from where it will actually be opened, then confirm all three: `zipfile.testzip()` is `None`, `document.xml` is well-formed, and `docx.Document(path)` reads back with sane paragraph/table counts.

### Uploading binaries to ClickUp
- Use a direct **curl multipart** POST — never base64 passed through context (a hand-pasted base64 truncated a file once):
  ```
  curl -X POST "https://api.clickup.com/api/v2/task/{task_id}/attachment" \
    -H "Authorization: $TOKEN" -F "attachment=@file.docx"
  ```
- Token from `~/.codex/credentials/clickup.env` (`CLICKUP_ACCESS_TOKEN`) — presence-check only, never echo it.
- The ClickUp API can **attach but not delete** attachments. To replace a bad one, delete+recreate the task (or accept a second attachment) — there is no API-side removal.

## Safe writes
- Read current state first; create new structure → verify by reading it back → only then archive old. **Archive, never delete** (recoverable); destructive actions need Steve's explicit OK.
- After any write batch, verify at the level Steve cares about (list the parent, confirm counts/names) — Zapier especially can claim success while doing nothing.
- Free plan: avoid custom-field sprawl (4 unused space-level fields already exist — Confidence/Impact/Owner Type/Workstream, slated for removal). Metadata goes in descriptions.
- One-shot migration scripts: dry-run by default, then archive the script to `tools/archive/` after use.

## Client data
Client-sensitive evidence (transcripts, contact info) only in: ClickUp attachments on the client's tasks, or the local gitignored client folder. Never in repos, never in chat transcripts. Internal analysis/coaching notes stay local — not attached where a client could see them.
