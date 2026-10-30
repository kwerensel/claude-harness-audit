#!/usr/bin/env bash
# Read-only harness inventory. Writes nothing and changes nothing.
#
# Usage: collect.sh [--no-machine] [repo_root]
#
# Two scopes:
#   checkout  what is inside the repository folder. Always collected.
#   machine   what surrounds it on this computer: the folders sessions were
#             launched from, settings outside the repository, memory notes,
#             session counts. Collected unless --no-machine is given.
#
# Machine scope rules, enforced here so the auditor does not have to remember:
#   - settings outside the repository: key names and permission rules only,
#     never other values
#   - memory notes: file names, sizes and description lines only
#   - session history: counts of launch folders only, never conversation text
#   - .env files are never opened in either scope

set -uo pipefail
MACHINE=1
ROOT=""
for arg in "$@"; do
  case "$arg" in
    --no-machine) MACHINE=0 ;;
    *) ROOT="$arg" ;;
  esac
done
ROOT="${ROOT:-${CLAUDE_PROJECT_DIR:-$PWD}}"
cd "$ROOT" 2>/dev/null || { echo "cannot cd to $ROOT"; exit 1; }
ROOT="$(pwd -P)"

H(){ printf '\n===== %s =====\n' "$1"; }
# --no-optional-locks stops status checks from refreshing the index, which would be a write.
G(){ git --no-optional-locks "$@" </dev/null 2>/dev/null; }
# Redact anything that looks like a credential before it reaches the transcript.
RED='s#(Bearer|Token|token|api[_-]?key|apiKey|password|secret)([\"'"'"':= ]+)[A-Za-z0-9._~+/-]{12,}#\1\2<REDACTED-SECRET>#gI; s#(pat[A-Za-z0-9]{10,}[.A-Za-z0-9]*|sk-[A-Za-z0-9_-]{16,}|sbp_[A-Za-z0-9]{16,}|ntn_[A-Za-z0-9]{16,}|secret_[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})#<REDACTED-SECRET>#g'
redact(){ sed -E "$RED"; }
# Claude Code stores per-project data under a folder named after the path, with
# every character that is not a letter or digit replaced by a dash.
encode(){ printf '%s' "$1" | sed 's/[^A-Za-z0-9]/-/g'; }

# Key names, permission rules and connector server names from a settings file.
# Values are never printed, except permission rules, which are redacted.
settings_outline(){
  python3 - "$1" <<'PY' 2>/dev/null || echo "    (could not parse; python3 missing or file is not valid JSON)"
import json, re, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception as exc:
    print(f"    not valid JSON: {type(exc).__name__}"); sys.exit(0)
SECRET = re.compile(r'(Bearer\s+\S{8,}|pat[A-Za-z0-9]{10,}|sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{20,})')
def mask(text):
    return SECRET.sub('<REDACTED-SECRET>', text)
print("    top-level keys: " + (", ".join(sorted(data)) or "(none)"))
perms = data.get("permissions") or {}
for kind in ("allow", "ask", "deny"):
    rules = perms.get(kind) or []
    print(f"    permissions.{kind}: {len(rules)} rule(s)")
    for i, rule in enumerate(rules, 1):
        print(f"      {i:>2}. {mask(str(rule))[:160]}")
for key in ("defaultMode", "additionalDirectories"):
    if key in perms:
        print(f"    permissions.{key}: {perms[key]}")
hooks = data.get("hooks") or {}
if hooks:
    for event, entries in hooks.items():
        for entry in entries or []:
            for hook in entry.get("hooks", []):
                target = mask(str(hook.get("command") or hook.get("url") or hook.get("prompt") or ""))[:120]
                print(f"    hook {event} matcher={entry.get('matcher', '*')!r} type={hook.get('type')} -> {target}")
else:
    print("    hooks: none")
for name, server in (data.get("mcpServers") or {}).items():
    blob = json.dumps(server)
    inline = bool(SECRET.search(blob)) or '"Authorization"' in blob and "${" not in blob
    print(f"    connector server {name!r}: type={server.get('type', 'stdio')} inline credential={'YES' if inline else 'no'}")
if "sandbox" in data:
    print("    sandbox keys: " + ", ".join(sorted(data["sandbox"])))
if "enabledPlugins" in data:
    on = [k for k, v in data["enabledPlugins"].items() if v]
    print(f"    enabled plugins: {len(on)}" + (" (" + ", ".join(on[:12]) + ")" if on else ""))
if "env" in data:
    print("    env var names: " + ", ".join(sorted(data["env"])))
PY
}

echo "harness inventory: $ROOT"
echo "collected: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "scopes: checkout$([ "$MACHINE" = 1 ] && echo ' + machine')"

H "repo shape"
if G rev-parse --is-inside-work-tree >/dev/null; then
  echo "git: yes  branch=$(G branch --show-current)  commit=$(G rev-parse --short HEAD)"
  echo "repository root: $(G rev-parse --show-toplevel)"
  echo "commits: $(G rev-list --count HEAD)  contributors: $(G shortlog -sn --all | wc -l | tr -d ' ')"
  echo "last commit: $(G log -1 --format='%ad' --date=short)"
  echo "ahead/behind upstream: $(G rev-list --left-right --count '@{upstream}...HEAD' | awk '{print "behind " $1 ", ahead " $2}' | grep . || echo 'no upstream')"
  echo "tracked files: $(G ls-files | wc -l | tr -d ' ')"
  echo "-- uncommitted --"; G status --porcelain | head -30 | grep . || echo "  clean"
else
  echo "git: no"
fi
echo "top-level:"; ls -A 2>/dev/null | head -40

H "instruction files (checkout)"
for f in CLAUDE.md .claude/CLAUDE.md CLAUDE.local.md AGENTS.md .cursorrules .github/copilot-instructions.md; do
  [ -f "$f" ] && printf '%-36s %5s lines %6s words  last commit %s\n' "$f" "$(wc -l <"$f" | tr -d ' ')" "$(wc -w <"$f" | tr -d ' ')" "$(G log -1 --format=%ad --date=short -- "$f" | grep . || echo 'untracked')"
done
[ -f CLAUDE.md ] || [ -f .claude/CLAUDE.md ] || echo "  no project CLAUDE.md"
[ -f AGENTS.md ] && { [ -f CLAUDE.md ] || [ -f .claude/CLAUDE.md ]; } && ! grep -qs '@AGENTS.md' CLAUDE.md .claude/CLAUDE.md 2>/dev/null \
  && echo "  note: AGENTS.md and CLAUDE.md both exist and CLAUDE.md does not import AGENTS.md. Check which one a session reads."
echo "-- nested CLAUDE.md / AGENTS.md (below root) --"
find . -mindepth 2 \( -name 'CLAUDE.md' -o -name 'AGENTS.md' \) -not -path '*/node_modules/*' -not -path './.git/*' -not -path './.claude/CLAUDE.md' 2>/dev/null | head -30 | grep . || echo "  none"
echo "-- rules --"; find .claude/rules -name '*.md' 2>/dev/null | while read -r r; do
  printf '  %s%s\n' "$r" "$(grep -qs '^paths:' "$r" && echo '  (path-scoped)' || echo '  (always on)')"; done | grep . || echo "  none"

H "stated rules (candidates for the rules table)"
for f in CLAUDE.md .claude/CLAUDE.md AGENTS.md; do
  [ -f "$f" ] || continue
  echo "--- $f ---"
  echo "headings:"; grep -n '^#\+ ' "$f" | head -40
  echo "imports:"; grep -n '^[^`]*@[A-Za-z0-9./~_-]\+' "$f" | head -20 | grep . || echo "  none"
  echo "always / never / must statements:"
  grep -nEi '\b(always|never|must|do not|don.t|required|no exceptions|before (you )?(commit|push|merge)|only (in|from|via))\b' "$f" | cut -c1-220 | head -50
done

H "agent-facing documents (checkout)"
echo "words  bytes  state      last-commit  path"
{ G ls-files '*.md' '*.mdx' 2>/dev/null | sed 's/^/T /'; G ls-files --others --exclude-standard '*.md' '*.mdx' 2>/dev/null | sed 's/^/U /'; } \
  | grep -v node_modules | while read -r state path; do
    [ -f "$path" ] || continue
    printf '%6s %6s  %-9s  %-11s  %s\n' "$(wc -w <"$path" | tr -d ' ')" "$(wc -c <"$path" | tr -d ' ')" \
      "$([ "$state" = T ] && echo tracked || echo UNTRACKED)" "$(G log -1 --format=%ad --date=short -- "$path" | grep . || echo '-')" "$path"
  done | sort -rn | head -60
echo "(largest 60 shown; untracked documents are invisible to a fresh clone)"

H "capabilities (checkout)"
echo "-- project skills --"; find .claude/skills -name SKILL.md 2>/dev/null | while read -r s; do printf '%s (%s lines)\n' "$s" "$(wc -l <"$s"|tr -d ' ')"; sed -n '1,25p' "$s" | grep -E '^(name|description|when_to_use|allowed-tools|disallowed-tools|disable-model-invocation|user-invocable|context|agent|model|effort|paths|background):' | cut -c1-200 | sed 's/^/    /'; done | grep . || echo "  none"
echo "-- project agents --"; find .claude/agents -name '*.md' 2>/dev/null | while read -r a; do printf '%s\n' "$a"; sed -n '1,20p' "$a" | grep -E '^(name|description|tools|disallowedTools|model|permissionMode|maxTurns|skills|mcpServers|memory|isolation|background):' | cut -c1-200 | sed 's/^/    /'; done | grep . || echo "  none"
echo "-- project commands --"; find .claude/commands -name '*.md' 2>/dev/null | head -30 | grep . || echo "  none"

H "settings, hooks, connectors (checkout)"
for f in .claude/settings.json .claude/settings.local.json; do
  [ -f "$f" ] && { echo "--- $f  ($(G check-ignore -q "$f" && echo gitignored || echo 'NOT gitignored')) ---"; settings_outline "$f"; }
done
[ -f .claude/settings.json ] || [ -f .claude/settings.local.json ] || echo "  no settings files in the repository"
echo "-- hook scripts --"
find .claude/hooks -type f 2>/dev/null | while read -r h; do
  printf '%s  executable=%s\n' "$h" "$([ -x "$h" ] && echo yes || echo NO)"
  grep -nE 'exit [0-9]|permissionDecision' "$h" 2>/dev/null | head -6 | sed 's/^/    /'
done | grep . || echo "  none"
if [ -f .mcp.json ]; then echo "--- .mcp.json ---"; settings_outline_mcp=1; python3 - .mcp.json <<'PY' 2>/dev/null || echo "    (could not parse)"
import json, sys
for name, server in (json.load(open(sys.argv[1])).get("mcpServers") or {}).items():
    blob = json.dumps(server)
    print(f"    {name}: type={server.get('type', 'stdio')} inline credential={'YES' if 'Bearer ' in blob and '${' not in blob else 'no'}")
PY
else echo "  no project .mcp.json"; fi
echo "-- literal credentials in checked-in agent config (redacted) --"
grep -rInE '(pat[A-Za-z0-9]{14,}|sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|"Authorization"\s*:\s*"Bearer [A-Za-z0-9]{12,})' .claude .mcp.json 2>/dev/null | redact | cut -c1-160 | head -20 | grep . || echo "  none found"

H "secret files (names only, never opened)"
find . -maxdepth 3 -name '.env*' -not -path '*/node_modules/*' 2>/dev/null | while read -r e; do
  printf '  %-34s %s\n' "$e" "$(G check-ignore -q "$e" && echo gitignored || echo 'NOT gitignored')"; done | grep . || echo "  none"

H "checks and enforcement (checkout)"
for f in package.json Makefile justfile Taskfile.yml pyproject.toml Cargo.toml go.mod; do [ -f "$f" ] && echo "  build file: $f"; done
[ -f package.json ] && { echo "  root npm scripts:"; sed -n '/"scripts"/,/}/p' package.json | head -25; }
for p in */package.json; do [ -f "$p" ] && { echo "  $p scripts:"; sed -n '/"scripts"/,/}/p' "$p" | head -15; }; done 2>/dev/null
[ -f Makefile ] && { echo "  make targets:"; grep -E '^[a-zA-Z0-9_.-]+:' Makefile | head -20; }
echo "  test files: $(G ls-files | grep -ciE '(\.|_)(test|spec)\.|/tests?/|/__tests__/')"
G ls-files | grep -iE '(\.|_)(test|spec)\.|/tests?/|/__tests__/' | sed 's|/[^/]*$||' | sort | uniq -c | sort -rn | head -8 | sed 's/^/    /'
echo "  CI workflows:"; ls .github/workflows 2>/dev/null | sed 's/^/    /' | grep . || echo "    none in the checkout"
echo "  git hooks path: $(G config core.hooksPath | grep . || echo default); pre-commit config: $(ls .pre-commit-config.yaml .husky 2>/dev/null | tr '\n' ' ' | grep . || echo none)"
echo "  launch config: $(ls .claude/launch.json 2>/dev/null || echo none)"

H "gitignore hygiene"
grep -nE 'settings\.local\.json|CLAUDE\.local\.md|\.claude|\.env' .gitignore 2>/dev/null | head -12 || echo "  no relevant .gitignore entries"

H "maintenance"
G log -1 --format='last .claude change: %ad by %an' --date=short -- .claude | grep . || echo "  .claude has no tracked history"
G log -1 --format='last CLAUDE.md change: %ad by %an' --date=short -- CLAUDE.md .claude/CLAUDE.md | grep . || echo "  CLAUDE.md has no tracked history"
echo "  commits touching CLAUDE.md: $(G log --oneline -- CLAUDE.md .claude/CLAUDE.md | wc -l | tr -d ' ')"
echo "  commits touching AGENTS.md: $(G log --oneline -- AGENTS.md | wc -l | tr -d ' ')"

H "always-on instruction size (file sizes, not runtime tokens)"
tot=0
for f in CLAUDE.md .claude/CLAUDE.md CLAUDE.local.md; do [ -f "$f" ] && { c=$(wc -c <"$f"|tr -d ' '); tot=$((tot+c)); printf '  %-30s %s bytes\n' "$f" "$c"; }; done
for f in $(find .claude/rules -name '*.md' 2>/dev/null); do grep -qs '^paths:' "$f" || { c=$(wc -c <"$f"|tr -d ' '); tot=$((tot+c)); printf '  %-30s %s bytes (always on)\n' "$f" "$c"; }; done
printf '  total: %s bytes\n' "$tot"

if [ "$MACHINE" = 1 ]; then
  H "MACHINE SCOPE: launch folders and session counts"
  echo "A session's project is its launch folder. If sessions for this repository were"
  echo "launched from a folder above it, the repository's CLAUDE.md is a nested file"
  echo "for those sessions unless an instruction file above imports it, and the deny"
  echo "rules in its .claude/settings.json do not apply (measured 2026-10-02)."
  dir="$ROOT"; found=0
  while :; do
    proj="$HOME/.claude/projects/$(encode "$dir")"
    if [ -d "$proj" ]; then
      found=1
      n=$(find "$proj" -maxdepth 1 -name '*.jsonl' 2>/dev/null | wc -l | tr -d ' ')
      rel="$([ "$dir" = "$ROOT" ] && echo 'the repository itself' || echo 'ABOVE the repository')"
      echo "  launch folder: $dir  ($rel)  sessions recorded: $n"
      if [ "$n" -gt 0 ]; then
        echo "    working folders seen in those sessions (counts only):"
        grep -oh '"cwd": *"[^"]*"' "$proj"/*.jsonl 2>/dev/null | sed 's/"cwd": *"/"cwd":"/' | sort | uniq -c | sort -rn | head -5 | sed 's/^/      /'
      fi
      if [ -d "$proj/memory" ]; then
        echo "    memory notes in $proj/memory (names and descriptions only):"
        [ -f "$proj/memory/MEMORY.md" ] && echo "      MEMORY.md index: $(wc -l <"$proj/memory/MEMORY.md" | tr -d ' ') lines (only the first 200 lines or 25KB load each session)"
        for note in "$proj"/memory/*.md; do
          [ -f "$note" ] || continue; [ "$(basename "$note")" = MEMORY.md ] && continue
          printf '      %-40s %4s lines  %s\n' "$(basename "$note")" "$(wc -l <"$note" | tr -d ' ')" "$(grep -m1 '^description:' "$note" | cut -c1-140)"
        done
      fi
    fi
    [ "$dir" = "$HOME" ] || [ "$dir" = "/" ] && break
    dir="$(dirname "$dir")"
  done
  [ "$found" = 0 ] && echo "  no recorded sessions for this repository or any folder above it"
  for wt in "$ROOT"/.claude/worktrees/*/; do
    [ -d "$wt" ] && [ -d "$HOME/.claude/projects/$(encode "${wt%/}")" ] && echo "  worktree sessions also recorded for: ${wt%/}"
  done 2>/dev/null

  H "MACHINE SCOPE: instruction and settings files above the repository"
  dir="$(dirname "$ROOT")"
  while :; do
    for f in CLAUDE.md CLAUDE.local.md AGENTS.md; do [ -f "$dir/$f" ] && echo "  $dir/$f  ($(wc -l <"$dir/$f" | tr -d ' ') lines)"; done
    for f in .claude/settings.json .claude/settings.local.json; do
      [ -f "$dir/$f" ] && [ "$dir" != "$HOME" ] && { echo "--- $dir/$f  (outside the repository, not version controlled with it) ---"; settings_outline "$dir/$f"; }
    done
    [ "$dir" = "$HOME" ] || [ "$dir" = "/" ] && break
    dir="$(dirname "$dir")"
  done
  echo "(nothing listed above means no such files between the repository and the home folder)"

  H "MACHINE SCOPE: user-level setup (key names and rules only)"
  [ -f "$HOME/.claude/CLAUDE.md" ] && echo "  ~/.claude/CLAUDE.md: $(wc -l <"$HOME/.claude/CLAUDE.md" | tr -d ' ') lines" || echo "  no ~/.claude/CLAUDE.md"
  echo "  user rules: $(find "$HOME/.claude/rules" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
  echo "  user skills: $(ls "$HOME/.claude/skills" 2>/dev/null | tr '\n' ' ' | grep . || echo none)"
  echo "  user agents: $(ls "$HOME/.claude/agents" 2>/dev/null | tr '\n' ' ' | grep . || echo none)"
  if [ -f "$HOME/.claude/settings.json" ]; then
    echo "--- ~/.claude/settings.json  (mode $(stat -f '%Lp' "$HOME/.claude/settings.json" 2>/dev/null || stat -c '%a' "$HOME/.claude/settings.json" 2>/dev/null)) ---"
    settings_outline "$HOME/.claude/settings.json"
    grep -nE '"Authorization"\s*:\s*"Bearer [A-Za-z0-9]{12,}|pat[A-Za-z0-9]{14,}|sk-[A-Za-z0-9_-]{16,}' "$HOME/.claude/settings.json" 2>/dev/null | cut -d: -f1 | tr '\n' ' ' | sed 's/^/    lines holding a literal credential: /' | grep '[0-9]' || true
  else echo "  no ~/.claude/settings.json"; fi
  if [ -f "$HOME/.claude.json" ]; then
    echo "--- ~/.claude.json  (user and local connector servers; names only) ---"
    python3 - "$HOME/.claude.json" "$ROOT" <<'PY' 2>/dev/null || echo "    (could not parse)"
import json, sys
data = json.load(open(sys.argv[1]))
def show(label, servers):
    for name, server in (servers or {}).items():
        blob = json.dumps(server)
        inline = ('Bearer ' in blob or '"Authorization"' in blob) and '${' not in blob
        print(f"    {label} connector server {name!r}: type={server.get('type', 'stdio')} inline credential={'YES' if inline else 'no'}")
show("user", data.get("mcpServers"))
root = sys.argv[2]
for path, project in (data.get("projects") or {}).items():
    if root == path or root.startswith(path.rstrip("/") + "/"):
        show(f"local ({path})", project.get("mcpServers"))
if not data.get("mcpServers"):
    print("    no user-level connector servers")
PY
  else echo "  no ~/.claude.json"; fi
  echo "  managed settings: $(ls "/Library/Application Support/ClaudeCode/managed-settings.json" /etc/claude-code/managed-settings.json 2>/dev/null | grep . || echo 'none found')"
  echo
  echo "Not visible to this script: connectors attached through claude.ai. The auditor"
  echo "must list them from its own session's tool list (tools named mcp__...)."
fi

H "end"
