# forge

Ten agents write the code. One human says yes or no.

forge runs parallel Claude Code workers on a personal Claude subscription (no API key) against a ticket tracker: a refiner that refuses unready tickets, a planner, a tech-lead agent that answers questions and reviews every diff with a different model from the one that wrote it, a guard hook that keeps agents away from git, and an audit log committed into the repo when a ticket closes. You are the only committer.

Quick start: copy `forge.example.json` to `forge.json`, point it at your repos, `forge init`, `forge login`, then `forge next <issue>`.

Parallel Claude Code workers. One human committer. Portable: clone it, point `forge.json` at your repos, run `forge init`.

## What it does

- **ticket** comes from your tracker through its CLI, run as you: GitHub Issues via `gh` (default) or Jira via `twg`. `forge ticket 41` / `forge ticket COS-123`, or implicitly by `refine`/`plan`. Agents never get these commands.
- **refiner** (sonnet, read-only) checks the ticket is ready: outcome, testable acceptance criteria, scope boundary, dependencies, contradictions in comments, references that resolve in the repo, size. Outputs READY/NOT_READY and questions, each tagged `reporter` / `tech-lead` / `platform`. `forge refine post` puts the non-tech-lead questions on the ticket as one comment, after you confirm. Nothing plans until `forge refine accept` (or `--force`).
- **planner** (read-only, strong model, runs once per ticket) reads the repo and writes a step-level plan: files, signatures, named tests with assertions, numbered red→green steps, complexity per subtask. Saved to `plans_dir` (default `~/.forge/plans/<KEY>/plan.{json,md}`), never inside a repo. **Nothing runs until you `forge plan approve KEY`.** Edit `plan.json` by hand or `forge plan revise KEY "feedback"` first.
- **workers** (one `claude -p` per subtask, each in its own `git worktree`) execute the plan's steps; they don't design. Model is chosen by the plan's complexity: low→haiku, medium→sonnet, high→opus. A rejected attempt re-runs one tier up. A PreToolUse hook blocks `git commit/push/merge`, PR creation and outbound POSTs. They finish by writing `FORGE_SUMMARY.md`.
- **tech lead** (read-only) has two jobs. It answers the refiner's and planner's questions from the decisions document, the P register, the repo and the web, and walks you through its proposals one at a time (`forge refine answer KEY`, `forge plan answer KEY`; `--auto` posts what it could source and shows you only what it could not). And it reviews every worker round, adversarially, always as a *different model one tier above the worker* (haiku→sonnet, sonnet→opus; opus work is reviewed by sonnet and forced to your desk, since there is no stronger model). It rejects on plan drift, missing red-before-green, weakened tests, invented APIs, and the design rules below, naming the principle and the line. REJECT feeds back and escalates the worker one tier, up to `max_rework_rounds`.
- **you** run `forge review --open` (worktree in VS Code, Source Control view is the diff, summary and findings alongside), then `forge approve` (commits with *your* git identity and signing config, pushes, optionally opens the PR) or `forge reject "reason"`.
- **scheduler** (`forge run` tick, or `forge loop`) keeps `max_workers` busy, kills workers over `worker_timeout_min`, reaps and reviews finished ones.

Everything runs on whichever Claude Code login is active on the machine. No API key. Commits carry nothing but your identity. Tracker writes (comments, labels/transitions, issue creation) are made only by forge's own code through your CLI, never by an agent.

## Tracker: GitHub or Jira

`forge.json → tracker.kind`: `github` (default, uses `gh`), `jira` (uses `twg`), or `none` (local markdown tickets only). Presets are built in; any field can be overridden (`view`, `comment`, `transition`, `create`, `states`, `key_pattern`, `commit_prefix`).

| step | GitHub (`gh`) | Jira (`twg`) |
|---|---|---|
| `forge backlog approve` | `gh issue create` per story, dependencies as `#N` | — (tickets already exist) |
| `forge refine post KEY` | issue comment with open questions | ticket comment |
| `forge plan approve KEY` | label `in progress` + comment | transition → In Progress + comment |
| `forge approve <task>` | comment with branch; commit `#41 …`, branch `feat/41-<subtask>` | comment; commit `COS-123 …`, branch `feat/COS-123-<subtask>` |
| last subtask approved | label `in review` + summary | transition → In Review + summary |

GitHub keys are issue numbers (`41`); Jira keys are `COS-123`. `require_key: false` allows free-form ticket ids with `tracker.kind: none`.

GitHub needs `tracker.repo` (`owner/name`): every `gh` call gets `-R` because forge does not run inside a repo. All of a project's issues live in that one repo, even in a multi-repo project, so `#N` is unambiguous and `tickets/N.md` never collides. A commit in a different code repo is prefixed `owner/name#N`, which GitHub links back to the issue. `forge backlog approve` creates the labels it uses (`forge`, `in progress`, `in review`) first, stops on the first failed issue create, and refuses to run twice (that would duplicate issues).

## Discovery (product team) — for projects that have no tickets yet

`forge discover decisions.md --project NAME` runs five roles over a decisions document (D = decided, P = proposed, Q = open):

- **product** (opus): pass 1 returns at most eight blocking decisions, merged and ordered by what they unblock, each with the options the document already contains and a stated default if you defer it. Nothing else runs until they're answered. `forge discover answer NAME` walks them one at a time (number picks an option, `d` defers to the default, `s` skips, or type an answer) and writes the `## ANSWERS` section into the document; re-run `discover` and it proceeds. Pass 2 writes epics → stories with acceptance criteria, dependencies, complexity, target repo, and `forgeable` vs manual (choose a voice by ear, test on your headphones). Stories that would need a guess are listed as deferred, not written.
- **architect** (opus): ADRs, invariants with how each is enforced, a `CLAUDE.md` per repo written as rules, scaffold stories, risks (UNVERIFIED for anything it can't confirm exists).
- **qa** (sonnet): what proves each story, which need you on a device, cross-cutting suites, untestable acceptance criteria called out.
- **finance** (sonnet): run-cost range from the document's own figures with their dates, build-cost estimate, agent-spend ledger summary, drift, stale prices to recheck, and a one-minute report.
- **challenger** (sonnet, adversarial): contradictions with D items, P items treated as decided, scope creep, missing stories, untested invariants. REVISE blocks approval unless `--force`.

When the challenger says REVISE, `forge backlog resolve NAME` walks its findings, missing stories and questions one at a time: `a` accepts the proposed fix as a decision, `d <reason>` dismisses it (the challenger is told and must not raise it again), `?` asks the challenger to expand that one item in a few lines, or type your own decision. Decisions are appended to the document under a dated heading; one more `discover` run folds them in.

Each story carries a `repo` tag; forge plans, runs workers and reviews inside that repo's own worktree with that repo's `test_cmd`. `repos` entries may be a path or `{path, test_cmd, lint_cmd}`.

Output lands in `~/.forge/plans/_discovery/NAME/` (`backlog.md` to read; JSON per role). `forge backlog approve NAME` creates the issues on the tracker in build order (dependencies resolved to real numbers), writes `tickets/<key>.md`, and puts `CLAUDE.md` into each repo in `forge.json → repos` (existing files left alone unless `--overwrite-claude-md`). Then the normal loop: `forge refine 41`, `forge plan 41`, …

## Forge's own Claude login

Forge signs in to Claude on its own, separately from the `claude` login in your shell or editor. `forge login` opens the usual browser sign-in and stores the result in forge's own config directory (`claude_home` in forge.json, default `<forge>/account`); every agent forge starts (worker, tech lead, planner, refiner, test gate) runs with `CLAUDE_CONFIG_DIR` pointing there, so whichever account you are using yourself, forge bills the account it was signed in with. `forge whoami` says which, `forge logout` then `forge login` switches, `forge doctor` and `forge loop` refuse to start agents while forge is signed out. Nothing of forge's lives in that directory: tasks, plans, logs, audits and the repos are forge's own files and read the same under any login. Credentials and API keys in your shell are stripped from agent environments as before, so a key in your profile cannot silently take over from the login.

## Identity: one machine, two lives

`forge.json → identity {name, email, signingkey, gpgsign, ssh_key}` pins author, committer and signing for every commit forge makes, as `git -c` flags, so the directory's git config cannot leak the wrong identity into a commit. `forge init` shows what git would resolve for each repo next to what forge will use and flags a mismatch. `ssh_key` (or `ssh_command`) sets `GIT_SSH_COMMAND` for pushes so the right key is used. `tracker.gh_user` pins the `gh auth login` account; forge runs `gh auth switch --user` before every tracker call.

Set per forge copy: a work copy carries your work identity and `gh_user`/`twg` as appropriate; the personal copy carries yours. Belt and braces: also add `includeIf "gitdir:~/projects/personal/"` to `~/.gitconfig` so manual commits outside forge get the right identity too.

## Containment

A worker can write only inside its own worktree: the guard hook blocks Write and Edit outside `FORGE_WRITE_ROOT` and any shell command that names a mapped repo's main checkout (`FORGE_PROTECT`), on top of the git write, PR and outbound-POST blocks. A worker whose file lives in another repo is told to say so and stop; the owner then moves the task with `forge reject <id> --tag env --repo NAME "..."`. Plans may set `repo` per subtask, and `forge plan approve` warns when a subtask's text names a different mapped repo from the one it is assigned to.

## A worker that stops without a diff says why

A worker that cannot make the change writes `NO_CHANGES: <kind>: <detail>` as the first line of its summary, with kind one of wrong-repo, already-done, blocked, needs-decision. Forge acts on it at reap time: wrong-repo naming a mapped repo moves the task there and re-queues it with no human involved; the others land in `failed` with the reason in the status note, and `forge why <id>` prints the worker's words, what the guard blocked, and the one command that moves the task. Workers that forget the line are classified from their log and summary as best forge can.

## Redaction

`forge.json → redact {term: replacement}`: applied to everything forge sends to the tracker (issue titles, bodies, comments) and to `CLAUDE.md` files it writes into repos. Local plans, tickets and logs keep the original text. Use it for a name that must stay off public or vendor-visible surfaces.

## Finance

Every agent run (refiner, planner, worker, reviewer, discovery roles) is appended to `finance/ledger.jsonl` with model, tokens and the notional USD Claude Code reports (on a Max seat this is quota, not a bill, but it is the right proxy). `forge finance report` prints spend by role, model and ticket, plus each discovered project's run-cost range, drift and stale facts; `--post` sends it to Slack. The hourly digest carries today's spend; put `forge finance report --post` on a weekly cron for the standing report.

## Install (once per machine)

```
unzip forge.zip && cd forge
./install.sh            # asks for the repo path, writes hook settings, sanity-checks claude + git
export PATH="$PWD/bin:$PATH"
```

Edit `forge.json`: `test_cmd`, `lint_cmd`, `allowed_bash` (prefix patterns the workers may run), `max_workers` (3 is right for one Max seat), `plans_dir` (where plans live, outside any repo), `models` (per-role/tier; aliases `opus|sonnet|haiku` or full model ids), `slack_webhook` (optional).

## What do I do now?

`forge status` ends with a `next:` line computed from the task states. The whole table: `needs_human` → `forge review --open`, then `forge approve <id> --merge` or `forge reject <id> --tag …`; `failed` → read `tasks/<id>/gate.log`, fix, `forge reject <id> --tag env "retry"`; `owner` → do it yourself, then `forge approve <id>`; everything of a ticket `approved` → `forge ticket close N`, then `forge next N+1`. Loop glyphs: `▶` started, `⋯` reviewing, `↺` sent back (automatic), `●` yours, `✗` failed. Only `●` and `✗` need you.

## One command per ticket

`forge next KEY` runs refine → tech-lead answers (you confirm each) → re-refine → accept → plan → tech-lead answers to planner questions → revised plan, and stops at the one gate that is yours: `forge plan approve KEY`. It also stops whenever a question needs a decision only you can make (a secret, money, scope). After approval the loop does the rest; `forge approve <task> --merge` squash-merges the PR and pulls main; `forge ticket close KEY` checks every subtask is approved, runs the repo's test command on main, and closes the issue with the PR list.

## Design rules the pipeline enforces

TDD by construction: the planner must name a test for every production file and order the steps red → green; the worker records both runs; the tech lead rejects without them. SOLID as concrete cues, not an acronym: one reason to change per class; vendor SDKs behind a port the domain owns, used from one adapter package only; collaborators by constructor, as interfaces where more than one implementation is plausible; variation by extension where the spec says a set will grow; test doubles that honour the port's contract; narrow interfaces; records across boundaries. Owner-only steps (a paid live run, a device test) are their own subtask with `owner: true` and no worker.

## Secrets never reach an agent

Workers, the tech lead and the test gate run with your environment minus anything that looks like a credential (`*_API_KEY`, `*_TOKEN`, `*_SECRET`, `*_PASSWORD`, `AWS_*`, …). A paid-vendor key such as `JEV_API_KEY` is therefore invisible to every agent even though it is set in your shell; live tests are run by you. `forge.json → strip_env` adds names, `keep_env` whitelists one.

## Gate, rounds and what is measured

- **Test gate before any reviewer.** When a worker finishes, forge runs the repo's `test_cmd` (then `lint_cmd`) in the worktree itself. Red goes straight back to the *same* model and session with the failure tail as feedback; no reviewer tokens are spent on a red tree. Red rounds have their own cap (`max_red_rounds`, default 2) and never escalate the tier; past the cap the task waits for you with reason `tests_red`. An environment failure (command not found, Docker not reachable, dependency resolution, Gradle daemon) is detected by exit code and pattern, counts toward nothing, and parks the task as `failed`; `forge reject <id> --tag env "retry"` re-queues it once the environment is fixed.
- **Only a reviewer REJECT escalates** one tier, up to `max_rework_rounds`. Reviewer output that cannot be parsed is recorded as `UNPARSED`, not approved, and comes to you.
- **Every round is logged** in `tasks/<id>/state.json → round_log`: model, gate result, reviewer model, verdict, risk, finding count, cumulative cost. Each round's review is kept as `review.r<N>.json`.
- **Your review** is stamped from the first `forge review <id>` of a sitting to `approve`/`reject`, capped at 45 minutes, and reported as *elapsed*, not attention.
- **`forge reject` requires a tag**: `defect` (the code is wrong; after a reviewer APPROVE it is recorded as a false accept), `spec` (plan or ticket changed), `style`, `env`. The false-accept rate is a lower bound: it cannot see what you approved without noticing or what surfaces after merge.
- **Control arm.** `opus_control_rate` (default 0.2) starts that fraction of low and medium subtasks on opus at random, flagged `control`, so tier cost can be compared on observed runs rather than a counterfactual estimate. Set 0 to turn it off.
- **`forge finance report`** prints an outcomes table per arm × complexity: n, first-pass accept, escalations, red rounds, false accepts, cost per subtask, median elapsed review. Cells with n < 10 are marked insufficient; tasks approved before round logging existed are excluded and counted.

## Cost model

One expensive call per ticket (planner, opus) buys cheap execution: haiku/sonnet workers that follow numbered steps, sonnet review. Quota goes where judgement is needed. Escalation on reject means a cheap failure costs one extra cheap run, not a bad merge. Mark a subtask `high` in the plan if you want opus from the start.

## Rules baked in

- **Tracker key everywhere**: branch `feat/<key>-<subtask>`, commit and PR title start with `#41` / `COS-123`, so GitHub and Jira link them automatically.
- **TDD**: worker must show a red run before a green run for every acceptance check in `FORGE_SUMMARY.md`; reviewer rejects without that evidence.
- **No invention**: worker may only state what it read or ran in the worktree; unknowns are marked `UNVERIFIED`. Reviewer greps every API/config/field the diff introduces and rejects anything that doesn't exist in the repo or installed deps.
- **Comments**: only non-obvious invariants and workarounds, one line. Narrative comments, change logs, commented-out code and TODOs without a key are rejected.

## Daily use

```
forge discover decisions.md --project trainer   # new project: questions, then backlog
forge backlog approve trainer       # issues created, tickets written, CLAUDE.md per repo
forge refine 41                     # fetches issue via gh, checks readiness, lists questions
forge refine post 41                # optional: put reporter questions on the issue
forge refine accept 41              # READY; planning now allowed
forge plan 41                       # -> ~/.forge/plans/41/plan.md  (read it)
forge plan revise 41 "…"            # optional: re-plan with your feedback, or edit plan.json directly
forge plan approve 41               # creates tasks; workers may now start
forge plan list                     # all plans and status
forge loop --every 120              # leave running in a tmux pane (or cron: */5 * * * * forge run)
forge status                        # one line per task
forge review --open                 # next item for you; opens worktree + summary + findings in VS Code
forge approve <id> -m "msg" --pr    # YOUR commit, pushed, PR opened via gh if present
forge reject <id> --tag defect "why"   # back to the worker; tags: defect|spec|style|env
forge next 42                       # refine → answers → plan, stops at plan approve
forge approve <id> --merge          # commit, push, PR, squash-merge, pull main
forge ticket close 42               # all subtasks approved → test main → close issue
forge clean --done                  # drop worktrees of approved tasks
forge status --digest               # posts the Slack digest (hourly cron for a "standup")
forge finance report --post         # weekly cron: spend + run-cost report
```

`forge add "goal" --key 41 --accept "pytest tests/x.py passes"` skips the planner for a one-liner task.

## Layout

```
forge.json            config
bin/forge             the CLI (python3, stdlib only)
bin/guard.py          PreToolUse hook that keeps agents off git
prompts/              refiner planner worker tech-lead + discover-{product,architect,qa,finance,challenger}.md
finance/ledger.jsonl  every agent run: role, model, tokens, notional cost
templates/            generated hook settings (install.sh)
tickets/              your inputs
tasks/<id>/           spec.json state.json worker.log patch.diff summary.md review.json
~/.forge/plans/KEY/   refine.{json,md}  plan.json (source of truth) + plan.md   ← outside every repo
~/.forge/plans/_discovery/NAME/   questions.md backlog.md + per-role JSON + CLAUDE.<repo>.md
.worktrees/<id>/      one git worktree per task (branch feat/<key>-<subtask>)
```

## Two setups from one checkout

- **Personal / GitHub** (default config): `tracker.kind: github`, `repos: {"server": "~/projects/trainer-server", "android": "~/projects/trainer-android"}`, `require_refine: true`. Start with `forge discover`.
- **Work / Jira**: `tracker.kind: jira`, single `repo`, `branch_prefix` as the team uses. Tickets already exist, so skip discover.

One forge folder per project, each with its own `plans_dir`. `forge init` regenerates the machine-specific bits (hook settings, directories).

## Limits to know

- A Max seat's rate limit is shared by all workers. 3 concurrent is comfortable; 5+ will stall under load.
- Workers run with your filesystem permissions in the worktree. Keep secrets out of the repo tree.
- `forge approve` commits whatever is in the worktree; read the diff for anything above low risk.
- The reviewer catches spec drift and weakened tests; it does not replace your judgement on design.

## Which repo a ticket is planned in

The planner runs in the repo named by a `repo: <name>` line in the issue body (a name from `repos` in forge.json), or by `forge plan KEY --repo <name>`. With more than one repo mapped and neither given, `forge plan` refuses rather than guessing, because a plan generated in the wrong repo queues workers against the wrong codebase and the wrong test command. `forge status` shows the repo per task; check that column before `forge plan approve`. If a plan was approved against the wrong repo and no worker has started, `forge plan withdraw KEY` removes the queued tasks and returns the plan to draft so it can be regenerated.

Note on GitHub: `gh issue view N --comments` prints only the comments when its output is not a terminal. Forge fetches the title and body in a second call and joins them, so the refiner, tech lead and planner see the whole issue.

## Owner steps run like worker steps

An owner subtask (device run, paid-vendor live test, anything needing a secret or a hand) carries `owner_run` in the plan: preflight checks, the commands in order, prompts for physical actions, the JUnit XML that counts as evidence, and one check per acceptance criterion naming the test classes that must pass, must not run, or may fail. `forge owner run <id>` runs that script the way the loop runs a worker, streams and logs the output, reads the XML rather than the exit code, writes `tasks/<id>/owner-run.md` and `evidence/`, posts the per-criterion result on the issue, and approves the step on green. On red it names the failure shape it recognises (no device, zero tests ran, cleartext blocked, no TCP path, version skew, dependency conflict, Room schema assets) and, for code defects, prints the exact `forge plan extend` with `--defect-in` and offers to run it. After every device test step and at the end it captures the device log and `dumpsys media_session` into `evidence/`, and the report says who the system delivered each media button to, which packages hold a MediaSession and which holds the button, and which instrumented tests started, finished or aborted; the diagnosis distinguishes "the app has no session" (service not alive) from "the app's session loses the button" (inactive, not PLAYING, or out-played). `forge plan extend KEY "..." --evidence FILE` (repeatable) attaches a filtered excerpt of a log or dump to the defect so the planner reads the facts, not a paraphrase. `forge doctor` runs the same preflight on demand with a fix per failure.

## Audit log in the repo

`forge ticket close KEY` renders `docs/forge/KEY/audit.md` into the code repo: refinement rounds and questions, plan and post-merge extensions, every subtask with its models, rounds, verdicts, owner rejects and tags, false accepts, PR, owner-run results, and the notional spend. `plan.json` and the owner-run summaries sit beside it. Forge commits it as you on `forge/KEY-audit`, opens the PR, squash-merges, and lists it in the closing comment; redaction and credential scrubbing apply. `"audit": false` in forge.json turns it off. When an acceptance criterion is withdrawn after the fact (an owner step that can no longer pass because the product decision changed), `forge ticket close KEY --superseded-by NEW --reason "..."` withdraws the open owner steps, records the reason and the new issue in the audit and the closing comment, and closes; worker subtasks must still be approved.
