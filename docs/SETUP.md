# Connection setup

## OpenAI

1. Create an API key in your OpenAI API account with API billing enabled.
2. Open the local dashboard, Settings, and save it in the OpenAI key field.
   Alternatively run `.venv/Scripts/python.exe -m agent.cli set-key OPENAI_API_KEY`.
3. The default model is `gpt-4.1-mini`. Change the model in Settings if your API account uses
   another Responses/Structured Outputs-compatible model. ChatGPT subscriptions do not supply
   credentials to this standalone application. No keys should be pasted into GitHub or chat.

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
and the company name in the message. Ambiguous codes, link-only verification, and unsupported
senders need review. No general inbox text is sent to OpenAI.

## Candidate profile

The initial installation for the requester already includes the four supplied PDFs in private
local storage. For a fresh clone, copy `profile.example.json` to `data/profile.json`, enter
the candidate's actual facts, then import PDF files:

```powershell
.venv/Scripts/python.exe -m agent.cli import-resume --kind sde --path 'C:/path/resume.pdf'
.venv/Scripts/python.exe -m agent.cli import-resume --kind aiml --path 'C:/path/ai-resume.pdf'
.venv/Scripts/python.exe -m agent.cli import-resume --kind ds --path 'C:/path/cloud-resume.pdf'
.venv/Scripts/python.exe -m agent.cli import-resume --kind cv --path 'C:/path/cv.pdf'
```

Kinds control routing: `sde` for software, `aiml` for AI/ML/Data Science, `ds` for IT/cloud,
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
