---
name: easel
description: Copy Canvas LMS units into organised Markdown notes for Obsidian or any Markdown app. One note per week and one per assessment, with the brief, rubric, the student's submission, marks, rubric levels reached, marker comments and annotated feedback PDFs, plus a Grades note with the mark needed for each grade. Use when the user asks to scrape, sync, update, download or back up Canvas units, notes, rubrics, grades or feedback, or runs /easel with unit codes.
argument-hint: <UNIT CODES> [--canvas <url>] [--root <notes folder>] | update
allowed-tools: Bash, Read, AskUserQuestion, mcp__claude-in-chrome__tabs_context_mcp, mcp__claude-in-chrome__navigate, mcp__claude-in-chrome__javascript_tool, mcp__claude-in-chrome__browser_batch, mcp__claude-in-chrome__tabs_close_mcp, mcp__claude-in-chrome__list_connected_browsers
---

# easel

Run every step yourself, in this session. Do not spawn subagents. Do not read, explain or change the code. A normal run takes about eight tool calls. Keep messages to the user short and plain.

## Terms

- **Kit**: `${CLAUDE_SKILL_DIR}`. If that text appears unchanged, the kit is the folder that holds this file.
- **Helper**: `<kit>/scripts/easel.py`.
- **PY**: the Python command that works on this computer. Step 1 finds it.
- **Tab**: the Chrome tab that you open for Canvas.

## Values

Take each value from the user's message or from the prompt that loaded this skill.

- **UNIT CODES**: one or more codes, such as `IFB201 IFB220`. If none are given, ask the user with `AskUserQuestion`.
- **CANVAS URL**: such as `https://canvas.qut.edu.au`. Optional after the first run, because the helper remembers it.
- **NOTES FOLDER**: the folder that holds the unit folders. Optional: the helper uses the current folder or the folder from the last run.
- **FLAGS**: `--media` also downloads video, audio and files over 100 MB. `--no-feedback` skips annotated feedback. `--refresh-feedback` checks every marked file again.

If the user types `update` with no unit codes, run `PY "<kit>/scripts/easel.py" update`, say the result in one sentence, and stop.

## Step 1: find Python

1. Run `python3 --version`. If it fails, or it mentions the Microsoft Store, run `python --version`. If that fails, run `py -3 --version`.
2. PY is the first command that prints Python 3.8 or newer.
3. If no command works, go to "If Python is missing". Come back here when Python works.

## Step 2: start the helper

Run this command. Put each value in double quotes. Leave out any value that you do not have.

```bash
PY "<kit>/scripts/easel.py" start <UNIT CODES> --canvas "<CANVAS URL>" --root "<NOTES FOLDER>" <FLAGS>
```

- If the output has a line that starts with `easel updated`, tell the user that line in one sentence.
- If the output starts with `CANVAS_NEEDED`, ask the user for the Canvas address, then run the command again with `--canvas`.
- If the output starts with `ROOT_NEEDED`, ask the user for the notes folder, then run the command again with `--root`.
- If the command fails with any other error, quote the error to the user and stop.
- The last line starts with `LOADER: `. Keep the text after `LOADER: ` exactly. This text is the loader.

## Step 3: open Canvas and run the loader

1. Load the browser tools with one ToolSearch call: `select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__browser_batch,mcp__claude-in-chrome__javascript_tool,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__tabs_close_mcp,mcp__claude-in-chrome__list_connected_browsers`
2. If ToolSearch returns none of these tools, go to "If the browser tools are missing".
3. Call `tabs_context_mcp` with `createIfEmpty: true`. Use the tab that it returns.
4. If the call fails, call `list_connected_browsers`, then call `tabs_context_mcp` once more. If it fails again, go to "If Chrome is not connected".
5. Make one `browser_batch` call with two actions: `navigate` the tab to the CANVAS URL, then `javascript_tool` with `action: "javascript_exec"` and the loader as the text.
6. If Claude Code denies the call, go to "If Claude Code stops the browser step".

The loader returns one of these results:

- `PERMISSION_GRANTED` or `PERMISSION_UNKNOWN`: go to step 4.
- `PERMISSION_PROMPT`: tell the user: "Chrome is showing a small box under the address bar: Canvas wants to access other apps and services on this device. Click **Allow**." Then go to step 4.
- `PERMISSION_DENIED`: go to "If Chrome blocks the connection".
- `WRONG_PAGE`: the tab is not on Canvas. Go to "If Canvas asks the user to sign in".

## Step 4: wait for the helper

Run this command with a Bash timeout of 600000:

```bash
PY "<kit>/scripts/easel.py" wait
```

The first word of the output tells you what to do:

- `easel`: the run is finished. Go to step 5.
- `VIEWER`: the tab is moving to Canvas's document viewer. Copy every line after `VIEWER_JS:` into one `javascript_tool` call on the tab. If Claude Code denies the call, go to "If Claude Code stops the browser step". If the result starts with `NOT_READY`, wait 3 seconds and call it again, up to five times. Then run the wait command again. If the output also says that the browser asks where to save downloads, tell the user to click **Save** in that dialog.
- `LOGIN`: go to "If Canvas asks the user to sign in".
- `NOT_CONNECTED`: go to "If Chrome blocks the connection".
- `STILL_RUNNING`: run the wait command again.

## Step 5: report

1. Close the tab with `tabs_close_mcp`.
2. Show the user the summary lines exactly as printed, as plain text. Do not add a list of steps that you took.
3. Do not show the full report. Each unit folder keeps it in `.easel/report.txt`.
4. If a line contains `SCALE_NEEDED`, ask the user for their grade scale with `AskUserQuestion`. Offer these options:
   - "1 to 7": `7:85,6:75,5:65,4:50,3:40,2:25,1:0`
   - "HD to F": `HD:85,D:75,C:65,P:50,F:0`
   - "A to F": `A:90,B:80,C:70,D:60,F:0`
   Then run `PY "<kit>/scripts/easel.py" scale --canvas "<CANVAS URL>" --set "<the scale>"`. Then run `PY "<kit>/scripts/easel.py" refresh <UNIT CODES>`. Tell the user that the Grades notes now show the mark needed for each grade.
5. If a line starts with `Needs you:`, tell the user each item in plain words.

## Notes that the student edited

The student owns any note that they changed. Keep it exactly as they left it.

- Do not mention edited notes to the user. Students change notes by hand when their university changes a rule, for example about Gen AI use.
- Do not offer to replace an edited note.
- If the user asks to replace edited notes with the Canvas version, run `PY "<kit>/scripts/easel.py" refresh <UNIT CODES> --reset-edited`. The helper keeps a copy of each edited note in `.easel/backups`.

## If Python is missing

- macOS: run `xcode-select --install`. Tell the user: "A window asks to install the command line developer tools. Click **Install**. It takes about five minutes." Every 60 seconds, run `python3 --version`, up to 15 times.
- Windows: ask the user with `AskUserQuestion`: "easel needs Python. Install it now? About 30 MB, no admin rights needed." If the user agrees, run `winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements`. Then use `py -3` as PY.
- Linux: tell the user to run `sudo apt install python3`, or the command for their package manager. Wait for the user to say that it is done.

## If the browser tools are missing

The Claude in Chrome extension is not enabled in this session.

1. Tell the user: "easel reads Canvas through your Chrome. Type `/chrome`, choose **Enabled by default**, then tell me."
2. If the user does not have the extension, give them this link: https://chromewebstore.google.com/detail/claude/fcoeoabgfenejglbffodgkkbkcdhcgfn
3. The extension works in Chrome, Edge, Brave, Arc, Vivaldi and Opera. It needs a Claude Pro, Max, Team or Enterprise plan.
4. When the user says that it is done, run the ToolSearch call again. If the tools appear, go back to step 3, item 3.
5. If the tools still do not appear, tell the user to start a new chat and run easel again. The helper closes by itself after 30 minutes.

## If Chrome is not connected

1. Claude Code can show its own box called "Claude wants to use your browser". If it appears, tell the user to choose **Install extension** and follow its steps.
2. Otherwise, open the extension page for the user. On macOS run `open "https://chromewebstore.google.com/detail/claude/fcoeoabgfenejglbffodgkkbkcdhcgfn"`. On Windows run `start "" "https://chromewebstore.google.com/detail/claude/fcoeoabgfenejglbffodgkkbkcdhcgfn"`. On Linux run `xdg-open` with the same link.
3. Tell the user: "Click **Add to Chrome**, then open the extension and sign in with your Claude account. If it is already installed, open Chrome."
4. Every 30 seconds, call `tabs_context_mcp` with `createIfEmpty: true`, up to 10 times. When it works, go back to step 3, item 5.
5. If it still fails, tell the user: "Type `/chrome` and choose **Reconnect extension**. If that fails, restart Chrome." Wait for the user, then try once more.

## If Canvas asks the user to sign in

1. Tell the user: "Sign in to Canvas in the Chrome tab that I opened. I will carry on when you are in."
2. Never type a password, a code or any account detail for the user.
3. Every 15 seconds, run `javascript_tool` on the tab with this text: `location.origin`. Do this up to 40 times.
4. When the result equals the CANVAS URL, run the loader again with `javascript_tool`. Then go to step 4.

## If Claude Code stops the browser step

Claude Code's safety check can deny the loader or the viewer script. The denial can name a rule, such as "Browser JS Exfil".

1. Do not run the script again. Do not try another way to reach Canvas.
2. Close the tab with `tabs_close_mcp`.
3. Tell the user: "Claude Code's safety check stopped the browser step. Open a new chat in your notes folder. Run the same /easel command in the new chat."
4. Stop. The helper closes by itself after 30 minutes.

## If Chrome blocks the connection

1. Tell the user: "Chrome is stopping Canvas from reaching easel on this computer. Click the icon to the left of the Canvas address, open **Site settings**, and set **Apps on device** (or **Local network access**) to **Allow**. Then tell me."
2. When the user says that it is done, `navigate` the tab to the CANVAS URL again.
3. Run the loader again with `javascript_tool`. Then go to step 4.

## Rules

- Do not create, edit, move or delete anything in a unit folder yourself. The helper owns `1 Course Info/`, `2 Assessments/`, `3 Weeks/`, `Files/`, `INDEX.md` and `.easel/`. The student owns everything else.
- Send Canvas no request that changes anything.
- Do not use any browser other than the one that the Claude in Chrome tools control.
- If a unit fails, quote its error line to the user. Do not copy Canvas pages by hand.
