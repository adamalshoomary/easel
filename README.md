# easel

easel copies your Canvas units into Markdown notes on your own computer. Claude does the work in your own Chrome, signed in as you, so it sees exactly what you see on Canvas. You get one folder per unit, ready for Obsidian, VS Code or any Markdown app.

## What you get

For each unit:

- **One note per week**, with every page, file, quiz and discussion from that week's modules.
- **One note per assessment**: the brief, the due date, the weight, the rubric, the files you submitted, your mark, the rubric level you reached on each criterion, your marker's comments, and every annotation your marker left on your file, with the marked-up PDF beside it.
- **A Grades note**: your average on marked work, the share of the unit you have already secured, and the mark you need on the remaining work for each grade. It follows the weights and drop rules on the Canvas Grades tab and your university's grade scale.
- **Course info**: teaching staff and their roles, your groups, links to the unit's Canvas tools, the syllabus, every announcement, and Inbox messages from staff.
- **Files** in folders beside the notes that link them. Logos, banners and other page images stay on Canvas.

Each later run updates the notes in place and prints a short summary of what changed: new announcements, released marks, changed weeks, new feedback. Anything you write under the **My notes** heading at the bottom of a note survives every update. A note you have edited anywhere else stays exactly as you left it.

## What you need

- Claude Code (the desktop app, the terminal or VS Code), signed in with a Claude Pro, Max, Team or Enterprise plan.
- The [Claude in Chrome extension](https://chromewebstore.google.com/detail/claude/fcoeoabgfenejglbffodgkkbkcdhcgfn), in Chrome, Edge, Brave, Arc, Vivaldi or Opera.
- Python 3.8 or newer. Most Macs and Linux computers have it. On Windows, easel offers to install it.
- A Canvas account at any university that uses Canvas.

## Install

Pick one.

**Paste a prompt.** Copy [prompt/easel-prompt.md](prompt/easel-prompt.md) into Claude Code. Change the three lines at the top to your Canvas address, your unit codes and your notes folder. Claude installs easel and runs it.

**Install the skill.** Run this command once:

```bash
npx skills add adamalshoomary/easel -g
```

**Install the Claude Code plugin.** Run these two commands in Claude Code:

```
/plugin marketplace add adamalshoomary/easel
/plugin install easel@easel
```

**Install without Node.** On macOS or Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/adamalshoomary/easel/main/install.sh | sh
```

On Windows, in PowerShell:

```powershell
irm https://raw.githubusercontent.com/adamalshoomary/easel/main/install.ps1 | iex
```

**No access to GitHub?** Each release has an offline prompt that carries easel inside it. Paste it into Claude Code.

## Use

Open Claude Code in the folder that holds your unit folders, then run:

```
/easel IFB201 IFB220 IFB240 --canvas https://canvas.qut.edu.au
```

Use your own unit codes and Canvas address. easel remembers the address and the folder, so later runs need only the unit codes:

```
/easel IFB201 IFB220 IFB240
```

The first run asks for one or two clicks from you:

1. Chrome shows a small box under the address bar: Canvas wants to access other apps and services on this device. Click **Allow**. Chrome remembers your answer.
2. If Canvas asks you to sign in, sign in in the tab that Claude opened. Claude waits, then carries on.

A run takes one to three minutes for four or five units. Claude then shows a summary like this one:

```
easel 4.0.0: 3 of 3 units updated in 96 s.
- IFB201: 1 new announcement; changed: Week 11; average on marked work 93.5% (High Distinction (7)).
- IFB220: marks released: Portfolio Artefact 7 4/6; average on marked work 83.3% (Distinction (6)).
- IFB240: annotated feedback saved for Assessment Task 2 - Part A; average on marked work 89% (High Distinction (7)).
```

## Your unit folder

```
IFB220 Introduction to AI/
├── INDEX.md            the unit at a glance: next due date, every assessment, every week
├── 1 Course Info/      course info, announcements, Inbox, modules that are not weeks
├── 2 Assessments/      one note per assessment, and Grades.md
├── 3 Weeks/            Week 01 - Topic.md, Week 02 - Topic.md, ...
├── Files/              attachments, your submissions and marked-up feedback PDFs
└── .easel/             easel's records, backups and the full report of the last run
```

Your own files and folders can sit anywhere in the unit folder. easel never changes, moves or deletes a file it did not create, and it checks your files before and after each run.

## Privacy

- easel runs on your computer. Canvas data travels from your Chrome tab to a small helper on `127.0.0.1`, then into your notes folder. It goes to no other server.
- easel only reads Canvas. It never submits, posts or changes anything. Canvas records three of its reads as actions: one query for your grade scale, one request that asks Canvas's document viewer to build each marked-up PDF, and the "feedback seen" mark that opening your feedback sets, as it does when you open it yourself.
- Marked-up PDFs pass through your browser's download folder for a moment. The helper moves them into the assessment folder.
- easel keeps the last copy of each unit's Canvas data in `~/.easel/bundles`, so it can rebuild notes without a browser.

## Updates

Each run checks GitHub once for a newer version. If one exists, easel installs it and tells you in one line. To update now, run `/easel update`.

## Limits

- easel 4 needs the Claude in Chrome extension. Version 5 adds a route without it, version 6 adds other agents, and version 7 adds a route with no agent at all.
- Marked-up PDFs need Chrome to allow third-party cookies for Canvas. Chrome allows them unless you changed the setting.
- New Quizzes, lecture recordings and other tools inside Canvas stay as links.
- Canvas hides the unit total from students at some universities. easel then works the total out from your released marks and the Canvas Grades tab. Your unit outline and Canvas decide your real result.

## Moving from the v3 prompt

The first easel run on a v3 unit folder zips the v3 notes into `.easel/backups`, then rebuilds them in the new layout. Notes you edited by hand stay as they are. Your files stay where they are.

## Licence

MIT. See [LICENSE](LICENSE).
