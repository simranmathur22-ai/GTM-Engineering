# GTM-Engineering

## Turn company research into better sales conversations

Sales teams spend time researching prospects, finding a relevant reason to
reach out, and writing a message that feels personal. This project brings those
preparation steps together in two simple, locally run apps: a **Researcher
Agent** and an **Email Composer**.

The goal is to help a sales rep go from a company name to a researched,
reviewable first-touch message faster. The tools organize public information
and help prepare outreach; the rep stays in control of what gets sent.

[Watch the product demo](https://drive.google.com/file/d/1A9CWIrStV6OnpqNdQFGWtVT_TBjD-Qso/view?usp=drive_link)

## The sales workflow

1. **Research an account.** Enter a company domain to create a concise brief
   with an overview, industry, likely customers, strategic priorities, recent
   news, and links to sources.
2. **Choose a relevant contact.** Connect a HubSpot account and find a contact
   associated with the company. The app checks that the selected contact
   belongs to that account.
3. **Prepare a campaign.** The Email Composer uses the company research to
   suggest a buyer persona, outline a sales angle, and create three distinct
   first-touch email drafts.
4. **Review before sending.** Each draft includes source links and is checked
   for unsupported claims, length, and a clear question. The sales rep reviews
   the message, copies it, opens the contact record in HubSpot, and decides
   whether to send it.

## Why it can help sales

- **Spend less time starting from a blank page:** get an account brief and
  initial outreach drafts in one workflow.
- **Make outreach more relevant:** connect the message to public company
  information and show where that information came from.
- **Keep the rep in charge:** review and edit every draft before taking action
  in HubSpot.
- **Fit into an existing CRM workflow:** look up companies and contacts in
  HubSpot rather than manually matching a prospect to an account.
- **Support a consistent process:** create multiple draft options and apply
  basic quality checks before a rep reviews them.

## Product concept and important boundaries

The Email Composer uses the **CRM PII Exposure Scanner** as a demo product
concept for its outreach examples. It does not connect to or scan CRM fields
for exposed personal information. Public research cannot establish that a
company has a data exposure, breach, or legal violation, so the generated
messages must frame product fit as a question or hypothesis, never as a claim
that a problem was found.

This is a local prototype, not a production sales-engagement platform:

- HubSpot access is read-only and limited to company and contact lookup.
- Contact details are used to select the recipient and are not sent to Gemini.
- Email is never sent by the application. A person must review the message and
  send it themselves from HubSpot.
- AI-generated research and copy can be incomplete or incorrect. Verify
  sources and review every message before using it.
- The apps run locally; they are not configured as public, multi-user services.

## Technology used

| Area | Technologies |
| --- | --- |
| Language and web apps | Python, Flask, HTML, CSS, JavaScript, Jinja templates |
| AI and structured output | Google Gemini API, Google Gen AI Python SDK, Pydantic |
| Public web research | Serper search API, HTTP requests, lightweight webpage scraping |
| Local research storage | SQLite company-research cache with a seven-day lifetime |
| CRM connection | HubSpot OAuth 2.0 and CRM APIs for read-only company/contact lookup |
| Configuration and reliability | `python-dotenv`, shared Gemini request pacing, bounded retries for temporary service errors |
| Testing | Python `unittest` offline workflow tests |

The project has two applications:

- [Researcher Agent](./researcher-agent/README.md) — company research in a
  browser or from the command line.
- [Email Composer](./email%20composer/README.md) — a four-stage workflow that
  turns research into reviewed outreach drafts and supports HubSpot contact
  lookup.

Both apps use the shared [Gemini runtime](./shared_gemini.py) and configuration
in a repository-root `.env` file.

## Run locally

Create the shared environment file from the safe template:

```powershell
Copy-Item .env.example .env
notepad .env
```

Add your own Gemini and Serper API keys to `.env`. To use HubSpot contact
lookup, also configure the HubSpot OAuth client ID, secret, and Flask session
secret as described in the [Email Composer setup guide](./email%20composer/README.md).
Each user must supply credentials for services they connect. API availability,
quotas, and charges depend on those accounts.

Follow the app-specific guides to install dependencies and start either app:

- [Run the Researcher Agent](./researcher-agent/README.md#run-the-web-app)
- [Run the Email Composer](./email%20composer/README.md#run-locally)

The real `.env` file is excluded from Git. Never commit or share API keys,
OAuth secrets, or other credentials.
