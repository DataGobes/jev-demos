"""Body of jev_demo.jev.noul_pack_demo: SIMULATED values, no network, no secret.

Same contract as noul_pack.handler so the dbt hook cannot tell them apart; values are a hash of
(question, record), not a judgment (port of demo 04's DemoBackend). Embedded into CREATE FUNCTION
like noul_pack: no future imports, no SQL delimiters.
"""

import hashlib
import json


def hash_unit(*parts):
    digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def handler(records, question, model, *, now, new_id):
    started = now()
    return json.dumps({
        "values": [hash_unit(question, r) ** 6 for r in records],
        "input_tokens": sum(len(r) // 4 + 40 for r in records),
        "model": "demo:" + model,
        "error": None,
        "attempts": 1,
        "retries": [],
        "pack_uuid": new_id(),
        "started": started,
        "finished": now(),
    })
