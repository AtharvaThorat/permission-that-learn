"""Explicit mocks for combination/enforcement/API shape; no model downloads."""
import copy
import itertools
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from gatekeeper.laya_adapter import QUESTIONS, _worker, parse_response, model_state
from gatekeeper.questions import DECOMPOSED_QUESTIONS, combine_answers
from gatekeeper.policy import Gatekeeper
from gatekeeper.schemas import Request
from scripts.experiment import config, new_output_dir
from tests.test_gatekeeper import request, response

def decomposed_response(relation='SUPPORTED', details='RESOLVED'):
    raw = {'answers': {}, 'usage': {'truncated': False, 'state_tokens_dropped': 0, 'truncated_questions': []}}
    for qid, choice in [('task_relation', relation), ('authorization_details', details)]:
        raw['answers'][qid] = {'type': 'choice', 'choice': choice,
            'probabilities': {key: 0.8 if key == choice else 0.1 for key in DECOMPOSED_QUESTIONS[qid]['criteria']},
            'confidence': 0.1, 'answer_confidence': 0.6}
    return raw

class Stub:
    def __init__(self, raw):
        self.raw, self.inputs = raw, []
    def predict(self, req):
        self.inputs.append(model_state(req))
        return parse_response(self.raw, 'decomposed')

class QuestionDesignTests(unittest.TestCase):
    def test_all_nine_combinations_and_override_precedence(self):
        relations = ('SUPPORTED', 'CONTRADICTORY', 'UNCLEAR')
        details = ('RESOLVED', 'UNRESOLVED', 'UNCLEAR')
        expected = [['ALLOW', 'ASK', 'ASK'], ['BLOCK', 'BLOCK', 'BLOCK'], ['ASK', 'ASK', 'ASK']]
        for i, relation in enumerate(relations):
            for j, detail in enumerate(details):
                for confirm, complete in itertools.product((True, False), repeat=2):
                    with self.subTest(relation=relation, detail=detail, confirm=confirm, complete=complete):
                        data = request()
                        data['verified_context'].update(confirmation_required=confirm, evidence_complete=complete)
                        result = Gatekeeper(Stub(decomposed_response(relation, detail))).evaluate(data)
                        self.assertEqual(result.combined_semantic_decision, expected[i][j])
                        final = 'BLOCK' if relation == 'CONTRADICTORY' else 'ASK' if confirm or not complete else expected[i][j]
                        self.assertEqual(result.output.decision, final)
                        if relation == 'CONTRADICTORY':
                            self.assertEqual(result.output.reason_code, 'TASK_MISMATCH')
                        elif confirm:
                            self.assertEqual(result.output.reason_code, 'CONFIRMATION_REQUIRED')
                        elif not complete:
                            self.assertEqual(result.output.reason_code, 'INSUFFICIENT_EVIDENCE')
                        self.assertIsNone(result.raw_model_decision)

    def test_reason_mapping(self):
        for relation, detail, reason in [('UNCLEAR', 'RESOLVED', 'UNCERTAIN'),
                                        ('SUPPORTED', 'UNCLEAR', 'UNCERTAIN'),
                                        ('SUPPORTED', 'UNRESOLVED', 'NEEDS_CLARIFICATION')]:
            self.assertEqual(Gatekeeper(Stub(decomposed_response(relation, detail))).evaluate(request()).output.reason_code, reason)

    def test_missing_malformed_and_truncated_answers(self):
        invalid = [None, {}, {'answers': {}}, {'answers': []}, decomposed_response('INVALID')]
        for qid in DECOMPOSED_QUESTIONS:
            for mutation in ('missing', 'type', 'value', 'probability', 'abstained'):
                raw = decomposed_response()
                if mutation == 'missing':
                    del raw['answers'][qid]
                elif mutation == 'type':
                    raw['answers'][qid]['type'] = 'score'
                elif mutation == 'value':
                    raw['answers'][qid]['choice'] = []
                elif mutation == 'probability':
                    raw['answers'][qid]['probabilities'] = {'INVALID': float('nan')}
                else:
                    raw['answers'][qid]['low_confidence'] = True
                invalid.append(raw)
        for key, value in [('truncated', True), ('state_tokens_dropped', 2),
                           ('truncated_questions', ['authorization_details']), ('options', {'task_relation': {}})]:
            raw = decomposed_response()
            raw['usage'][key] = value
            invalid.append(raw)
        raw = decomposed_response('CONTRADICTORY')
        del raw['answers']['authorization_details']
        invalid.append(raw)  # Partial contradiction is unusable, not a valid two-answer result.
        for raw in invalid:
            with self.subTest(raw=raw):
                result = Gatekeeper(Stub(raw)).evaluate(request())
                self.assertIsNone(result.combined_semantic_decision)
                self.assertEqual(result.output.decision, 'ASK')
                self.assertEqual(result.output.reason_code, 'MODEL_UNAVAILABLE')
                self.assertIsNotNone(result.error)

    def test_probability_distributions_are_separate(self):
        raw = decomposed_response()
        result = parse_response(raw, 'decomposed')
        self.assertEqual(result.probabilities_by_question, {k: v['probabilities'] for k, v in raw['answers'].items()})
        self.assertIsNone(result.probabilities)  # No synthesized authorization probability.
        self.assertIsNone(result.raw_decision)
        self.assertEqual(result.decision, 'ALLOW')

    def test_hard_wall_and_validation_unchanged(self):
        for verdict in ('DENY', 'UNKNOWN', None):
            data = request()
            data['wall']['verdict'] = verdict
            stub = Stub(decomposed_response())
            result = Gatekeeper(stub).evaluate(data)
            self.assertEqual(result.output.decision, 'BLOCK')
            self.assertFalse(result.model_called)
            self.assertEqual(stub.inputs, [])
        data = request()
        del data['action']['arguments']['to']
        self.assertEqual(Gatekeeper(Stub(decomposed_response())).evaluate(data).output.reason_code, 'INVALID_ACTION')

    def test_labels_excluded_for_decomposed_mode(self):
        stub = Stub(decomposed_response())
        envelope = {'request': request(), 'expected': {'decision': 'SECRET_LABEL', 'rationale': 'SECRET_RATIONALE'},
                    'title': 'SECRET_TITLE', 'category': 'SECRET_CATEGORY', 'case_id': 'SECRET_CASE'}
        Gatekeeper(stub).evaluate(envelope['request'])
        serialized = stub.inputs[0] + json.dumps(DECOMPOSED_QUESTIONS)
        self.assertNotIn('SECRET_', serialized)
        self.assertEqual(stub.inputs[0], model_state(Request.model_validate(request())))
        self.assertEqual(Gatekeeper(stub).evaluate(envelope).output.reason_code, 'INVALID_REQUEST')

    def test_both_questions_in_one_api_call(self):
        calls, sent = [], []
        state = model_state(Request.model_validate(request()))
        inputs = iter((state, None))
        class Agent:
            def __init__(self, **kwargs):
                self.model_id, self.revision, self.device, self.cfg = 'mock', 'mock-revision', 'cpu', {}
            def system_one(self, actual_state, questions):
                calls.append((actual_state, questions))
                return decomposed_response()
        pipe = SimpleNamespace(send=sent.append, recv=lambda: next(inputs), close=lambda: None)
        with patch.dict('sys.modules', {'laya': SimpleNamespace(Agent=Agent)}), patch.dict(os.environ):
            _worker(pipe, 'mock', 'mock-revision', '.cache/mock', 'decomposed')
        self.assertEqual(calls, [(state, DECOMPOSED_QUESTIONS)])
        self.assertEqual(sent[-1]['api_calls'], 1)

    def test_archived_single_template_and_decisions_unchanged(self):
        archive = Path(config()['baseline_archive'])
        self.assertEqual(QUESTIONS, json.loads((archive / 'single-question.json').read_text(encoding='utf-8')))
        fixtures = [json.loads(x) for x in Path('data/gatekeeper_smoke_cases.jsonl').read_text(encoding='utf-8').splitlines()]
        rows = [json.loads(x) for x in (archive / 'predictions.jsonl').read_text(encoding='utf-8').splitlines()]
        for case, row in zip(fixtures, rows):
            # Replay saved outputs solely as a regression test, never as evaluation results.
            backend = SimpleNamespace(predict=lambda req, raw=row['raw_model_output']: parse_response(raw))
            result = Gatekeeper(backend).evaluate(case['request'])
            self.assertEqual(result.output.model_dump(), row['output'])

    def test_output_directory_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = new_output_dir(Path(tmp) / 'experiment')
            with self.assertRaises(FileExistsError):
                new_output_dir(path)

    def test_invalid_combination_rejected(self):
        for relation, detail in [('ALLOW', 'RESOLVED'), ('SUPPORTED', None)]:
            with self.assertRaises(ValueError):
                combine_answers(relation, detail)
