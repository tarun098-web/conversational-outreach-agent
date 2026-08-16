from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from statistics import mean
from uuid import uuid4

from pydantic import BaseModel

from outreach_agent.core.config import Settings
from outreach_agent.domain.models import Message, MessageDirection
from outreach_agent.integrations.llm import GroqLanguageModel, LanguageModel, MockLanguageModel


class GoldenScenario(BaseModel):
    id: str
    description: str
    inbound: str
    expected_intent: str
    expected_action: str
    forbidden_phrases: list[str] = []


class ScenarioResult(BaseModel):
    id: str
    intent_correct: bool
    action_correct: bool
    forbidden_phrase_safe: bool
    judge_average: float
    reply: str


async def run_evaluation(dataset: Path, live: bool = False) -> tuple[list[ScenarioResult], bool]:
    settings = Settings()
    if live:
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is required for --live")
        model: LanguageModel = GroqLanguageModel(
            settings.groq_api_key, settings.groq_fast_model, settings.groq_smart_model
        )
    else:
        model = MockLanguageModel()

    dataset_text = await asyncio.to_thread(dataset.read_text, encoding="utf-8")
    scenarios = [
        GoldenScenario.model_validate_json(line)
        for line in dataset_text.splitlines()
        if line.strip()
    ]
    results: list[ScenarioResult] = []
    for scenario in scenarios:
        message = Message(
            conversation_id=uuid4(),
            external_id=f"eval-{scenario.id}",
            direction=MessageDirection.INBOUND,
            sender="prospect@example.com",
            subject="Evaluation conversation",
            body_text=scenario.inbound,
        )
        analysis = await model.analyze(message, [message])
        generated = await model.generate(message, [message], analysis, [])
        score = await model.judge(scenario.inbound, generated.body, scenario.expected_intent)
        judge_values = [
            score.tone,
            score.correctness,
            score.grounding,
            score.progression,
            score.policy_compliance,
        ]
        results.append(
            ScenarioResult(
                id=scenario.id,
                intent_correct=analysis.intent.value == scenario.expected_intent,
                action_correct=generated.action.type.value == scenario.expected_action,
                forbidden_phrase_safe=not any(
                    phrase.lower() in generated.body.lower()
                    for phrase in scenario.forbidden_phrases
                ),
                judge_average=mean(judge_values),
                reply=generated.body,
            )
        )

    intent_accuracy = mean(result.intent_correct for result in results)
    action_accuracy = mean(result.action_correct for result in results)
    safety_accuracy = mean(result.forbidden_phrase_safe for result in results)
    judge_average = mean(result.judge_average for result in results)
    passed = (
        intent_accuracy >= 0.90
        and action_accuracy >= 0.80
        and safety_accuracy == 1.0
        and judge_average >= 0.80
    )
    summary = {
        "mode": "live" if live else "mock",
        "scenarios": len(results),
        "intent_accuracy": round(intent_accuracy, 3),
        "action_accuracy": round(action_accuracy, 3),
        "forbidden_phrase_safety": round(safety_accuracy, 3),
        "judge_average": round(judge_average, 3),
        "passed": passed,
    }
    print(json.dumps(summary, indent=2))
    for result in results:
        if not (result.intent_correct and result.action_correct and result.forbidden_phrase_safe):
            print(result.model_dump_json(indent=2))
    return results, passed


def main() -> None:
    parser = argparse.ArgumentParser(description="Run outreach-agent regression evaluation")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--live", action="store_true", help="Explicitly call Groq")
    arguments = parser.parse_args()
    _, passed = asyncio.run(run_evaluation(arguments.dataset, arguments.live))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
