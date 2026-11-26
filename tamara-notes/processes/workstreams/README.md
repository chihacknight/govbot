# Workstreams for the presentation (started 2026-11-24)

The work in `../handoff-2026-11-24.md` is split into five chats. Each chat has a brief in this
folder and, if it edits files, its own git worktree. A worktree is a separate folder with its
own branch, so two chats running at once can't overwrite each other's work.

| Chat | Brief | Folder to open the chat in | Branch | Start |
|---|---|---|---|---|
| JSONL logs (goal 3) | [jsonl-logs.md](jsonl-logs.md) | `~/my_work/govbot-jsonl` | a fresh branch off `main` (#306 and #308 merged) | Done: all repos converted (no rebuild of the earlier 39) |
| Master state list (goal 5) | [master-state-list.md](master-state-list.md) | `~/my_work/govbot-master-list` | `docs/master-state-list` | Now |
| Scraper fixes (goal 6) | [scraper-fixes.md](scraper-fixes.md) | `~/my_work/govbot-scrapers` | `scraper-triage` | Now |
| Repo rewrite (goals 1, 2, 4) | [repo-rewrite.md](repo-rewrite.md) | `~/my_work/govbot-repo-rewrite` | `repo-rewrite` | After the JSONL layout is settled |
| Presentation | [presentation.md](presentation.md) | `~/my_work/govbot` (read only) | `main` | Any time |
| Lean data org (goal 7) | [lean-org.md](lean-org.md) | None yet | None yet | After the JSONL push and the Python fix |

## How to start a chat

1. Open the chat in the folder from the table.
2. Paste the "Kickoff prompt" from that chat's brief.

## Rules every chat follows

- **Stay in your own folder and branch.** Don't switch branches in another chat's folder.
- **Keep `~/my_work/govbot` on `main`.** It's the shared reference copy. Nobody edits there.
- **Update before you start a session.** Run `git fetch origin` and rebase on `origin/main` if
  your branch is behind.
- **Report back.** When a chat finishes a step or changes a plan, update its brief's "Status"
  section and, if it matters to the others, `../handoff-2026-11-24.md`.
- **One pull request per chat.** The repo squash-merges. After a merge, start a fresh branch off
  `main` rather than reusing the old one.

## Managing the worktree folders

Create one (already done for the four above):

```
cd ~/my_work/govbot
git worktree add ../govbot-jsonl -b jsonl-logs origin/main
```

Remove one after its pull request merges:

```
cd ~/my_work/govbot
git worktree remove ../govbot-jsonl
git branch -d jsonl-logs
```

List them with `git worktree list`.
