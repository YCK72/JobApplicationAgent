# How to use Job Application Agent

## 1. Install and start

In PowerShell, from the repository folder:

```powershell
.\scripts\setup.ps1
.\scripts\start.ps1
```

Setup creates a virtual environment, installs locked dependencies and Chromium, and creates
local data folders. Use `-Python py` with the setup script if you use the Windows Python launcher.
Open **http://127.0.0.1:8765**. Keep the terminal running. On subsequent launches, you can
double-click **Open Job Application Agent.cmd**. Run only one server at a time.

## 2. Complete your candidate profile

Open **Profile & resumes**. Enter your name, email, phone, current location and professional
links. Select your actual US work authorization, future sponsorship requirement and relocation
preference. Enter other preferences and work-authorization details accurately. Save the profile.
Leave unknown facts unspecified rather than entering an assumption.

Under **Resume slot**, choose the role and import a readable PDF:

| Slot | Intended content |
| --- | --- |
| Software engineering | SDE/software developer resume |
| AI / ML | Machine learning and AI resume |
| Data Science | Data Science resume |
| IT / Cloud | IT, support, systems or cloud resume |

You do not need every slot. The agent selects an enabled resume from the documents available.
Uploads must be under 10 MB, at most 20 pages, and contain extractable text. Scanned PDFs need
OCR first. The public repository includes example configuration only, not personal resumes.

Tailoring preserves the original candidate claims and reorders recognized complete sections.
Documents without reliable section headings keep their original layout. Disable tailoring
in Settings if you prefer to submit the original PDF.

## 3. Connect services

**Required:** save an OpenAI API key under Settings. Configure an available compatible model
if needed. API usage is billed separately from the software.

**Optional:**

- **Gmail:** enables supported verification codes/links and daily Excel emails. Follow
  [Gmail setup](docs/SETUP.md#gmail-api); use the same email as your candidate profile.
- **Adzuna:** save an App ID and App Key to add cross-company US searches.
- **Apify:** save a token and configure an actor or dataset source. Actor runs can incur charges.
- **Existing accounts:** save the password for the exact HTTPS career-site hostname.
- **Authenticator MFA:** save an existing account's Base32 seed for supported TOTP. The agent
  does not enroll new authenticators. Do not enter a short, temporary OTP as the seed.

Public employer boards need no discovery credentials. Store credentials in the dashboard
vault fields; never commit them or paste them into issues.

## 4. Configure job sources

Settings contains an editable **Job sources (JSON)** list. Keep the sources you want and use
the company's actual public board slug. For example:

```json
[
  {"provider":"greenhouse","board":"datadog","company":"Datadog"},
  {"provider":"lever","board":"COMPANY_SLUG","company":"Company name"},
  {"provider":"ashby","board":"ramp","company":"Ramp"}
]
```

An existing Apify dataset source:

```json
{"provider":"apify","board":"YOUR_DATASET_ID","company":"LinkedIn"}
```

An automatic Apify actor source:

```json
{
  "provider":"apify_actor",
  "board":"OWNER~ACTOR",
  "company":"LinkedIn",
  "max_items":100,
  "input":{"YOUR_ACTOR_INPUT_FIELD":"YOUR_LINKEDIN_SEARCH_URL"}
}
```

Replace the example input with the actual actor's JSON input from Apify. Output must contain
`applyUrl` or `applicationUrl`, `title` or `jobTitle`, `companyName`, `location`, and
`descriptionText` or `descriptionHtml`. Rows without a direct HTTPS application URL are excluded.
The adapter imports at most 10,000 rows per dataset fetch. Running actors are checked on the
next discovery cycle; ambiguous starts and failed runs stop rather than starting repeated paid runs.

You can also choose **Add job** and enter a company, role, location, application URL and full
description. Importing a posting does not guarantee its application flow is supported.

## 5. Run applications

Set your daily limit, interval, timezone, optional company-review list and tailoring preference.
Choose **Discover jobs** to populate the queue without applying. The play button beside it runs
one application cycle. **Enable autopilot** runs recurring discovery and application cycles.

Autopilot requires a saved profile/email, an enabled imported resume and an OpenAI key.
Gmail is optional. API/provider costs depend on usage; the daily limit counts submission attempts,
not model requests or discovery requests. Your PC must stay awake, online and running the server.

Choose **Pause autopilot** to stop between operations. An already-sent submission cannot be recalled.
Optional Windows sign-in startup is documented in [Connection setup](docs/SETUP.md#scheduling).

## 6. Handle authentication prompts

Supported logins, signup controls, Gmail codes/verification links, and configured TOTP are handled
automatically. For interactive prompts, enable **Show application browser and resume after
interactive security prompts** in Settings and save. Set the handoff timeout as needed.

The browser remains open for the current application while you complete a recognized CAPTCHA,
push/SMS approval or other security prompt. Automation resumes when the prompt clears.
If the timeout expires, inspect the review item. This feature does not automatically solve
CAPTCHAs or evade access restrictions.

## 7. Resolve review items and save answers

Open a **Needs review** row to inspect the reason, job description and screenshot. Enter the
requested answers. Select **Remember these answers for future applications** only when you
want those explicit choices reused. Choose **Approve & queue** to retry on the next cycle.

Minor punctuation and case differences are ignored for saved questions. Negation is preserved;
conflicting answers stop for review. For multiselects, save exact labels separated by semicolons,
such as `Python;SQL`. Job-specific answers take precedence for the same question.

If a submission was attempted, check the employer site first and explicitly confirm it was
not submitted before retrying. If you applied manually, choose **Record submission** and enter
confirmation evidence. **Skip job** removes it from application processing.

The agent requests missing facts and new commitments instead of inventing them.

## 8. Check results and export

- **Applied:** a confirmation was observed or recorded by you.
- **Needs review:** a decision, missing fact, unsupported control, security prompt or uncertain outcome.
- **Queue/In progress:** awaiting or undergoing processing.
- **Skipped:** filtered out or skipped by you; see its reason.

The download button exports an Excel tracker with separate Applied, Needs Review and Pipeline
sheets. Job details expose available screenshots and prepared resumes. **Activity** lists
discovery errors and report delivery. Optional Gmail reports are scheduled while autopilot is enabled.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Autopilot cannot be enabled | Saved candidate email, enabled readable resume, OpenAI key |
| No jobs found | Actual board slugs, configured search sources, Activity errors |
| Form does not advance | Screenshot, required choices, unsupported widgets; inspect before retrying |
| Verification unavailable | Gmail connection, matching profile email, authenticated company message and supported destination |
| MFA does not work | Exact career-site host, existing Base32 seed, supported TOTP settings and system clock |
| HTTP 429 persists | Wait and retry later; no restriction bypass is included |
| Worker/browser already locked | Stop the other server instance; do not run concurrent workers |
| Submission uncertain | Reconcile on the employer site; never retry blindly |

Workday variants, LinkedIn Easy Apply, Indeed and repeated experience widgets require live
validation and can still need manual steps. Tests cover controlled forms, not universal live ATS support.
