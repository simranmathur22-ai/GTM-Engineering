"""Schemas owned by the standalone Email Composer application."""

from typing import List

from pydantic import BaseModel, Field


class EvidenceSignal(BaseModel):
    """A public company fact used to ground an outreach hypothesis."""

    fact: str = Field(description="A concise public fact from the company research")
    source_url: str = Field(description="A source URL present in the company research")


class OutreachStrategy(BaseModel):
    """A tentative, evidence-grounded account strategy."""

    buyer_persona: str = Field(description="A relevant buyer role, not an invented contact name")
    account_hypothesis: str = Field(
        description="A tentative reason the topic may be relevant, not a claim of an existing incident"
    )
    product_relevance: str = Field(
        description="A careful description of how the scanner might be useful"
    )
    evidence: List[EvidenceSignal] = Field(
        min_length=1,
        max_length=3,
        description="One to three facts with research source URLs",
    )
    suggested_call_to_action: str = Field(description="A low-pressure question")
    caveat: str = Field(description="What public research cannot establish")


class DraftEmail(BaseModel):
    """One copywriter-produced email variant."""

    angle: str
    subject: str
    body: str
    source_urls: List[str] = Field(description="Research URLs supporting personalization")


class EmailDraftSet(BaseModel):
    """Exactly three distinct first-touch email options."""

    drafts: List[DraftEmail] = Field(min_length=3, max_length=3)


class ReviewedEmail(BaseModel):
    """A reviewer-checked email draft."""

    angle: str
    subject: str
    body: str
    source_urls: List[str]
    approved_by_ai_review: bool = Field(
        description="Whether automated review passed; human review is still required"
    )
    review_notes: List[str]
    changes_made: str


class ReviewResult(BaseModel):
    """Review result for all email options."""

    drafts: List[ReviewedEmail] = Field(min_length=3, max_length=3)
    summary: str


class EmailCampaign(BaseModel):
    """Complete researcher-to-email-composer result."""

    company: dict
    strategy: OutreachStrategy
    drafts: List[ReviewedEmail]
    review_summary: str
    human_review_required: bool = True
    email_sent: bool = False
