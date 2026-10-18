# Email Composer

Email Composer is a standalone local multi-agent app in the `GTM-Engineering` repository. It uses the existing [`researcher-agent`](../researcher-agent/) as the first stage, then runs three specialist agents to create a source-grounded sales outreach campaign for a demo product: the **CRM PII Exposure Scanner**. It can use HubSpot read-only CRM data to select an associated recipient and link to that contact's HubSpot record for the user to send the reviewed draft.

## Agent workflow

1. **Company Researcher** — reuses the existing company research agent, Serper search, webpage scraper, and seven-day SQLite cache.
2. **Account Strategist** — chooses a plausible buyer persona and a clearly labeled account hypothesis from public research.
3. **Email Copywriter** — writes three distinct first-touch email drafts, each tied to supplied research URLs.
4. **Quality Reviewer** — reviews all three drafts for unsupported claims, word count, source provenance, and a low-pressure question CTA.

The app performs extra deterministic checks after the reviewer: exactly three distinct drafts, trusted source URLs, a 100-word maximum, a question in each body, and selected unsupported exposure/breach/legal-violation claims. AI review is not a guarantee of correctness.

## Privacy and human review

- This is a portfolio/demo product concept; it reads company and contact data from HubSpot only to find and select a recipient. It does not scan CRM fields.
- HubSpot contact names, email addresses, and job titles are not sent to Gemini. Drafts are generated from public company research.
- Public company research cannot prove that a company exposed personal information, had a breach, or violated a law. The workflow must present product fit as a question or hypothesis, never as a finding.
- Do not enter customer records, real PII, credentials, or confidential prospect information.
- Company research webpages are treated as untrusted input; their contents are facts to evaluate, not instructions to obey.
- The app never sends email. After review, copy the draft and open the selected HubSpot contact record to send it from HubSpot yourself. Verify sources, check legal/privacy claims, and approve each message.
- HubSpot access is OAuth with read-only company/contact scopes. OAuth tokens stay in the running local process and are discarded when the app stops; reconnect after a restart. Do not expose this local demo publicly.
- Use your own Gemini and Serper API keys. API requests may incur charges or use quota.

## Run locally

From the `GTM-Engineering` repository root, open PowerShell and create one
shared root-level environment file first:

```powershell
Copy-Item .env.example .env
notepad .env
```

Add your Gemini and Serper API keys to the root `.env`. To enable HubSpot, create
a HubSpot OAuth app, configure the redirect URL
`http://localhost:5001/hubspot/callback`, and grant the read scopes
`crm.objects.companies.read` and `crm.objects.contacts.read`. Add the OAuth
client ID and secret to the same root `.env`:

```dotenv
HUBSPOT_CLIENT_ID=your-oauth-client-id
HUBSPOT_CLIENT_SECRET=your-oauth-client-secret
HUBSPOT_REDIRECT_URI=http://localhost:5001/hubspot/callback
FLASK_SECRET_KEY=your-random-secret
```

Generate a local session secret with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
Never commit the real values. Then set up the Email Composer:

```powershell
cd "email composer"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python webapp.py
```

Open [http://127.0.0.1:5001](http://127.0.0.1:5001). Stop the server with
`Ctrl+C`. The existing researcher web app continues to use port 5000. Both apps
load their shared credentials and Gemini configuration from the repository-root
`.env`. It is excluded from Git; do not commit or share it.

PowerShell activation alternative if script execution is restricted:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

The standalone folder reuses Python modules from `researcher-agent` and a
shared Gemini retry helper from the repository root. Keep this layout:

```text
GTM-Engineering/
├── .env.example            # Shared key/config template; safe for Git
├── shared_gemini.py        # Shared Gemini pacing and temporary-error retry
├── researcher-agent/
└── email composer/
```

In the app, connect HubSpot, enter a company domain, find and select an associated
contact, and generate a campaign. The app rechecks the selected contact belongs
to that company. Review the draft, copy it, open the contact in HubSpot, and
send it using your connected HubSpot inbox. Sending is always a deliberate action
inside HubSpot; the app cannot send on your behalf.

The default Gemini pacing is 12.5 seconds between requests. After a fresh
company-research run, Email Composer waits 60.5 seconds before starting its
three specialist calls to accommodate common free-tier per-minute quotas. It
also retries temporary 5xx service errors up to three times with exponential
backoff. These values are configurable in the root `.env`; generation may take
a few minutes on rate-limited plans.

## Test

Run the offline workflow tests without making Gemini or Serper requests:

```powershell
python -m unittest discover -s tests -v
```

## Project files

- `.env.example` and `.env` — shared repository-root config; the real `.env` is ignored.
- `../shared_gemini.py` — shared request pacing and temporary-service retry helper.
- `webapp.py` — separate Flask app on port 5001.
- `outreach.py` — sequential orchestration, structured Gemini calls, and deterministic safeguards.
- `hubspot_client.py` — read-only company/contact lookup and contact record links.
- `campaign_models.py` — Pydantic schemas for strategy and reviewed email drafts.
- `templates/index.html` — campaign UI with source links and copy-draft actions.
- `tests/` — offline tests for ordering, source validation, guardrails, and HTTP behavior.
