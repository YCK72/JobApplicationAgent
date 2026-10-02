# Connection setup

## Gemini and Groq

1. Create a Gemini API key at [Google AI Studio](https://aistudio.google.com/apikey).
2. Save it in Settings > Gemini API key (job filtering).
3. Create a Groq API key at [Groq Console](https://console.groq.com/keys).
4. Save it in Settings > Groq API key (application answers).
5. Keep the filtering model `gemini-3.1-flash-lite` and application model `openai/gpt-oss-20b`,
   or select compatible structured-output models available to your accounts. Save settings.
6. Restart the application after upgrading. API keys are stored in the OS credential vault.

OpenAI API billing is not required. The OpenAI Python SDK is used only as a client for the
Google and Groq endpoints. Free tiers have rate and quota limits; check each provider's console.
Gemini free-tier inputs may be used to improve Google products. Both providers receive the
profile facts and resume text needed for their task. No inbox text is sent to these models.
Never paste keys into GitHub or chat.

## Gmail API

1. In [Google Cloud Console](https://console.cloud.google.com/), create/select a project.
2. Enable the **Gmail API**.
3. Configure the OAuth consent screen / Google Auth Platform. For a personal account, use
   External and add your application email as a test user while the app is in Testing.
4. Create an OAuth client with application type **Desktop app**.
5. Download its client JSON to `secrets/gmail-client.json` inside this project.
6. In the dashboard, click **Settings > Gmail > Connect**. Complete Google's consent in
   your browser using the same email as your local profile. A local callback completes sign-in.
7. The app requests `gmail.readonly` to read verification messages and `gmail.send` to send reports.
   Tokens are stored in your OS credential vault. The app does not delete or mark mail as read.

Google OAuth applications in Testing can have short-lived refresh authorization, requiring
reconnection. For reliable ongoing access, review Google's publishing and verification
requirements for your project and selected Gmail scopes. The app reports refresh failures.

Verification uses messages received after the current application started, addressed to the
profile email, from the platform's configured domain, with aligned passing DKIM/DMARC results
and the company name in the message. Ambiguous codes/links and unsupported
senders need review. No general inbox text is sent to Gemini and Groq.

## Candidate profile

Import current resume PDFs through Profile & resumes before applying. For a fresh clone, copy
`profile.example.json` to `data/profile.json`, enter
the candidate's actual facts, then import PDF files:

```powershell
.venv/Scripts/python.exe -m agent.cli import-resume --kind sde --path 'C:/path/resume.pdf'
.venv/Scripts/python.exe -m agent.cli import-resume --kind aiml --path 'C:/path/ai-resume.pdf'
.venv/Scripts/python.exe -m agent.cli import-resume --kind ds --path 'C:/path/data-science-resume.pdf'
.venv/Scripts/python.exe -m agent.cli import-resume --kind it --path 'C:/path/cloud-resume.pdf'
.venv/Scripts/python.exe -m agent.cli import-resume --kind cv --path 'C:/path/cv.pdf'
```

Kinds control routing: `sde` for software, `aiml` for AI/ML, `ds` for Data Science, `it` for IT/cloud,
and `cv` for research reference. The CV is not submitted automatically.

## Broader discovery

Public boards need no key. Edit their JSON list in Settings, for example:

```json
{"provider":"lever","board":"company-slug","company":"Company Name"}
```

For cross-company US search, create an [Adzuna developer account](https://developer.adzuna.com/)
and enter its App ID and App Key in Settings. Use the exact slug from a company's public board.
The shipped board list is a starting point, not universal search coverage.

## Scheduling

After connections are configured, enable autopilot. A manual Run command processes one cycle
without enabling the recurring schedule. Pause stops between operations; an already-sent
submission cannot be recalled. Email reports are scheduled while autopilot is enabled.

To launch the worker at Windows sign-in:

```powershell
./scripts/install-startup.ps1
```

This creates a task named `JobApplicationAgent` under your Windows account and starts a hidden
Python process at sign-in. The PC must remain awake and connected. The same process serves
the dashboard, performs discovery/applications, and sends daily reports. A local process lock
prevents two workers from using the same queue. No application runs while the computer is off.

## Review

Open an application row to see its reason, posting, and screenshot. Enter requested answers
and select Approve & queue. An attempted submission cannot be retried until you explicitly
confirm it was not submitted. If you completed it manually, Record submission asks for a
confirmation reference and marks it Applied. Do not retry an uncertain submission blindly.

Unknown account passwords can be saved under the exact career-site URL in Settings. Account
creation generates a unique password per career-site hostname and email. The application
does not reset existing passwords. Large-tech approval does not override missing facts,
agreements, unsupported controls or uncertain submission state.

You can also import PDFs and edit candidate facts directly in the dashboard. Gmail is optional; without it, email verification requires review and daily email reports are disabled.

## Verification and MFA

Authenticated email verification links are supported when the link targets the exact current
career-site host and its path identifies a verification, confirmation or activation action.
Tracking redirects, cross-host verification services, password resets, and ambiguous messages
require review. The navigation guard blocks cross-host redirects. Verification tokens are not
written to activity logs or sent to the language model.

For an existing account using SHA-1 TOTP (six digits, 30-second period), enter the career-site URL
and the account's existing Base32 setup seed under Settings > Authenticator MFA. The seed is
stored in the OS credential vault, scoped to the exact hostname and candidate email. The agent
does not enroll new authenticators or obtain seeds from your phone. Other TOTP configurations,
SMS codes, push approvals, passkeys and security keys need an interactive handoff.

Enable Settings > Show application browser to allow a visible browser during an application.
When a recognized security or MFA prompt blocks progress, the worker waits up to the configured
timeout in the same browser session and resumes when the prompt disappears. Complete the
prompt there. This does not solve CAPTCHAs automatically or evade access restrictions.
Autopilot starts disabled until current resumes and credentials are supplied.

## Reusable decisions and richer forms

When resolving a review item, opt into Remember these answers to reuse your explicit choices
on future applications. Formatting differences are ignored, but negation and question wording
are preserved; conflicting saved answers require review. Unprovided candidate facts and new
commitments are never fabricated. For native multiselects, separate exact option labels with
semicolons in a saved answer. Editable text areas and ARIA checkbox/radio groups are supported
by the common engine. Tenant-specific widgets and repeated employment sections still need
live validation; no universal Workday, LinkedIn or Indeed coverage is claimed.

Initial HTTP 429 responses respect a bounded Retry-After delay and allow one retry before any
submission. Repeated rate limits stop for later review. Submission attempts are never blindly
repeated after an uncertain result.


## Gemini filtering and Groq application setup

1. Create a Gemini key at https://aistudio.google.com/apikey and save it in Settings > Gemini API key.
2. Create a Groq key at https://console.groq.com/keys and save it in Settings > Groq API key.
3. Save the separate Gemini filtering and Groq application model settings. OpenAI credentials are no longer used.
4. Restart the application after upgrading. Resume autopilot only after both keys and current resumes are ready.

Gemini evaluates entry-level relevance, US eligibility, sponsorship and fit against your profile.
Groq composes supported application answers and resume section ordering; the browser still executes forms.
Both responses are validated, and candidate facts and commitments are never invented. Provider rate limits
stop the cycle and disable autopilot. Jobs not yet attempted remain queued; uncertain submissions require review.
Free tiers have quotas; Gemini free-tier data may be used to improve Google products. Review provider terms
before sending resumes and profile details.
