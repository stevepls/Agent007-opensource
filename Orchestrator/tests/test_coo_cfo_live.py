"""
Live integration tests — send real prompts through the chat API and verify
the COO/CFO agent responds with business intelligence, not generic assistant talk.

Run with: python3 tests/test_coo_cfo_live.py

Requires the Orchestrator API running on localhost:8502 with a valid ANTHROPIC_API_KEY.
"""

import os
import sys
import json
import re
import time
import requests

API_URL = os.getenv("API_URL", "http://localhost:8502")
CHAT_URL = f"{API_URL}/api/chat"

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def send_prompt(prompt: str, timeout: int = 120) -> dict:
    """Send a prompt to the chat API and collect the full streamed response."""
    payload = {
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {"Content-Type": "application/json"}

    # Try service key auth (dashboard → orchestrator pattern)
    service_key = os.getenv("SERVICE_API_KEY", os.getenv("SESSION_SECRET_KEY", ""))
    if service_key:
        headers["X-Service-Key"] = service_key

    resp = requests.post(CHAT_URL, json=payload, headers=headers, stream=True, timeout=timeout)
    resp.raise_for_status()

    text_chunks = []
    tool_calls = []
    status_cards = []
    structured_data = []

    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue

        # Parse PROGRESS: prefixed JSON lines (streaming tool events)
        if line.startswith("PROGRESS:"):
            json_str = line[len("PROGRESS:"):]
            try:
                data = json.loads(json_str)
                if data.get("type") == "tool_start" and "tool" in data:
                    tool_calls.append({"tool_name": data["tool"]})
                if "status_card" in data:
                    status_cards.append(data["status_card"])
                if "structured_data" in data:
                    structured_data.append(data["structured_data"])
            except json.JSONDecodeError:
                pass
            continue

        # Try to parse bare JSON lines
        if line.startswith('{"'):
            try:
                data = json.loads(line)
                if "tool_name" in data:
                    tool_calls.append(data)
                elif "status_card" in data:
                    status_cards.append(data["status_card"])
                elif "structured_data" in data:
                    structured_data.append(data["structured_data"])
                elif "type" in data and data["type"] == "status_card":
                    status_cards.append(data)
                else:
                    text_chunks.append(line)
            except json.JSONDecodeError:
                text_chunks.append(line)
        else:
            text_chunks.append(line)

    full_text = "\n".join(text_chunks)
    return {
        "text": full_text,
        "tool_calls": tool_calls,
        "status_cards": status_cards,
        "structured_data": structured_data,
    }


def check(condition: bool, label: str, detail: str = ""):
    """Print pass/fail for a check."""
    if condition:
        print(f"  {GREEN}✓{RESET} {label}")
    else:
        print(f"  {RED}✗{RESET} {label}")
        if detail:
            print(f"    {DIM}{detail}{RESET}")
    return condition


def run_test(name: str, prompt: str, checks: list) -> bool:
    """Run a single test: send prompt, apply checks, return pass/fail."""
    print(f"\n{BOLD}{CYAN}━━━ {name} ━━━{RESET}")
    print(f"  {YELLOW}Prompt:{RESET} {prompt}")

    try:
        start = time.time()
        result = send_prompt(prompt)
        elapsed = time.time() - start
        print(f"  {YELLOW}Time:{RESET} {elapsed:.1f}s")

        # Show response preview
        preview = result["text"][:400].replace("\n", " ").strip()
        print(f"  {YELLOW}Response:{RESET} {preview[:300]}{'...' if len(preview) > 300 else ''}")
        if result["tool_calls"]:
            tool_names = [t.get("tool_name", "?") for t in result["tool_calls"]]
            print(f"  {YELLOW}Tools used:{RESET} {', '.join(tool_names)}")
        if result["status_cards"]:
            card_titles = [c.get("title", "?") for c in result["status_cards"]]
            print(f"  {YELLOW}Status cards:{RESET} {', '.join(card_titles)}")

        all_passed = True
        for check_fn in checks:
            if not check_fn(result):
                all_passed = False
        return all_passed

    except requests.exceptions.ConnectionError:
        print(f"  {RED}✗ Could not connect to API at {API_URL}{RESET}")
        return False
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print(f"  {RED}✗ Authentication failed (401). Set SERVICE_API_KEY or SESSION_SECRET_KEY env var.{RESET}")
        else:
            print(f"  {RED}✗ HTTP Error: {e}{RESET}")
        return False
    except Exception as e:
        print(f"  {RED}✗ Error: {e}{RESET}")
        return False


def main():
    # First verify API is reachable
    print(f"{BOLD}Testing COO/CFO agent at {API_URL}{RESET}")
    try:
        health = requests.get(f"{API_URL}/health", timeout=5).json()
        print(f"{GREEN}API healthy{RESET}\n")
    except Exception as e:
        print(f"{RED}API not reachable: {e}{RESET}")
        print("Start the Orchestrator first: cd Orchestrator && python3 -m uvicorn api:app --port 8502")
        sys.exit(1)

    # Quick auth check
    test_resp = requests.post(
        CHAT_URL,
        json={"messages": [{"role": "user", "content": "test"}]},
        headers={"Accept": "application/json"},
        timeout=30,
    )
    if test_resp.status_code == 401:
        print(f"{RED}Auth enabled but no SERVICE_API_KEY set.{RESET}")
        print(f"Run with: SERVICE_API_KEY=<key> python3 tests/test_coo_cfo_live.py")
        print(f"Or temporarily disable auth: AUTH_ENABLED=false")
        sys.exit(1)
    print(f"{GREEN}Auth OK{RESET}\n")

    results = []

    # ── Test 1: Business health question ──────────────────────────────────
    results.append(run_test(
        "Business health question",
        "How's the business doing?",
        [
            lambda r: check(
                any("advisor" in t.get("tool_name", "") for t in r["tool_calls"]),
                "Uses an advisor tool",
                f"Tools used: {[t.get('tool_name') for t in r['tool_calls']]}",
            ),
            lambda r: check(
                len(r["text"]) > 50,
                "Produces a substantive response",
                f"Response length: {len(r['text'])} chars",
            ),
        ],
    ))

    # ── Test 2: Advisories request ────────────────────────────────────────
    results.append(run_test(
        "Advisories request",
        "Any issues I should know about?",
        [
            lambda r: check(
                any("advisor" in t.get("tool_name", "") for t in r["tool_calls"]),
                "Uses advisor tools",
                f"Tools used: {[t.get('tool_name') for t in r['tool_calls']]}",
            ),
        ],
    ))

    # ── Test 3: COO/CFO identity ──────────────────────────────────────────
    results.append(run_test(
        "COO/CFO identity check",
        "What's your role here? Who are you?",
        [
            lambda r: check(
                any(term in r["text"].lower() for term in [
                    "coo", "cfo", "chief", "operations", "financial",
                    "people like software", "executive",
                ]),
                "Identifies as COO/CFO or executive role",
                f"First 200 chars: {r['text'][:200]}",
            ),
        ],
    ))

    # ── Test 4: Time data → business framing ──────────────────────────────
    results.append(run_test(
        "Time data with business framing",
        "What did I work on this week?",
        [
            lambda r: check(
                any(t.get("tool_name", "").startswith("harvest") or
                    t.get("tool_name") == "get_current_datetime"
                    for t in r["tool_calls"]),
                "Uses Harvest or datetime tools",
                f"Tools used: {[t.get('tool_name') for t in r['tool_calls']]}",
            ),
            lambda r: check(
                len(r["text"]) > 30,
                "Produces a response about work activity",
            ),
        ],
    ))

    # ── Test 5: Revenue/utilization question ──────────────────────────────
    results.append(run_test(
        "Revenue/utilization question",
        "What's our utilization looking like? Are we billing enough?",
        [
            lambda r: check(
                any("advisor" in t.get("tool_name", "") or "harvest" in t.get("tool_name", "")
                    for t in r["tool_calls"]),
                "Uses advisor or harvest tools for financial data",
                f"Tools used: {[t.get('tool_name') for t in r['tool_calls']]}",
            ),
        ],
    ))

    # ── Test 6: Regular task query still works ────────────────────────────
    results.append(run_test(
        "Regular task query (non-business)",
        "Show my ClickUp tasks",
        [
            lambda r: check(
                any("clickup" in t.get("tool_name", "") for t in r["tool_calls"]),
                "Uses ClickUp tools (operational tasks still work)",
                f"Tools used: {[t.get('tool_name') for t in r['tool_calls']]}",
            ),
        ],
    ))

    # ── Test 7: Trends question ───────────────────────────────────────────
    results.append(run_test(
        "Trends question",
        "Show me business trends over the last 30 days",
        [
            lambda r: check(
                any("advisor_get_trends" == t.get("tool_name", "") for t in r["tool_calls"]),
                "Uses advisor_get_trends specifically",
                f"Tools used: {[t.get('tool_name') for t in r['tool_calls']]}",
            ),
        ],
    ))

    # ── Test 8: Greeting stays lightweight ────────────────────────────────
    results.append(run_test(
        "Greeting stays lightweight (no tool spam)",
        "Hey, good morning",
        [
            lambda r: check(
                len(r["tool_calls"]) == 0,
                "No tools invoked for a greeting",
                f"Tools used: {[t.get('tool_name') for t in r['tool_calls']]}",
            ),
            lambda r: check(
                len(r["text"]) > 5,
                "Still produces a friendly response",
            ),
        ],
    ))

    # ── Summary ───────────────────────────────────────────────────────────
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{BOLD}{'━' * 50}{RESET}")
    color = GREEN if passed == total else YELLOW if passed >= total - 2 else RED
    print(f"{color}{BOLD}{passed}/{total} tests passed{RESET}")

    if passed < total:
        print(f"\n{YELLOW}Note: Some failures may be due to the LLM choosing")
        print(f"different tool paths. Review the responses to judge quality.{RESET}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
