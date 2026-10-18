"""
Main CLI entrypoint for the Native Research Agent.

Usage:
    python main.py --domain stripe.com
    python main.py --domain shopify.com --mock
    python main.py --clear-cache
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from dotenv import load_dotenv

APP_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY_DIRECTORY = APP_DIRECTORY.parent
load_dotenv(REPOSITORY_DIRECTORY / ".env")
load_dotenv(APP_DIRECTORY / ".env")

from agent import research_company
from cache import check_cache, save_cache, clear_cache

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def normalize_domain(url_or_domain: str) -> str:
    """Normalize input URL or domain to 'example.com' form."""
    cleaned = url_or_domain.strip().lower()
    cleaned = re.sub(r"^https?://", "", cleaned)
    cleaned = re.sub(r"^www\.", "", cleaned)
    cleaned = cleaned.split("/")[0].split("?")[0].split("#")[0]
    return cleaned


def main():
    parser = argparse.ArgumentParser(
        description="Native Tool-Calling Research Agent (Pure Python)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --domain stripe.com
  python main.py --domain shopify.com --mock
  python main.py --clear-cache
        """
    )
    parser.add_argument(
        "--domain",
        type=str,
        default="stripe.com",
        help="Target company domain or website URL (default: stripe.com)"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in offline demo/mock mode to inspect the tool-calling cycle without API keys"
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the local SQLite research cache"
    )

    args = parser.parse_args()

    if args.clear_cache:
        clear_cache()
        print("✓ Local SQLite cache cleared.")
        sys.exit(0)

    domain = normalize_domain(args.domain)
    if not domain:
        print("Error: Please provide a valid domain (e.g. --domain stripe.com)")
        sys.exit(1)

    print(f"\n=======================================================")
    print(f"  Target Company: {domain}")
    print(f"=======================================================")

    # 1. Cache Check (SQLite)
    cached_data = check_cache(domain)
    if cached_data and not args.mock:
        print(f"\n[CACHE HIT] Found valid research in local SQLite cache for '{domain}'!")
        print(f"            Returning instantly (0 API calls, 0 cost).\n")
        print(json.dumps(cached_data, indent=2))
        return

    print(f"\n[CACHE MISS] No valid cached research found for '{domain}'.")
    print("             Running native agent research pipeline...")

    # 2. Run Native Tool-Calling Agent
    report = research_company(domain, mock=args.mock)

    if not report:
        print(f"\n[ERROR] Research failed for domain: {domain}")
        sys.exit(1)

    report_dict = report.model_dump()

    # 3. Save to Local Cache
    save_cache(domain, report_dict)
    print(f"\n✓ Saved research to local SQLite cache (7-day TTL).")

    # 4. Display Final Output
    print(f"\n=======================================================")
    print(f"  FINAL RESEARCH REPORT: {report.company_name}")
    print(f"=======================================================\n")
    print(json.dumps(report_dict, indent=2))


if __name__ == "__main__":
    main()
