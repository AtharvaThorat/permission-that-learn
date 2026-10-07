"""Mocked enforcement tests, runnable with unittest or pytest; no downloads."""
import copy
import json
from pathlib import Path
import unittest
from gatekeeper.laya_adapter import Prediction, parse_response, model_state, LayaBackend
from gatekeeper.policy import Gatekeeper
from gatekeeper.schemas import Request

def request():
    return {'schema_version': '0.1', 'request_id': 'request-x', 'task_id': 'task-x',
            'user_request': 'Send Morgan an email with subject Hello and body: Welcome.',
            'action': {'action_id': 'action-x', 'tool': 'email.send',
                       'arguments': {'to': ['morgan@example.test'], 'subject': 'Hello', 'body': 'Welcome.'}},
            'wall': {'verdict': 'PASS', 'policy_version': 'test-policy',
                     'evaluated_action_id': 'action-x', 'reason_codes': []},
            'verified_context': {'confirmation_required': False, 'evidence_complete': True,
                                 'facts': {'recipient_identity': 'Morgan'}}}

def response(choice='ALLOW'):
    return {'answers': {'decision': {'type': 'choice', 'choice': choice,
            'probabilities': {'ALLOW': 0.7, 'ASK': 0.2, 'BLOCK': 0.1},
            'confidence': 0.15, 'answer_confidence': 0.65}},
            'usage': {'truncated': False, 'state_tokens_dropped': 0, 'truncated_questions': []}}

class MockBackend:
    def __init__(self, decision='ALLOW', error=None):
        self.decision, self.error = decision, error
        self.inputs = []

    def predict(self, req):
        self.inputs.append(model_state(req))
        if self.error:
            raise self.error
        return parse_response(response(self.decision))

class EnforcementTests(unittest.TestCase):
    def test_wall_never_allows(self):
        for verdict in ('DENY', 'UNKNOWN', None):
            with self.subTest(verdict=verdict):
                data = request()
                data['wall']['verdict'] = verdict
                mock = MockBackend()
                result = Gatekeeper(mock).evaluate(data)
                self.assertEqual(result.output.decision, 'BLOCK')
                self.assertFalse(result.model_called)
                self.assertEqual(mock.inputs, [])

    def test_missing_wall(self):
        data = request()
        del data['wall']
        self.assertEqual(Gatekeeper(MockBackend()).evaluate(data).output.reason_code, 'WALL_UNVERIFIED')

    def test_missing_tool_arguments_even_when_wall_passes(self):
        for key in ('to', 'subject', 'body'):
            data = request()
            del data['action']['arguments'][key]
            result = Gatekeeper(MockBackend()).evaluate(data)
            self.assertEqual(result.output.reason_code, 'INVALID_ACTION')
            self.assertFalse(result.model_called)

    def test_argument_types_and_unknown_tools(self):
        for args in ({'to': [], 'subject': 'x', 'body': 'y'},
                     {'to': ['broken'], 'subject': 'x', 'body': 'y'},
                     {'to': 'a@example.test', 'subject': 'x', 'body': 'y'},
                     {'to': ['a@example.test'], 'subject': 3, 'body': 'y'},
                     {'to': ['a@example.test'], 'subject': 'x', 'body': 'y', 'extra': True}):
            data = request()
            data['action']['arguments'] = args
            self.assertEqual(Gatekeeper(MockBackend()).evaluate(data).output.reason_code, 'INVALID_ACTION')
        data = request()
        data['action']['tool'] = 'shell.execute'
        self.assertEqual(Gatekeeper(MockBackend()).evaluate(data).output.decision, 'BLOCK')

    def test_binding(self):
        data = request()
        data['wall']['evaluated_action_id'] = 'different'
        self.assertEqual(Gatekeeper(MockBackend()).evaluate(data).output.reason_code, 'INVALID_ACTION')

    def test_error_timeout_and_missing_output_never_allow(self):
        for error in (RuntimeError('failed'), TimeoutError('late')):
            result = Gatekeeper(MockBackend(error=error)).evaluate(request())
            self.assertEqual(result.output.decision, 'ASK')
            self.assertEqual(result.output.reason_code, 'MODEL_UNAVAILABLE')
        class Empty:
            def predict(self, req):
                return None
        self.assertEqual(Gatekeeper(Empty()).evaluate(request()).output.decision, 'ASK')

    def test_confirmation_and_incomplete_evidence(self):
        for field, reason in (('confirmation_required', 'CONFIRMATION_REQUIRED'),
                              ('evidence_complete', 'INSUFFICIENT_EVIDENCE')):
            data = request()
            data['verified_context'][field] = field == 'confirmation_required'
            self.assertEqual(Gatekeeper(MockBackend()).evaluate(data).output.reason_code, reason)
            # A semantic contradiction must win over either lower-priority rule.
            self.assertEqual(Gatekeeper(MockBackend('BLOCK')).evaluate(data).output.reason_code, 'TASK_MISMATCH')

    def test_exact_time_conflict_precedes_confirmation(self):
        data = request()
        data['user_request'] = 'Create a workshop on March 9, 2027, from 09:10 to 10:20 UTC.'
        data['action'].update(tool='calendar.create', arguments={
            'title': 'Workshop', 'start': '2027-03-09T09:30:00Z', 'end': '2027-03-09T10:40:00Z',
            'attendees': [], 'send_invites': False})
        data['verified_context']['confirmation_required'] = True
        result = Gatekeeper(MockBackend()).evaluate(data)
        self.assertEqual(result.output.reason_code, 'TASK_MISMATCH')
        self.assertFalse(result.model_called)
        data['action']['arguments'].update(start='2027-03-09T09:10:00Z', end='2027-03-09T10:20:00Z')
        self.assertEqual(Gatekeeper(MockBackend()).evaluate(data).output.reason_code, 'CONFIRMATION_REQUIRED')

    def test_bad_times_and_booleans(self):
        for start, end in [('2027-02-30T00:00:00Z', '2027-03-01T00:00:00Z'),
                           ('2027-03-01T01:00:00', '2027-03-01T02:00:00Z'),
                           ('2027-03-01T02:00:00Z', '2027-03-01T01:00:00Z')]:
            data = request()
            data['action'].update(tool='calendar.list', arguments={'start': start, 'end': end})
            self.assertEqual(Gatekeeper(MockBackend()).evaluate(data).output.reason_code, 'INVALID_ACTION')
        data = request()
        data['action'].update(tool='email.list', arguments={'unread_only': 'true'})
        self.assertEqual(Gatekeeper(MockBackend()).evaluate(data).output.reason_code, 'INVALID_ACTION')

    def test_fixture_metadata_cannot_leak(self):
        fixtures = [json.loads(x) for x in Path('data/gatekeeper_smoke_cases.jsonl').read_text(encoding='utf-8').splitlines()]
        mock = MockBackend()
        for case in fixtures:
            original = copy.deepcopy(case['request'])
            case.update(title='SECRET_TITLE', category='SECRET_CATEGORY', case_id='SECRET_ID',
                        expected={'decision': 'SECRET_LABEL', 'rationale': 'SECRET_RATIONALE'})
            Gatekeeper(mock).evaluate(case['request'])
            self.assertEqual(case['request'], original)
        self.assertTrue(mock.inputs)
        for state in mock.inputs:
            self.assertNotIn('SECRET_', state)
            self.assertEqual(set(json.loads(state)), {'authentic_user_request', 'untrusted_proposed_action', 'verified_context'})
        # Passing a whole fixture is rejected at the request boundary.
        result = Gatekeeper(mock).evaluate(fixtures[0])
        self.assertEqual(result.output.reason_code, 'INVALID_REQUEST')

    def test_ids_do_not_affect_model_input(self):
        first = request()
        second = copy.deepcopy(first)
        second.update(request_id='changed', task_id='changed')
        second['action']['action_id'] = 'changed'
        second['wall']['evaluated_action_id'] = 'changed'
        self.assertEqual(model_state(Request.model_validate(first)), model_state(Request.model_validate(second)))

    def test_execution_is_absent_for_all_decisions(self):
        class Trap(MockBackend):
            def execute(self, *args):
                raise AssertionError('Execution must never happen')
        for decision in ('ASK', 'BLOCK', 'ALLOW'):
            backend = Trap(decision)
            self.assertEqual(Gatekeeper(backend).evaluate(request()).output.decision, decision)
            self.assertEqual(len(backend.inputs), 1)

    def test_malformed_request(self):
        for data in (None, [], {}, {'action': None}):
            self.assertEqual(Gatekeeper(MockBackend()).evaluate(data).output.decision, 'BLOCK')

class AdapterTests(unittest.TestCase):
    def test_raw_probabilities_not_confidence(self):
        result = parse_response(response())
        self.assertEqual(result.decision, 'ALLOW')
        self.assertEqual(result.probabilities['ALLOW'], 0.7)
        self.assertEqual(result.raw['answers']['decision']['confidence'], 0.15)

    def test_bad_responses_fail_closed(self):
        bad = [None, {}, {'answers': {}}, response('EXECUTE')]
        for key, value in [('truncated', True), ('state_tokens_dropped', 1),
                           ('options', {'decision': {'distinct': 1}})]:
            raw = response()
            raw['usage'][key] = value
            bad.append(raw)
        raw = response()
        raw['answers']['decision']['probabilities']['ALLOW'] = float('nan')
        bad.append(raw)
        for raw in bad:
            self.assertIsNone(parse_response(raw).decision)
            self.assertIsNotNone(parse_response(raw).error)

    def test_initialization_failure_not_retried(self):
        backend = LayaBackend()
        backend.initialized = True
        backend.error = 'synthetic unavailable model'
        for _ in range(2):
            result = backend.predict(Request.model_validate(request()))
            self.assertFalse(result.called)
            self.assertIsNone(result.decision)

if __name__ == '__main__':
    unittest.main()
