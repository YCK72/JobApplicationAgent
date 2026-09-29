# JobApplicationAgent

A safety-first, local Python system for discovering, filtering, scoring, routing, tracking, and assisting with job applications for early-career Software Engineering, AI/ML, Data Science, and IT/Cloud roles.

> **Core principle:** application quality, factual accuracy, deterministic validation, traceability, and human control take priority over application volume.

## Current Project Status

**Branch:** `main`  
**Latest verified full regression:** `1307 passed`
**Most recently completed milestone:** **59C — explicit post-review submission confirmation command**
**Current development milestone:** **60A — resolve discovered listings to supported ATS application targets**

The repository is intentionally not a fully autonomous submission bot. The current architecture fills only explicitly authorized fields and **stops before final submission**.

## Safety Invariants

These rules are architectural requirements, not optional conventions:

1. Never fabricate candidate qualifications, experience, projects, technologies, dates, metrics, publications, certifications, or other facts.
2. Never infer sensitive application answers.
3. Never automatically apply to configured priority/manual companies.
4. Never knowingly submit duplicate applications.
5. Never mark a job `APPLIED` merely because form filling succeeded.
6. LLM output must never directly control Playwright. AI output must become structured data, pass Pydantic validation, and then pass deterministic Python safety checks.
7. Never bypass CAPTCHA, anti-bot controls, human-verification systems, legal attestations, or signatures.
8. External browser mutation is denied by default and requires explicit authorization.
9. Final application submission is not performed by the current application workflow.
10. `APPLIED` requires independent post-review submission confirmation. Ambiguous evidence becomes `SUBMISSION_UNCONFIRMED`.
11. SQLite is the authoritative application state; Excel is the human-facing tracker/report.
12. Credentials, private candidate data, resumes, application answers, databases, browser profiles, logs, and generated private files must stay out of source control.

### Sensitive application questions

Do **not** infer answers involving:

- work authorization
- sponsorship
- visa or immigration status
- citizenship
- race or ethnicity
- Hispanic/Latino status
- gender or sex
- sexual orientation
- disability
- veteran/military status
- criminal/background history
- conflicts of interest
- legal attestations
- electronic signatures
- CAPTCHA or verification prompts

Such questions require an explicitly configured approved answer or human review.

## High-Level Architecture

```text
Job Source
    ↓
Discovery Adapter
    ↓
RawJobPosting
    ↓
Normalization
    ↓
Job
    ↓
Company Routing
    ↓
Deduplication
    ↓
Role Classification
    ↓
Seniority / Eligibility Filtering
    ↓
Location Filtering
    ↓
Fit Scoring
    ↓
Fit Gate
    ↓
Resume Routing
    ↓
Persistence
    ↓
Application Preparation
    ↓
Form Inspection
    ↓
Deterministic Planning
    ↓
Controlled Execution
    ↓
READY_FOR_REVIEW
    ↓
HUMAN REVIEW + MANUAL SUBMISSION
    ↓
Independent Submission Confirmation
```

The controlled application workflow **does not submit**.

## Application Execution Safety Boundary

The intended production execution order is:

```text
Preparation
    ↓
Inspection
    ↓
Deterministic form-plan authorization
    ↓
External target authorization
    ↓
ONLY NOW create execution browser session
    ↓
Navigate to exact authorized URL
    ↓
PlaywrightFieldWriter
    ↓
BrowserFormExecutor
    ↓
Fill authorized fields
    ↓
READY_FOR_REVIEW
    ↓
Close execution browser
    ↓
STOP
```

The execution browser must never open when preparation, inspection, form authorization, or target authorization has already blocked the application.

## Browser Architecture

The project uses:

- Brave Browser
- Playwright
- `BrowserSession`
- `PlaywrightFieldWriter`
- `BrowserFormExecutor`
- `ApplicationExecutionSession`
- `ExternalExecutionGuard`

Inspection and execution are intended to use **separate browser lifecycles**.

`ApplicationExecutionSession` owns one controlled execution lifecycle:

```text
create BrowserSession
→ start
→ navigate exact target
→ bind PlaywrightFieldWriter
→ expose BrowserFormExecutor
→ controlled execution
→ cleanup
```

It does **not**:

- inspect forms
- decide answers
- authorize answers
- authorize external targets
- submit
- confirm submission
- mark jobs `APPLIED`

## Priority / Manual Companies

High-value companies are routed to manual application rather than automatic form execution.

The configurable list includes companies such as:

- Microsoft
- Amazon
- Apple
- Google
- Meta
- NVIDIA
- Tesla
- OpenAI
- Anthropic
- Netflix
- Salesforce
- Adobe
- Oracle
- Cisco
- Intel
- AMD
- Qualcomm
- Uber
- Airbnb
- LinkedIn
- Stripe
- Databricks
- Snowflake

The source of truth is configuration (for example `config/company_rules.yaml`), not hard-coded checks scattered through Python modules.

For a manual company:

```text
Discover
→ Score
→ Store
→ Preserve direct application URL
→ Manual Queue
→ STOP
```

Do not autofill, upload a generic resume, submit, or mark it applied.

## Resume Routing

Routine eligible applications route to specialized base resumes:

```text
SDE          → data/resumes/sde_resume.pdf
AI_ML        → data/resumes/aiml_resume.pdf
DATA_SCIENCE → data/resumes/data_science_resume.pdf
IT           → data/resumes/it_resume.pdf
```

Priority/manual opportunities intentionally do not automatically select a resume.

Actual personal resume PDFs are private and are **not committed**.

## Application Lifecycle

Important states include:

```text
NEEDS_APPLICATION
READY_TO_APPLY
FORM_STARTED
NEEDS_REVIEW
SUBMISSION_UNCONFIRMED
APPLIED
```

A successful controlled fill ends at:

```text
READY_FOR_REVIEW
```

Workflow success is **not** evidence of submission.

Submission confirmation is a separate service. Only independently supplied confirmation evidence may transition an application to `APPLIED`.

## Technology Stack

- Python 3.13.x (project currently developed with Python 3.13.5)
- PyCharm
- Brave Browser
- Playwright
- SQLite
- OpenPyXL
- YAML
- Pydantic
- pytest
- Git / GitHub

Development has primarily been performed on Windows/PowerShell.

## Getting Started

### 1. Clone the repository

```powershell
git clone https://github.com/YCK72/JobApplicationAgent.git
cd JobApplicationAgent
```

### 2. Create a virtual environment

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If Python 3.13 is unavailable, install a compatible project Python version before proceeding rather than silently changing project dependencies.

### 3. Install dependencies

Use the dependency file present in the repository:

```powershell
pip install -r requirements.txt
```

If Playwright browser/runtime setup is required, follow the project's existing Playwright configuration. Production browser sessions target Brave rather than changing the architecture to bundled Chromium without review.

### 4. Verify Brave

The original development machine uses:

```text
C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe
```

Do not hard-code that path for every developer. Use the existing Brave discovery/session abstractions.

### 5. Create private local configuration

Private configuration is intentionally excluded from Git.

Examples include:

```text
config/candidate.yaml
config/application_answers.yaml
.env
```

Do not ask another contributor to commit the owner's private files. Create local development-safe equivalents/templates as needed.

### 6. Private resumes

Real candidate resume PDFs are intentionally ignored:

```text
data/resumes/*.pdf
```

Tests should use fixtures, temporary files, or non-sensitive synthetic data where possible.

### 7. Run the test suite

```powershell
pytest -q
```

The latest verified result is:

```text
1307 passed
```

A different count after later commits is normal. Never claim a test count without actually running the suite.

### 8. Open the application dashboard

Generate or refresh the Excel tracker, then start the local read-only dashboard:

```powershell
python -m app.dashboard.server --open-browser
```

The dashboard reads `data/exports/Job_Application_Tracker.xlsx` and refreshes
the browser view every five seconds. It does not edit the workbook or change
application state. See [docs/dashboard.md](docs/dashboard.md) for PyCharm and
custom-path instructions.

### 9. Discover jobs into the live tracker

After configuring `COMPOSIO_API_KEY`, run bounded discovery into the persistent
database and regenerate the workbook used by the dashboard:

```powershell
python -m scripts.run_job_discovery `
    --query "software engineer entry level Seattle" `
    --limit 3
```

This command does not start the application workflow or open an execution
browser. See [docs/composio_discovery.md](docs/composio_discovery.md) for its
configuration, output, and exit-code contract.

### 10. Prepare one exact job for human review

List persisted jobs that are eligible to enter the controlled application
workflow:

```powershell
python -m scripts.run_application --list-eligible
```

Preview one exact job without starting browser inspection:

```powershell
python -m scripts.run_application --job-id 123
```

After reviewing that output, explicitly authorize inspection and field mutation
for that job:

```powershell
python -m scripts.run_application --job-id 123 --allow-external
```

A successful run stops at `FORM_STARTED` for human review and manual
submission. It never clicks Submit or records `APPLIED`. See
[docs/application_launcher.md](docs/application_launcher.md) for supported ATS
and lifecycle details.

### 11. Record the post-review submission result

After manually reviewing and submitting an application, record independently
confirmed success with evidence:

```powershell
python -m scripts.record_submission `
    --job-id 123 `
    --submitted `
    --confirmed `
    --evidence "Portal displayed confirmation number 456"
```

If submission was attempted but success could not be confirmed, omit
`--confirmed`. The command records `SUBMISSION_UNCONFIRMED` instead of
`APPLIED`. See
[docs/submission_recording.md](docs/submission_recording.md) for the complete
contract.

## Useful Focused Tests

For the current execution-browser work:

```powershell
pytest `
    tests/test_application_execution_session.py `
    tests/test_application_workflow.py `
    tests/test_browser_manager.py `
    tests/test_playwright_form_writer.py `
    tests/test_browser_form_executor.py `
    -q
```

At checkpoint `e688997`, this set produced:

```text
168 passed
```

## Current Development Handoff

### Completed immediately before this handoff

Milestone 58C.1 introduced:

```text
app/applications/execution_session.py
tests/test_application_execution_session.py
```

`ApplicationExecutionSession` now owns controlled browser creation, navigation, writer binding, executor creation, and cleanup.

Milestone 58C.2B extended `ApplicationWorkflow` so it can use an execution-session factory while preserving direct `BrowserFormExecutor` injection for isolated tests.

Verified checkpoint:

```text
e688997 Add controlled application execution session
```

### Completed — Milestone 58C.2C

Production composition now uses a lazy `ApplicationExecutionSession` factory
instead of requiring a pre-bound `BrowserFieldWriter`.

The old production shape is conceptually:

```text
build_application_workflow(..., writer=...)
→ BrowserFormExecutor(writer)
→ ApplicationWorkflow(browser_executor=...)
```

The production shape is:

```text
build_application_workflow(
    ...,
    browser_session_factory=...
)
→ execution_session_factory(target_url)
→ ApplicationExecutionSession(
       target_url=target_url,
       browser_session_factory=browser_session_factory,
   )
→ ApplicationWorkflow(
       execution_session_factory=...
   )
```

The production execution browser is created **only after** form authorization
and target authorization succeed.

### Verified 58C.2C safety contract

The composition tests prove that:

1. Building the workflow does not launch Brave.
2. Inspection sessions remain lazy.
3. Execution sessions are created only when execution reaches the authorized boundary.
4. Inspection and execution receive separate `BrowserSession` instances.
5. Blocked form authorization never creates the execution session.
6. Blocked external authorization never creates the execution session.
7. Execution-session startup/navigation failure becomes a fail-closed workflow result.
8. Execution cleanup occurs on successful execution.
9. Execution cleanup occurs on execution failure.
10. Workflow completion remains `READY_FOR_REVIEW`; it never becomes `APPLIED`.
11. No production composition path authorizes submission.

Inspect the current `tests/test_application_composition.py` before implementing this change.

## Development Workflow

Work incrementally and preserve existing safety boundaries.

For each meaningful change:

```text
1. Inspect current implementation.
2. Explain the architectural layer being modified.
3. Write/modify focused tests first when practical.
4. Confirm RED for a new contract.
5. Implement the smallest reliable change.
6. Run focused tests.
7. Run adjacent regression tests.
8. Run the full suite.
9. Run git diff --check.
10. Inspect git status --short.
11. Stage explicit files only.
12. Commit only after verification.
```

### Never use

```powershell
git add .
```

Stage explicit files:

```powershell
git add `
    app\path\file.py `
    tests\test_file.py
```

### Before a checkpoint commit

```powershell
pytest -q
git diff --check
git status --short
```

Then inspect the diff and commit only the intended files.

## Git Collaboration

The main remote is:

```text
https://github.com/YCK72/JobApplicationAgent.git
```

Recommended collaborator workflow:

```powershell
git checkout main
git pull --ff-only origin main
git checkout -b feature/<short-description>
```

Example:

```powershell
git checkout -b feature/58c-production-execution-session
```

Commit focused changes:

```powershell
git status --short
git diff --check
git add <explicit-files>
git commit -m "Integrate production execution session"
git push -u origin feature/58c-production-execution-session
```

Open a pull request rather than having multiple developers independently push unfinished work directly to `main`.

Before starting new work:

```powershell
git checkout main
git pull --ff-only origin main
```

Before opening a PR:

```powershell
pytest -q
git diff --check
git status --short
```

## Source-Control Privacy

Never commit:

```text
.env
.venv/
config/candidate.yaml
config/application_answers.yaml
data/resumes/*.pdf
personal databases
SQLite files containing application/candidate data
browser profiles/sessions
logs containing application information
generated private files
API keys or tokens
temporary inspection files such as step58*.txt
```

If a secret is accidentally committed, do not merely delete it in a later commit. Treat it as compromised, rotate it, and clean the Git history appropriately.

## Testing Philosophy

Tests are part of the safety architecture.

Important categories include:

- company routing
- duplicate prevention
- role classification
- seniority/eligibility filtering
- fit gating
- resume routing
- application preparation
- form inspection
- sensitive-question blocking
- deterministic form planning
- select/radio/checkbox handling
- file upload authorization
- external target authorization
- browser target revalidation
- execution-session cleanup
- workflow failure containment
- submission-confirmation separation
- persistence/lifecycle transitions

Do not weaken an existing test merely to make a new implementation pass unless the underlying contract was deliberately changed and reviewed.

## Browser / Form Rules

Browser actions must be deterministic and narrowly authorized.

The controlled writer/executor may handle supported operations such as:

- safe text fields
- native select controls
- explicitly authorized radio options
- explicitly authorized checkbox state
- authorized resume upload

Custom or ambiguous controls must fail closed or require review.

The browser executor revalidates the target URL and must block unexpected navigation.

No arbitrary clicking, arbitrary keyboard control, verification bypass, or submission belongs in the field-execution layer.

## Error Handling

Runtime boundaries should fail closed.

Unexpected workflow exceptions become `FAILED` results rather than being mistaken for successful preparation.

Batch processing isolates per-job failures so one unexpected application failure does not automatically terminate processing of unrelated jobs.

Cleanup code should be idempotent and safe after partial browser startup.

## Submission Confirmation

Submission tracking is intentionally independent from form filling.

Conceptually:

```text
READY_FOR_REVIEW
      │
      │ human reviews + manually submits
      ▼
Independent confirmation
      │
      ├── confirmed success → APPLIED
      ├── uncertain result  → SUBMISSION_UNCONFIRMED
      └── no submission     → no lifecycle advance
```

**Browser filling success is not submission confirmation.**

## Contributor Checklist

Before changing code:

- [ ] Pull latest `main`.
- [ ] Create a feature branch.
- [ ] Read this README.
- [ ] Identify the module that owns the behavior.
- [ ] Read existing tests for that module.
- [ ] Preserve safety invariants.
- [ ] Do not use private candidate data in tests.

Before committing:

- [ ] Focused tests pass.
- [ ] Adjacent regression tests pass.
- [ ] Full suite passes for checkpoint-worthy work.
- [ ] `git diff --check` is clean.
- [ ] `git status --short` contains only intended changes.
- [ ] No secrets/private files are staged.
- [ ] Files are staged explicitly.
- [ ] Commit message describes one coherent milestone.

Before opening a PR:

- [ ] Rebase/merge latest `main` as agreed by maintainers.
- [ ] Resolve conflicts without deleting safety checks.
- [ ] Run the full test suite again.
- [ ] Explain architectural changes in the PR.
- [ ] State exactly which tests were run.
- [ ] Call out any new configuration/dependencies.
- [ ] Confirm no automatic final submission was introduced.

## Where to Start as a New Contributor

If you are joining the project at checkpoint `e688997`:

1. Clone the repository.
2. Create `.venv`.
3. Install dependencies.
4. Run `pytest -q`.
5. Read:
   - `app/applications/workflow.py`
   - `app/applications/execution_session.py`
   - `app/applications/composition.py`
   - `app/applications/execution_guard.py`
   - `app/applications/browser_form_executor.py`
   - `app/browser/manager.py`
   - `app/browser/playwright_form_writer.py`
6. Read the corresponding tests.
7. Create a feature branch.
8. Continue with the current milestone shown at the top of this README.
9. Do not redesign completed layers unless a verified defect requires it.

## Project Direction

The near-term MVP endpoint is:

```text
discover
→ normalize
→ filter
→ score
→ route
→ choose verified resume
→ inspect eligible application
→ deterministically plan safe answers
→ authorize exact target
→ open controlled execution browser
→ fill authorized fields
→ upload correct resume
→ stop before submit
→ human reviews/submits
→ independently record result
```

The goal is not maximum automation. The goal is a reliable, auditable system that saves time while preserving human control over consequential application decisions.
