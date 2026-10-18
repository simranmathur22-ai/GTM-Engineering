import os
import sys
import unittest
from pathlib import Path
from unittest.mock import ANY, Mock, patch

REPOSITORY_DIRECTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_DIRECTORY))
sys.path.insert(0, str(REPOSITORY_DIRECTORY / "researcher-agent"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from campaign_models import (  # noqa: E402
    EvidenceSignal,
    EmailCampaign,
    EmailDraftSet,
    OutreachStrategy,
    ReviewResult,
    ReviewedEmail,
)
from outreach import _validate_campaign, run_email_campaign  # noqa: E402
from webapp import app  # noqa: E402
from models import CompanyProfile  # noqa: E402
from google.genai import errors  # noqa: E402
from shared_gemini import generate_content_with_retry  # noqa: E402
from hubspot_client import HubSpotClient  # noqa: E402

SOURCE_URL = "https://example.com/about"


def company_profile():
    return CompanyProfile(
        company_name="Example",
        domain="example.com",
        industry="Software",
        summary="Example makes business software.",
        target_customers="Businesses",
        recent_news="Example announced an expansion.",
        sources=[SOURCE_URL],
    )


def strategy():
    return OutreachStrategy(
        buyer_persona="CRM operations leader",
        account_hypothesis="The announced expansion may increase the complexity of CRM data workflows.",
        product_relevance="A scanner could help teams review sensitive data in free-text CRM fields.",
        evidence=[{"fact": "Example announced an expansion.", "source_url": SOURCE_URL}],
        suggested_call_to_action="Would a short discussion be useful?",
        caveat="Public research does not establish that Example has exposed personal information.",
    )


def reviewed_drafts(body=None):
    return ReviewResult(
        drafts=[
            ReviewedEmail(
                angle=f"Angle {index}",
                subject=f"Question about {index}",
                body=f"Angle {index}: " + (body or (
                    "Example announced an expansion. Could a scanner help review "
                    "free-text CRM fields? Would a short chat be useful?"
                )),
                source_urls=[SOURCE_URL],
                approved_by_ai_review=True,
                review_notes=[],
                changes_made="None",
            )
            for index in range(1, 4)
        ],
        summary="Three concise drafts were reviewed.",
    )


def copywriter_drafts():
    from campaign_models import DraftEmail

    return EmailDraftSet(
        drafts=[
            DraftEmail(
                angle=f"Angle {index}",
                subject=f"Question about {index}",
                body=(
                    f"Angle {index}: Example announced an expansion. Could a scanner help review "
                    "free-text CRM fields? Would a short chat be useful?"
                ),
                source_urls=[SOURCE_URL],
            )
            for index in range(1, 4)
        ]
    )


class EmailComposerTests(unittest.TestCase):
    def test_hubspot_client_returns_contacts_associated_to_matching_company(self):
        class Response:
            status_code = 200
            ok = True

            def __init__(self, payload):
                self.payload = payload

            def json(self):
                return self.payload

        responses = [
            Response({"results": [{"id": "20"}]}),
            Response({"results": [{"toObjectId": "15"}]}),
            Response(
                {
                    "results": [
                        {
                            "id": "15",
                            "properties": {
                                "firstname": "Riley",
                                "lastname": "Example",
                                "email": "riley@example.com",
                                "jobtitle": "CRM Operations",
                            },
                        }
                    ]
                }
            ),
        ]
        with patch("hubspot_client.requests.request", side_effect=responses) as request:
            contacts = HubSpotClient(
                {"access_token": "test-token", "hub_id": 123},
                "client-id",
                "client-secret",
                "http://127.0.0.1:5001/hubspot/callback",
            ).find_contacts_for_company("example.com")

        self.assertEqual(contacts[0]["name"], "Riley Example")
        self.assertEqual(contacts[0]["record_url"], "https://app.hubspot.com/contacts/123/record/0-1/15")
        self.assertEqual(request.call_count, 3)
        self.assertEqual(
            request.call_args_list[0].kwargs["json"]["filterGroups"][0]["filters"][0]["value"],
            "example.com",
        )

    def test_hubspot_oauth_requires_matching_state(self):
        with (
            app.test_client() as client,
            patch.dict(
                os.environ,
                {
                    "HUBSPOT_CLIENT_ID": "client-id",
                    "HUBSPOT_CLIENT_SECRET": "client-secret",
                    "HUBSPOT_REDIRECT_URI": "http://127.0.0.1:5001/hubspot/callback",
                },
            ),
        ):
            response = client.get("/hubspot/connect")
            self.assertEqual(response.status_code, 302)
            callback = client.get("/hubspot/callback?code=test-code&state=wrong-state")

        self.assertEqual(callback.status_code, 400)
        self.assertIn("state did not match", callback.get_json()["error"])

    def test_hubspot_connect_uses_callback_host_before_setting_oauth_state(self):
        with (
            app.test_client() as client,
            patch.dict(
                os.environ,
                {
                    "HUBSPOT_CLIENT_ID": "client-id",
                    "HUBSPOT_CLIENT_SECRET": "client-secret",
                    "HUBSPOT_REDIRECT_URI": "http://localhost:5001/hubspot/callback",
                },
            ),
        ):
            response = client.get("/hubspot/connect", base_url="http://127.0.0.1:5001")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "http://localhost:5001/hubspot/connect")
        self.assertNotIn("session=", response.headers.get("Set-Cookie", ""))

    def test_hubspot_contacts_requires_connection(self):
        response = app.test_client().get("/api/hubspot/contacts?domain=example.com")
        self.assertEqual(response.status_code, 401)

    def test_campaign_validates_hubspot_contact_without_sending_contact_data_to_ai(self):
        expected = _validate_campaign(
            company_profile(),
            strategy(),
            copywriter_drafts(),
            reviewed_drafts(),
        )
        contact = {
            "id": "15",
            "first_name": "Riley",
            "last_name": "Example",
            "name": "Riley Example",
            "email": "riley@example.com",
            "job_title": "CRM Operations",
            "record_url": "https://app.hubspot.com/contacts/123/record/0-1/15",
        }
        hubspot_client = Mock()
        hubspot_client.find_contacts_for_company.return_value = [contact]
        with (
            patch.dict(
                os.environ,
                {"GEMINI_API_KEY": "test-key", "SERPER_API_KEY": "test-key"},
            ),
            patch("webapp._hubspot_client_for_current_session", return_value=hubspot_client),
            patch("webapp.run_email_campaign", return_value=expected) as workflow,
        ):
            response = app.test_client().post(
                "/api/campaign",
                json={"company": "example.com", "hubspot_contact_id": "15"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["campaign"]["hubspot_contact"]["email"], "riley@example.com")
        workflow.assert_called_once_with("example.com", on_stage=ANY)

    def test_agents_run_sequentially_using_existing_research_cache(self):
        company = company_profile()
        generated = [strategy(), copywriter_drafts(), reviewed_drafts()]
        requested_schemas = []

        class FakeModels:
            def generate_content(self, **kwargs):
                schema = kwargs["config"].response_schema
                requested_schemas.append(schema)
                return type("Response", (), {"text": generated.pop(0).model_dump_json()})()

        class FakeClient:
            def __init__(self, **kwargs):
                self.models = FakeModels()

        stages = []
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "test-model"}),
            patch("outreach.check_cache", return_value=company.model_dump()),
            patch("outreach.genai.Client", FakeClient),
            patch("outreach.generate_content_with_retry") as generate,
        ):
            generate.side_effect = lambda method, **kwargs: method(**kwargs)
            result = run_email_campaign("example.com", on_stage=stages.append)

        self.assertEqual(
            stages,
            ["Company Researcher", "Account Strategist", "Email Copywriter", "Quality Reviewer"],
        )
        self.assertEqual(
            requested_schemas,
            [OutreachStrategy, EmailDraftSet, ReviewResult],
        )
        self.assertIsInstance(result, EmailCampaign)
        self.assertEqual(len(result.drafts), 3)
        self.assertTrue(result.human_review_required)
        self.assertFalse(result.email_sent)

    def test_deterministic_review_rejects_unverified_pii_claim(self):
        result = _validate_campaign(
            company_profile(),
            strategy(),
            copywriter_drafts(),
            reviewed_drafts("We found exposed PII in your CRM. Would you discuss it?"),
        )
        self.assertFalse(result.drafts[0].approved_by_ai_review)
        self.assertTrue(any("unverified exposure" in note for note in result.drafts[0].review_notes))

    def test_deterministic_review_rejects_email_over_100_words(self):
        long_body = "A factual introduction. " * 40 + "Would you discuss this?"
        result = _validate_campaign(
            company_profile(),
            strategy(),
            copywriter_drafts(),
            reviewed_drafts(long_body),
        )
        self.assertFalse(result.drafts[0].approved_by_ai_review)
        self.assertTrue(any("limit is 100" in note for note in result.drafts[0].review_notes))

    def test_researcher_cannot_cite_unknown_source(self):
        invalid_strategy = strategy().model_copy(
            update={
                "evidence": [
                    EvidenceSignal(
                        fact="Unverified fact.",
                        source_url="https://unknown.example/",
                    )
                ]
            }
        )
        with self.assertRaisesRegex(ValueError, "absent from company research"):
            _validate_campaign(
                company_profile(),
                invalid_strategy,
                copywriter_drafts(),
                reviewed_drafts(),
            )

    def test_reviewer_cannot_introduce_unknown_source(self):
        invalid_review = reviewed_drafts()
        invalid_review.drafts[0].source_urls = ["https://unknown.example/"]
        result = _validate_campaign(
            company_profile(),
            strategy(),
            copywriter_drafts(),
            invalid_review,
        )
        self.assertFalse(result.drafts[0].approved_by_ai_review)
        self.assertTrue(any("company research" in note for note in result.drafts[0].review_notes))

    def test_campaign_endpoint_rejects_invalid_domain(self):
        response = app.test_client().post("/api/campaign", json={"company": "not a domain"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("valid company website", response.get_json()["error"])

    def test_campaign_endpoint_requires_keys(self):
        with patch.dict(os.environ, {}, clear=True):
            response = app.test_client().post("/api/campaign", json={"company": "example.com"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("GEMINI_API_KEY", response.get_json()["error"])
        self.assertIn(str(REPOSITORY_DIRECTORY / ".env"), response.get_json()["error"])

    def test_campaign_endpoint_returns_serialized_campaign(self):
        expected = _validate_campaign(
            company_profile(),
            strategy(),
            copywriter_drafts(),
            reviewed_drafts(),
        )
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "SERPER_API_KEY": "test-key"}),
            patch("webapp.run_email_campaign", return_value=expected) as workflow,
        ):
            response = app.test_client().post(
                "/api/campaign",
                json={"company": "https://www.example.com/about"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()["campaign"]["drafts"]), 3)
        self.assertFalse(response.get_json()["campaign"]["email_sent"])
        workflow.assert_called_once_with("example.com", on_stage=ANY)

    def test_temporary_gemini_503_is_retried_with_bounded_backoff(self):
        calls = []

        def flaky_request(**kwargs):
            calls.append(kwargs)
            if len(calls) < 3:
                raise errors.ServerError(503, {"error": "temporary high demand"})
            return "success"

        with (
            patch.dict(
                os.environ,
                {
                    "GEMINI_MIN_REQUEST_INTERVAL_SECONDS": "0",
                    "GEMINI_TRANSIENT_RETRY_BASE_SECONDS": "0",
                },
            ),
            patch("shared_gemini.time.sleep") as sleep,
        ):
            result = generate_content_with_retry(flaky_request, prompt="test")

        self.assertEqual(result, "success")
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleep.call_count, 2)

    def test_temporary_gemini_503_stops_after_max_attempts(self):
        with (
            patch.dict(
                os.environ,
                {
                    "GEMINI_MIN_REQUEST_INTERVAL_SECONDS": "0",
                    "GEMINI_TRANSIENT_RETRY_BASE_SECONDS": "0",
                },
            ),
            patch("shared_gemini.time.sleep") as sleep,
        ):
            generate = Mock(
                side_effect=errors.ServerError(503, {"error": "temporary high demand"})
            )
            with self.assertRaises(errors.ServerError):
                generate_content_with_retry(generate, prompt="test")

        self.assertEqual(generate.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_non_retryable_gemini_error_is_not_retried(self):
        generate = Mock(
            side_effect=errors.ClientError(400, {"error": "invalid request"})
        )
        with (
            patch.dict(os.environ, {"GEMINI_MIN_REQUEST_INTERVAL_SECONDS": "0"}),
            patch("shared_gemini.time.sleep"),
            self.assertRaises(errors.ClientError),
        ):
            generate_content_with_retry(generate, prompt="test")

        generate.assert_called_once()

    def test_campaign_endpoint_explains_transient_gemini_503(self):
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "SERPER_API_KEY": "test-key"}),
            patch(
                "webapp.run_email_campaign",
                side_effect=errors.ServerError(503, {"error": "temporary high demand"}),
            ),
        ):
            response = app.test_client().post(
                "/api/campaign",
                json={"company": "example.com"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("temporarily unavailable", response.get_json()["error"])

    def test_home_page_is_email_composer(self):
        response = app.test_client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Email Composer", response.data)
        self.assertIn(b"Build email campaign", response.data)
        self.assertIn(b"Human approval required", response.data)


if __name__ == "__main__":
    unittest.main()
