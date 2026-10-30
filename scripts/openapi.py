"""Write the service's OpenAPI schema to stdout, for the client's generated types.

python scripts/openapi.py > client/openapi.json
"""

from __future__ import annotations

import json

from camanchaca_demo.serve.app import app

print(json.dumps(app.openapi(), indent=1, sort_keys=True))
