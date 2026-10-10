<div align="center">

# easel

**Your Canvas units, as clean Markdown notes.**

Weeks, assessments, rubrics, marks, feedback and grades, in one folder per unit.

[![Release](https://img.shields.io/github/v/release/adamalshoomary/easel?label=release&color=2b6cb0)](https://github.com/adamalshoomary/easel/releases/latest)
[![Tests](https://img.shields.io/github/actions/workflow/status/adamalshoomary/easel/test.yml?label=tests)](https://github.com/adamalshoomary/easel/actions/workflows/test.yml)
[![Licence](https://img.shields.io/badge/licence-MIT-718096)](/easel/LICENSE)

<a href="https://adamalshoomary.github.io/easel/"><img src="/easel/site/install-button.svg" alt="Install in Claude Code" height="44"></a>

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
Install easel from https://github.com/adamalshoomary/easel.
```

Claude installs easel. Then follow [Use](#use) in a new chat.

**2. Or run one command.** On macOS or Linux, in Terminal:

```bash
curl -fsSL https://github.com/adamalshoomary/easel/releases/latest/download/install.sh | sh
```

On Windows, in PowerShell:

```powershell
irm https://github.com/adamalshoomary/easel/releases/latest/download/install.ps1 | iex
```

Then go to [Use](#use).

<details>
<summary>Other ways to install</summary>

**With Node.js**, on any system:

```bash
npx skills add adamalshoomary/easel -g
```

</details>

## Use

Open a new Claude Code chat in your notes folder. Then run this command:

```
/easel IFB201 IFB220 --canvas https://canvas.qut.edu.au
```

Use your own unit codes and Canvas address. Later runs need only the unit codes. On the first run, if Chrome shows a box about other apps and services on this device, click **Allow**. If Canvas shows its sign-in page, sign in.

If Claude says a safety check stopped the browser step, run the command again in a new chat.

Each unit gets one folder, ready for Obsidian or any Markdown app:

```
IFB220 Introduction to AI/
├── INDEX.md            next due date, every assessment, every week
├── 1 Course Info/      staff, groups, syllabus, announcements, Inbox
├── 2 Assessments/      brief, rubric, your files, mark, feedback; Grades.md
├── 3 Weeks/            one note per week
└── Files/              attachments, submissions, marked-up feedback PDFs
```

Grades.md shows your average on marked work and the mark you need for each grade. Each later run updates the notes and lists what changed. Write your own notes under **My notes**. easel keeps them, and it never changes a file it did not create.

## Privacy and limits

- easel runs on your computer. Canvas data goes from your Chrome tab to your notes folder.
- Claude sees the folder paths, the address of the Canvas tab and the summary of each run. The summary can show assessment names, new marks and your average on marked work.
- easel only reads Canvas. When easel opens a feedback file, Canvas marks it as seen.
- Marked-up PDFs need third-party cookies for Canvas. Chrome allows them by default.
- New Quizzes and lecture recordings stay as links.
- If Canvas hides your unit total, easel still works out your average on marked work. Your university calculates your real result from the rules in your unit outline.
- easel updates itself from each new release. To update now, run `/easel update`.
- If you installed easel before 4.1.0, install it again. Those copies cannot update themselves.
- On a v3 folder, the first run backs up the v3 notes to `.easel/backups`.

## For agents

If a user asks you to install easel from this page, follow these steps.

1. On macOS or Linux, run `curl -fsSL https://github.com/adamalshoomary/easel/releases/latest/download/install.sh | sh`.
2. On Windows, run `powershell -NoProfile -Command "irm https://github.com/adamalshoomary/easel/releases/latest/download/install.ps1 | iex"`.
3. Tell the user to open a new chat in their notes folder.
4. Tell them to type `/easel` with their unit codes and Canvas address, for example `/easel IFB201 --canvas https://canvas.example.edu`.

Do not run easel in the chat where you installed easel. In that chat, Claude Code's safety check can stop the browser step.

## Licence

MIT. See [LICENSE](/easel/LICENSE).
