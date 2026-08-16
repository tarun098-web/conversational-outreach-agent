from __future__ import annotations

import re

from outreach_agent.domain.models import DraftResponse, Intent, IntentAnalysis, RiskLevel

OPT_OUT_PATTERNS = (
    r"\bunsubscribe\b",
    r"\bremove me\b",
    r"\bstop (emailing|contacting|messaging)\b",
    r"\bdo not contact\b",
)

INJECTION_PATTERNS = (
    r"ignore (all |any )?(previous|prior) instructions",
    r"reveal (the )?(system prompt|secrets|api key)",
    r"developer message",
    r"act as (a )?system",
)


class PolicyEngine:
    def is_opt_out(self, text: str) -> bool:
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in OPT_OUT_PATTERNS)

    def detects_prompt_injection(self, text: str) -> bool:
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in INJECTION_PATTERNS)

    def validate_analysis(self, analysis: IntentAnalysis, body: str) -> IntentAnalysis:
        if self.detects_prompt_injection(body):
            analysis.prompt_injection_suspected = True
            analysis.requires_human = True
            analysis.risk_level = RiskLevel.HIGH
        return analysis

    def validate_draft(self, draft: DraftResponse) -> list[str]:
        warnings: list[str] = []
        lowered = draft.body.lower()
        if draft.analysis.prompt_injection_suspected:
            warnings.append("Potential prompt injection detected in the inbound message.")
        if draft.analysis.risk_level == RiskLevel.HIGH:
            warnings.append("High-risk conversation requires careful human review.")
        if draft.analysis.intent == Intent.PRICING_QUESTION and any(
            token in lowered for token in ("$", "£", "€", " per month", "discount")
        ):
            warnings.append("Draft may contain an unapproved pricing claim.")
        if len(draft.body) > 2000:
            warnings.append("Draft is unusually long for an outreach reply.")
        if not draft.evidence and draft.analysis.intent in {
            Intent.PRICING_QUESTION,
            Intent.PRODUCT_QUESTION,
        }:
            warnings.append("No approved evidence was found for a factual question.")
        return warnings
