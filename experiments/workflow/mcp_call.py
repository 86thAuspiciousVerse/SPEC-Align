"""Call the workspace-configured MCP server; never infer or auto-approve reviews."""
import json
import sys
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

try:
    import tomllib
except ImportError:
    import tomli as tomllib


async def main():
    root = Path(__file__).resolve().parents[2]
    config = tomllib.loads((root / '.codex/config.toml').read_text(encoding='utf-8'))
    server = config['mcp_servers']['specalign']
    request = json.load(sys.stdin)
    params = StdioServerParameters(command=server['command'], args=server['args'],
                                   env={'PYTHONIOENCODING': 'utf-8'})
    with anyio.fail_after(30):
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()
                result = await client.call_tool(request['tool'], request.get('arguments', {}))
                evidence = root / '.specalign/workflow-lab'
                evidence.mkdir(parents=True, exist_ok=True)
                record = {'request': request, 'response': result.model_dump(mode='json')}
                with (evidence / 'mcp.jsonl').open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(record, ensure_ascii=False) + '\n')
                for content in result.content:
                    if content.type == 'text':
                        print(content.text)
                failed = result.isError
    return 3 if failed else 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(anyio.run(main))

