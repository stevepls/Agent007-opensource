"""
Tests for COO/CFO persona — routing, classification, advisor tool wiring,
dashboard rendering, and system prompt content.

Run with: pytest tests/test_coo_cfo.py -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_chat import (
    SYSTEM_PROMPT,
    TOOL_DOMAINS,
    KEYWORD_TO_CATEGORY,
    STRUCTURED_SCHEMAS,
    _detect_tool_domains,
    _classify_request_keywords,
    _make_status_card,
    _make_structured_data,
)


# ============================================================================
# System Prompt — COO/CFO persona is present
# ============================================================================

class TestSystemPromptPersona(unittest.TestCase):
    """Verify the system prompt establishes the COO/CFO identity."""

    def test_identifies_as_coo_cfo(self):
        self.assertIn("COO/CFO", SYSTEM_PROMPT)

    def test_identifies_company(self):
        self.assertIn("People Like Software", SYSTEM_PROMPT)

    def test_has_decision_hierarchy(self):
        self.assertIn("Revenue impact", SYSTEM_PROMPT)
        self.assertIn("Client satisfaction", SYSTEM_PROMPT)

    def test_has_escalation_tiers(self):
        self.assertIn("CRITICAL", SYSTEM_PROMPT)
        self.assertIn("WARNING", SYSTEM_PROMPT)
        self.assertIn("INFO", SYSTEM_PROMPT)

    def test_mentions_advisor_tools(self):
        self.assertIn("advisor_get_health_report", SYSTEM_PROMPT)
        self.assertIn("advisor_get_advisories", SYSTEM_PROMPT)
        self.assertIn("advisor_get_trends", SYSTEM_PROMPT)
        self.assertIn("advisor_take_snapshot", SYSTEM_PROMPT)

    def test_business_intelligence_section_exists(self):
        self.assertIn("### Business Intelligence", SYSTEM_PROMPT)

    def test_executive_response_style(self):
        """Prompt should instruct the agent to interpret, not just dump data."""
        self.assertIn("interpret", SYSTEM_PROMPT.lower())

    def test_anti_hallucination_preserved(self):
        """Safety rails must survive the persona rewrite."""
        self.assertIn("NEVER fabricate IDs", SYSTEM_PROMPT)
        self.assertIn("No phantom data", SYSTEM_PROMPT)
        self.assertIn("verification.verified", SYSTEM_PROMPT)

    def test_act_dont_ask_preserved(self):
        self.assertIn("ACT, DON'T ASK", SYSTEM_PROMPT)


# ============================================================================
# Keyword routing — business queries hit the advisor domain
# ============================================================================

class TestBusinessKeywordRouting(unittest.TestCase):
    """Verify business-related keywords route to the advisor category."""

    ADVISOR_QUERIES = [
        "how's the business",
        "how is the business",
        "show me the health report",
        "what are our KPIs",
        "any advisories I should know about?",
        "show me business trends",
        "what's our revenue looking like",
        "check profitability",
        "what's the utilization rate",
        "run a SWOT analysis",
        "what's our business health score",
    ]

    def test_advisor_keywords_in_tool_domains(self):
        """All advisor keywords should be in TOOL_DOMAINS."""
        advisor_kws = [k for k, v in KEYWORD_TO_CATEGORY.items() if v == "advisor"]
        for kw in advisor_kws:
            self.assertIn(kw, TOOL_DOMAINS,
                          f"Advisor keyword '{kw}' missing from TOOL_DOMAINS")

    def test_advisor_queries_classify_as_orchestrator(self):
        """Business questions should route to orchestrator (not direct/crew)."""
        for query in self.ADVISOR_QUERIES:
            result = _classify_request_keywords(query)
            self.assertEqual(result, "orchestrator",
                             f"'{query}' classified as '{result}', expected 'orchestrator'")

    def test_advisor_queries_detect_advisor_domain(self):
        """Business questions should include 'advisor' in detected domains."""
        for query in self.ADVISOR_QUERIES:
            domains = _detect_tool_domains(query)
            self.assertIn("advisor", domains,
                          f"'{query}' did not detect advisor domain, got {domains}")

    def test_general_always_included(self):
        """The 'general' domain should always be present."""
        domains = _detect_tool_domains("how's the business")
        self.assertIn("general", domains)

    def test_non_business_query_excludes_advisor(self):
        """Regular queries should not trigger advisor domain."""
        domains = _detect_tool_domains("show my clickup tasks")
        self.assertNotIn("advisor", domains)


# ============================================================================
# Classification edge cases — business queries don't misroute
# ============================================================================

class TestClassificationEdgeCases(unittest.TestCase):
    """Edge cases for request classification around business queries."""

    def test_short_business_query(self):
        """Short business queries should still route to orchestrator."""
        self.assertEqual(_classify_request_keywords("health report"), "orchestrator")
        self.assertEqual(_classify_request_keywords("show advisories"), "orchestrator")
        self.assertEqual(_classify_request_keywords("business trends"), "orchestrator")

    def test_mixed_domain_query(self):
        """Queries touching multiple domains should route to orchestrator."""
        result = _classify_request_keywords("compare harvest hours to our revenue trends")
        self.assertEqual(result, "orchestrator")

    def test_casual_business_question(self):
        """Casual phrasing should still trigger orchestrator."""
        self.assertEqual(
            _classify_request_keywords("how's the business doing today"),
            "orchestrator",
        )

    def test_greeting_stays_direct(self):
        """Plain greetings should not trigger orchestrator."""
        self.assertEqual(_classify_request_keywords("hey"), "direct")
        self.assertEqual(_classify_request_keywords("good morning"), "direct")


# ============================================================================
# Status cards — advisor tools render correctly
# ============================================================================

class TestAdvisorStatusCards(unittest.TestCase):
    """Verify status cards render correctly for advisor tool results."""

    def test_health_report_high_score(self):
        result = {"health_score": 85, "advisories": []}
        card = _make_status_card("advisor_get_health_report", result)
        self.assertIsNotNone(card)
        self.assertEqual(card["type"], "success")
        self.assertIn("85", card["title"])

    def test_health_report_medium_score(self):
        result = {"health_score": 55, "advisories": [{"severity": "warning"}]}
        card = _make_status_card("advisor_get_health_report", result)
        self.assertEqual(card["type"], "warning")

    def test_health_report_low_score(self):
        result = {"health_score": 30, "advisories": [{"severity": "critical"}]}
        card = _make_status_card("advisor_get_health_report", result)
        self.assertEqual(card["type"], "error")
        self.assertIn("1 critical", card["description"])

    def test_advisories_all_clear(self):
        result = {"total": 0, "by_severity": {}}
        card = _make_status_card("advisor_get_advisories", result)
        self.assertIsNotNone(card)
        self.assertEqual(card["type"], "success")
        self.assertIn("All clear", card["description"])

    def test_advisories_with_critical(self):
        result = {"total": 5, "by_severity": {"critical": 2, "warning": 3}}
        card = _make_status_card("advisor_get_advisories", result)
        self.assertEqual(card["type"], "error")
        self.assertIn("2 critical", card["description"])

    def test_advisories_warnings_only(self):
        result = {"total": 3, "by_severity": {"warning": 3}}
        card = _make_status_card("advisor_get_advisories", result)
        self.assertEqual(card["type"], "warning")

    def test_trends_all_healthy(self):
        result = {"trends_count": 6, "unhealthy": 0, "healthy": 6}
        card = _make_status_card("advisor_get_trends", result)
        self.assertEqual(card["type"], "success")
        self.assertIn("All healthy", card["description"])

    def test_trends_some_declining(self):
        result = {"trends_count": 6, "unhealthy": 2, "healthy": 4}
        card = _make_status_card("advisor_get_trends", result)
        self.assertEqual(card["type"], "warning")
        self.assertIn("2 declining", card["description"])

    def test_snapshot_card(self):
        result = {"status": "success", "timestamp": "2026-03-24T10:00:00"}
        card = _make_status_card("advisor_take_snapshot", result)
        self.assertIsNotNone(card)
        self.assertEqual(card["type"], "success")
        self.assertIn("Snapshot", card["title"])

    def test_error_result_returns_none(self):
        """Tool errors should not produce a status card."""
        result = {"error": "connection failed"}
        card = _make_status_card("advisor_get_health_report", result)
        self.assertIsNone(card)


# ============================================================================
# Structured schemas — advisor data renders as dashboard tables
# ============================================================================

class TestAdvisorStructuredSchemas(unittest.TestCase):
    """Verify advisor tools have correct structured schemas for table rendering."""

    def test_advisories_schema_exists(self):
        self.assertIn("advisor_get_advisories", STRUCTURED_SCHEMAS)

    def test_advisories_schema_columns(self):
        schema = STRUCTURED_SCHEMAS["advisor_get_advisories"]
        col_keys = [c["key"] for c in schema["columns"]]
        self.assertIn("severity", col_keys)
        self.assertIn("category", col_keys)
        self.assertIn("title", col_keys)
        self.assertIn("recommendation", col_keys)

    def test_advisories_schema_row_path(self):
        schema = STRUCTURED_SCHEMAS["advisor_get_advisories"]
        self.assertEqual(schema["row_path"], "advisories")

    def test_trends_schema_exists(self):
        self.assertIn("advisor_get_trends", STRUCTURED_SCHEMAS)

    def test_trends_schema_columns(self):
        schema = STRUCTURED_SCHEMAS["advisor_get_trends"]
        col_keys = [c["key"] for c in schema["columns"]]
        self.assertIn("metric", col_keys)
        self.assertIn("current", col_keys)
        self.assertIn("change_pct", col_keys)
        self.assertIn("direction", col_keys)

    def test_trends_schema_row_path(self):
        schema = STRUCTURED_SCHEMAS["advisor_get_trends"]
        self.assertEqual(schema["row_path"], "trends")

    def test_advisories_structured_data_renders(self):
        """Full advisory result should produce structured table data."""
        result = {
            "total": 2,
            "advisories": [
                {
                    "severity": "critical",
                    "category": "revenue",
                    "title": "Hours down 40% WoW",
                    "recommendation": "Check if team is logging time",
                },
                {
                    "severity": "warning",
                    "category": "task_management",
                    "title": "12 overdue tasks",
                    "recommendation": "Review and reprioritize backlog",
                },
            ],
        }
        structured = _make_structured_data("advisor_get_advisories", result)
        self.assertIsNotNone(structured)
        self.assertEqual(structured["title"], "Business Advisories")
        self.assertEqual(len(structured["rows"]), 2)
        self.assertEqual(structured["rows"][0]["severity"], "critical")

    def test_trends_structured_data_renders(self):
        """Full trends result should produce structured table data."""
        result = {
            "period_days": 30,
            "trends_count": 2,
            "healthy": 1,
            "unhealthy": 1,
            "trends": [
                {
                    "metric": "Weekly Hours",
                    "current": 35.0,
                    "previous": 40.0,
                    "change_pct": -12.5,
                    "direction": "down",
                    "is_healthy": False,
                },
                {
                    "metric": "Tasks Completed",
                    "current": 15,
                    "previous": 12,
                    "change_pct": 25.0,
                    "direction": "up",
                    "is_healthy": True,
                },
            ],
        }
        structured = _make_structured_data("advisor_get_trends", result)
        self.assertIsNotNone(structured)
        self.assertEqual(structured["title"], "Business Trends")
        self.assertEqual(len(structured["rows"]), 2)
        self.assertEqual(structured["rows"][0]["metric"], "Weekly Hours")

    def test_empty_advisories_returns_none(self):
        """Empty advisory list should not produce a table."""
        result = {"total": 0, "advisories": []}
        structured = _make_structured_data("advisor_get_advisories", result)
        self.assertIsNone(structured)


# ============================================================================
# CrewAI orchestrator — persona is consistent
# ============================================================================

class TestCrewAIPersona(unittest.TestCase):
    """Verify the CrewAI orchestrator agent has the COO/CFO identity."""

    def test_backstory_has_coo_cfo(self):
        from crews.orchestrator_crew import ORCHESTRATOR_AGENT_BACKSTORY
        self.assertIn("COO/CFO", ORCHESTRATOR_AGENT_BACKSTORY)

    def test_backstory_has_company(self):
        from crews.orchestrator_crew import ORCHESTRATOR_AGENT_BACKSTORY
        self.assertIn("People Like Software", ORCHESTRATOR_AGENT_BACKSTORY)

    def test_backstory_has_advisor_tools(self):
        from crews.orchestrator_crew import ORCHESTRATOR_AGENT_BACKSTORY
        self.assertIn("advisor_get_health_report", ORCHESTRATOR_AGENT_BACKSTORY)
        self.assertIn("advisor_get_advisories", ORCHESTRATOR_AGENT_BACKSTORY)
        self.assertIn("advisor_get_trends", ORCHESTRATOR_AGENT_BACKSTORY)

    def test_backstory_has_business_intelligence_category(self):
        from crews.orchestrator_crew import ORCHESTRATOR_AGENT_BACKSTORY
        self.assertIn("Business Intelligence", ORCHESTRATOR_AGENT_BACKSTORY)

    def test_backstory_has_business_judgment(self):
        from crews.orchestrator_crew import ORCHESTRATOR_AGENT_BACKSTORY
        self.assertIn("Revenue impact", ORCHESTRATOR_AGENT_BACKSTORY)

    def test_agent_role(self):
        from crews.orchestrator_crew import create_orchestrator_agent
        agent = create_orchestrator_agent(tools=[])
        self.assertIn("COO/CFO", agent.role)
        self.assertIn("People Like Software", agent.role)

    def test_agent_goal_mentions_revenue(self):
        from crews.orchestrator_crew import create_orchestrator_agent
        agent = create_orchestrator_agent(tools=[])
        self.assertIn("revenue", agent.goal.lower())

    def test_agent_goal_mentions_client_health(self):
        from crews.orchestrator_crew import create_orchestrator_agent
        agent = create_orchestrator_agent(tools=[])
        self.assertIn("client health", agent.goal.lower())


# ============================================================================
# Advisor tools — registered and callable
# ============================================================================

class TestAdvisorToolsRegistered(unittest.TestCase):
    """Verify advisor tools are registered in the tool registry."""

    def test_advisor_tools_importable(self):
        from services.business_advisor import (
            advisor_take_snapshot,
            advisor_get_advisories,
            advisor_get_health_report,
            advisor_get_trends,
            ADVISOR_TOOLS,
        )
        self.assertTrue(callable(advisor_take_snapshot))
        self.assertTrue(callable(advisor_get_advisories))
        self.assertTrue(callable(advisor_get_health_report))
        self.assertTrue(callable(advisor_get_trends))

    def test_advisor_tools_list_complete(self):
        from services.business_advisor import ADVISOR_TOOLS
        names = [t["name"] for t in ADVISOR_TOOLS]
        self.assertIn("advisor_take_snapshot", names)
        self.assertIn("advisor_get_advisories", names)
        self.assertIn("advisor_get_health_report", names)
        self.assertIn("advisor_get_trends", names)

    def test_advisor_tools_have_required_fields(self):
        from services.business_advisor import ADVISOR_TOOLS
        for tool in ADVISOR_TOOLS:
            self.assertIn("name", tool, f"Tool missing 'name': {tool}")
            self.assertIn("description", tool, f"Tool missing 'description': {tool}")
            self.assertIn("function", tool, f"Tool missing 'function': {tool}")
            self.assertIn("parameters", tool, f"Tool missing 'parameters': {tool}")
            self.assertTrue(callable(tool["function"]),
                            f"Tool '{tool['name']}' function not callable")


if __name__ == "__main__":
    unittest.main()
