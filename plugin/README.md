# GRIDS permission plugin

A demonstration of the project's guard in front of a working assistant. It ships in two forms that share one guard:

| Form | Who proposes actions | Use it for |
|---|---|---|
| **Chat demo** (`grids_plugin.app`, Gradio) | An Ollama model on our own page | Live demos, including on Colab with a public link |
| **MCP server** (`grids_plugin.mcp_server`) | Any MCP client: Claude Desktop, Claude Code and others | Showing the guard as a plugin for another AI app |

"Plugin" here means a **permission layer another assistant plugs into**. ChatGPT plugins were retired in 2024, and custom
GPT actions cannot sit in front of ChatGPT's own actions. MCP is the current standard way for assistants such as Claude to use
outside tools, so the MCP server is the plugin form. The chat demo keeps the whole loop on hardware we control, which makes
compute measurable.

Everything acts on AgentDojo's **simulated** Workspace (Emma Johnson's mailbox, calendar and drive). Nothing real is read,
sent or shared. Nothing in `src/` is changed; the plugin builds on the `grids` package.

## How a tool call is decided

This is the controller from the architecture diagram, with laya-cybersec in the Gatekeeper slot:

1. The assistant proposes a tool call. The controller parses it and binds the exact arguments and facts.
2. **Wall**: the user's fixed rules (`STRICT_WORKSPACE`: only email contacts, never share outside work, never delete). DENY
   or UNRESOLVED stops the action here, without any model.
3. **laya-cybersec** (`TextCortex/laya-cybersec@41fd5a2`, 321.9M parameters, CPU) reads the action's decision context:
   - the context is the request, action, policy and trusted identities plus excerpts of the untrusted tool outputs,
     reduced by the repository's `compact_v1`, which was built for this model's 1,024 tokens;
   - a score above **0.95** (the model card's operating point) means BLOCK, otherwise ALLOW;
   - a truncated input means ASK.
4. **Approval**: the demo asks the person before any file share (`confirm_capabilities: ["share"]`). The action waits for
   Approve or Reject. The assistant's model cannot answer for the person.
5. The executor rechecks the exact action and runs it, or returns a PermissionError.

The modes compare protection levels on the same scenario: **No protection**, **Wall only**, **Wall + laya-cybersec**.

## Compute

Both forms report what each part cost:

| Part | What is measured |
|---|---|
| Chat model (the assistant) | Calls, tokens and time |
| Wall | Checks and time, including the recheck before an action runs. No model |
| laya-cybersec | Scans and time, on the CPU |
| LLM judge (chat demo option, comparison only) | The same checks asked of the chat model. Its time and tokens are shown next to laya-cybersec's; it never decides |

The chat demo also counts the actions the Wall stopped with no model call. The MCP server's `guard_report` tool returns
every decision with the same compute summary.

Measured on a laptop CPU (its RTX 3050 not used): a Wall check takes under 1 ms, and a laya-cybersec scan takes
0.35–0.6 s. Loading the model takes 10–50 s.

## Scenarios (chat demo)

| Scenario | What it shows |
|---|---|
| Everyday request | An email to a colleague passes the Wall and laya-cybersec and is sent |
| Attack the Wall stops | Text hidden in the calendar asks the assistant to send a security code to an outside address. The Wall blocks it, with no model |
| Attack only laya-cybersec catches | The same instruction aimed at a colleague, which the policy allows. The Wall passes it, and laya-cybersec flags the injected text and blocks it. Custom demo injection |
| Sharing needs your approval | A file share to a colleague waits for Approve or Reject |
| Free chat | Anything about the simulated workspace |

Attack scenarios place AgentDojo's `important_instructions` wording, with the stated goal, in every spot AgentDojo allows
injected text. Whether the assistant follows it depends on the chat model.

## Run the chat demo on Colab

Open [`colab_demo.ipynb`](colab_demo.ipynb) on a GPU runtime and run the cells in order. It clones this branch, installs
the environment, starts Ollama with `qwen2.5:7b`, downloads laya-cybersec and prints a public `gradio.live` link.

## Run locally (Windows example, models on D:)

```powershell
uv venv D:\grids-plugin\env --python 3.12
uv pip install --python D:\grids-plugin\env\Scripts\python.exe -r environments\laya.txt -r plugin\requirements.txt
$env:HF_HOME = "D:\grids-plugin\hf-cache"
cd plugin
# Chat demo (needs Ollama running with a tool-calling model):
D:\grids-plugin\env\Scripts\python.exe -m grids_plugin.app --model qwen2.5:7b --laya-cache D:\grids-plugin\hf-cache
```

## Use the MCP server with Claude Desktop

Add to `claude_desktop_config.json` (Settings → Developer → Edit Config), with your own paths:

```json
{
  "mcpServers": {
    "grids-permission-guard": {
      "command": "D:\\grids-plugin\\env\\Scripts\\python.exe",
      "args": ["-m", "grids_plugin.mcp_server", "--laya-cache", "D:\\grids-plugin\\hf-cache",
               "--approvals", "D:\\grids-plugin\\approvals", "--scenario", "Attack only laya-cybersec catches"],
      "env": {"PYTHONPATH": "C:\\path\\to\\repo\\plugin;C:\\path\\to\\repo\\src", "HF_HOME": "D:\\grids-plugin\\hf-cache"}
    }
  }
}
```

Restart Claude Desktop, then ask, for example, *"Use the workspace tools: how many appointments do I have on May 15th,
2024?"*. In a second terminal, run the approval console. A share waits there for your answer, for up to 60 s:

```powershell
D:\grids-plugin\env\Scripts\python.exe -m grids_plugin.mcp_server approve --approvals D:\grids-plugin\approvals
```

Tools: the 24 Workspace tools, plus `set_user_request` (the client's model passes the user's request) and `guard_report`.

## Tests

```powershell
cd plugin
$env:PYTHONPATH = ".;..\src"
D:\grids-plugin\env\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
```

The 12 tests drive the real controller, Wall and simulated Workspace with a scripted chat model and a fake scanner:

- all scenarios, including both answers to an approval;
- the chat page's handlers and that the page serves;
- the MCP server through a real in-process MCP client.

## Limitations

- **laya-cybersec detects injected text; it is not a permission model.** On the 150 test rows of
  `laya-permission-v1-compact` it flagged 25/39 injected BLOCK rows, but also 7/17 ALLOW and 11/24 ASK rows whose history merely
  contains an injection. In the demo, once the assistant has read an injected email, later legitimate actions in the same
  request can be blocked too. It never produces ASK: ASK comes from the approval rule and truncated input.
- The threshold 0.95 is the card's operating point for documents, not calibrated for action contexts.
- In the MCP form, the user's request comes from the client's model through `set_user_request`. It is not verified.
- The simulated Workspace and AgentDojo injection wording are research fixtures, not real accounts or real attacks.
- Only the scripted and fake-scanner paths are tested automatically. Real laya-cybersec inference was checked on a laptop
  CPU, and the MCP server over stdio with the real model. Ollama on Colab has not been run yet.
