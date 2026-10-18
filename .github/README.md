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
<sub>A real run on five QUT units, 7 October 2026. The wait plays at 5× speed.</sub>
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
├── 1 Course Info/      staff, groups, announcements, Inbox
├── 2 Assessments/      brief, rubric, your files, mark, feedback; Grades.md
├── 3 Weeks/            one note per week
└── Files/              attachments, submissions, feedback PDFs, transcripts, slide text
```

Each assessment note holds the brief, the rubric with the level you reached on each criterion, your submitted files, the mark, the marker's comments and the marked-up PDF. The [install page](https://adamalshoomary.github.io/easel/) shows one.

Lecture slides and Word handouts get a text file beside them, so you can search them. Each unit folder also keeps a list of everything Canvas showed easel and what it did with each item, in `.easel/coverage.md`.

Grades.md shows your average on marked work and the mark you need for each grade, using the drop rules and extra credit your unit set in Canvas. Each later run updates the notes and lists what changed. Write your own notes under **My notes**. easel keeps them, and it never changes a file it did not create. A note you edit stays as you left it.

## Privacy and limits

- easel runs on your computer. Canvas data goes from your Chrome tab to your notes folder.
- Claude sees the folder paths, the address of the Canvas tab and the summary of each run. The summary can show assessment names, new marks and your average on marked work.
- While easel collects feedback, Claude also sees the address of the Canvas document viewer, which carries a session token.
- easel only reads Canvas. When easel opens a feedback file, Canvas marks it as seen.
- Marked-up PDFs need third-party cookies for Canvas. Chrome allows them by default.
- A video that Canvas hosts gets a transcript file when Canvas has subtitles for it. Recordings on other services, such as Echo360 and YouTube, and New Quizzes stay as links, with the service named.
- To name a Canvas tool link, easel opens the link's Canvas page. It never opens the tool itself.
- For a classic quiz, easel copies your attempts: each question, the options and whether you got it right. Canvas does not say which option you picked.
- If Canvas hides your unit total, easel still works out your average on marked work. Your university calculates your real result from the rules in your unit outline.
- If Canvas does not answer a read, the summary says INCOMPLETE and names the part. The notes keep the last good copy. Run easel again later.
- Each unit folder belongs to one Canvas site. easel refuses to update it from another site.
- easel updates itself from each new release. If an update is interrupted, the next run repairs it. To update now, run `/easel update`.
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
