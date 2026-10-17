"""
Data models for the Native Research Agent using Pydantic.
These define the exact structure of the output we expect from the LLM.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class CompanyProfile(BaseModel):
    """Structured report returned by the research agent."""
    company_name: str = Field(
        ...,
        description="Clean company name without corporate suffixes like Inc, LLC, Corp"
    )
    domain: str = Field(
        ...,
        description="The normalized domain of the company (e.g., example.com)"
    )
    industry: str = Field(
        ...,
        description="Primary industry or business sector of the company"
    )
    summary: str = Field(
        ...,
        description="2-3 sentence overview of what the company does and its core offerings"
    )
    target_customers: str = Field(
        ...,
        description="Key customer segments and target markets"
    )
    strategic_goals: List[str] = Field(
        default_factory=list,
        description="List of stated forward-looking strategic goals, expansion priorities, or initiatives"
    )
    recent_news: str = Field(
        ...,
        description="Summary of the most relevant news or press release from the past 6 months"
    )
    sources: List[str] = Field(
        default_factory=list,
        description="List of all real URLs visited/scraped to produce this report"
    )
