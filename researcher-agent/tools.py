"""
Native tools for the Research Agent.
Contains real web search (Serper) and web scraping functions,
along with JSON tool schemas for LLM native tool calling.
"""

import os
import json
import logging
from html.parser import HTMLParser
import requests

logger = logging.getLogger(__name__)


class SimpleHTMLTextExtractor(HTMLParser):
    """Clean HTML text extractor using Python standard library (no extra dependencies)."""

    def __init__(self):
        super().__init__()
        self.text_parts = []
        self._ignore = False

    def handle_starttag(self, tag, attrs):
        # Ignore scripts, stylesheets, and navigation headers/footers
        if tag.lower() in ("script", "style", "noscript", "svg", "header", "footer", "nav"):
            self._ignore = True

    def handle_endtag(self, tag):
        if tag.lower() in ("script", "style", "noscript", "svg", "header", "footer", "nav"):
            self._ignore = False

    def handle_data(self, data):
        if not self._ignore:
            stripped = data.strip()
            if stripped:
                self.text_parts.append(stripped)

    def get_clean_text(self) -> str:
        return " ".join(self.text_parts)


def search_web(query: str, num_results: int = 3) -> str:
    """Search Google using the Serper API.

    Returns a JSON string list of search result objects (title, link, snippet).
    """
    api_key = os.getenv("SERPER_API_KEY", "")

    if not api_key:
        logger.warning("SERPER_API_KEY not found in environment. Using simulated search results.")
        # Simulated search result for offline/testing mode
        domain = query.split()[0].replace("site:", "").replace("https://", "").replace("http://", "").strip("/")
        return json.dumps([
            {
                "title": f"About {domain.title()} - Official Overview",
                "link": f"https://{domain}/about",
                "snippet": f"Learn about {domain.title()}'s enterprise mission, modern cloud products, and global market position."
            },
            {
                "title": f"{domain.title()} Newsroom & Press Releases",
                "link": f"https://{domain}/news/latest-quarterly-update",
                "snippet": f"Recent announcements, strategic business expansions, and product updates for {domain.title()}."
            }
        ], indent=2)

    try:
        url = "https://google.serper.dev/search"
        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json"
        }
        payload = {"q": query, "num": num_results}
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("organic", [])[:num_results]:
            results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", "")
            })
        return json.dumps(results, indent=2)
    except Exception as e:
        logger.error(f"Search API error: {e}")
        return json.dumps({"error": f"Failed to search: {str(e)}"})


def scrape_url(url: str) -> str:
    """Fetch and extract clean text content from a webpage URL."""
    # Check for excluded social media domains or file downloads
    excluded = ["facebook.com", "instagram.com", "twitter.com", "x.com", "linkedin.com", "youtube.com"]
    if any(domain in url.lower() for domain in excluded):
        return json.dumps({"error": f"Scraping excluded domain: {url}"})

    if url.lower().endswith((".pdf", ".doc", ".docx", ".zip", ".ppt")):
        return json.dumps({"error": "Cannot scrape binary document file."})

    # Simulated scrape when no network or testing
    if "example.com" in url or not url.startswith("http"):
        return f"Simulated content for {url}: Leading enterprise software provider specializing in cloud solutions."

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=12)
        response.raise_for_status()

        # Extract clean text from HTML
        extractor = SimpleHTMLTextExtractor()
        extractor.feed(response.text)
        text = extractor.get_clean_text()

        # Truncate to first 4,000 characters to fit cleanly in context
        truncated = text[:4000]
        return json.dumps({
            "url": url,
            "content": truncated if truncated else "No readable text content found on page."
        })
    except Exception as e:
        logger.warning(f"Failed to scrape {url}: {e}")
        return json.dumps({"error": f"Failed to scrape {url}: {str(e)}"})


# ==============================================================================
# Function tool definitions (JSON Schema)
# ==============================================================================

TOOLS_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Searches Google for real company websites, about pages, and recent press releases.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query (e.g. 'stripe.com about us' or 'shopify recent press releases 2025')"
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of top results to return (default is 3)"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scrape_url",
            "description": "Fetches and extracts clean readable text from an HTML web page URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full HTTP or HTTPS URL to scrape (e.g. 'https://stripe.com/about')"
                    }
                },
                "required": ["url"]
            }
        }
    }
]

# Map tool names to Python functions for direct execution
AVAILABLE_TOOLS = {
    "search_web": search_web,
    "scrape_url": scrape_url
}
