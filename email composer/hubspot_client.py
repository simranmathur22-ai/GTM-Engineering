"""Small, read-only HubSpot CRM client for the local Email Composer."""

from urllib.parse import quote

import requests


class HubSpotAPIError(RuntimeError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class HubSpotClient:
    API_ROOT = "https://api.hubapi.com"

    def __init__(
        self,
        token_data: dict,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ):
        self.token_data = token_data
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def _refresh_access_token(self) -> None:
        response = requests.post(
            f"{self.API_ROOT}/oauth/v1/token",
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.token_data["refresh_token"],
            },
            timeout=20,
        )
        if not response.ok:
            raise HubSpotAPIError(response.status_code, "HubSpot authorization expired. Reconnect HubSpot.")
        refreshed = response.json()
        self.token_data.update(refreshed)

    def _request(self, method: str, path: str, **kwargs):
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.token_data['access_token']}"
        headers.setdefault("Content-Type", "application/json")
        response = requests.request(
            method,
            f"{self.API_ROOT}{path}",
            headers=headers,
            timeout=20,
            **kwargs,
        )
        if response.status_code == 401:
            self._refresh_access_token()
            headers["Authorization"] = f"Bearer {self.token_data['access_token']}"
            response = requests.request(
                method,
                f"{self.API_ROOT}{path}",
                headers=headers,
                timeout=20,
                **kwargs,
            )
        if not response.ok:
            raise HubSpotAPIError(
                response.status_code,
                f"HubSpot CRM request failed (HTTP {response.status_code}).",
            )
        return response.json()

    def find_contacts_for_company(self, domain: str) -> list[dict]:
        companies = self._request(
            "POST",
            "/crm/v3/objects/companies/search",
            json={
                "filterGroups": [
                    {
                        "filters": [
                            {
                                "propertyName": "domain",
                                "operator": "EQ",
                                "value": domain,
                            }
                        ]
                    }
                ],
                "properties": ["name", "domain"],
                "limit": 10,
            },
        ).get("results", [])
        if not companies:
            return []

        company_ids = [str(company["id"]) for company in companies]
        associated_ids = []
        for company_id in company_ids:
            associations = self._request(
                "GET",
                f"/crm/v4/objects/companies/{quote(company_id, safe='')}/associations/contacts",
            ).get("results", [])
            associated_ids.extend(
                str(item["toObjectId"])
                for item in associations
                if item.get("toObjectId") is not None
            )

        contact_ids = list(dict.fromkeys(associated_ids))
        if not contact_ids:
            return []

        contacts = self._request(
            "POST",
            "/crm/v3/objects/contacts/batch/read",
            json={
                "properties": ["firstname", "lastname", "email", "jobtitle"],
                "inputs": [{"id": contact_id} for contact_id in contact_ids],
            },
        ).get("results", [])
        hub_id = self.token_data.get("hub_id")
        result = []
        for contact in contacts:
            properties = contact.get("properties", {})
            first_name = (properties.get("firstname") or "").strip()
            last_name = (properties.get("lastname") or "").strip()
            result.append(
                {
                    "id": str(contact["id"]),
                    "first_name": first_name,
                    "last_name": last_name,
                    "name": " ".join(part for part in (first_name, last_name) if part)
                    or "Unnamed contact",
                    "email": properties.get("email") or "",
                    "job_title": properties.get("jobtitle") or "",
                    "record_url": (
                        f"https://app.hubspot.com/contacts/{quote(str(hub_id), safe='')}"
                        f"/record/0-1/{quote(str(contact['id']), safe='')}"
                        if hub_id
                        else None
                    ),
                }
            )
        return result
