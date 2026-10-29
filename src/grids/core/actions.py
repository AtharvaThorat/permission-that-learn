"""Pure JSON validation before native argument resolution can execute anything."""
import hashlib
import json
import math
from .contracts import BoundAction

def json_value(value):
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            json_value(item)
        return
    if type(value) is dict and all(type(k) is str for k in value):
        for item in value.values():
            json_value(item)
        return
    # Native FunctionCall, arbitrary Pydantic models, callables, nonfinite numbers,
    # and non-JSON containers are all rejected recursively, without evaluating them.
    raise ValueError('NON_JSON_OR_NESTED_EXECUTABLE')

def canonical(value):
    json_value(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()

def parse_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    value = json.loads(text, object_pairs_hook=pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('NONFINITE_JSON')))
    json_value(value)
    return value

def bind(proposal, action_id, tools, facts, wall, env, max_chars):
    original = canonical(proposal.arguments)
    if len(original) > max_chars:
        raise ValueError('ACTION_BUDGET')
    arguments = tools.validate(proposal.tool, proposal.arguments)
    normalized = canonical(arguments)
    if len(normalized) > max_chars:
        raise ValueError('ACTION_BUDGET')
    effect = tools.effects(proposal.tool)
    resolved = facts.resolve(proposal.tool, arguments, env)
    frozen_facts = canonical(resolved)
    return BoundAction(action_id, proposal.call_id, proposal.tool, original, normalized,
                       digest({'tool': proposal.tool, 'arguments': arguments}), tuple(effect),
                       frozen_facts, digest(resolved), wall.version, not bool(resolved.get('missing')),
                       tools.schema_digest(proposal.tool))
