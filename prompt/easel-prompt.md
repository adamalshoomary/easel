Use easel to copy my Canvas units into Markdown notes.

Canvas: https://canvas.your-university.edu
Units: ABC101 ABC102
Notes folder: this folder

1. If `~/.claude/skills/easel/SKILL.md` does not exist, install easel with this command:
   `curl -fsSL https://raw.githubusercontent.com/adamalshoomary/easel/main/install.sh | sh`
2. If that command fails on Windows, run this one instead:
   `powershell -NoProfile -Command "irm https://raw.githubusercontent.com/adamalshoomary/easel/main/install.ps1 | iex"`
3. Read `~/.claude/skills/easel/SKILL.md`. In it, the kit is `~/.claude/skills/easel`.
4. Follow `SKILL.md` with the values above. If "Notes folder" says "this folder", leave out `--root`.
