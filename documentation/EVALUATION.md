# Evaluation design

The golden JSONL dataset covers interest, meeting requests, pricing, opt-out,
rejection, complaints, ambiguous replies, security questions and prompt
injection. Each case declares the expected intent, action and forbidden phrases.

The default evaluation is deterministic and consumes no external tokens. A live
run must be explicitly requested with `--live`; it calls Groq for extraction,
generation and judging.

Release thresholds:

- Intent accuracy: at least 90%
- Action accuracy: at least 80%
- Forbidden-phrase safety: 100%
- Mean judge score: at least 80%

Human edits are recorded as workflow evaluation events. A reviewer should curate
representative corrections into the golden dataset rather than allowing
unreviewed production data to change prompts automatically.

