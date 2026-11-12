"""MCP server: AgentDojo's simulated Workspace tools, every call guarded by the Wall, laya-cybersec and permission memory.

Any MCP client (Claude Desktop, Claude Code and others) connects to it; the client's model proposes tool calls and this
server decides each one with the repository's controller, exactly as in the chat demo. The data is simulated: nothing
real is read, sent or shared.

    python -m grids_plugin.mcp_server --laya-cache D:\\grids-plugin\\hf-cache --approvals D:\\grids-plugin\\approvals
    python -m grids_plugin.mcp_server approve --approvals D:\\grids-plugin\\approvals    (in a second terminal)
"""
import argparse
import json
import threading
import time
from pathlib import Path
from uuid import uuid4

from .guard import CybersecGate, TimedWall, gate_output, ledger
from .session import INJECTION, SCENARIOS, LiveAudit

INSTRUCTIONS = ("Tools act on a simulated workspace (Emma Johnson's email, calendar and cloud drive). Every call is checked by "
                "a permission guard before it runs; a refused call returns a PermissionError and must not be retried in "
                "another form. Call set_user_request first with the user's exact request.")


class GuardedWorkspace:
    """One simulated Workspace and one guarded episode at a time; `set_user_request` starts a new one."""

    def __init__(self, scanner=None, *, memory=None, memory_mode='grants', scenario='Free chat', confirm_shares=True,
                 approvals=None, approval_wait=60.0):
        from agentdojo.functions_runtime import FunctionsRuntime
        from agentdojo.task_suite.load_suites import get_suite
        from grids.benchmarks.agentdojo.codec import NativeCodec
        from grids.benchmarks.agentdojo.context import Metadata, suite_facts
        from grids.benchmarks.agentdojo.tools import NativeTools
        from grids.core.config import Config, WallConfig
        from grids.core.controller import Controller
        from grids.core.execution import GuardedExecutor
        from grids.core.permissions.approvals import FileApprovalProvider
        from grids.core.permissions.ptl_adapter import PtlWall
        from grids.core.state import Clock
        suite = get_suite('v1.2.2', 'workspace')
        goal = SCENARIOS[scenario]['goal']
        self.env = suite.load_and_inject_default_environment(
            {v: INJECTION.format(goal=goal) for v in suite.get_injection_vector_defaults()} if goal else {})
        self.runtime = FunctionsRuntime(suite.tools)
        self.tools = NativeTools(self.runtime, True)
        wall_config = WallConfig(confirm_capabilities=['share'] if confirm_shares else [])
        self.wall = TimedWall(PtlWall.from_clean_environment(wall_config, suite.load_and_inject_default_environment({}),
                                                             'workspace'))
        self.history, self.decisions, self.lock = [], [], threading.Lock()
        self.gate = CybersecGate(scanner, self.wall, lambda: self.history) if scanner else None
        self.mode = 'wall_gatekeeper' if scanner else 'wall_only'
        self.clock, self.audit = Clock(), LiveAudit()
        self.approvals_dir = Path(approvals) if approvals else Path(__file__).resolve().parents[1] / 'approvals'
        # Permission memory answers laya-cybersec's own asks, so it needs the Gatekeeper (as in the repository).
        self.memory = memory if scanner and memory_mode != 'off' else None
        self.memory_mode, self.memory_events = (memory_mode if self.memory else 'off'), []
        config = Config(mode=self.mode, wall=wall_config, learning_enabled=self.memory is not None)
        facts = suite_facts('workspace', Metadata.model_validate(json.loads(Path(config.wall.metadata_path).read_text(encoding='utf-8'))))
        approvals = FileApprovalProvider(self.approvals_dir, wait_seconds=approval_wait)
        if self.memory:
            approvals = self.memory.provider(approvals, self.memory_mode, record=self.memory_events.append)
        self.controller = Controller(config, None, self.wall, self.gate, facts, approvals,
                                     GuardedExecutor(), self.clock, self.audit, NativeCodec())
        self.laya_device = getattr(scanner, 'device', 'cpu')
        self.set_user_request('(the MCP client did not state the request)')

    def set_user_request(self, request):
        from grids.core.state import Episode
        now = self.clock.monotonic()
        # A new request is a new episode: no authorization carries over from the previous one.
        self.episode = Episode(uuid4().hex, request, self.mode, self.wall.version, now, now + 8 * 3600)
        self.history = [{'role': 'user', 'content': request}]

    def schemas(self):
        return [tool['function'] for tool in self.tools.schemas()]

    def call(self, name, arguments):
        """Returns (text for the model, was it refused)."""
        from agentdojo.agent_pipeline.tool_execution import tool_result_to_str
        from grids.core.audit import EpisodeAudit
        from grids.core.contracts import Proposal
        with self.lock:
            episode = self.episode
            episode.calls += 1
            call_id = f'mcp_{episode.calls}'
            self.history.append({'role': 'assistant', 'content': None, 'tool_calls': [
                {'id': call_id, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments)}}]})
            scans, checks = len(self.gate.scans) if self.gate else 0, len(self.wall.checks)
            outcome = self.controller.mediate(episode, Proposal(call_id, name, arguments), f'{episode.episode_id}:{episode.calls}:0',
                                              self.tools, self.runtime, self.env, EpisodeAudit(self.audit, episode, self.clock))
            text = tool_result_to_str(outcome.result) if outcome.executed else (outcome.error or 'PermissionError: refused')
            self.history.append({'role': 'tool', 'tool_call_id': call_id, 'content': text})
            wall = self.wall.checks[checks]['verdict'] if len(self.wall.checks) > checks else None
            scan = self.gate.scans[scans] if self.gate and len(self.gate.scans) > scans else None
            action_id = f'{episode.episode_id}:{episode.calls}:0'
            remembered = [e for e in self.memory_events if e['binding']['action_id'] == action_id]
            approval = [e['reason_code'] for e in self.audit.events
                        if e['event'] == 'approval' and e['action_id'] == f'{episode.episode_id}:{episode.calls}:0']
            asked = any(e['event'] == 'pending_approval' and e['action_id'] == f'{episode.episode_id}:{episode.calls}:0'
                        for e in self.audit.events)
            by_grant = bool(remembered) and remembered[-1]['action'] == 'USE_EXISTING_GRANT'
            self.decisions.append({'tool': name, 'arguments': arguments, 'wall': wall,
                                   'laya_cybersec': gate_output(scan['probabilities']) if scan else None,
                                   'memory': ('answered by remembered permission' if by_grant else 'asked') if remembered else None,
                                   'decision': 'ASK' if asked else outcome.decision,
                                   'person': ('not asked: remembered permission' if by_grant else
                                              approval[0].lower() if approval else 'no answer') if asked else None,
                                   'reason': outcome.reason, 'executed': outcome.executed})
            return text, not outcome.executed

    def report(self):
        compute = ledger(self.wall.checks, [], self.gate.scans if self.gate else [], laya_device=self.laya_device)
        used = sum(e['action'] == 'USE_EXISTING_GRANT' for e in self.memory_events)
        return {'decisions': self.decisions, 'compute': {k: v for k, v in compute.items() if not k.startswith(('agent', 'judge'))},
                'memory': {'mode': self.memory_mode, 'eligible_asks': len(self.memory_events), 'answered_by_grant': used,
                           'grants': self.memory.grants() if self.memory else []}}


def build_server(workspace):
    from mcp import types
    from mcp.server.lowlevel import Server
    extra = [types.Tool(name='set_user_request', description="Start a task: pass the user's exact request. "
                        'Checks use it to judge later tool calls.',
                        input_schema={'type': 'object', 'properties': {'request': {'type': 'string'}}, 'required': ['request']}),
             types.Tool(name='guard_report', description='Every decision the permission guard made, and the compute it used.',
                        input_schema={'type': 'object', 'properties': {}})]

    async def list_tools(context, params):
        return types.ListToolsResult(tools=extra + [types.Tool(name=s['name'], description=s['description'],
                                                               input_schema=s['parameters']) for s in workspace.schemas()])

    async def call_tool(context, params):
        import anyio
        arguments = params.arguments or {}
        if params.name == 'set_user_request':
            workspace.set_user_request(str(arguments.get('request', '')))
            text, refused = 'Request recorded. Guarded tool calls will be checked against it.', False
        elif params.name == 'guard_report':
            text, refused = json.dumps(workspace.report(), indent=1, default=str), False
        else:
            # The Wall, laya-cybersec and a possible approval wait block, so they run off the event loop.
            text, refused = await anyio.to_thread.run_sync(workspace.call, params.name, arguments)
        return types.CallToolResult(content=[types.TextContent(type='text', text=text)], is_error=refused)

    return Server('grids-permission-guard', version='0.1.0', instructions=INSTRUCTIONS,
                  on_list_tools=list_tools, on_call_tool=call_tool)


def approve_console(directory, memory_store=None):
    """Second terminal: the person approves or rejects each waiting action. The MCP client's model cannot.

    `r` approves and remembers (an exact grant in the same permission store as the server)."""
    from grids.core.permissions.approvals import respond
    memory = None
    if memory_store:
        from .memory import Memory
        memory = Memory(memory_store)
    directory, seen = Path(directory), set()
    print(f'Watching {directory} for actions that need approval. Ctrl+C to stop.')
    while True:
        for path in sorted(directory.glob('*.json')):
            if path.name.endswith('.response.json') or path in seen or path.with_name(path.stem + '.response.json').exists():
                continue
            seen.add(path)
            pending = json.loads(path.read_text(encoding='utf-8'))
            action = pending['action']
            print(f"\n{action['tool']} {action['arguments_json']}\nreason: {pending['reason']}")
            can_remember = memory is not None and memory.rememberable(pending)
            answer = input('Approve? [y = yes, r = yes and remember, N = no] ' if can_remember else 'Approve? [y/N] ').strip().lower()
            try:
                if answer == 'r' and can_remember:
                    print('remembered as grant', memory.remember(path)[:8])
                respond(path, answer in ('y', 'r'))
                print('approved' if answer in ('y', 'r') else 'rejected')
            except ValueError as exc:
                print(f'not applied: {exc}')
        time.sleep(0.5)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('command', nargs='?', default='serve', choices=['serve', 'approve'])
    parser.add_argument('--approvals', default=str(Path(__file__).resolve().parents[1] / 'approvals'))
    parser.add_argument('--laya-cache', help='folder for the laya-cybersec download; omit for the Wall only')
    parser.add_argument('--scenario', default='Free chat', choices=list(SCENARIOS))
    parser.add_argument('--approval-wait', type=float, default=60.0)
    parser.add_argument('--memory', default='grants', choices=['off', 'grants', 'shadow', 'active'],
                        help='permission memory mode (needs --laya-cache)')
    parser.add_argument('--memory-store', default=str(Path(__file__).resolve().parents[1] / 'memory' / 'permissions.sqlite'),
                        help="SQLite file for remembered permissions (the repository's PermissionStore)")
    args = parser.parse_args(argv)
    if args.command == 'approve':
        return approve_console(args.approvals, args.memory_store)
    import anyio
    from mcp.server.stdio import stdio_server
    scanner = memory = None
    if args.laya_cache:
        from .cybersec import Scanner, download
        scanner = Scanner(download(args.laya_cache))
        if args.memory != 'off':
            from .memory import Memory
            memory = Memory(args.memory_store)
    workspace = GuardedWorkspace(scanner, memory=memory, memory_mode=args.memory, scenario=args.scenario,
                                 approvals=args.approvals, approval_wait=args.approval_wait)
    server = build_server(workspace)

    async def serve():
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(serve)


if __name__ == '__main__':
    main()
