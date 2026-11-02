"""Write the JSON schema of every mailbox/1 model to docs/contracts/mailbox-1/.

Run from backend/: uv run python ../packages/mailbox-contract/write_schemas.py
"""

import json
from pathlib import Path

import mailbox_contract as contract

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "mailbox-1"

models = {tool.input for tool in contract.TOOLS.values()}
models |= {tool.output for tool in contract.TOOLS.values()}
models.add(contract.ToolError)

SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
for model in sorted(models, key=lambda model: model.__name__):
    schema = model.model_json_schema(by_alias=True)
    (SCHEMA_DIR / f"{model.__name__}.schema.json").write_text(json.dumps(schema, indent=2) + "\n")
    print(model.__name__)
