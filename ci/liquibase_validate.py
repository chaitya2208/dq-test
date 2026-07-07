#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
liquibase_validate.py — Data Quality gate for Liquibase + GitHub Actions

Scans a Liquibase changelog file for CREATE TABLE statements, validates each
one against all active data quality rules, and posts a structured report as a
GitHub PR comment.

Zero external dependencies (stdlib only).

Usage:
  python liquibase_validate.py --changelog changelogs/v1.xml
  python liquibase_validate.py --changelog changelogs/v1.xml --fail-on critical high
  python liquibase_validate.py --changelog changelogs/v1.xml --soft-gate

Environment variables (GitHub Actions sets most of these automatically):
  DQ_URL            — Data Quality Platform URL (default: http://localhost:8000)
  GITHUB_TOKEN      — GitHub token for posting PR comments (auto-set in Actions)
  GITHUB_REPOSITORY — owner/repo  (auto-set in Actions)
  GITHUB_PR_NUMBER  — PR number   (set manually or via github.event.pull_request.number)

Exit codes:
  0 — all tables passed (or --soft-gate mode)
  1 — blocking violations found (hard gate mode)
  2 — script error (changelog not found, API unreachable, etc.)
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from typing import List, Dict

# Force UTF-8 output — Windows console defaults to cp1252 which breaks emojis
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ── Colour helpers ────────────────────────────────────────────────────────────

_TTY = sys.stdout.isatty()
RED    = "\033[91m" if _TTY else ""
GREEN  = "\033[92m" if _TTY else ""
YELLOW = "\033[93m" if _TTY else ""
BOLD   = "\033[1m"  if _TTY else ""
RESET  = "\033[0m"  if _TTY else ""

SEV_EMOJI = {
    "critical": "[CRITICAL]",
    "high":     "[HIGH]",
    "medium":   "[MEDIUM]",
    "low":      "[LOW]",
    "info":     "[INFO]",
}

# ── API call ──────────────────────────────────────────────────────────────────

def call_validate_api(base_url: str, sql: str, fail_on: List[str]) -> dict:
    url     = base_url.rstrip("/") + "/api/v1/validate/ddl"
    payload = json.dumps({"sql": sql, "fail_on": fail_on}).encode("utf-8")
    req     = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body).get("detail", body)
        except Exception:
            detail = body
        print(f"{RED}ERROR{RESET} Validate API HTTP {e.code}: {detail}", file=sys.stderr)
        sys.exit(2)
    except urllib.error.URLError as e:
        print(f"{RED}ERROR{RESET} Cannot reach {url}: {e.reason}", file=sys.stderr)
        print("Set DQ_URL env var to point to your Data Quality Platform.", file=sys.stderr)
        sys.exit(2)


# ── GitHub PR comment ─────────────────────────────────────────────────────────

def post_github_comment(body: str) -> bool:
    token  = os.environ.get("GITHUB_TOKEN")
    repo   = os.environ.get("GITHUB_REPOSITORY")
    pr_num = os.environ.get("GITHUB_PR_NUMBER") or os.environ.get("PR_NUMBER")

    if not all([token, repo, pr_num]):
        print(
            f"{YELLOW}NOTE{RESET} GitHub comment skipped "
            f"(GITHUB_TOKEN / GITHUB_REPOSITORY / GITHUB_PR_NUMBER not set)",
            file=sys.stderr,
        )
        return False

    url     = f"https://api.github.com/repos/{repo}/issues/{pr_num}/comments"
    payload = json.dumps({"body": body}).encode("utf-8")
    req     = urllib.request.Request(
        url, data=payload,
        headers={
            "Authorization":  f"Bearer {token}",
            "Content-Type":   "application/json",
            "Accept":         "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            comment_data = json.loads(resp.read().decode("utf-8"))
            print(f"  GitHub comment posted: {comment_data.get('html_url', '')}")
            return True
    except Exception as e:
        print(f"{YELLOW}WARNING{RESET} Could not post GitHub comment: {e}", file=sys.stderr)
        return False


def request_github_review(reason: str) -> bool:
    """Request a review on the PR — prevents merge until someone approves."""
    token  = os.environ.get("GITHUB_TOKEN")
    repo   = os.environ.get("GITHUB_REPOSITORY")
    pr_num = os.environ.get("GITHUB_PR_NUMBER") or os.environ.get("PR_NUMBER")

    if not all([token, repo, pr_num]):
        return False

    # Create a pending review (REQUEST_CHANGES puts the PR in a blocked state)
    url     = f"https://api.github.com/repos/{repo}/pulls/{pr_num}/reviews"
    payload = json.dumps({
        "event": "REQUEST_CHANGES",
        "body":  reason,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={
            "Authorization":        f"Bearer {token}",
            "Content-Type":         "application/json",
            "Accept":               "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30):
            print("  GitHub review requested (PR blocked until approved)")
            return True
    except Exception as e:
        print(f"{YELLOW}WARNING{RESET} Could not request review: {e}", file=sys.stderr)
        return False


# ── Markdown report builder ───────────────────────────────────────────────────

def build_pr_comment(all_results: List[Dict], fail_on: List[str], soft_gate: bool) -> str:
    total_tables  = len(all_results)
    total_findings = sum(r["findings_count"] for r in all_results)
    total_blocked  = sum(r["blocked_by"] for r in all_results)
    all_passed     = total_blocked == 0

    gate_label = "⚠️ Soft Gate" if soft_gate else "🔒 Hard Gate"
    status_line = (
        "✅ **All tables passed data quality validation**"
        if all_passed
        else f"❌ **{total_blocked} blocking violation(s) found across {total_tables} table(s)**"
    )

    lines = [
        "## 🔍 Data Quality Validation Report",
        "",
        f"{status_line}",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Tables validated | {total_tables} |",
        f"| Total findings | {total_findings} |",
        f"| Blocking findings | {total_blocked} |",
        f"| Gate mode | {gate_label} |",
        f"| Fail on | {', '.join(f'`{s}`' for s in fail_on)} |",
        "",
    ]

    for r in all_results:
        cs_label = f"changeset `{r['changeset_id']}`" if r.get("changeset_id") else r.get("source_file", "")
        table_passed = r["blocked_by"] == 0
        icon = "✅" if table_passed else "❌"

        lines.append(f"### {icon} `{r['table_name']}` — {cs_label}")
        lines.append("")
        lines.append(
            f"Rules checked: **{r['rules_checked']}** | "
            f"Findings: **{r['findings_count']}** | "
            f"Blocking: **{r['blocked_by']}**"
        )
        lines.append("")

        if r["findings"]:
            lines.append("| Severity | Rule | Column | Issue | Status |")
            lines.append("|----------|------|--------|-------|--------|")
            for f in r["findings"]:
                emoji    = SEV_EMOJI.get(f["severity"], "[INFO]")
                approved = f.get("approved", False)
                if approved:
                    status_col = "✅ Approved"
                elif f["severity"] in fail_on:
                    status_col = "⛔ Blocking"
                else:
                    status_col = "⚠️ Warning"
                col = f"`{f['column_name']}`" if f.get("column_name") else "—"
                lines.append(
                    f"| {emoji} {f['severity'].upper()} | "
                    f"`{f['rule_code']}` | "
                    f"{col} | "
                    f"{f['title']} | "
                    f"{status_col} |"
                )
            lines.append("")
        else:
            lines.append("_No findings._")
            lines.append("")

    # Approval commands section
    all_blocking_codes = sorted({
        f["rule_code"]
        for r in all_results
        for f in r.get("findings", [])
        if f["severity"] in fail_on and not f.get("approved", False)
    })

    if all_blocking_codes and not soft_gate:
        lines += [
            "---",
            "### How to approve violations",
            "",
            "If a violation is intentional or not applicable to this table,",
            "add a comment on this PR with one of these commands:",
            "",
            "**Approve a specific rule:**",
            "```",
            "/dq-approve RULE_CODE reason: your justification here",
            "```",
            "",
            "**Approve all violations at once:**",
            "```",
            "/dq-approve-all reason: your justification here",
            "```",
            "",
            "**Blocking rules in this PR:**",
        ]
        for code in all_blocking_codes:
            lines.append(f"- `{code}` — `/dq-approve {code} reason: <your reason>`")
        lines.append("")
        lines += [
            "> After adding the approve comment, re-run the workflow from the Actions tab.",
            "",
        ]

    # Footer
    if all_passed:
        lines += [
            "---",
            "_Data quality validation passed. No action required._",
        ]
    elif soft_gate:
        lines += [
            "---",
            "⚠️ **Soft gate mode** — pipeline will continue despite violations.",
            "Please review the findings above and fix them in a follow-up.",
        ]
    else:
        lines += [
            "---",
            "🔒 **Hard gate** — fix the DDL or approve violations (see commands above) to unblock.",
        ]

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate Liquibase changelogs against data quality rules.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--changelog", required=True, metavar="FILE",
                        help="Path to Liquibase changelog (.xml or .sql)")
    parser.add_argument("--url", default=os.environ.get("DQ_URL", "http://localhost:8000"),
                        help="Data Quality Platform API URL")
    parser.add_argument("--fail-on", nargs="+", default=["critical"],
                        metavar="SEVERITY",
                        help="Severity levels that block the build (default: critical)")
    parser.add_argument("--soft-gate", action="store_true",
                        help="Post PR comment but always exit 0 (warn, don't block)")
    parser.add_argument("--no-comment", action="store_true",
                        help="Skip posting GitHub PR comment")
    parser.add_argument("--approved-rules", nargs="*", default=[],
                        metavar="RULE_CODE",
                        help="Rule codes approved via /dq-approve PR comments")
    parser.add_argument("--approve-all", action="store_true",
                        help="All violations approved — only warn, never block")
    args = parser.parse_args()

    fail_on       = [s.lower() for s in args.fail_on]
    approved_rules = {r.upper() for r in (args.approved_rules or [])}
    approve_all   = args.approve_all

    # Parse changelog
    try:
        from liquibase_parser import parse_changelog
    except ImportError:
        # Allow running from any directory
        import importlib.util, pathlib
        spec = importlib.util.spec_from_file_location(
            "liquibase_parser",
            pathlib.Path(__file__).parent / "liquibase_parser.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        parse_changelog = mod.parse_changelog

    print(f"Parsing changelog: {args.changelog}")
    try:
        tables = parse_changelog(args.changelog)
    except FileNotFoundError:
        print(f"{RED}ERROR{RESET} File not found: {args.changelog}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"{RED}ERROR{RESET} Could not parse changelog: {e}", file=sys.stderr)
        sys.exit(2)

    if not tables:
        print(f"{YELLOW}NOTE{RESET} No CREATE TABLE statements found in {args.changelog}")
        print("Nothing to validate — exiting 0.")
        sys.exit(0)

    print(f"Found {len(tables)} CREATE TABLE statement(s). Validating against {args.url}...")

    # Show approval status
    if approve_all:
        print(f"{YELLOW}NOTE{RESET} All violations approved via /dq-approve-all — warnings only")
    elif approved_rules:
        print(f"{YELLOW}NOTE{RESET} Approved rules (will not block): {', '.join(sorted(approved_rules))}")

    # Validate each table
    all_results = []
    total_blocked = 0

    for t in tables:
        cs_label = f"[{t['changeset_id']}]" if t.get("changeset_id") else ""
        print(f"  Validating {t['table_name']} {cs_label}...", end=" ", flush=True)

        result = call_validate_api(args.url, t["sql"], fail_on)

        # Recalculate blocked_by excluding approved rules
        if approve_all:
            effective_blocked = 0
        elif approved_rules:
            effective_blocked = sum(
                1 for f in result.get("findings", [])
                if f["severity"] in fail_on and f["rule_code"] not in approved_rules
            )
        else:
            effective_blocked = result.get("blocked_by", 0)

        total_blocked += effective_blocked

        # Annotate findings with approved status
        for f in result.get("findings", []):
            f["approved"] = approve_all or f["rule_code"] in approved_rules

        result["blocked_by"]       = effective_blocked
        result["passed"]           = effective_blocked == 0
        result["approved_rules"]   = list(approved_rules)
        result["approve_all"]      = approve_all

        status = f"{GREEN}PASS{RESET}" if result["passed"] else f"{RED}FAIL ({effective_blocked} blocking){RESET}"
        print(status)

        all_results.append({
            **result,
            "changeset_id": t.get("changeset_id"),
            "source_file":  t.get("source_file"),
        })

    # Print summary to stdout
    print()
    if total_blocked == 0:
        print(f"{GREEN}{BOLD}PASSED: All tables passed data quality validation{RESET}")
    else:
        print(f"{RED}{BOLD}FAILED: {total_blocked} blocking violation(s) found{RESET}")
        for r in all_results:
            if r["blocked_by"] > 0:
                for f in r["findings"]:
                    if f["severity"] in fail_on:
                        col = f" [{f['column_name']}]" if f.get("column_name") else ""
                        print(f"  {SEV_EMOJI.get(f['severity'],'')} {r['table_name']}{col}: {f['title']}")

    # Post GitHub PR comment
    if not args.no_comment:
        comment = build_pr_comment(all_results, fail_on, args.soft_gate)
        print()
        print("Posting GitHub PR comment...")
        post_github_comment(comment)

        # Request review (blocks PR) if hard gate and violations found
        if total_blocked > 0 and not args.soft_gate:
            request_github_review(
                f"Data quality validation found {total_blocked} blocking violation(s). "
                f"Please fix the DDL or provide justification before merging."
            )

    # Exit code
    if total_blocked > 0 and not args.soft_gate:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
