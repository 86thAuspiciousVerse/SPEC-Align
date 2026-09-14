"""Bounded agent-facing findings, independent of host transport."""
import json


def agent_report(report, root, limit=10):
    findings = report.get('findings', [])
    lines = [f"Spec Align: {report.get('unresolved_count', len(findings))} finding(s); structure={'valid' if report['valid'] else 'invalid'}.",
             f"Snapshot: {report.get('snapshot') or 'unavailable'}"]
    for issue in findings[:limit]:
        location = f"{issue.get('path', '')}:{issue.get('line', '')}"
        lines.append(f"[{issue.get('id', issue['code'])}] {issue['severity']} {issue['code']} {issue['item']} {location}"[:500])
    if report.get('scope') is not None:
        lines.append(f"Scope: {report['scope']}; project errors={report.get('project_error_count', 0)}; project unresolved={report.get('project_unresolved_count', len(findings))}")
    if len(findings) > limit:
        lines.append(f'{len(findings) - limit} additional findings omitted; full check JSON contains all findings.')
    if report.get('findings_omitted'):
        lines.append(f"{report['findings_omitted']} findings omitted by projection; request detail=full.")
    if report.get('unmanaged'):
        lines.append(f"{len(report['unmanaged'])} file(s) are unmanaged; no semantic consistency guarantee.")
    if findings:
        lines.append('Inspect: specalign --root ' + json.dumps(str(root), ensure_ascii=False) + ' check')
        lines.append('Use explain ID for evidence; review only after examining the current dependencies.')
    return '\n'.join(lines)

