"""Local web app for the standalone Email Composer multi-agent workflow."""

import ipaddress
import logging
import os
import re
import secrets
import sys
import threading
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from google.genai import errors

APP_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY_DIRECTORY = APP_DIRECTORY.parent
RESEARCHER_DIRECTORY = REPOSITORY_DIRECTORY / "researcher-agent"

for env_path in (
    REPOSITORY_DIRECTORY / ".env",
    APP_DIRECTORY / ".env",
    RESEARCHER_DIRECTORY / ".env",
    REPOSITORY_DIRECTORY.parent / ".env",
):
    load_dotenv(env_path)

if str(RESEARCHER_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(RESEARCHER_DIRECTORY))

from outreach import run_email_campaign  # noqa: E402
from hubspot_client import HubSpotAPIError, HubSpotClient  # noqa: E402

app = Flask(__name__, template_folder=str(APP_DIRECTORY / "templates"))
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_urlsafe(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
logger = logging.getLogger(__name__)
DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
HUBSPOT_SCOPE = "crm.objects.companies.read crm.objects.contacts.read"
hubspot_connections: dict[str, dict] = {}
hubspot_connections_lock = threading.Lock()


def _configured_key(name: str) -> bool:
    value = os.getenv(name, "").strip()
    return bool(value) and not value.lower().startswith(("your-", "replace-", "<"))


def _hubspot_redirect_uri() -> str:
    return os.getenv(
        "HUBSPOT_REDIRECT_URI",
        "http://localhost:5001/hubspot/callback",
    )


def _hubspot_client_for_current_session() -> HubSpotClient | None:
    connection_id = session.get("hubspot_connection_id")
    with hubspot_connections_lock:
        token_data = hubspot_connections.get(connection_id)
    if token_data is None:
        return None
    return HubSpotClient(
        token_data,
        os.getenv("HUBSPOT_CLIENT_ID", ""),
        os.getenv("HUBSPOT_CLIENT_SECRET", ""),
        _hubspot_redirect_uri(),
    )


def normalize_company_domain(value: str) -> str:
    """Normalize a domain or HTTP(S) website URL and reject invalid hosts."""
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
            raise ValueError("Enter a valid company website or domain, such as example.com.")
    return hostname


@app.get("/")
def index():
    return render_template(
        "index.html",
        hubspot_connected=_hubspot_client_for_current_session() is not None,
        hubspot_configured=(
            _configured_key("HUBSPOT_CLIENT_ID")
            and _configured_key("HUBSPOT_CLIENT_SECRET")
        ),
    )


@app.get("/hubspot/connect")
def connect_hubspot():
    callback_url = urlsplit(_hubspot_redirect_uri())
    if request.host.lower() != callback_url.netloc.lower() or request.scheme != callback_url.scheme:
        canonical_connect_url = urlunsplit(
            (callback_url.scheme, callback_url.netloc, "/hubspot/connect", "", "")
        )
        return redirect(canonical_connect_url)

    if not (
        _configured_key("HUBSPOT_CLIENT_ID")
        and _configured_key("HUBSPOT_CLIENT_SECRET")
    ):
        return redirect(url_for("index", hubspot="not-configured"))

    state = secrets.token_urlsafe(32)
    session["hubspot_oauth_state"] = state
    previous_connection_id = session.get("hubspot_connection_id")
    if previous_connection_id:
        with hubspot_connections_lock:
            hubspot_connections.pop(previous_connection_id, None)
    session["hubspot_connection_id"] = secrets.token_urlsafe(24)
    authorize_url = "https://app.hubspot.com/oauth/authorize?" + urlencode(
        {
            "client_id": os.environ["HUBSPOT_CLIENT_ID"],
            "redirect_uri": _hubspot_redirect_uri(),
            "scope": HUBSPOT_SCOPE,
            "state": state,
        }
    )
    return redirect(authorize_url)


@app.get("/hubspot/callback")
def hubspot_callback():
    if request.args.get("error"):
        return redirect(url_for("index", hubspot="denied"))
    expected_state = session.pop("hubspot_oauth_state", None)
    supplied_state = request.args.get("state", "")
    if not expected_state or not secrets.compare_digest(expected_state, supplied_state):
        return jsonify(error="HubSpot authorization state did not match. Please reconnect."), 400

    code = request.args.get("code", "")
    connection_id = session.get("hubspot_connection_id")
    if not code or not connection_id:
        return jsonify(error="HubSpot did not return an authorization code. Please reconnect."), 400

    try:
        response = requests.post(
            "https://api.hubapi.com/oauth/v1/token",
            data={
                "grant_type": "authorization_code",
                "client_id": os.environ["HUBSPOT_CLIENT_ID"],
                "client_secret": os.environ["HUBSPOT_CLIENT_SECRET"],
                "redirect_uri": _hubspot_redirect_uri(),
                "code": code,
            },
            timeout=20,
        )
        if not response.ok:
            logger.error("HubSpot OAuth token exchange failed (HTTP %s).", response.status_code)
            return redirect(url_for("index", hubspot="failed"))
        token_data = response.json()
        with hubspot_connections_lock:
            hubspot_connections[connection_id] = token_data
    except (requests.RequestException, ValueError):
        logger.exception("HubSpot OAuth token exchange failed.")
        return redirect(url_for("index", hubspot="failed"))

    return redirect(url_for("index", hubspot="connected"))


@app.post("/hubspot/disconnect")
def disconnect_hubspot():
    connection_id = session.pop("hubspot_connection_id", None)
    session.pop("hubspot_oauth_state", None)
    if connection_id:
        with hubspot_connections_lock:
            hubspot_connections.pop(connection_id, None)
    return redirect(url_for("index", hubspot="disconnected"))


@app.get("/api/hubspot/contacts")
def hubspot_contacts():
    client = _hubspot_client_for_current_session()
    if client is None:
        return jsonify(error="Connect HubSpot before searching CRM contacts."), 401

    try:
        domain = normalize_company_domain(request.args.get("domain", ""))
        contacts = client.find_contacts_for_company(domain)
        return jsonify(contacts=contacts)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except HubSpotAPIError as exc:
        logger.warning("HubSpot contact search failed (HTTP %s).", exc.status_code)
        if exc.status_code == 401:
            connection_id = session.pop("hubspot_connection_id", None)
            with hubspot_connections_lock:
                hubspot_connections.pop(connection_id, None)
            return jsonify(error="HubSpot authorization expired. Reconnect HubSpot."), 401
        return jsonify(error=str(exc)), 502
    except requests.RequestException:
        logger.exception("HubSpot contact search could not reach the API.")
        return jsonify(error="Could not reach HubSpot. Check your connection and retry."), 502


@app.post("/api/campaign")
def create_campaign():
    if not request.is_json:
        return jsonify(error="Send the campaign request as JSON."), 400

    payload = request.get_json()
    if not isinstance(payload, dict) or not isinstance(payload.get("company"), str):
        return jsonify(error="Provide a company website in the company field."), 400
    try:
        domain = normalize_company_domain(payload["company"])
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    if not _configured_key("GEMINI_API_KEY"):
        return jsonify(
            error=(
                "GEMINI_API_KEY is missing or still a placeholder. Add your key to "
                f'"{REPOSITORY_DIRECTORY / ".env"}" and restart the Email Composer.'
            )
        ), 503
    if not _configured_key("SERPER_API_KEY"):
        return jsonify(
            error=(
                "SERPER_API_KEY is missing or still a placeholder. Add your key to "
                f'"{REPOSITORY_DIRECTORY / ".env"}" and restart the Email Composer.'
            )
        ), 503

    def log_stage(name: str) -> None:
        logger.info("Email-composer workflow for %s: %s", domain, name)

    try:
        selected_contact = None
        contact_id = payload.get("hubspot_contact_id")
        if contact_id is not None:
            if not isinstance(contact_id, str) or not re.fullmatch(r"\d{1,30}", contact_id):
                return jsonify(error="Select a valid HubSpot contact."), 400
            client = _hubspot_client_for_current_session()
            if client is None:
                return jsonify(error="Connect HubSpot before using a CRM contact."), 401
            contacts = client.find_contacts_for_company(domain)
            selected_contact = next(
                (contact for contact in contacts if contact["id"] == contact_id),
                None,
            )
            if selected_contact is None:
                return jsonify(
                    error="That contact is not associated with the selected HubSpot company."
                ), 400

        campaign = run_email_campaign(domain, on_stage=log_stage)
        campaign_data = campaign.model_dump(mode="json")
        if selected_contact:
            campaign_data["hubspot_contact"] = selected_contact
        return jsonify(campaign=campaign_data)
    except HubSpotAPIError as exc:
        logger.warning("HubSpot contact validation failed (HTTP %s).", exc.status_code)
        if exc.status_code == 401:
            return jsonify(error="HubSpot authorization expired. Reconnect HubSpot."), 401
        return jsonify(error=str(exc)), 502
    except requests.RequestException:
        logger.exception("HubSpot contact validation could not reach the API.")
        return jsonify(error="Could not reach HubSpot. Check your connection and retry."), 502
    except errors.APIError as exc:
        logger.exception("Email-composer workflow failed for %s", domain)
        if exc.code == 429:
            return jsonify(
                error="Gemini rate limit or quota reached. Wait for the limit to reset and try again."
            ), 429
        if exc.code in (401, 403):
            return jsonify(error="Gemini rejected the API key. Check GEMINI_API_KEY and Gemini API access."), 502
        if exc.code == 404:
            return jsonify(error="The configured Gemini model is unavailable. Check GEMINI_MODEL."), 502
        if exc.code in (500, 502, 503, 504):
            return jsonify(
                error=(
                    "Gemini is temporarily unavailable after automatic retries. "
                    "Wait a moment and try the campaign again."
                )
            ), 503
        return jsonify(error=f"Gemini API request failed (HTTP {exc.code}). Check the server terminal."), 502
    except Exception:
        logger.exception("Email-composer workflow failed for %s", domain)
        return jsonify(error="Campaign generation failed. Check the server terminal for details."), 502


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("Email Composer is running at http://127.0.0.1:5001")
    app.run(host="127.0.0.1", port=5001, debug=False)
