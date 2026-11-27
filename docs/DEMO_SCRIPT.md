# Demo video script: pallets/click (about 6 minutes)

The video shows the pipeline end to end: read click, make 5 tasks, open one, run Harbor in Docker, try to cheat the
checker. Every check runs live. The AI answers were saved earlier, and the narration says so.

## Before recording

1. In PowerShell, open Ubuntu, then go to the project folder (a folder on drive C is under `/mnt/c/`):

   ```
   wsl -d Ubuntu-24.04
   ```

2. Run the setup once (about 7 minutes, needs Docker and internet). It must end with `ready to record`.

   ```
   bash scripts/demo.sh setup
   ```

3. Hide your user and computer name, make the text large (Ctrl and +), and make the window wide:

   ```
   PS1='$ '; clear
   ```

4. Open slide 2 of the solution deck for the opening picture.
5. Do one full practice run. Close notifications, mail and other tabs.

To record screen and voice on Windows 11, Clipchamp (screen and camera recording) is one option.

## The script

Waiting times were measured on the development laptop. Keep talking while commands run.

| Time | On screen | Command | Wait |
|---|---|---|---|
| 0:00 | Slide 2 | | |
| 0:20 | Read the repository | `bash scripts/demo.sh read` | 8 s |
| 0:50 | Make 5 tasks | `bash scripts/demo.sh generate` | 80 s |
| 2:20 | Open one task | `bash scripts/demo.sh task` (Enter twice) | none |
| 3:05 | Harbor in Docker | `bash scripts/demo.sh harbor` | 95 s |
| 4:50 | Try to cheat | `bash scripts/demo.sh cheat` | 30 s |
| 5:30 | Results and limits | `bash scripts/demo.sh results` | none |

### 0:00 The problem

> "Coding exams for AI are hard to make fair. A task can be unclear, or its tests can accept broken code. TaskForge
> makes new feature tasks from a real codebase and rejects any task it cannot prove. Here it is running on
> pallets/click, one of the three starting repositories."

### 0:20 Read the repository

> "It reads click at release 8.5.1, one exact commit. Before making anything, it checks that click's own 2,434 tests
> pass."

Point at `commit` and `baseline: PASS`.

### 0:50 Make 5 tasks

Start the command, then talk while the tasks appear one by one.

> "Now it makes five tasks from different feature recipes, some of them combined. The AI is Claude Sonnet. Its ten
> answers were saved earlier, so anyone can repeat this without a key, but every check you see is running now.
>
> Each task must earn four proofs. The new tests fail on the original click. They pass with the reference solution,
> three times in a row. All existing tests still pass. And the tests must catch deliberately broken copies of the
> solution. The checker never asks an AI."

When it finishes, point at `accepted 5 of 5` and the variation score.

> "All five are accepted, and they differ in behaviour, not only in names."

### 2:20 Open one task

First screen, the files:

> "Each task is a Harbor folder: the instruction, a Dockerfile, the reference solution and the tests."

Press Enter. Second screen, the requirements:

> "The AI being tested sees only the instruction, with numbered rules that can each be tested."

Press Enter. Third screen, the solution:

> "Here is the heart of the solution: click's file type can now refuse a dash and demand a real file."

### 3:05 Harbor in Docker

> "Now the organisers' own checks, with Harbor in Docker. First the nop agent, which changes nothing. The reward must
> be zero."

While the first run finishes, continue:

> "The tests are not inside the image. They are copied in only for grading, and the grader first restores click's old
> tests, so editing them cannot raise a score."

Point at the yellow `reward (nop): 0.0`.

> "Then the oracle agent applies the reference solution. The reward must be one."

Point at `reward (oracle): 1.0`.

### 4:50 Try to cheat

> "Last, I damage this task on purpose. Tests that already pass: rejected. A broken solution: rejected. Tests with
> their checks removed: rejected, because they catch none of the planted bugs."

### 5:30 Results and limits

> "For all five tasks, all ten Harbor runs gave the required score.
>
> The limits: one of fifteen damaged copies was still accepted, because a planted bug that crashes the test code counts
> as caught. We have not yet had a separate AI solve the click tasks from their instructions. And Harbor was run on one
> computer. Thank you."

## Checklist

- The organisers had not stated a length or format when this was written. Check the submission page. To shorten the
  video, speed up the waiting parts in an editor and write "sped up" on screen.
- No user name, file path, key, other tab or notification is visible.
- The code on GitHub is the same code you recorded.
- Upload to Google Drive, set **General access** to **Anyone with the link** as **Viewer**, and open the link in a
  private window to test it.

## If a step fails while recording

Stop, run the step again, and cut the failed part out. If Harbor cannot run, show `bash scripts/demo.sh results` and say
that it is the saved run from 27 November 2026 (`evidence/click/harbor_docker.json`).
