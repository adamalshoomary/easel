#!/bin/sh
# Installs the easel skill for every coding agent on this computer that reads Agent Skills.
#
#   curl -fsSL https://raw.githubusercontent.com/adamalshoomary/easel/main/install.sh | sh
#   sh install.sh        from a clone
#
# The skill needs its whole folder: SKILL.md, VERSION and scripts/.
# Claude Code reads ~/.claude/skills. Codex, Gemini CLI, Cursor and most other agents read ~/.agents/skills.
set -e

REPO="adamalshoomary/easel"
SRC=""
TMP=""

HERE="$(cd "$(dirname "$0")" 2>/dev/null && pwd || true)"
if [ -n "$HERE" ] && [ -f "$HERE/skills/easel/SKILL.md" ]; then
  SRC="$HERE/skills/easel"
else
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  curl -fsSL "https://codeload.github.com/$REPO/tar.gz/refs/heads/main" -o "$TMP/easel.tar.gz"
  tar -xzf "$TMP/easel.tar.gz" -C "$TMP"
  SRC="$(find "$TMP" -path '*/skills/easel/SKILL.md' | head -n 1 | xargs dirname)"
fi

if [ -z "$SRC" ] || [ ! -f "$SRC/SKILL.md" ] || [ ! -f "$SRC/scripts/easel.py" ]; then
  echo "easel: the download did not contain the skill. Try again, or install with: npx skills add $REPO -g" >&2
  exit 1
fi

for DEST in "$HOME/.claude/skills/easel" "$HOME/.agents/skills/easel"; do
  mkdir -p "$DEST/scripts"
  cp "$SRC/SKILL.md" "$SRC/VERSION" "$DEST/"
  cp "$SRC/scripts/easel.py" "$SRC/scripts/scrape.js" "$SRC/scripts/viewer.js" "$DEST/scripts/"
  echo "installed: $DEST"
done

echo "easel $(cut -d' ' -f1 "$SRC/VERSION") is ready. In Claude Code, run: /easel <your unit codes>"
