"""Validate one local OpenAI-compatible tool-call response.

This script talks only to the configured local vLLM endpoint. It does not
download models, execute AgentDojo tools, or call paid/external services.
"""
import argparse
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TOOL = {
    "type": "function",
    "function": {
        "name": "get_day_calendar_events",
        "description": "Read calendar events for one day.",
        "parameters": {
            "type": "object",
            "properties": {"day": {"type": "string"}},
            "required": ["day"],
            "additionalProperties": False,
        },
    },
}


def request(base_url, model, api_key, timeout, *, messages=None, automatic=False):
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "Use the calendar tool to read events for 2024-05-15.",
            }
        ],
        "tools": [TOOL],
        "tool_choice": {"type": "function", "function": {"name": TOOL["function"]["name"]}},
        "temperature": 0,
        "max_tokens": 128,
    }
    if messages is not None:
        payload['messages'] = messages
    if automatic:
        payload['tool_choice'] = 'auto'
    payload['max_tokens'] = 512
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        base_url.rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def validate(response, expected_model):
    if response.get('model') != expected_model:
        raise ValueError('Server response model identity mismatch')
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("Response has no choices")
    message = choices[0].get("message", {})
    calls = message.get("tool_calls")
    if not isinstance(calls, list) or not calls:
        raise ValueError("Response does not contain tool_calls")
    call = calls[0]
    function = call.get("function", {})
    name = function.get("name")
    arguments = function.get("arguments")
    if not isinstance(name, str) or not name:
        raise ValueError("Tool call has no function name")
    if not isinstance(arguments, str):
        raise ValueError("Tool call arguments are not JSON text")
    parsed = json.loads(arguments)
    if not isinstance(parsed, dict):
        raise ValueError("Tool call arguments are not a JSON object")
    if name != TOOL["function"]["name"] or parsed.get("day") != "2024-05-15":
        raise ValueError(f"Unexpected tool call: {name}({parsed!r})")
    return {
        "validation": "passed",
        "endpoint_scope": "local_only",
        "model": expected_model,
        "tool_call": {"name": name, "arguments": parsed},
        "choice_count": len(choices),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_API_BASE", "http://127.0.0.1:8000/v1"))
    parser.add_argument("--model", default="Qwen2.5-7B-Instruct")
    parser.add_argument("--api-key-env", default="BLACKBOX_ACTOR_API_KEY")
    parser.add_argument("--output", type=Path, default=Path("handoff/validation_response.json"))
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument('--multi-turn', action='store_true')
    args = parser.parse_args()
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        raise SystemExit(f"Missing local credential environment variable: {args.api_key_env}")
    try:
        response = request(args.base_url, args.model, api_key, args.timeout, automatic=args.multi_turn)
        proof = validate(response, args.model)
        proof['raw_response'] = response
        if args.multi_turn:
            message = response['choices'][0]['message']
            messages = [{'role': 'user', 'content': 'Use the calendar tool to read events for 2024-05-15.'},
                        {k: message[k] for k in ('role', 'content', 'tool_calls') if k in message}]
            for call in message['tool_calls']:
                messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': 'No events on this day.'})
            continuation = request(args.base_url, args.model, api_key, args.timeout, messages=messages, automatic=True)
            if continuation.get('model') != args.model or continuation['choices'][0]['finish_reason'] != 'stop':
                raise ValueError('Model did not complete the controlled multi-turn tool interaction')
            if not continuation['choices'][0]['message'].get('content'):
                raise ValueError('Missing continuation answer')
            proof['continuation'] = continuation
            proof['scope'] = 'controlled simulated tool result; no native task executed'
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Local tool-call validation failed: {exc}") from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof, indent=2))


if __name__ == "__main__":
    main()
