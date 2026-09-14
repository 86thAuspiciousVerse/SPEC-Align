"""Read-only projections: filtering never weakens whole-project validation."""
import json
from .protocol import ProtocolError
from .graph import impact, cycle_members


def project_report(report, detail="summary", scope=None, limit=20):
    if detail not in ("summary", "full") or type(limit) is not int or not 1 <= limit <= 200:
        raise ProtocolError("detail must be summary/full; limit must be 1..200")
    items = report["items"]
    selected = {k: v for k, v in items.items() if scope is None or v.get("scope", "project") == scope}
    findings = [f for f in report["findings"] if scope is None or f["item"] in selected]
    result = {k: report[k] for k in ("schema_version", "snapshot", "valid", "stats") if k in report}
    result.update(scope=scope, project_error_count=sum(f["severity"] == "error" for f in report["findings"]),
                  project_unresolved_count=len(report["findings"]), unresolved_count=len(findings),
                  item_count=len(selected), findings=findings if detail == "full" else findings[:limit],
                  findings_omitted=0 if detail == "full" else max(0, len(findings)-limit),
                  affected_ids=sorted({f["item"] for f in findings}),
                  unmanaged_count=len(report.get("unmanaged", [])))
    if "last_valid_snapshot" in report:
        result["last_valid_snapshot"] = report["last_valid_snapshot"]
    if detail == "full":
        result["items"] = selected
        result["unmanaged"] = report.get("unmanaged", [])
    return result


def check(runtime, detail="summary", scope=None, since_snapshot=None, limit=20):
    report = runtime.scan()
    result = project_report(report, detail, scope, limit)
    if since_snapshot is not None:
        row = runtime.db.execute("SELECT payload FROM snapshots WHERE id=?", (since_snapshot,)).fetchone()
        if row is None:
            raise ProtocolError("Unknown since_snapshot; provide a saved snapshot")
        if not report["valid"]:
            raise ProtocolError("Cannot compare an invalid current scan")
        old, current = json.loads(row[0]), report["items"]
        changed = {k for k in old.keys() | current.keys() if old.get(k, {}).get("version") != current.get(k, {}).get("version")}
        visible = {k for k in changed if scope is None or any(m.get(k, {}).get("scope", "project") == scope for m in (old, current) if k in m)}
        affected = set(changed)
        for key in changed:
            affected.update(impact(old, key))
            affected.update(impact(current, key))
        result.update(since_snapshot=since_snapshot, changed_ids=sorted(visible),
                      deleted_ids=sorted(visible-current.keys()),
                      change_affected_ids=sorted(k for k in affected if scope is None or any(m.get(k, {}).get("scope", "project") == scope for m in (old,current) if k in m)))
    return result


def migration_plan(runtime, scope=None):
    report = runtime.scan()
    items = report["items"]
    successors = {}
    for key, item in items.items():
        if item["status"] in ("active", "retired"):
            for old in item.get("supersedes", []):
                successors.setdefault(old, []).append(key)
    migrations = []
    for key, item in sorted(items.items()):
        if item.get("effective_status", item["status"]) != "active" or (scope is not None and item.get("scope", "project") != scope):
            continue
        for dep in item["depends_on"]:
            if dep not in items or items[dep].get("effective_status") != "superseded":
                continue
            chain, seen, target = [dep], {dep}, dep
            while len(successors.get(target, [])) == 1:
                target = successors[target][0]
                if target in seen:
                    break
                chain.append(target)
                seen.add(target)
            candidate = target if target != dep and items[target].get("effective_status") == "active" else None
            cyclic = None
            if candidate:
                proposed = {k: dict(v) for k,v in items.items()}
                proposed[key]["depends_on"] = [candidate if d == dep else d for d in item["depends_on"]]
                cyclic = key in cycle_members(proposed, "depends_on")
            migrations.append(dict(item=key, dependency=dep, successor_chain=chain,
                                   candidate=candidate, would_create_cycle=cyclic, requires_judgment=True))
    return {**project_report(report, scope=scope), "migrations": migrations,
            "applied": False, "note": "Declared successors are evidence, not automatic semantic replacements."}


def context_many(runtime, ids, max_chars=12000, related=False, max_items=30):
    if not isinstance(ids, list) or not 1 <= len(ids) <= 20 or any(not isinstance(k,str) for k in ids):
        raise ProtocolError("Provide 1..20 explicit item IDs")
    if type(max_chars) is not int or not 500 <= max_chars <= 100000 or type(max_items) is not int or not 1 <= max_items <= 200:
        raise ProtocolError("Invalid body budget or max_items (1..200)")
    report = runtime.scan()
    items = report['items']
    if any(k not in items for k in ids):
        raise ProtocolError("Context target unavailable; inspect check")
    from collections import deque
    from .graph import edges
    wanted, seen, queue = [], set(), deque(dict.fromkeys(ids))
    while queue:
        key = queue.popleft()
        if key in seen or key not in items:
            continue
        seen.add(key)
        wanted.append(key)
        queue.extend(items[key]['depends_on'])
    graph_edges = edges(items)
    # Only one hop of non-upstream relationships around the explicitly requested IDs.
    if related:
        targets = set(ids)
        for edge in graph_edges:
            if edge['source'] in targets or edge['target'] in targets:
                for key in (edge['source'], edge['target']):
                    if key in items and key not in seen:
                        seen.add(key)
                        wanted.append(key)
    selected, remaining = {}, max_chars
    for key in wanted[:max_items]:
        item = dict(items[key])
        body = item['body']
        item['body'] = body[:remaining]
        item['body_truncated'] = len(item['body']) < len(body)
        remaining -= len(item['body'])
        row = runtime.db.execute('SELECT 1 FROM reviews WHERE item=? AND basis=? LIMIT 1',
                                 (key, runtime.basis(items[key], items))).fetchone()
        item['matching_review'] = bool(row)
        selected[key] = item
    result = project_report(report)
    selected_findings = [f for f in report['findings'] if f['item'] in seen]
    result.update(targets=list(dict.fromkeys(ids)), items=selected, omitted_items=wanted[max_items:],
                  body_character_budget=max_chars, findings=selected_findings[:20],
                  findings_omitted=max(0, len(selected_findings)-20), unresolved_count=len(selected_findings),
                  affected_ids=sorted({f['item'] for f in selected_findings}))
    if related:
        relevant = [e for e in graph_edges if e['source'] in selected and e['target'] in selected]
        result.update(edges=relevant[:200], edges_omitted=max(0,len(relevant)-200))
    return result

