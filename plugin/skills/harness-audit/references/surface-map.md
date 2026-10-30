# Claude Code surface map

Every place a harness decision can live, and how Claude Code treats it. Use it
as the checklist for the inventory, and as the only source for claims about
product behaviour.

**Last checked against the official documentation: 2026-10-01.** Claude Code
changes quickly. If this date is more than a few weeks old, or a finding rests
on one of these facts, the verification pass must re-check it against the page
named. Items marked *(uncertain)* were not settled by the documentation.

Built from the 2026-09 surface map and the Claude Code addendum of 2026-09-26.
Facts marked *(measured 2026-10-02)* come from short test sessions on Claude
Code 2.1.286 with a Haiku model, not from the documentation. Re-test them
after a major Claude Code update.

---

## 1. Instruction files

| Surface | Path | When it loads |
|---|---|---|
| Managed policy | macOS `/Library/Application Support/ClaudeCode/CLAUDE.md`, Linux `/etc/claude-code/CLAUDE.md` | Every session |
| User | `~/.claude/CLAUDE.md` | Every session on this machine |
| Project | `./CLAUDE.md` or `./.claude/CLAUDE.md` | At launch |
| Local | `./CLAUDE.local.md` (gitignored) | At launch |
| Above the launch folder | `CLAUDE.md` in any parent directory | At launch |
| Below the launch folder | `CLAUDE.md` in a subdirectory | **On demand**, when Claude reads files in that subdirectory |
| Rules | `.claude/rules/*.md`, `~/.claude/rules/*.md` | At launch, unless the file has `paths:` frontmatter, in which case when a matching file is read |
| Imports | `@path` inside an instruction file, up to 4 hops | At launch. Imports do not reduce context |
| Auto memory | `~/.claude/projects/<project>/memory/` | First 200 lines or 25KB of `MEMORY.md` each session. Topic files on demand |

Facts to audit against (memory.md):

- **The launch folder decides what loads at launch.** If sessions are launched
  from a folder above the repository, the repository's `CLAUDE.md` is a
  subdirectory file for those sessions.
- *(measured 2026-10-02)* An `@path` import in a `CLAUDE.md` in the folder
  above the repository, such as `@<repo>/CLAUDE.md`, loads the repository's
  `CLAUDE.md` at launch.
- **After compaction**, the project-root `CLAUDE.md` is re-read from disk and
  re-injected. Subdirectory `CLAUDE.md` files and path-scoped rules "reload as
  Claude reads files they apply to".
- **AGENTS.md.** "By default, Claude reads `AGENTS.md` only when you have no
  `CLAUDE.md` in your working directory or above it." The *Project
  instructions* setting changes this: `claude-md-or-agents-md` (default),
  `claude-md-and-agents-md`, `claude-md`, `managed-only`.
- **Auto memory folder.** "The `<project>` path is derived from the git
  repository, so all worktrees and subdirectories within the same repo share
  one auto memory directory. Outside a git repo, the project root is used
  instead." So a session launched from a non-git parent folder keeps its
  memory under the parent's path.
- Size guidance: keep `CLAUDE.md` under about 200 lines. Files over 4 MiB are
  skipped.
- Settings: `autoMemoryEnabled: false` or `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`
  turns auto memory off.
- *(measured 2026-10-02)* The `autoMemoryDirectory` setting points auto memory
  at a given folder. The benchmark runner uses it to give each run a copy of
  the memory notes.

Look for: instructions that contradict a hook or deny rule, imports pointing
at missing files, path-scoped rules whose globs match nothing, and an entry
file that restates the README instead of pointing to it.

## 2. Settings and precedence

Highest wins (settings.md): managed settings, then `--settings` on the command
line, then project local `.claude/settings.local.json`, then shared project
`.claude/settings.json`, then user `~/.claude/settings.json`.

- **What counts as the project root for `.claude/settings.json`.** Not
  settled by the documentation. *(measured 2026-10-02)*:
  - The deny rules in a repository's `.claude/settings.json` apply when the
    session starts in the repository.
  - They do **not** apply when the session starts in a folder above the
    repository.
  - Deny rules in the folder above's own `.claude/` settings, with paths
    written `./<repo>/...`, do apply to files in the repository.

  Only deny rules were tested. Treat other keys in the repository's settings
  the same way until checked.
- *(uncertain)* `.claude/settings.local.json` is added to `.gitignore`
  automatically only when Claude Code creates it. Not confirmed in the docs.
  Check with `git check-ignore`, which the inventory script does.
- A rule the project relies on that lives only in a local or
  outside-the-repository file is not shared with sessions on another machine
  or started elsewhere. That is a continuity gap only if such sessions need
  it. See "The harness is more than the repository" in `lenses.md`.

## 3. Permissions (permissions.md)

- Three lists: `allow`, `ask`, `deny`. Deny wins when it matches.
- Rule forms: `Bash(command pattern*)`, `Read(./path)`, `Edit(./path/**)`,
  `WebFetch(domain:example.com)`, connector tools by name.
- **What a Read or Edit deny rule covers:** "Read and Edit deny rules apply to
  Claude's built-in file tools, to file commands Claude Code recognizes in
  Bash, such as `cat`, `head`, `tail`, `sed`, and `tee`, and to the targets of
  Bash redirections". They do not apply "to a command that reads files without
  naming them, such as `grep -r pattern .`", "or to arbitrary subprocesses that
  read or write files indirectly, like a Python or Node script that opens files
  itself". For that, the sandbox is needed.
- In headless mode a tool outside the allowed list is refused without a prompt.

## 4. Hooks (hooks.md)

Defined in settings files, in a plugin's `hooks/hooks.json`, or in skill and
subagent frontmatter.

Event names: SessionStart, Setup, SessionEnd, UserPromptSubmit,
UserPromptExpansion, Stop, StopFailure, PostToolBatch, PreToolUse,
PermissionRequest, PermissionDenied, PostToolUse, PostToolUseFailure,
SubagentStart, SubagentStop, TeammateIdle, TaskCreated, TaskCompleted,
FileChanged, CwdChanged, DirectoryAdded, InstructionsLoaded, WorktreeCreate,
WorktreeRemove, ConfigChange, PreCompact, PostCompact, PreModelSwitch,
PostModelSwitch, MessageDisplay, Notification, Elicitation, ElicitationResult.

Hook types: `command`, `http`, `mcp_tool`, `prompt`, `agent`.

- **Matchers.** A matcher made only of letters, digits, `_`, `-`, spaces, `|`
  or `,` is an exact name or a list. Anything else is a regular expression.
  `mcp__.*[Nn]otion.*` therefore matches connector tools with "notion" in the
  name whatever the server id is.
- **Exit codes for command hooks.** 0 proceeds, and JSON on stdout may carry a
  decision. 2 blocks, and stderr is shown to Claude. Any other code is a
  non-blocking error and the action proceeds. A script that exits 1 expecting
  to block does nothing.
- Hook bugs to look for: exit 1 used to block, a decision emitted on an event
  that does not support it, a matcher that never matches the real tool name, a
  script that is not executable, no timeout on a hook that calls the network.
- In a read-only audit, do not trigger a hook by doing what it matches. Read
  the script.

Hooks and deny rules are the agent-level enforcement. A convention that appears
in prose and also as a deny rule or blocking hook is enforced. One that appears
only in prose is remembered.

## 5. Sandbox

`sandbox.enabled` and its filesystem, network and credential-masking sub-keys.
*(uncertain)* The current key list was not confirmed in the 2026-10-01 check.
Verify key names against sandboxing.md before recommending any.

## 6. Skills, subagents, plugins

**Skills** live in `<scope>/skills/<name>/SKILL.md`: managed, `~/.claude/skills/`,
`.claude/skills/`, and plugin `skills/`. Documented frontmatter (skills.md):
`name`, `description`, `disable-model-invocation`, `user-invocable`,
`allowed-tools`, `context`, `paths`, `arguments`. Keep `SKILL.md` under 500
lines and put depth in sibling files.

- A skill with `disable-model-invocation: true` is a command the person runs.
  Without it, Claude may pick the skill up on its own. Side-effecting skills
  should have it.
- `${CLAUDE_SKILL_DIR}` points at the skill's own folder.
- A plugin skill is invoked as `/plugin-name:skill-name`.

**Subagents** live in `.claude/agents/*.md`, `~/.claude/agents/*.md`, and plugin
`agents/`. Documented frontmatter (sub-agents.md): `name`, `description`
(required); `tools`, `disallowedTools`, `model`, `permissionMode`, `maxTurns`,
`effort`, `background`, `isolation`, `skills`, `memory`, `omitClaudeMd`,
`mcpServers`, `hooks`, `initialPrompt`, `color`. Keep combined subagent
descriptions well under 15,000 tokens.

For each, note the fields that change what the agent can do without any prose
saying so: tool lists, permission mode, model, hooks, connector servers.

**Plugins** bundle skills, subagents, hooks and connector servers. Layout:
`.claude-plugin/plugin.json`, `skills/`, `agents/`, `hooks/`. Enabled through
`enabledPlugins` in settings.

## 7. Connectors (mcp.md)

- Project servers: `.mcp.json`, shared with the team. Approval is controlled by
  settings keys such as `enabledMcpjsonServers`.
- Local and user servers: `~/.claude.json`. Outside the checkout.
- Connectors attached through claude.ai also appear as tools named `mcp__...`.
  No file in the repository shows them. List them from the audit session's own
  tools when machine scope is on.
- For each: does it earn its always-on cost, are credentials inline, and can it
  write to something the repository's rules say never to touch?

## 8. Orchestration

Subagents, worktree isolation, saved workflows, scheduled runs. See
`workflow-fit.md`.

## 9. Preview and launch

`.claude/launch.json` (desktop.md) tells the desktop app how to start the
project's dev servers so the agent can see the result running:
`{"version": "0.0.1", "configurations": [{"name", "runtimeExecutable", "runtimeArgs", "port"}]}`.

## 10. Headless runs (cli-reference.md, headless.md)

Used by the benchmark step. `claude -p` with:

- `--output-format stream-json --verbose`: one JSON object per line. The last
  has `type: "result"` with `usage`, `num_turns`, `duration_ms`, `is_error`
  and `result`.
- `--setting-sources user,project,local`: which settings layers load.
- `--strict-mcp-config` with no `--mcp-config`: no connector servers at all.
- `--no-session-persistence`, `--model`, `--effort`, `--plugin-dir`,
  `--allowedTools`, `--permission-mode`.
- Token accounting is not documented. Observed on 2026-09-30: `input_tokens`
  excludes both cache figures, which are reported separately.

## What this map does not cover

It does not judge the quality of instruction prose beyond contradiction and
staleness. It is not a security review of hook scripts or connector servers.
If a hook runs shell commands on untrusted input or a server holds
credentials, recommend a separate security review.
