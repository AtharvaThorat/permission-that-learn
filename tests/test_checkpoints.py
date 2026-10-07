"""Explicit mocks for checkpoint selection, metadata, failures and controls."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import warnings
from gatekeeper.laya_adapter import _worker, LayaBackend, Prediction, QUESTIONS, model_state
from gatekeeper.schemas import Request
from scripts.checkpoints import checkpoint_config, resolve_checkpoint
from scripts.compare_checkpoints import compare_checkpoints
from scripts.experiment import dump
from tests.test_gatekeeper import request, response
from tests.test_comparison import write_mock_run

class CheckpointTests(unittest.TestCase):
    def test_repository_pins_are_independent(self):
        config=checkpoint_config()
        for profile in ('baseline','typed-decisions'):
            spec=config[profile]
            self.assertEqual(resolve_checkpoint(profile=profile),(spec['checkpoint'],spec['revision']))
            self.assertEqual(resolve_checkpoint(checkpoint=spec['checkpoint']),(spec['checkpoint'],spec['revision']))
        self.assertNotEqual(config['baseline']['revision'],config['typed-decisions']['revision'])
        with self.assertRaises(ValueError):
            resolve_checkpoint(checkpoint='unregistered/repo')

    def test_requested_identity_reaches_same_agent_loader(self):
        for profile in ('baseline','typed-decisions'):
            checkpoint,revision=resolve_checkpoint(profile=profile)
            calls,sent=[],[]
            state=model_state(Request.model_validate(request()))
            inputs=iter((state,None))
            class Agent:
                def __init__(self,**kwargs):
                    calls.append(kwargs)
                    self.model_id,self.revision,self.device,self.cfg=checkpoint,revision,'cpu',{'max_len':512}
                    warnings.warn('synthetic calibration warning',RuntimeWarning)
                def system_one(self,actual_state,questions):
                    self_test.assertEqual(actual_state,state)
                    self_test.assertEqual(list(questions['decision']['criteria']),['ALLOW','ASK','BLOCK'])
                    return response()
            self_test=self
            pipe=SimpleNamespace(send=sent.append,recv=lambda:next(inputs),close=lambda:None)
            with patch.dict('sys.modules',{'laya':SimpleNamespace(Agent=Agent)}),patch.dict(os.environ),warnings.catch_warnings(record=True):
                _worker(pipe,checkpoint,revision,'.cache/mock','single')
            self.assertEqual(calls,[{'model_id_or_path':checkpoint,'revision':revision,'device':'cpu',
                                    'fast':False,'compile':False,'backend':'eager'}])
            self.assertEqual(sent[0]['actual_checkpoint'],checkpoint)
            self.assertEqual(sent[0]['revision'],revision)
            self.assertEqual(sent[0]['load_warnings'][0]['message'],'synthetic calibration warning')
            self.assertEqual(sent[1]['api_calls'],1)

    def test_failed_loading_does_not_switch_checkpoint(self):
        calls,sent=[],[]
        def broken(**kwargs):
            calls.append(kwargs)
            raise OSError('synthetic download failure')
        pipe=SimpleNamespace(send=sent.append,close=lambda:None)
        with patch.dict('sys.modules',{'laya':SimpleNamespace(Agent=broken)}),patch.dict(os.environ):
            _worker(pipe,'explicit/typed','b'*40,'.cache/mock','single')
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['model_id_or_path'],'explicit/typed')
        self.assertIn('synthetic download failure',sent[0]['error'])
        self.assertNotIn('actual_checkpoint',sent[0])

    def test_actual_metadata_saved_and_mismatch_fails(self):
        for actual in ('explicit/typed','wrong/model'):
            status={'ready':True,'actual_checkpoint':actual,'revision':'b'*40,'device':'cpu',
                    'config':{'max_len':1024},'load_warnings':[{'message':'mock warning'}]}
            pipe=SimpleNamespace(poll=lambda timeout:True,recv=lambda:status,close=lambda:None)
            child=SimpleNamespace(close=lambda:None)
            process=SimpleNamespace(start=lambda:None,is_alive=lambda:False,join=lambda timeout:None)
            context=SimpleNamespace(Pipe=lambda:(pipe,child),Process=lambda **kwargs:process)
            backend=LayaBackend('explicit/typed','b'*40)
            with patch('gatekeeper.laya_adapter.mp.get_context',return_value=context),patch(
                'gatekeeper.laya_adapter.importlib.util.find_spec',return_value=object()),patch.object(
                backend,'_infer',return_value=Prediction(decision='ALLOW')):
                backend.initialize()
            with tempfile.TemporaryDirectory() as tmp:
                target=Path(tmp)/'metadata.json'
                dump(target,backend.metadata)
                saved=json.loads(target.read_text(encoding='utf-8'))
                self.assertEqual(saved['actual_checkpoint'],actual)
                self.assertEqual(saved['requested_revision'],'b'*40)
                self.assertEqual(saved['config']['max_len'],1024)
            self.assertEqual(backend.error is None,actual=='explicit/typed')

    def test_controls_unchanged_and_no_labels_in_input(self):
        archive = Path('benchmarks/development')
        manifest = json.loads((archive/'source-hashes.json').read_text())
        for name, digest in manifest.items():
            self.assertEqual(hashlib.sha256(Path(name).read_bytes()).hexdigest(), digest)
        self.assertEqual(QUESTIONS, json.loads((archive/'single-question.json').read_text()))
        envelope={'request':request(),'expected':{'decision':'SECRET_LABEL'},'title':'SECRET_TITLE'}
        self.assertNotIn('SECRET_',model_state(Request.model_validate(envelope['request'])))

def checkpoint_mock(path,checkpoint,revision,called=True):
    summary=write_mock_run(path,'single',called)
    summary.update(question_template=QUESTIONS,python='mock',platform='mock',host='mock',processor='mock')
    summary['model'].update(selected_checkpoint=checkpoint,requested_revision=revision,
        actual_checkpoint=checkpoint if called else None,revision=revision if called else None,
        inference_settings={'device':'cpu'},runtime={'cpu_threads':1,'cpu_interop_threads':1})
    dump(path/'summary.json',summary)
    row=json.loads((path/'predictions.jsonl').read_text(encoding='utf-8'))
    row.update(raw_model_decision=row['combined_semantic_decision'],truncated=False if called else None,
               output={'decision':row['final_decision'],'reason_code':row['reason_code']})
    (path/'predictions.jsonl').write_text(json.dumps(row)+'\n',encoding='utf-8')
    return summary

class CheckpointReportTests(unittest.TestCase):
    def test_ask_to_allow_on_expected_block_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp)/'base',Path(tmp)/'typed'
            checkpoint_mock(a,'base','a'*40)
            checkpoint_mock(b,'typed','b'*40)
            row=json.loads((b/'predictions.jsonl').read_text(encoding='utf-8'))
            row.update(final_decision='ALLOW',raw_model_decision='ALLOW')
            (b/'predictions.jsonl').write_text(json.dumps(row)+'\n',encoding='utf-8')
            result=compare_checkpoints(a,b)
            self.assertEqual(result['changes']['unchanged'],['synthetic'])
            self.assertEqual(result['ask_to_allow_on_expected_block_cases'],['synthetic'])
            self.assertEqual(result['metrics']['typed-decisions']['incorrect_automatic_allowances'],['synthetic'])

    def test_failed_checkpoint_has_no_model_accuracy_or_fake_latency(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp)/'base',Path(tmp)/'typed'
            checkpoint_mock(a,'base','a'*40)
            checkpoint_mock(b,'typed','b'*40,False)
            result=compare_checkpoints(a,b)
            self.assertEqual(result['status'],'incomplete_execution')
            self.assertIsNone(result['metrics']['typed-decisions']['final_accuracy'])
            self.assertIsNone(result['metrics']['typed-decisions']['warm_complete_decision_seconds']['median'])
            self.assertEqual(result['changes']['not_comparable'],['synthetic'])

    def test_different_configs_allowed_but_prompt_order_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp)/'base',Path(tmp)/'typed'
            checkpoint_mock(a,'base','a'*40)
            sb=checkpoint_mock(b,'typed','b'*40)
            sb['model']['config']={'max_len':1024}
            dump(b/'summary.json',sb)
            result=compare_checkpoints(a,b)
            self.assertIn('max_len',result['configuration_differences'])
            sb['question_template']=copy.deepcopy(QUESTIONS)
            sb['question_template']['decision']['criteria']=dict(reversed(list(QUESTIONS['decision']['criteria'].items())))
            dump(b/'summary.json',sb)
            with self.assertRaises(ValueError):
                compare_checkpoints(a,b)
