"""Regression for collection metadata overflowing the semantic model input."""
import json
from datetime import datetime
from types import SimpleNamespace as NS

import pytest
from pydantic import BaseModel
from blackbox.actions import bind
from blackbox.contracts import Proposal
from blackbox.permissions.gatekeeper_adapter import COLLECTION_READS, ExistingLayaGate, semantic_facts, usage_diagnostics
from gatekeeper.laya_adapter import parse_response
from gatekeeper.policy import Gatekeeper
from gatekeeper.schemas import Request
from gatekeeper.state import model_state
from integrations.agentdojo.context import Metadata, WorkspaceFacts
from integrations.agentdojo.tools import NativeTools
from .helpers import fixture


class CalendarSearch(BaseModel):
    query: str
    date: str | None = None


@pytest.mark.parametrize('truncated', [False, True])
def test_calendar_summary_preserves_action_and_fails_closed_on_real_truncation(truncated):
    f = fixture()
    f.runtime.functions['search_calendar_events'] = NS(parameters=CalendarSearch)
    event = NS(participants=['person@example.com'], start_time=datetime(2026, 5, 26, 10),
               end_time=datetime(2026, 5, 26, 11), status='confirmed',
               title='Networking', description='Private event text', location='Office')
    env = NS(calendar=NS(events={str(i): event for i in range(200)}))
    facts = WorkspaceFacts(Metadata(provenance='test', version='1'))
    proposal = Proposal('c', 'search_calendar_events', {'query': 'Networking', 'date': '2026-05-26'})
    action = bind(proposal, 'a', NativeTools(f.runtime), facts, f.wall, env, 32000)
    original_facts = action.facts_json
    captured = []

    def predict(req):
        captured.append(model_state(req))
        return parse_response({'answers': {'decision': {'type': 'choice', 'choice': 'ALLOW',
            'probabilities': {'ALLOW': 0.8, 'ASK': 0.1, 'BLOCK': 0.1}}},
            'usage': {'state_tokens': 160, 'state_tokens_dropped': 10 if truncated else 0,
                      'truncated': truncated, 'truncated_questions': ['decision'] if truncated else []}})

    backend = NS(predict=predict, checkpoint='test', revision='test')
    adapter = ExistingLayaGate(None, 24000)
    adapter.gate = Gatekeeper(backend, request_validator=lambda raw: (Request.model_validate(raw), None))
    result = adapter.evaluate(NS(episode_id='episode', task='Find the Networking event on May 26.'),
                              action, f.wall.evaluate(action))
    assert len(original_facts) > 24000  # Previously exceeded even the character guard.
    assert len(captured[0]) < 1000
    state = json.loads(captured[0])
    assert state['authentic_user_request'] == 'Find the Networking event on May 26.'
    assert state['untrusted_proposed_action']['arguments'] == json.loads(action.arguments_json)
    assert state['verified_context']['facts']['metadata']['resource_count'] == 200
    assert state['verified_context']['evidence_complete'] is True
    assert action.facts_json == original_facts
    assert result.decision == ('ASK' if truncated else 'ALLOW')
    assert result.error_kind == ('truncation' if truncated else None)
    assert result.diagnostics['state_tokens_dropped'] == (10 if truncated else 0)

    # Full collection facts still enforce scopes and invalidate stale actions.
    f.wall.policy.resource_scopes = {'event': ['0']}
    rebound = bind(proposal, 'a', NativeTools(f.runtime), facts, f.wall, env, 32000)
    assert f.wall.evaluate(rebound).reason == 'RESOURCE_OUTSIDE_SCOPE'
    event.description = 'Changed content'
    changed = bind(proposal, 'a', NativeTools(f.runtime), facts, f.wall, env, 32000)
    assert changed.state_version != rebound.state_version


def test_projection_keeps_missing_evidence_and_leaves_noncollection_actions_intact():
    facts = {'resources': [{'id': '1', 'participants': ['person@example.com']}],
             'missing': ['event:missing'], 'recipients': ['person@example.com']}
    for tool in COLLECTION_READS:
        projected = semantic_facts(tool, facts)
        assert projected['missing'] == facts['missing']
        assert projected['recipients'] == facts['recipients']
        assert projected['scope'] == 'full_collection_not_search_results'
    assert semantic_facts('reschedule_calendar_event', facts) is facts


def test_diagnostics_do_not_expose_free_text():
    result = usage_diagnostics({'usage': {'state_tokens': 999, 'state_tokens_dropped': 500,
        'truncated': True, 'truncated_questions': ['private question'],
        'options': {'private': 'text'}, 'prompt': 'secret'}})
    assert result == {'state_tokens': 999, 'state_tokens_dropped': 500, 'truncated': True,
                      'truncated_question_count': 1, 'option_collapse': True}
    assert usage_diagnostics(None) == {'option_collapse': False}
