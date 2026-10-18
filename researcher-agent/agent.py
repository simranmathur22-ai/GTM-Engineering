"""
Native Tool Calling Agent (Pure Python).

This module implements the fundamental Agent-Tool interaction loop:
1. Provide the LLM with instructions and a list of tool definitions (JSON schema).
2. The LLM decides if and when to call a tool (returns a function call).
3. Python executes the function locally and sends its result back to the model.
4. The cycle repeats until the LLM has all facts needed.
5. The LLM formats the final response into our Pydantic schema (CompanyProfile).
"""

import os
import json
import sys
from pathlib import Path
from typing import Optional
from google import genai
from google.genai import types

REPOSITORY_DIRECTORY = Path(__file__).resolve().parent.parent
if str(REPOSITORY_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_DIRECTORY))

from shared_gemini import generate_content_with_retry
from models import CompanyProfile
from tools import AVAILABLE_TOOLS, TOOLS_DEFINITION

SYSTEM_PROMPT = """
You are an expert enterprise research analyst.
Your job is to thoroughly research a target company by:
1. Using the `search_web` tool to find the company's official About page and recent news/press releases.
2. Using the `scrape_url` tool to read the contents of those pages.
3. Extracting verifiable facts: company overview, industry, target customers, strategic goals, and recent business news.
4. Outputting the final result in valid JSON matching the required schema.

Never invent URLs. Always search first, scrape the returned links, and base your report on real evidence.
"""


def _run_mock_agent(domain: str) -> CompanyProfile:
    """Simulated execution loop for offline testing without a Gemini API key."""
    print("\n--- [DEMO/MOCK MODE] Simulating Native Tool Calling Cycle ---")

    # Step 1: Agent decides to search for About page
    print(f"[Step 1] Agent requests tool call: search_web(query='{domain} about us')")
    search_about = AVAILABLE_TOOLS["search_web"](f"{domain} about us")
    print(f"         Tool output received: {search_about[:120]}...")

    # Step 2: Agent decides to scrape About page
    about_url = f"https://{domain}/about"
    print(f"\n[Step 2] Agent requests tool call: scrape_url(url='{about_url}')")
    scraped_about = AVAILABLE_TOOLS["scrape_url"](about_url)
    print(f"         Tool output received: {scraped_about[:120]}...")

    # Step 3: Agent decides to search for News
    print(f"\n[Step 3] Agent requests tool call: search_web(query='{domain} recent news 2025')")
    search_news = AVAILABLE_TOOLS["search_web"](f"{domain} recent news 2025")
    print(f"         Tool output received: {search_news[:120]}...")

    # Step 4: Final synthesis into Pydantic model
    print("\n[Step 4] Agent finishes research and produces structured CompanyProfile object.")
    name = domain.split(".")[0].title()
    return CompanyProfile(
        company_name=name,
        domain=domain,
        industry="Enterprise Software & Cloud Services",
        summary=f"{name} is an enterprise software platform providing cloud infrastructure and automation.",
        target_customers="Global enterprise organizations, scaling startups, and mid-market businesses.",
        strategic_goals=[
            "Accelerating AI-driven automation capabilities",
            "Expanding enterprise customer base across international markets",
            "Scaling operational efficiency and platform integrations"
        ],
        recent_news=f"{name} reported strong enterprise adoption and announced new cloud workflow integrations.",
        sources=[about_url, f"https://{domain}/news/latest-quarterly-update"]
    )


def research_company(domain: str, mock: bool = False) -> Optional[CompanyProfile]:
    """Execute the native tool-calling agent to research a company domain."""
    api_key = os.getenv("GEMINI_API_KEY")

    if mock or not api_key:
        if not api_key and not mock:
            print("\n[NOTICE] No GEMINI_API_KEY found in environment.")
            print("         Running in interactive demo mode to illustrate tool calling mechanics.")
        return _run_mock_agent(domain)

    client = genai.Client(api_key=api_key)
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    function_declarations = [
        types.FunctionDeclaration(
            name=tool["function"]["name"],
            description=tool["function"]["description"],
            parameters=tool["function"]["parameters"],
        )
        for tool in TOOLS_DEFINITION
    ]
    tool = types.Tool(function_declarations=function_declarations)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[tool],
        temperature=0.2,
    )

    contents = [
        f"Please conduct deep enterprise research for the company domain: {domain}"
    ]

    max_steps = 3  # Stay within the common Gemini free-tier per-minute request limit.
    print(f"\n[Agent] Starting research for {domain} with model={model}...")

    for step in range(1, max_steps + 1):
        response = generate_content_with_retry(
            client.models.generate_content,
            model=model,
            contents=contents,
            config=config,
        )
        candidate = response.candidates[0] if response.candidates else None
        if candidate is None or candidate.content is None:
            raise RuntimeError("Gemini returned no candidate content.")
        function_calls = response.function_calls or []
        if not function_calls:
            print(f"[Agent] Finished research after {step} step(s). Synthesizing report...")
            break

        contents.append(candidate.content)
        for function_call in function_calls:
            function_name = function_call.name
            if not function_name:
                raise RuntimeError("Gemini returned a function call without a name.")
            function_args = dict(function_call.args or {})

            print(f"[Step {step}] LLM called tool: {function_name}({function_args})")

            tool_func = AVAILABLE_TOOLS.get(function_name)
            if tool_func:
                tool_output = tool_func(**function_args)
            else:
                tool_output = json.dumps({"error": f"Tool '{function_name}' not found."})

            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(
                            name=function_name,
                            response={"result": str(tool_output)},
                        )
                    ],
                )
            )

    contents.append(
        "Now compile all gathered information into the final CompanyProfile. "
        "Use the required structured output and only include information supported by the sources."
    )
    final_response = generate_content_with_retry(
        client.models.generate_content,
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=CompanyProfile,
            temperature=0.2,
        ),
    )
    if not final_response.text:
        raise RuntimeError("Gemini returned an empty structured research report.")
    return CompanyProfile.model_validate_json(final_response.text)
