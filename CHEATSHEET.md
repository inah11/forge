# forge cheat sheet

All commands run from `~/tools/forge`. `forge help <command>` (or `forge <command> --help`) explains any command; `forge status` ends with the one thing to do now; this sheet is for when you want the situation, not the command. Issues live in the tracker repo named in forge.json; code repos are the `repos` mapped there. Every commit is yours; agents cannot push, merge or touch main.

## After installing a new forge

Ctrl-C the running `forge loop` and start it again; it loads code once at start. `forge version` (and the last line of `forge status`) says when the loop is older than the install.

## Which Claude account forge uses

```
forge login
forge whoami
```
Forge has its own login, separate from the `claude` in your shell. Sign in once with the account that should pay for the agents; your own account stays whatever it is. `forge logout` then `forge login` to switch. `forge loop` refuses to start while forge is signed out.

## One ticket, start to finish

```
forge next 3
```
Refines, has the tech lead draft answers (Enter accepts, type to override, `h` leaves it for you, `q` stops), re-refines, plans, walks you through planner questions. Stops at the plan.

```
forge plan approve 3
forge status
forge loop
```
Approve, then CHECK THE REPO COLUMN of the `3--` rows (`android` or `server`), then start the loop. The loop picks up queued tasks within two minutes, so never approve with the loop running unless you have already checked.

While the loop runs: `forge status` ends with a `next:` line. Do what it says. The states that need you:

| state | meaning | you do |
|---|---|---|
| needs_human | tech lead reviewed, waiting for you | `forge review --open`; at its prompt: `m` merge, `p` PR only, `c` commit only, `r` reject (asks tag + reason), `d` diff, `n` next, `q` quit |
| owner | a step only you can do (device, paid vendor, secret) | `forge owner run <id>`: checks the script against the repo and offers amendments, runs it, judges the JUnit evidence, approves on green; on red says why each test did not run, who got the media buttons and whether the app even had a MediaSession, and gives `--from N` to rerun only the device leg. Hand a code defect back with `forge plan extend KEY "..." --defect-in <subtask> --evidence tasks/<id>/evidence/logcat-final.txt --evidence tasks/<id>/evidence/media_session-final.txt` |
| withdrawn | an owner step whose criterion moved to a later ticket | nothing; set by `forge ticket close KEY --superseded-by NEW --reason "..."` |
| failed, note `worker: wrong repo / already done / blocked / needs decision` | the worker stopped without a diff and said why | `forge why <id>` prints the reason and the command; wrong-repo cases forge moves by itself |
| failed | environment or timeout, not code | read the reason in status, fix the environment, `forge reject <id> --tag env "reason"` |

Approve and merge in one go:
```
forge approve 3--app-room-database --merge
```
Commits as you, pushes, opens the PR, squash-merges, deletes the branch, pulls main.

Reject with a tag so the outcomes table stays honest:
```
forge reject 3--app-room-database --tag defect "what is wrong"
```
Tags: `defect` (code wrong; counts as a false accept if the tech lead had approved), `spec` (plan was wrong), `style`, `env` (not the worker's fault, not counted).

When every subtask of the ticket is approved:
```
forge ticket close 3
forge next 4
```
`ticket close` checks every PR merged, runs the repo's tests on main, writes `docs/forge/<key>/audit.md` into the repo as its own PR, closes the issue. Nothing else closes issues.

## Before a device run

```
forge doctor android_device local_server
```
Phone attached and authorised, server answering, `adb reverse` in place. Each failure prints its fix. `forge owner run <id>` runs these itself first.

## When the chain stops early

| it prints | do |
|---|---|
| `stopping: a refinement question needs you` | `forge refine answer 3`, answer the ones marked NEEDS YOU, then `forge next 3` |
| `left for you (N)` after an answer round | each kept question is printed with what it needs; answer it yourself with `forge refine answer 3 N "..."` (or `forge plan answer 3 N "..."`), no agents run; then `forge next 3` |
| `still NOT_READY after 3 round(s)` | `forge refine show 3`; if the questions are already answered, `forge refine accept 3 && forge plan 3` |
| `has open questions (ready=false)` on approve | `forge plan answer 3`, then approve |
| `PLANNER HAS N QUESTION(S)` | `forge plan answer 3` |
| plan approved against the wrong repo | stop the loop, `forge plan withdraw 3`, `forge ticket 3`, `forge plan 3 --repo android` |
| a defect found after merge (owner live test) | `forge plan extend 3 "what broke" --defect-in sub1,sub2`; the loop picks up the new subtasks |

## The loop

Start: `forge loop` (foreground; leave the terminal open). Stop: Ctrl-C. It restarts only when a drop changes code the loop runs (tick, reap, workers, gate, review) or model tiers in forge.json; the drop will say so. Changes to prompts, `forge next`, `plan`, `status` never need a restart.

`forge run` is one tick by hand; useful to see what the loop would do right now.

## Reading status

Rows are grouped by ticket and listed in the order the planner meant them to run; closed tickets collapse to one line (`--all` shows them). Columns: state, task, repo, complexity/model it ran on (`*` = opus control arm), tech-lead reject rounds/red-test rounds, tech-lead risk, goal, and a note saying what the row waits for or what you do (`after b` = blocked on subtask b; `you: ...` = your move). `forge status --legend` prints the column key. Risk `high` is forced when an opus worker was reviewed by sonnet: read that diff yourself.

## Money and measurement

```
forge finance report
```
Notional API-equivalent spend per role and the outcomes table (false accepts, rework, cost by tier). Cells with n<10 say nothing yet.

## Secrets and safety

Workers, tech lead and the test gate get no `*_API_KEY`, `*_TOKEN`, `*_SECRET`, `*_PASSWORD` variables. Paid-vendor live tests are owner steps; run them yourself with the key set via `read -s`. The guard hook blocks every git write by an agent. The dedicatee's name is redacted on every tracker surface.

## Recovery

```
forge clean <id>
forge clean --done
```
Removes worktrees (and branches for anything not approved). Safe after a merge.

If a worker is wedged: stop the loop, `forge reject <id> --tag env "wedged"`, `forge clean <id>`, start the loop.

If status looks wrong, the truth is on disk: `tasks/<id>/state.json`, `~/.forge/plans/<project>/<key>/plan.json`, `tickets/<key>.md`, `logs/`.

## Installing a drop

```
cp <new forge> ~/tools/forge/bin/forge
chmod +x ~/tools/forge/bin/forge
```
Prompts go to `prompts/`, README and this file to the top level. The exec bit is lost on every copy; the chmod is not optional.
