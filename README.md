# Job Application Agent

A local Python application for discovering US technical jobs, matching candidate resumes,
filling application forms, requesting only necessary decisions, and emailing an Excel tracker.
The dashboard runs at **http://127.0.0.1:8765**. It is not a hosted website.

## Run

```powershell
./scripts/setup.ps1
./scripts/start.ps1
```

Follow [connection setup](docs/SETUP.md) to configure OpenAI and Gmail, import resumes,
and optionally enable Windows startup. Autopilot starts disabled until credentials are supplied.
Only run one server process. Keep the computer awake, online, and the application running.

## Behavior

- Discovery: public Greenhouse, Lever and Ashby boards; optional Adzuna US search;
  manual import of a job URL plus its full description. Source boards are editable.
- Matching: US eligibility, documented experience, sponsorship restrictions, and resume relevance.
  The supplied `ds` resume slot is intentionally routed to IT/cloud roles; `aiml` covers Data Science.
- Applications: Playwright fills standard HTML controls, native selects, supported custom
  comboboxes, radio groups, file uploads, and recognized multi-page flows.
- Accounts: recognized sign-up forms use the candidate email and a generated password
  saved in the OS credential vault. Existing passwords can be entered in Settings.
- Gmail: read-only inbox access for scoped verification codes and separate send access for
  daily Excel reports. OAuth tokens are stored in the OS vault.
- OpenAI: structured answers grounded in the candidate documents; questions about unknown
  facts or decisions enter review. A model cannot establish facts missing from a resume.
- Major tech companies and subsidiaries enter review before application, using both an
  editable company list and model classification. Approval applies to that job only.
- `Applied` means a post-submission confirmation was observed, or the user recorded explicit
  confirmation. `Needs review` means a decision, missing fact, unsupported control, security
  challenge, or ambiguous submission needs attention. Queued/skipped are pipeline states.
- No blind retries after a submit click or uncertain email send. Job URL deduplication and
  atomic queue claiming prevent ordinary duplicate runs. Equivalent jobs on different URLs
  may still require review; discovery does not promise universal duplicate detection.
- Default schedule: every two hours, at most 25 submission attempts per day; daily report
  at 18:00 America/Los_Angeles. At most 80 model-based fit evaluations per cycle.

## Coverage and limits

This is a working local implementation, **not a guarantee of unattended support for every ATS**.
Live employer submission and Gmail/OpenAI integration need credentials and live validation.
Greenhouse, Lever and Ashby discovery uses their documented public APIs. Application submission
uses the public browser form because employer-owned submission API keys are not candidate keys.
Workday is tenant-specific: basic sign-up, login, form fields, and navigation are supported by
the shared engine, but repeated experience widgets, unusual controls, MFA, verification links,
and CAPTCHAs can require a manual handoff. Codes are supported; arbitrary email links are not clicked.
LinkedIn Easy Apply and Indeed have no dedicated adapter. Their postings can be imported, but
complex or blocked flows go to review. No anti-bot evasion or CAPTCHA solver is included.

Discovery covers configured boards and optional Adzuna pages, not all vacancies on the Internet.
Adzuna defaults to three pages per query from the last 14 days. Google, Apple and Microsoft
postings can be imported directly or discovered through an enabled search provider.
Check source errors in Activity. No model classification or generated prose is infallible.

## Data

`data/` contains the SQLite queue, profile, resumes, browser session, screenshots and reports.
`secrets/`, `.env`, `data/`, and logs are Git-ignored. Never force-add them to a public repository.
The public example profile contains no candidate information. Saved API keys, Gmail refresh
tokens and career-site passwords use the system keyring. Job pages cannot execute model tools.
The server binds to loopback, enforces local hosts and same-origin mutations, and exposes no
remote login. Do not publish this local service to the Internet.

## Tests

```powershell
.venv/Scripts/python.exe -m pytest -q
```

Tests use temporary databases and controlled HTML forms. They exercise confirmation handling,
multi-step forms, missing decisions, deduplication, queue recovery, OTP correlation, formula-safe
Excel export, CSRF controls, and uncertain report delivery. They do not submit to real employers.

## References

- [User's reference video](https://www.youtube.com/watch?v=lq8OaM-SeJo): transcript was unavailable
  during implementation; no claim is made that this reproduces its n8n workflow.
- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Gmail Python OAuth quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python)
- [Gmail sending](https://developers.google.com/workspace/gmail/api/guides/sending)
- [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html)
- [Lever Postings API](https://github.com/lever/postings-api)
- [Ashby public postings](https://developers.ashbyhq.com/docs/public-job-posting-api)
- [Adzuna search](https://developer.adzuna.com/docs/search)

Icons: Lucide, ISC license, bundled locally in `static/`.
