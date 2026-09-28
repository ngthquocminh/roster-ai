#!/usr/bin/env bash
# SessionStart hook: regenerate the BMad skills in Claude Code cloud sessions.
#
# .claude/skills/ is gitignored (reinstallable tooling), so a fresh cloud clone
# has the committed _bmad/ config but no skills. This rebuilds them from that
# config at the versions pinned in _bmad/_config/manifest.yaml. Local sessions
# already have the skills and skip this. Never fails the session start.
set -uo pipefail

[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

# Already installed (resumed container) -> nothing to do.
if [ -f .claude/skills/bmad-help/SKILL.md ]; then
  exit 0
fi

echo "Installing BMad skills for this cloud session..."
if npx -y bmad-method@6.10.0 install \
    --directory . \
    --action quick-update \
    --modules core,bmm,tea,bmb,cis \
    --pin tea=v1.21.6 --pin bmb=v2.1.0 --pin cis=v0.2.1 \
    --tools claude-code \
    --yes >/tmp/bmad-install.log 2>&1; then
  # The installer rewrites committed _bmad/ config (timestamps, paths); restore
  # it so the session starts with a clean tree. The skills live outside git.
  git checkout -- _bmad >/dev/null 2>&1
  git clean -fq -- _bmad >/dev/null 2>&1
  echo "BMad skills installed: $(ls -d .claude/skills/bmad-* 2>/dev/null | wc -l)"
else
  echo "BMad install failed (see /tmp/bmad-install.log); continuing without BMad skills."
fi
exit 0
