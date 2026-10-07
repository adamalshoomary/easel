<div align="center">

# easel

**Your Canvas units, as clean Markdown notes.**

Weeks, assessments, rubrics, marks, feedback and grades, in one folder per unit.

[![Release](https://img.shields.io/github/v/release/adamalshoomary/easel?label=release&color=2b6cb0)](https://github.com/adamalshoomary/easel/releases/latest)
[![Tests](https://img.shields.io/github/actions/workflow/status/adamalshoomary/easel/test.yml?label=tests)](https://github.com/adamalshoomary/easel/actions/workflows/test.yml)
[![Licence](https://img.shields.io/github/license/adamalshoomary/easel?color=718096)](LICENSE)

</div>

https://github.com/user-attachments/assets/f1512e3e-4c7e-4c2a-9b41-571083998323

<p align="center">
<b>5 units in 81 seconds</b> &nbsp;·&nbsp; <b>1% of a Pro plan's 5-hour limit</b><br>
<sub>A real run on five QUT units. The wait plays at 5× speed.</sub>
</p>

You need Claude Code on a paid plan, the [Claude in Chrome extension](https://chromewebstore.google.com/detail/claude/fcoeoabgfenejglbffodgkkbkcdhcgfn) and Python 3.8 or newer.

## Install

**1. Paste this into Claude Code.** This is the easiest way.

```
Install easel from https://github.com/adamalshoomary/easel and run it for me.
```

Claude installs easel, asks for your Canvas address and unit codes, then makes your notes.

**2. Or run one command.** On macOS or Linux, in Terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/adamalshoomary/easel/main/install.sh | sh
```

On Windows, in PowerShell:

```powershell
irm https://raw.githubusercontent.com/adamalshoomary/easel/main/install.ps1 | iex
```

Then go to [Use](#use).

**3. Or paste the full prompt.** Copy [prompt/easel-prompt.md](prompt/easel-prompt.md) into Claude Code. Change the three lines at the top to your Canvas address, your unit codes and your notes folder.

<details>
<summary>Other ways to install</summary>

**With Node.js**, on any system:

```bash
npx skills add adamalshoomary/easel -g
```

**As a Claude Code plugin.** Type these two commands in Claude Code:

```
/plugin marketplace add adamalshoomary/easel
/plugin install easel@easel
```

**Without GitHub access.** Download `easel-offline-prompt.md` from the [latest release](https://github.com/adamalshoomary/easel/releases/latest). Paste it into Claude Code. The prompt holds all of easel.

</details>

## Use

Open Claude Code in the folder for your notes, then run:

```
/easel IFB201 IFB220 --canvas https://canvas.qut.edu.au
```

Use your own unit codes and Canvas address. Later runs need only the unit codes. On the first run, click **Allow** if Chrome asks to reach other apps on this device. Sign in to Canvas if it asks.

Each unit gets one folder, ready for Obsidian or any Markdown app:

```
IFB220 Introduction to AI/
├── INDEX.md            next due date, every assessment, every week
├── 1 Course Info/      staff, groups, syllabus, announcements, Inbox
├── 2 Assessments/      brief, rubric, your files, mark, feedback; Grades.md
├── 3 Weeks/            one note per week
└── Files/              attachments, submissions, marked-up feedback PDFs
```

Grades.md shows your average so far and the mark you need for each grade. Each later run updates the notes and lists what changed. Write your own notes under **My notes**. easel keeps them, and it never changes a file it did not create.

## Privacy and limits

- easel runs on your computer. Canvas data goes from your Chrome tab to your notes folder and nowhere else.
- easel only reads Canvas. Canvas marks your feedback as seen when easel opens it.
- Marked-up PDFs need third-party cookies for Canvas. Chrome allows them by default.
- New Quizzes and lecture recordings stay as links.
- If Canvas hides your unit total, easel works it out. Your unit outline decides your real result.
- easel updates itself. To update now, run `/easel update`.
- On a v3 folder, the first run backs up the v3 notes to `.easel/backups`.

## For agents

Follow these steps if a user asks you to install easel from this page.

1. If `~/.claude/skills/easel/SKILL.md` exists, go to step 4.
2. On macOS or Linux, run `curl -fsSL https://raw.githubusercontent.com/adamalshoomary/easel/main/install.sh | sh`.
3. On Windows, run `powershell -NoProfile -Command "irm https://raw.githubusercontent.com/adamalshoomary/easel/main/install.ps1 | iex"`.
4. Ask the user for their Canvas address and their unit codes, in one question.
5. Read `~/.claude/skills/easel/SKILL.md`. In it, the kit is `~/.claude/skills/easel`.
6. Follow `SKILL.md` with the two values from step 4. Use the current folder as the notes folder.

If the user asked only to install, stop after step 3 and tell them to type `/easel` with their unit codes.

## Licence

MIT. See [LICENSE](LICENSE).
