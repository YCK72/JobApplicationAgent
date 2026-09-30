# Windows desktop application

The Windows build starts the local dashboard without a terminal window. Double-click:

```text
dist\JobApplicationAgent\JobApplicationAgent.exe
```

Keep the complete `dist\JobApplicationAgent` folder together. The executable starts a loopback-only server on `127.0.0.1:8765` and opens the dashboard in Brave. If Brave is unavailable, it uses the Windows default browser.

The first launch creates a private SQLite database and Excel tracker inside the executable folder. An existing workbook is never replaced during startup. Discovery credentials are loaded from the nearest `.env` file, including the repository `.env` when the executable remains in the default `dist` folder.

## Search and prepare

1. Enter a request such as `entry level software engineer in Seattle`.
2. Select a bounded result count and choose **Search jobs**.
3. The discovery pipeline verifies LinkedIn availability, removes closed postings, deduplicates jobs, applies candidate eligibility and sponsorship rules, scores fit, and refreshes the tracker.
4. If the search returns eligible automatic applications, read and select the batch authorization, then choose **Prepare eligible applications**.

Each eligible application receives its own fresh preview authorization. Supported forms are filled and left open for review. Applications that require an account, CAPTCHA, an unsupported step, or an unanswered sensitive question stop and remain in the review queue.

The desktop application does not click the final Submit button. After reviewing and submitting an application yourself, use **Record result** in the dashboard to record independently observed evidence.

## Rebuild

From the project virtual environment:

```powershell
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean JobApplicationAgent.spec
```

PyInstaller produces the application folder under `dist`. Build output and private runtime data remain excluded from Git.
