"""Export the contracts consumed by model, agent and Core/UI integration."""

import json
from pathlib import Path

from travel_agent.domain import AgentTurn, Intent, Snapshot, State

root = Path(__file__).resolve().parent / "schemas"
root.mkdir(exist_ok=True)
for model in (State, Intent, AgentTurn, Snapshot):
    (root / (model.__name__ + ".schema.json")).write_text(
        json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
    )
