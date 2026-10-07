"""Allowlisted model input; evaluator metadata never belongs here."""
import json
from .schemas import Request

def model_state(req: Request) -> str:
    # Positive allowlist excludes all IDs, fixture wrappers, and evaluator labels.
    return json.dumps({'authentic_user_request': req.user_request,
                       'untrusted_proposed_action': {'tool': req.action.tool, 'arguments': req.action.arguments},
                       'verified_context': req.verified_context.model_dump()}, ensure_ascii=False)

