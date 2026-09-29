# Composio / LinkedIn discovery

`LinkedInComposioJobSource` implements the existing `JobSource` interface. It
returns `RawJobPosting` objects and normalizes them into `Job`; use it with
`DiscoveryRunner` alongside `GreenhouseJobSource`. The existing pipeline owns
classification, eligibility, scoring, deduplication, routing and persistence.
No browser, application workflow, submission or confirmation is invoked here.

## Local configuration

Create a project API key in the [Composio dashboard](https://dashboard.composio.dev/).
Add it to the repository's ignored `.env` file, or configure the variable in
PyCharm's Run Configuration. Never commit the actual key:

```dotenv
COMPOSIO_API_KEY=your-project-api-key
COMPOSIO_USER_ID=job-application-agent
```

The user ID is an optional application-local identifier. This adapter calls the
no-auth Composio Search toolkit; it does not use a LinkedIn connected account,
LinkedIn cookies, or credentials from the ChatGPT connector. Composio API calls
may consume account credits. No SDK or CLI installation is required. Existing
`python-dotenv` support is used by the local command entry points.

## Run from PyCharm

From the repository root in the project virtual environment:

```powershell
python -m scripts.smoke_test_composio_discovery --query "software engineer entry level Seattle" --limit 3
```

Or select `scripts/smoke_test_composio_discovery.py` as the script, use the same
parameters, and set the working directory to the repository root. The runner
loads the existing candidate/company/role configuration and creates a temporary
SQLite database. It never modifies the production database or exports a tracker.
Temporary storage is removed on exit. It sends only the search query and public
posting URLs to Composio, not your resume or candidate configuration.

Exit codes: 0 = at least one posting processed, 1 = discovery/API failure,
2 = invalid/missing configuration, 3 = no usable postings (inconclusive).

## Run persistent discovery

After the discovery-only smoke test succeeds, run the persistent boundary from
the repository root:

```powershell
python -m scripts.run_job_discovery `
    --query "software engineer entry level Seattle" `
    --limit 3
```

This command uses `database/jobs.db` as the authoritative store and regenerates
`data/exports/Job_Application_Tracker.xlsx`. If the local dashboard is open, it
will display the refreshed workbook on its next five-second poll.

The command performs discovery, deterministic pipeline processing, persistence,
and Excel export only. It does not open a browser, fill a form, start the
application workflow, submit an application, or confirm submission.

Use `--database` and `--export` to select different persistent output paths.
The result limit is always bounded from 1 through 20. Exit code 0 means the run
completed, 1 means a discovery source failed, and 2 means local configuration or
output setup failed.

## Parsing contract and limits

- One `COMPOSIO_SEARCH_WEB` query and at most one
  `COMPOSIO_SEARCH_FETCH_URL_CONTENT` batch per run; default five pages in the
  adapter, three in the smoke runner, hard maximum twenty.
- REST API: `https://backend.composio.dev/api/v3/tools/execute/{tool_slug}`.
  Toolkit version is pinned to `20260903_00`. Schema changes require review and
  updated contract tests before changing the pin.
- Search citations are preferred; organic results are a fallback. Generated
  search answers and summaries are never parsed as job facts.
- Only HTTP/S LinkedIn `/jobs/view/` pages with numeric posting IDs are accepted.
  Tracking parameters and slug variations share the same canonical ID/URL.
- Title parsing supports `Company hiring Role in Location | LinkedIn` and
  `Role at Company <em dash> Location | LinkedIn Jobs`. A hiring title without
  location is supported with location left unset. Fetched text must contain a
  matching Markdown H1 and the company name. Unrecognized layouts are skipped.
- Explicitly closed postings, failed fetch statuses, non-job pages, and pages
  without corroborating text are skipped. Counts are reported by the smoke run.
- Description is extracted page text, not a generated summary. It may contain
  page boilerplate and is capped at 20,000 characters. Relative dates are not
  guessed; posting date stays unset. Search coverage and posting freshness are
  not guaranteed, and a fetched page may be cached.
- HTTP failures, schema errors and timeouts raise `ComposioDiscoveryError`.
  No automatic retries, broad searches, pagination or account fallback occur.
  Re-run intentionally after resolving rate limits or credentials.

## Verification

```powershell
python -m pytest tests/test_composio_discovery.py tests/test_discovery_base.py tests/test_discovery_runner.py tests/test_greenhouse_discovery.py -q
```

Tests cover response contracts, URL identity, parsing, skipped pages, sanitized
errors, API request shape, and persistence/deduplication through the real pipeline.
Unit tests use synthetic data; successful tests do not establish that a local
Composio key works. Run the live smoke command to verify local account access.

References: [Search toolkit](https://docs.composio.dev/toolkits/composio_search),
[REST execution](https://docs.composio.dev/reference/v3/api-reference/tools/postToolsExecuteByToolSlug).
