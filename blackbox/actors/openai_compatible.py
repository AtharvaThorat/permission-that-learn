"""Lazy, connection-reusing HTTP client; no SDK provider defaults or discovery."""
import os
import time
from blackbox.actions import parse_json

class OpenAICompatibleActor:
    def __init__(self, config):
        self.config = config
        self.client = None
        self.closed = False
        self.last_metadata = {}

    def respond(self, messages, tools, timeout):
        if self.closed:
            raise RuntimeError('ACTOR_CLOSED')
        import httpx
        if self.client is None:
            self.client = httpx.Client(follow_redirects=False, trust_env=False)
        key = os.environ.get(self.config.api_key_env)
        if not key:
            raise RuntimeError('ACTOR_CREDENTIAL_ENV_MISSING')
        body = {'model': self.config.served_model_name, 'messages': messages,
                'tools': tools, 'tool_choice': 'auto', 'stream': False,
                'temperature': self.config.temperature, 'top_p': self.config.top_p,
                'max_tokens': self.config.max_output_tokens}
        if self.config.thinking_enabled is not None:
            body['chat_template_kwargs'] = {'enable_thinking': self.config.thinking_enabled}
        if self.config.seed is not None:
            body['seed'] = self.config.seed
        self.last_metadata = {}
        deadline = time.monotonic() + min(timeout, self.config.timeout_seconds)
        for attempt in range(self.config.max_retries + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('ACTOR_TIMEOUT')
            try:
                with self.client.stream('POST', self.config.base_url.rstrip('/') + '/chat/completions',
                                        json=body, headers={'Authorization': 'Bearer ' + key},
                                        timeout=remaining) as response:
                    response.raise_for_status()
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > self.config.max_response_bytes or time.monotonic() > deadline:
                            raise TimeoutError('ACTOR_RESPONSE_BUDGET')
                        chunks.append(chunk)
                parsed = parse_json(b''.join(chunks).decode('utf-8'))
                self.last_metadata = {'usage': parsed.get('usage'), 'model': parsed.get('model'),
                                      'system_fingerprint': parsed.get('system_fingerprint')}
                choices = parsed['choices']
                if len(choices) != 1 or choices[0].get('finish_reason') not in ('stop', 'tool_calls'):
                    raise ValueError('ACTOR_INCOMPLETE_RESPONSE')
                return choices[0]['message']
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                retryable = isinstance(exc, httpx.TransportError) or exc.response.status_code in (429, 500, 502, 503, 504)
                if not retryable or attempt == self.config.max_retries:
                    raise RuntimeError('ACTOR_TRANSPORT_FAILURE') from exc
        raise RuntimeError('ACTOR_RETRY_EXHAUSTED')

    def close(self):
        self.closed = True
        if self.client is not None:
            self.client.close()
