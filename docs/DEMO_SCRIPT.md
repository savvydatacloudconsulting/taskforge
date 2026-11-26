# Demo video script (about 3 minutes)

Recorded entirely on the local web page. It needs no API key and no internet connection.

Start it in a terminal in the project folder, then open <http://localhost:8765> (press Ctrl+F5 once):

```
taskforge ui
```

The waiting times below were measured on a Windows laptop. Keep talking while checks run, and do one practice run first.

| Time | On screen | Wait |
|---|---|---|
| 0:00 | The top of the page | |
| 0:20 | Step 1: repository and recipes | a few seconds |
| 0:35 | Make the exam, then steps 2 to 6 | about 14 s |
| 1:30 | Try to cheat the checker | 4 s, then 14 s |
| 2:10 | The retry example | about 17 s |
| 2:40 | Reports, limits, close | |

## 0:00 – The problem (20 s)

Show the title, **TaskForge: Exam Maker for Code**.

> "Coding exams for AI are hard to make fair. A task can be unclear, or its tests can pass broken code. TaskForge turns a
> real codebase into new exams, and rejects any exam it cannot prove is fair."

## 0:20 – Read the repo and pick a recipe (15 s)

1. In **Who writes the exam?** choose **Any AI chat**. The ten recipes appear. Point at two of them.
2. Switch back to **Recorded example (works offline)**. Leave **shop: Time-windowed promotion applied at checkout** selected.
3. Point at the facts under the boxes: language, version, number of files, tests passing.

> "It reads the repository at one exact version and runs its tests. Then we pick a recipe, or combine two. With any AI
> chat you can copy and paste, so no key is needed. For this video the AI's reply was saved earlier, but every check you
> see is running now."

## 0:35 – Make the exam (55 s)

Click **Make the exam**. Scroll slowly through the steps as they fill in.

- **Step 2, the feature request:** show the numbered requirements.
  > "The exam question, in plain words, with exact rules."
- **Step 3, the correct answer and the tests:** show the green added lines, then one test.
- **Step 4, three checks:** wait for each PASS.
  > "The new tests fail on the original code. They pass with the answer, three times in a row. And all the old tests still
  > pass."
- **Step 5, break the answer on purpose:** show the table and the bar.
  > "We plant small bugs in the answer. These tests caught 10 of 12. At least 60% is required. The AI plays no part in
  > these checks."
- **Step 6, the saved package:** show the **ACCEPTED** banner and `task.toml` with the repository version.

## 1:30 – Try to cheat the checker (40 s)

Scroll to the bottom.

1. Click **A broken solution** (about 4 s).
   > "I plant a bug in the answer. Check 2 fails, so the exam is rejected."
2. Click **Tests with the assertions removed** (about 14 s).
   > "Now the tests run the code but check nothing. The three checks still pass, so those alone would be fooled. The
   > planted bugs expose it: only 3 of 12 caught. Rejected."

This second result is the strongest moment of the demo. Pause on the red **FAIL** and the banner.

If there is time, **Tests that already pass** is rejected at check 1.

## 2:10 – A failed first attempt (30 s)

1. Scroll to the top. In **Recorded exam** choose **library: Escalating tiered late fines for overdue returns**.
2. Click **Make the exam** (about 17 s).
3. In step 6, show the history line: attempt 1 failed `passes_after`, attempt 2 was accepted.

> "A second repository. The AI's first answer was wrong: its own solution and tests disagreed. The checker caught it,
> sent back the failing output, and the second attempt passed."

## 2:40 – Results, limits and close (20 s)

Click **Solver check: shop** at the top (it opens in a new tab).

> "A different AI run saw only each question, never the tests or the answer, and solved all 8. It is the same model family
> that wrote them, so other systems would probably score lower. So far we have tested on small example repositories, and
> the planted-bug check works for Python only. Thank you."

## Checklist before recording

- Zoom the browser to about 125% so the text is readable in the video.
- Step 6 shows the full folder path on your computer, which usually includes your user name. Scroll past it, blur it, or
  run the project from a neutral folder such as `C:\taskforge`.
- No `.env`, keys, other tabs or notifications are visible.
- The tests pass (`evidence/pytest.txt`).
- Upload as unlisted and open the link while logged out. The organisers had not stated a required length or format when
  this was written, so check the submission portal.

## If the page fails during recording

The same proof works in the terminal: `taskforge controls` accepts one good task and rejects six bad ones (about a
minute).
