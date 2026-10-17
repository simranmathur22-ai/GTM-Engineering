# Researcher Agent

A local company research app powered by Google's Gemini API. Enter a company website in the browser to get a structured research brief with an overview, industry, target customers, strategic priorities, recent news, and source links.

## Features

- Gemini function calling for research steps and structured report generation.
- Serper web search and a lightweight HTML scraper.
- Local SQLite cache with a seven-day time-to-live.
- Flask web app and command-line interface.
- Demo mode for trying the CLI without API keys.

## Requirements

- Python 3.10 or newer
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)
- A Serper API key from [serper.dev](https://serper.dev) for live web search
- Internet access when making live API calls

Each person running the app must provide their own API keys. API quotas, billing, and model availability depend on their Google and Serper accounts.

## Run the web app

### 1. Get the project

Clone the repository, or download and extract its ZIP file. Open a terminal in the `researcher-agent` project folder.

```text
GTM-Engineering/
└── researcher-agent/
```

### 2. Create and activate a virtual environment

**Windows — PowerShell**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, allow it only for the current terminal session, then activate:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Configure API keys

Copy `.env.example` to `.env`.

**Windows — PowerShell**

```powershell
Copy-Item .env.example .env
notepad .env
```

**macOS / Linux**

```bash
cp .env.example .env
nano .env
```

Set your own values in `.env`:

```dotenv
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-3.8-flash
SERPER_API_KEY=your-serper-api-key
```

Keep `.env` private. It is excluded from Git; never commit or share API keys.

### 5. Start the app

```bash
python webapp.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in a browser and submit a domain such as `stripe.com`. Stop the server with `Ctrl+C`.

The web server listens on the local computer only. Do not expose this development server directly to the public internet.

## Try the command-line interface

The demo uses simulated company data and does not call Gemini:

```bash
python main.py --domain stripe.com --mock
```

Run live research from the terminal after configuring both API keys:

```bash
python main.py --domain shopify.com
```

Clear saved research:

```bash
python main.py --clear-cache
```

The SQLite cache is stored locally in `research_cache.db` and is not shared between users or computers.

## Troubleshooting

- **`GEMINI_API_KEY is missing`**: Confirm `.env` exists in this project folder, contains a non-placeholder `GEMINI_API_KEY`, and restart `python webapp.py` after editing it.
- **`SERPER_API_KEY is missing`**: Add a Serper key to `.env`; the web app requires it for live web search.
- **Gemini `404` / model unavailable**: Check that the configured `GEMINI_MODEL` is currently enabled for your API key.
- **Gemini `429` / quota reached**: Wait for the quota window to reset or review the limits and billing for your Gemini project.
- **Port 5000 is already in use**: Stop the other process using that port, then restart the app.

## Project layout

```text
researcher-agent/
├── agent.py             # Gemini function-calling and report generation
├── cache.py             # Local SQLite cache
├── main.py              # Command-line interface
├── models.py            # Pydantic company report schema
├── tools.py             # Serper search and webpage scraping
├── webapp.py            # Local Flask web server
├── templates/
│   └── index.html       # Research form and report page
├── requirements.txt
└── .env.example         # API-key template (no real keys)
```
