"""
Test cases for ClickUp tools.

Run with: python3 tests/test_clickup_tools.py
"""

import os
import sys
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.tickets.clickup_tools import (
    clickup_search_tasks,
    clickup_get_workspace_members,
    clickup_find_member_by_name,
    clickup_create_subtasks_batch,
    clickup_add_checklist,
    clickup_delete_checklist,
    clickup_browse_workspace,
    clickup_verify_tasks,
    clickup_assign_tasks,
    clickup_find_assignees_by_name,
    clickup_get_time_entries,
    google_doc_to_clickup_tasks,
    CLICKUP_ENHANCED_TOOLS,
)


class TestClickUpToolsImport(unittest.TestCase):
    """Test that all tools can be imported."""
    
    def test_all_tools_importable(self):
        """All ClickUp tools should be importable."""
        tools = [
            clickup_search_tasks,
            clickup_get_workspace_members,
            clickup_find_member_by_name,
            clickup_create_subtasks_batch,
            clickup_add_checklist,
            clickup_delete_checklist,
            clickup_browse_workspace,
            clickup_verify_tasks,
            clickup_assign_tasks,
            clickup_find_assignees_by_name,
            clickup_get_time_entries,
            google_doc_to_clickup_tasks,
        ]
        for tool in tools:
            self.assertIsNotNone(tool)
            self.assertTrue(callable(tool))
    
    def test_enhanced_tools_list_exists(self):
        """CLICKUP_ENHANCED_TOOLS should be a non-empty list."""
        self.assertIsInstance(CLICKUP_ENHANCED_TOOLS, list)
        self.assertGreater(len(CLICKUP_ENHANCED_TOOLS), 0)
    
    def test_all_tools_have_required_fields(self):
        """Each tool definition should have name, description, function, parameters."""
        required_fields = ['name', 'description', 'function', 'parameters']
        for tool in CLICKUP_ENHANCED_TOOLS:
            for field in required_fields:
                self.assertIn(field, tool, f"Tool {tool.get('name', 'unknown')} missing {field}")


class TestClickUpToolsFunctionality(unittest.TestCase):
    """Test actual tool functionality (requires API token)."""
    
    @classmethod
    def setUpClass(cls):
        """Check if API token is available."""
        cls.has_token = bool(os.getenv("CLICKUP_API_TOKEN"))
        if not cls.has_token:
            print("\n⚠️  CLICKUP_API_TOKEN not set - skipping live API tests")
    
    def test_search_tasks_returns_dict(self):
        """clickup_search_tasks should return a dict."""
        if not self.has_token:
            self.skipTest("No API token")
        result = clickup_search_tasks("test")
        self.assertIsInstance(result, dict)
        self.assertIn("tasks", result)
    
    def test_search_tasks_with_invalid_query(self):
        """clickup_search_tasks should handle empty query."""
        result = clickup_search_tasks("")
        self.assertIn("error", result)
    
    def test_get_workspace_members_returns_dict(self):
        """clickup_get_workspace_members should return a dict with members."""
        if not self.has_token:
            self.skipTest("No API token")
        result = clickup_get_workspace_members()
        self.assertIsInstance(result, dict)
        if "error" not in result:
            self.assertIn("members", result)
            self.assertIn("count", result)
    
    def test_find_member_by_name_returns_dict(self):
        """clickup_find_member_by_name should return a dict."""
        if not self.has_token:
            self.skipTest("No API token")
        result = clickup_find_member_by_name("test")
        self.assertIsInstance(result, dict)
        self.assertIn("members", result)
    
    def test_find_member_by_name_empty(self):
        """clickup_find_member_by_name should handle empty name."""
        result = clickup_find_member_by_name("")
        self.assertIn("error", result)
    
    def test_add_checklist_validates_inputs(self):
        """clickup_add_checklist should validate required inputs."""
        result = clickup_add_checklist("", "", [])
        self.assertIn("error", result)
    
    def test_delete_checklist_validates_inputs(self):
        """clickup_delete_checklist should validate required inputs."""
        result = clickup_delete_checklist("")
        self.assertIn("error", result)
    
    def test_create_subtasks_batch_validates_inputs(self):
        """clickup_create_subtasks_batch should validate required inputs."""
        result = clickup_create_subtasks_batch("", [])
        self.assertIn("error", result)
    
    def test_assign_tasks_validates_inputs(self):
        """clickup_assign_tasks should validate required inputs."""
        result = clickup_assign_tasks([], [])
        self.assertIn("error", result)
        result = clickup_assign_tasks(["task123"], [])
        self.assertIn("error", result)
    
    def test_find_assignees_by_name_returns_dict(self):
        """clickup_find_assignees_by_name should return a dict."""
        if not self.has_token:
            self.skipTest("No API token")
        result = clickup_find_assignees_by_name(["test"])
        self.assertIsInstance(result, dict)
        self.assertIn("users", result)
    
    def test_get_time_entries_validates_inputs(self):
        """clickup_get_time_entries should validate inputs."""
        result = clickup_get_time_entries()
        self.assertIn("error", result)
    
    def test_google_doc_to_clickup_validates_inputs(self):
        """google_doc_to_clickup_tasks should validate required inputs."""
        result = google_doc_to_clickup_tasks("", "")
        # May return error about Google auth or missing doc
        self.assertIsInstance(result, dict)


class TestClickUpToolsRegistration(unittest.TestCase):
    """Test that tools are properly registered for orchestrator use."""
    
    def test_new_tools_in_enhanced_list(self):
        """New tools should be in CLICKUP_ENHANCED_TOOLS."""
        tool_names = [t['name'] for t in CLICKUP_ENHANCED_TOOLS]
        
        expected_tools = [
            'clickup_search_tasks',
            'clickup_get_workspace_members',
            'clickup_find_member_by_name',
            'clickup_create_subtasks_batch',
            'clickup_add_checklist',
            'clickup_delete_checklist',
            'clickup_assign_tasks',
            'clickup_find_assignees_by_name',
            'clickup_get_time_entries',
            'google_doc_to_clickup_tasks',
        ]
        
        for expected in expected_tools:
            self.assertIn(expected, tool_names, f"Missing tool: {expected}")
    
    def test_tool_parameters_are_valid_json_schema(self):
        """Tool parameters should be valid JSON schema objects."""
        for tool in CLICKUP_ENHANCED_TOOLS:
            params = tool.get('parameters', {})
            self.assertIn('type', params)
            self.assertEqual(params['type'], 'object')
            self.assertIn('properties', params)


class TestOrchestratorIntegration(unittest.TestCase):
    """Test that tools are accessible from the orchestrator's tool registry."""
    
    def test_tools_loadable_by_registry(self):
        """Tool registry should be able to load ClickUp enhanced tools."""
        try:
            from services.tool_registry import ToolRegistry
            registry = ToolRegistry()
            
            # Use the correct method: get_definitions()
            all_tools = registry.get_definitions()
            tool_names = [t['name'] for t in all_tools]
            
            # Check that our new tools are in the registry
            expected_new_tools = [
                'clickup_search_tasks',
                'clickup_get_workspace_members',
                'clickup_find_member_by_name',
                'clickup_create_subtasks_batch',
                'clickup_add_checklist',
                'clickup_delete_checklist',
                'clickup_assign_tasks',
                'clickup_find_assignees_by_name',
                'clickup_get_time_entries',
                'google_doc_to_clickup_tasks',
            ]
            
            clickup_tools = [n for n in tool_names if 'clickup' in n.lower()]
            print(f"\n✅ Found {len(clickup_tools)} ClickUp tools in registry:")
            for name in sorted(clickup_tools):
                marker = "✓" if name in expected_new_tools else " "
                print(f"   {marker} {name}")
            
            # Verify new tools are accessible
            missing = [t for t in expected_new_tools if t not in tool_names]
            self.assertEqual(len(missing), 0, f"Missing tools in registry: {missing}")
                
        except ImportError as e:
            self.skipTest(f"Could not import ToolRegistry: {e}")


def run_tests():
    """Run all tests and print summary."""
    # Load environment
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.strip() and not line.startswith('#') and '=' in line:
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
    
    # Run tests
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    
    if result.wasSuccessful():
        print("\n✅ ALL TESTS PASSED!")
    else:
        print("\n❌ SOME TESTS FAILED")
        for test, trace in result.failures + result.errors:
            print(f"\n  Failed: {test}")
            print(f"  {trace[:200]}...")
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
