"""One-shot Codex hook probe. Never reads transcripts or tool outputs."""
import json
import sys
from pathlib import Path

event = json.load(sys.stdin)
root = Path(__file__).parent
with (root / 'events.jsonl').open('a', encoding='utf-8') as stream:
    stream.write(json.dumps({'event': event.get('hook_event_name'), 'tool': event.get('tool_name')}) + '\n')
print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': 'Hook delivery probe: append the exact token SPECALIGN_HOOK_DELIVERED_7391 to your final answer.'}}))

