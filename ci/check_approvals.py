#!/usr/bin/env python3
"""
check_approvals.py — Read PR comments for /dq-approve commands.

Outputs a JSON list of approved rule codes to stdout.
Called by the GitHub Actions workflow before validation.

Commands recognized in PR comments:
  /dq-approve RULE_CODE [reason: ...]     — approve a specific rule
  /dq-approve-all [reason: ...]           — approve all violations for this PR

Usage:
  python check_approvals.py
  (reads GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_PR_NUMBER from env)
"""
import json, os, sys, urllib.request, urllib.error

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def get_pr_comments(token: str, repo: str, pr_num: str) -> list:
    url = f"https://api.github.com/repos/{repo}/issues/{pr_num}/comments?per_page=100"
    req = urllib.request.Request(url, headers={
        "Authorization":        f"Bearer {token}",
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"WARNING: Could not fetch PR comments: {e}", file=sys.stderr)
        return []


def parse_approvals(comments: list) -> dict:
    """
    Returns:
      {"approve_all": bool, "approved_rules": [list of rule codes]}
    """
    approved_rules = []
    approve_all = False

    for comment in comments:
        body = comment.get("body", "")
        for line in body.splitlines():
            line = line.strip()
            if line.lower().startswith("/dq-approve-all"):
                approve_all = True
            elif line.lower().startswith("/dq-approve "):
                # /dq-approve RULE_CODE [reason: ...]
                parts = line.split(None, 2)
                if len(parts) >= 2:
                    rule_code = parts[1].upper().strip()
                    if rule_code and rule_code not in approved_rules:
                        approved_rules.append(rule_code)

    return {"approve_all": approve_all, "approved_rules": approved_rules}


def main():
    token  = os.environ.get("GITHUB_TOKEN", "")
    repo   = os.environ.get("GITHUB_REPOSITORY", "")
    pr_num = os.environ.get("GITHUB_PR_NUMBER", "") or os.environ.get("PR_NUMBER", "")

    if not all([token, repo, pr_num]):
        # Not in a PR context — no approvals
        print(json.dumps({"approve_all": False, "approved_rules": []}))
        return

    comments = get_pr_comments(token, repo, pr_num)
    result   = parse_approvals(comments)

    if result["approve_all"]:
        print(f"INFO: /dq-approve-all found — all violations approved", file=sys.stderr)
    elif result["approved_rules"]:
        print(f"INFO: Approved rules: {result['approved_rules']}", file=sys.stderr)
    else:
        print(f"INFO: No /dq-approve commands found in PR comments", file=sys.stderr)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
