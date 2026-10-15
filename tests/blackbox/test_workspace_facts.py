from datetime import datetime
from types import SimpleNamespace as NS
from blackbox.actions import bind
from blackbox.contracts import Proposal
from integrations.agentdojo.context import Metadata, WorkspaceFacts
from integrations.agentdojo.tools import NativeTools
from .helpers import fixture

def environment():
    file = NS(owner='owner@example.com', shared_with={}, last_modified=datetime(2026, 1, 1), content='notes')
    return NS(cloud_drive=NS(files={'notes-7': file}), inbox=NS(emails={}), calendar=NS(events={}))

def test_missing_resource_and_missing_label_fail_closed():
    f = fixture()
    facts = WorkspaceFacts(Metadata(provenance='test-sidecar', version='1'))
    action = bind(Proposal('c', 'get_file_by_id', {'file_id': 'missing'}), 'a', NativeTools(f.runtime), facts, f.wall, environment(), 32000)
    assert f.wall.evaluate(action).verdict == 'UNRESOLVED'
    f.wall.policy.require_labels = True
    action = bind(Proposal('c', 'get_file_by_id', {'file_id': 'notes-7'}), 'a', NativeTools(f.runtime), facts, f.wall, environment(), 32000)
    assert f.wall.evaluate(action).verdict == 'UNRESOLVED'

def test_sidecar_scope_and_content_freshness():
    f, env = fixture(), environment()
    facts = WorkspaceFacts(Metadata(provenance='test', version='1', labels={'file': {'notes-7': 'public'}}))
    proposal = Proposal('c', 'get_file_by_id', {'file_id': 'notes-7'})
    a = bind(proposal, 'a', NativeTools(f.runtime), facts, f.wall, env, 32000)
    env.cloud_drive.files['notes-7'].content = 'changed by earlier action'
    b = bind(proposal, 'a', NativeTools(f.runtime), facts, f.wall, env, 32000)
    assert a.state_version != b.state_version
    assert 'changed by earlier action' not in b.facts_json
    f.wall.policy.resource_scopes = {'file': []}
    c = bind(proposal, 'a', NativeTools(f.runtime), facts, f.wall, env, 32000)
    assert f.wall.evaluate(c).verdict == 'DENY'
