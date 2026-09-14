"""Standard MCP SDK stdio transport, using the same runtime as the CLI."""
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .core import Runtime
from .query import project_report


def build_server(root):
    root = Path(root).resolve()
    server = FastMCP('spec-align', instructions='Explicit Markdown dependency checks. Use check, then explain before review. Findings are not semantic proof. Review requires the returned snapshot and an evidence-based reason.', log_level='ERROR')

    def call(method, *args):
        runtime = Runtime(root)
        try:
            return getattr(runtime, method)(*args)
        finally:
            runtime.close()

    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False)

    @server.tool(annotations=read)
    def spec_check(detail: str = "summary", scope: str | None = None, since_snapshot: str | None = None, limit: int = 20) -> dict:
        """Scan declared document dependencies and return current findings and snapshot."""
        return call('check', detail, scope, since_snapshot, limit)

    @server.tool(annotations=read)
    def spec_explain(item: str) -> dict:
        """Get current and reviewed evidence for one explicit item ID; does not approve it."""
        return call('explain', item)

    @server.tool(annotations=read)
    def spec_context(item: str | None = None, max_chars: int = 12000, items: list[str] | None = None, related: bool = False, max_items: int = 30) -> dict:
        """Get an item and declared upstream context with an explicit body limit."""
        if (item is None) == (items is None):
            raise ValueError('Provide exactly one of item or items')
        return call('context_many', [item] if item is not None else items, max_chars, related, max_items)

    @server.tool(annotations=read)
    def spec_impact(item: str) -> dict:
        """Return declared downstream impact chains and graph edges."""
        return call('graph', item)

    @server.tool(annotations=read)
    def spec_history(item: str | None = None) -> dict:
        """Read review, decision and finding history."""
        return call('history', item)

    @server.tool(annotations=write)
    def spec_review(item: str, snapshot: str, reason: str) -> dict:
        """Record compatibility only after examining evidence; rejects changed snapshots."""
        return {**project_report(call('review', item, snapshot, reason)), 'reviewed_ids': [item]}

    @server.tool(annotations=write)
    def spec_decide(item: str, action: str, snapshot: str, reason: str, actor: str) -> dict:
        """Explicitly accept or retire a declaration within existing user authorization."""
        return {**project_report(call('transition', item, action, snapshot, reason, actor)), 'decision': {'item': item, 'action': action}}

    @server.tool(annotations=write)
    def spec_review_batch(snapshot: str, reviews: list[dict[str, str]]) -> dict:
        """Review an explicit batch atomically in the ledger, with one reason per item."""
        return call('review_batch', snapshot, reviews)

    @server.tool(annotations=read)
    def spec_migration_plan(scope: str | None = None) -> dict:
        """Preview declared successor candidates; never edit dependencies automatically."""
        return call('migration_plan', scope)

    return server


def run_server(root):
    build_server(root).run(transport='stdio')

