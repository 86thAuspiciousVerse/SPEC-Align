"""Typed graph operations; only depends_on drives implementation impact."""
from collections import deque


RELATIONS = ('depends_on', 'references', 'supersedes', 'challenges')


def cycle_members(items, relation):
    """Iterative Kosaraju SCC avoids recursion and repeated transitive walks."""
    adjacency = {key: [v for v in item.get(relation, []) if v in items] for key, item in items.items()}
    reverse = {key: [] for key in items}
    for key, values in adjacency.items():
        for value in values:
            reverse[value].append(key)
    visited, order = set(), []
    for key in items:
        if key in visited:
            continue
        stack = [(key, False)]
        while stack:
            current, finish = stack.pop()
            if finish:
                order.append(current)
            elif current not in visited:
                visited.add(current)
                stack.append((current, True))
                stack.extend((v, False) for v in adjacency[current] if v not in visited)
    seen, cyclic = set(), set()
    for key in reversed(order):
        if key in seen:
            continue
        component, stack = [], [key]
        seen.add(key)
        while stack:
            current = stack.pop()
            component.append(current)
            for parent in reverse[current]:
                if parent not in seen:
                    seen.add(parent)
                    stack.append(parent)
        if len(component) > 1 or key in adjacency[key]:
            cyclic.update(component)
    return cyclic


def edges(items):
    return [{'source': key, 'target': target, 'type': relation}
            for key, item in sorted(items.items()) for relation in RELATIONS for target in item.get(relation, [])]


def impact(items, ident):
    reverse = {}
    for edge in edges(items):
        if edge['type'] == 'depends_on':
            reverse.setdefault(edge['target'], []).append(edge['source'])
    chains, queue = {ident: [ident]}, deque([ident])
    while queue:
        key = queue.popleft()
        for child in sorted(reverse.get(key, [])):
            if child not in chains:
                chains[child] = [child, *chains[key]]
                queue.append(child)
    return {key: chain for key, chain in chains.items() if key != ident}


def mermaid(items):
    graph_edges = edges(items)
    names = sorted(set(items) | {e['target'] for e in graph_edges})
    nodes = {key: f'n{i}' for i, key in enumerate(names)}
    lines = ['flowchart TD']
    for key in names:
        label = key if key in items else key + ' (missing)'
        lines.append(f'  {nodes[key]}["{label}"]')
    for edge in graph_edges:
        lines.append(f"  {nodes[edge['source']]} -->|{edge['type']}| {nodes[edge['target']]}")
    return '\n'.join(lines) + '\n'

