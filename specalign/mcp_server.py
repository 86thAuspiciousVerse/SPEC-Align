"""Standard MCP SDK stdio transport, using the same runtime as the CLI."""
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .config import initialize_project
from .core import Runtime
from .query import project_report


def build_server(root=None):
    bound_root = Path(root).resolve() if root is not None else None
    if bound_root is None:
        instructions = (
            'This Spec Align MCP server starts unbound and performs no project scan at startup. '
            'Every project tool call must provide an absolute root path, usually the current '
            'workspace. The server never infers a root from chat context. Call spec_init(root) '
            'when the project needs initialization, then check before review. Every successful '
            'result includes project_root; if it does not match, do not review or decide and '
            'use the CLI with an explicit --root. Findings are not semantic proof.'
        )
    else:
        instructions = (
            f'Explicit Markdown dependency checks for project root {bound_root}. '
            'This server is permanently bound to that root for its lifetime. '
            'Use it only when it matches the current workspace; if it does not, '
            'do not review or decide and use the CLI with an explicit --root instead. '
            'Use check, then explain before review. Findings are not semantic proof. '
            'Review requires the returned snapshot and an evidence-based reason.'
        )
    server = FastMCP('spec-align', instructions=instructions, log_level='ERROR')

    def requested_root(value):
        if value is None:
            raise ValueError('An absolute root is required when this MCP server is unbound')
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            raise ValueError('MCP root must be an absolute path')
        return candidate.resolve()

    def resolve_root(value=None):
        if bound_root is None:
            return requested_root(value)
        if value is None:
            return bound_root
        candidate = requested_root(value)
        if candidate != bound_root:
            raise ValueError(f'MCP server is bound to {bound_root}; requested root is {candidate}')
        return bound_root

    def scoped(result, target):
        """Attach the immutable scope used for this successful projection."""
        if isinstance(result, dict):
            return {**result, 'project_root': str(target)}
        return result

    def call(target, method, *args):
        runtime = Runtime(target)
        try:
            return getattr(runtime, method)(*args)
        finally:
            runtime.close()

    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False)

    @server.tool(annotations=write)
    def spec_init(root: str | None = None) -> dict:
        """Initialize one explicitly named project without scanning another project."""
        target = resolve_root(root)
        return scoped(initialize_project(target), target)

    @server.tool(annotations=read)
    def spec_check(detail: str = "summary", scope: str | None = None, since_snapshot: str | None = None, limit: int = 20, root: str | None = None) -> dict:
        """Scan declared document dependencies and return current findings and snapshot."""
        target = resolve_root(root)
        return scoped(call(target, 'check', detail, scope, since_snapshot, limit), target)

    @server.tool(annotations=read)
    def spec_explain(item: str, root: str | None = None) -> dict:
        """Get current and reviewed evidence for one explicit item ID; does not approve it."""
        target = resolve_root(root)
        return scoped(call(target, 'explain', item), target)

    @server.tool(annotations=read)
    def spec_context(item: str | None = None, max_chars: int = 12000, items: list[str] | None = None, related: bool = False, max_items: int = 30, root: str | None = None) -> dict:
        """Get an item and declared upstream context with an explicit body limit."""
        if (item is None) == (items is None):
            raise ValueError('Provide exactly one of item or items')
        target = resolve_root(root)
        return scoped(call(target, 'context_many', [item] if item is not None else items, max_chars, related, max_items), target)

    @server.tool(annotations=read)
    def spec_impact(item: str, root: str | None = None) -> dict:
        """Return declared downstream impact chains and graph edges."""
        target = resolve_root(root)
        return scoped(call(target, 'graph', item), target)

    @server.tool(annotations=read)
    def spec_history(item: str | None = None, root: str | None = None) -> dict:
        """Read review, decision and finding history."""
        target = resolve_root(root)
        return scoped(call(target, 'history', item), target)

    @server.tool(annotations=write)
    def spec_review(item: str, snapshot: str, reason: str, root: str | None = None) -> dict:
        """Record compatibility only after examining evidence; rejects changed snapshots."""
        target = resolve_root(root)
        return scoped({**project_report(call(target, 'review', item, snapshot, reason)), 'reviewed_ids': [item]}, target)

    @server.tool(annotations=write)
    def spec_decide(item: str, action: str, snapshot: str, reason: str, actor: str, root: str | None = None) -> dict:
        """Explicitly accept or retire a declaration within existing user authorization."""
        target = resolve_root(root)
        return scoped({**project_report(call(target, 'transition', item, action, snapshot, reason, actor)), 'decision': {'item': item, 'action': action}}, target)

    @server.tool(annotations=write)
    def spec_review_batch(snapshot: str, reviews: list[dict[str, str]], root: str | None = None) -> dict:
        """Review an explicit batch atomically in the ledger, with one reason per item."""
        target = resolve_root(root)
        return scoped(call(target, 'review_batch', snapshot, reviews), target)

    @server.tool(annotations=read)
    def spec_migration_plan(scope: str | None = None, root: str | None = None) -> dict:
        """Preview declared successor candidates; never edit dependencies automatically."""
        target = resolve_root(root)
        return scoped(call(target, 'migration_plan', scope), target)

    return server


def run_server(root=None):
    build_server(root).run(transport='stdio')

