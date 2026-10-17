"""Local web interface for the company research agent."""

import ipaddress
import logging
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from google.genai import errors

from agent import research_company
from cache import check_cache, save_cache

load_dotenv(Path(__file__).with_name(".env"))

app = Flask(__name__)
logger = logging.getLogger(__name__)

DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def normalize_company_domain(value: str) -> str:
    """Accept a domain or HTTP(S) URL and return a validated hostname."""
    value = value.strip()
    if not value:
        raise ValueError("Enter a company website or domain.")

    parsed = urlsplit(value)
    if parsed.scheme:
        if parsed.scheme.lower() not in ("http", "https"):
            raise ValueError("Use a website URL beginning with http:// or https://.")
    else:
        parsed = urlsplit(f"//{value}")

    if not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Enter a valid company website or domain.")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("The website URL contains an invalid port.") from exc

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Enter a valid company website or domain.")

    try:
        hostname = hostname.rstrip(".").encode("idna").decode("ascii").lower()
        if hostname.startswith("www."):
            hostname = hostname[4:]
        ipaddress.ip_address(hostname)
        is_ip_address = True
    except ValueError:
        is_ip_address = False
    except UnicodeError as exc:
        raise ValueError("Enter a valid company website or domain.") from exc

    if not is_ip_address:
        labels = hostname.split(".")
        if (
            len(hostname) > 253
            or len(labels) < 2
            or any(not DOMAIN_LABEL.fullmatch(label) for label in labels)
        ):
            raise ValueError("Enter a valid company website or domain, such as stripe.com.")

    return hostname


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/research")
def research():
    if not request.is_json:
        return jsonify(error="Send the research request as JSON."), 400

    payload = request.get_json()
    if not isinstance(payload, dict) or not isinstance(payload.get("company"), str):
        return jsonify(error="Provide a company website in the company field."), 400

    try:
        domain = normalize_company_domain(payload["company"])
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    if not os.getenv("GEMINI_API_KEY"):
        return jsonify(error="GEMINI_API_KEY is missing. Add it to the project .env file."), 503
    if not os.getenv("SERPER_API_KEY"):
        return jsonify(error="SERPER_API_KEY is missing. Add it to the project .env file for live web search."), 503

    cached_data = check_cache(domain)
    if cached_data:
        return jsonify(report=cached_data, cached=True)

    try:
        report = research_company(domain)
        if report is None:
            return jsonify(error="The research agent did not return a report. Check the server terminal for details."), 502

        report_data = report.model_dump()
        save_cache(domain, report_data)
        return jsonify(report=report_data, cached=False)
    except errors.APIError as exc:
        logger.exception("Company research failed for %s", domain)
        if exc.code == 429:
            return jsonify(
                error=(
                    "Gemini API rate limit or quota reached. Wait a minute and try again, "
                    "or check your Gemini API plan and usage limits."
                )
            ), 429
        if exc.code in (401, 403):
            return jsonify(
                error="Gemini rejected the API key. Check that GEMINI_API_KEY is valid and enabled for the Gemini API."
            ), 502
        if exc.code == 404:
            return jsonify(
                error="The configured Gemini model is unavailable. Set GEMINI_MODEL to a model enabled for your API key."
            ), 502
        return jsonify(error=f"Gemini API request failed (HTTP {exc.code}). Check the server terminal for details."), 502
    except Exception:
        logger.exception("Company research failed for %s", domain)
        return jsonify(error="Research failed. Check the server terminal for the error details and try again."), 502


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("Researcher is running at http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
