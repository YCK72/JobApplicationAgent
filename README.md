# Job Application Agent

A local application that discovers entry-level US software engineering, AI/ML, Data Science,
and IT jobs, checks candidate fit, prepares resumes, fills supported application forms,
and tracks confirmed submissions. A review queue handles missing facts and unsupported flows.

The dashboard runs at **http://127.0.0.1:8765**. Automation starts disabled.

## Quick start on Windows

Install Python 3.11 or newer and Git, then open PowerShell:

```powershell
git clone https://github.com/YCK72/JobApplicationAgent.git
cd JobApplicationAgent
.\scripts\setup.ps1
.\scripts\start.ps1
```

If Python is available through the Windows `py` launcher instead of `python`, run
`.\scripts\setup.ps1 -Python py`. If PowerShell blocks these scripts, use a process-scoped
execution policy for the current terminal: `Set-ExecutionPolicy -Scope Process Bypass`.

Open the dashboard, save your actual candidate facts, import current resume PDFs, and save
an OpenAI API key. Configure sources and limits, then run a cycle or enable autopilot.
After initial setup, you can also launch **Open Job Application Agent.cmd**.

See **[How to use](HOW_TO_USE.md)** for the complete workflow and
**[Connection setup](docs/SETUP.md)** for credentials, Gmail, MFA, and Windows startup.

## Features

| Stage | Implementation |
| --- | --- |
| Discovery | Public Greenhouse, Lever and Ashby boards; optional Adzuna US search, Apify datasets and resumable actor runs; manual job import |
| Fit | Entry-level filtering, US eligibility, documented skills/experience and candidate-specific sponsorship requirements |
| Resumes | Software, AI/ML, Data Science and IT slots; extractive tailoring reorders complete sections without generating new candidate claims |
| Applications | Supported HTML inputs, file uploads, native selects/multiselects, custom comboboxes, editable text and ARIA checkbox/radio groups |
| Accounts | Recognized signup/login forms; passwords stored in the OS credential vault |
| Verification | Correlated authenticated Gmail codes and same-host verification links; redirects inspected before following |
| MFA | Candidate-configured SHA-1 TOTP, six digits and a 30-second period |
| Handoff | Optional visible browser waits for a recognized security/MFA prompt to clear, then resumes the same application |
| Decisions | Job-specific answers and opt-in reusable answers; missing facts or new commitments require review |
| Tracking | SQLite queue, attempt history, confirmation screenshots, prepared resumes and formula-safe Excel exports; optional Gmail reports |

Defaults: every two hours, up to 25 submission attempts per day, up to 80 model fit evaluations
per cycle, and an optional daily email report at 18:00 America/Los_Angeles.

## Coverage and limitations

Discovery covers configured sources, not every vacancy in the US. The supplied employer-board
list is a starting point. Application forms use a shared browser engine: Workday tenants,
LinkedIn Easy Apply, Indeed, repeated employment/education sections, and unfamiliar widgets
can require review. Recognized navigation labels do not establish complete platform support.

CAPTCHAs are not solved automatically, and access restrictions are not bypassed. SMS/push
approvals, passkeys, security keys and unsupported MFA configurations require intervention.
Email verification links must target the exact current career-site host; tracking services,
cross-host links, password resets and ambiguous messages are excluded.

Only a site-confirmed submission or an explicit user confirmation becomes **Applied**.
The agent never blindly repeats an uncertain submission. It cannot invent missing facts,
guarantee the correctness of model answers, or guarantee unattended operation on every ATS.
Live employer submissions and credentialed integrations still require validation.

## Local data and credentials

`data/` holds the profile, resumes, SQLite database, browser session, screenshots and reports.
`.env`, `data/`, `secrets/`, logs and virtual environments are excluded from Git. API keys,
OAuth refresh credentials, career-site passwords and TOTP seeds use the operating system
credential vault. Candidate documents are provided to the configured model for fit and answers;
general inbox contents and verification tokens are not sent to it.

The server binds to loopback and checks request origins. Keep it local; it has no remote
authentication. The computer must remain awake, online, and running the application.

## Development and tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Tests use temporary data and controlled forms. They cover submission confirmation,
duplicate protection, queue recovery, remembered answers, OTP/link correlation, TOTP test vectors,
redirect restrictions, browser handoff, richer controls, resume preparation and Excel safety.
They do not submit applications to real employers.

## Reference workflow

The [reference video](https://www.youtube.com/watch?v=lq8OaM-SeJo) discovers jobs, checks relevance,
prepares resumes and writes a tracker. This implementation uses Python, local PDFs, SQLite
and Excel instead of n8n and Google Docs/Sheets, and extends that workflow with browser submission.

API references: [Greenhouse](https://docs.greenhouse.io/job-board.html),
[Lever](https://github.com/lever/postings-api),
[Ashby](https://developers.ashbyhq.com/docs/public-job-posting-api),
[Adzuna](https://developer.adzuna.com/docs/search),
[Apify](https://docs.apify.com/api/v2/actors-runs-post),
[Gmail](https://developers.google.com/workspace/gmail/api/quickstart/python),
and [TOTP](https://www.rfc-editor.org/rfc/rfc6238).

Icons: Lucide, ISC license; bundled license in `static/LUCIDE-LICENSE`.
