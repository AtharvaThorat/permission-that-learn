"""Mock HTTP transport only; no endpoint probing and no real inference."""
import json
import httpx
import pytest
from blackbox.actors.openai_compatible import OpenAICompatibleActor
from blackbox.config import ActorConfig

def test_actor_uses_explicit_model_template_tools_and_connection(monkeypatch):
    monkeypatch.setenv('BLACKBOX_ACTOR_API_KEY', 'test-key-never-logged')
    seen = []
    def handle(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'Done'}}]})
    actor = OpenAICompatibleActor(ActorConfig())
    actor.client = httpx.Client(transport=httpx.MockTransport(handle))
    client = actor.client
    try:
        first = actor.respond([{'role': 'user', 'content': 'Task'}], [], 2)
        second = actor.respond([{'role': 'user', 'content': 'Task'}], [], 2)
        assert first['content'] == second['content'] == 'Done'
        assert actor.client is client and len(seen) == 2
        assert seen[0]['model'] == 'Qwen3-8B'
        assert seen[0]['chat_template_kwargs'] == {'enable_thinking': False}
        assert seen[0]['stream'] is False
    finally:
        actor.close()

def test_actor_retry_budget_has_no_provider_fallback(monkeypatch):
    monkeypatch.setenv('BLACKBOX_ACTOR_API_KEY', 'test-only')
    hosts = []
    def handle(request):
        hosts.append(request.url.host)
        return httpx.Response(503)
    actor = OpenAICompatibleActor(ActorConfig(max_retries=1))
    actor.client = httpx.Client(transport=httpx.MockTransport(handle))
    try:
        with pytest.raises(RuntimeError, match='TRANSPORT_FAILURE'):
            actor.respond([], [], 2)
        assert hosts == ['127.0.0.1', '127.0.0.1']
    finally:
        actor.close()

def test_truncated_actor_output_never_becomes_action(monkeypatch):
    monkeypatch.setenv('BLACKBOX_ACTOR_API_KEY', 'test-only')
    actor = OpenAICompatibleActor(ActorConfig())
    actor.client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json={'choices': [{'finish_reason': 'length', 'message': {'role': 'assistant', 'content': 'partial'}}]})))
    try:
        with pytest.raises(ValueError, match='INCOMPLETE_RESPONSE'):
            actor.respond([], [], 2)
    finally:
        actor.close()
