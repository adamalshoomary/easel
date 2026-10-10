#!/bin/sh
# Installs the easel skill for every coding agent on this computer that reads Agent Skills.
#
#   curl -fsSL https://github.com/adamalshoomary/easel/releases/latest/download/install.sh | sh
#   sh easel/install.sh      from a clone: installs the copy in that clone
#
# The skill needs its whole folder: SKILL.md, VERSION and scripts/.
# Claude Code reads ~/.claude/skills. Codex, Gemini CLI, Cursor and most other agents read ~/.agents/skills.
# A release holds its files flat. EASEL_FROM sets another address for them; CI uses it to test a build.
set -e

FROM="${EASEL_FROM:-https://github.com/adamalshoomary/easel/releases/latest/download}"
SRC=""
TMP=""

# "$0" names a file only when this script runs from a file. Piped from curl, it downloads.
HERE="$(cd "$(dirname "$0")" 2>/dev/null && pwd || true)"
if [ -z "$EASEL_FROM" ] && [ -f "$0" ] && [ -f "$HERE/skills/easel/SKILL.md" ]; then
  SRC="$HERE/skills/easel"
else
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  mkdir -p "$TMP/scripts"
  for F in VERSION SKILL.md scripts/easel.py scripts/scrape.js scripts/viewer.js; do
    curl -fsSL "$FROM/$(basename "$F")" -o "$TMP/$F" || {
      echo "easel: could not download $(basename "$F") from $FROM. Try again, or install with: npx skills add adamalshoomary/easel -g" >&2
      exit 1
    }
  done
  SRC="$TMP"
fi

if [ ! -s "$SRC/SKILL.md" ] || [ ! -s "$SRC/scripts/easel.py" ]; then
  echo "easel: the download did not contain the skill. Try again, or install with: npx skills add adamalshoomary/easel -g" >&2
  exit 1
fi

for DEST in "$HOME/.claude/skills/easel" "$HOME/.agents/skills/easel"; do
  mkdir -p "$DEST/scripts"
  cp "$SRC/SKILL.md" "$SRC/VERSION" "$DEST/"
  cp "$SRC/scripts/easel.py" "$SRC/scripts/scrape.js" "$SRC/scripts/viewer.js" "$DEST/scripts/"
  echo "installed: $DEST"
done

echo "easel $(cut -d' ' -f1 "$SRC/VERSION") is ready. In Claude Code, run: /easel <your unit codes>"
