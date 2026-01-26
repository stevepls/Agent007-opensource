#!/usr/bin/env python3
"""
Harvest Time Tracking Integration

This module integrates with Harvest API to automatically track time on tickets.
It can start/stop timers and log time entries for Airtable tickets.

Usage:
    python harvest_integration.py --ticket 4962 --start "Working on payment plan update"
    python harvest_integration.py --ticket 4962 --stop
    python harvest_integration.py --ticket 4962 --log-time 2.5 "Updated payment plan database"
"""

import os
import json
import requests
import argparse
from datetime import datetime, date
from dotenv import load_dotenv

class HarvestTimeTracker:
    def __init__(self, access_token, account_id):
        self.access_token = access_token
        self.account_id = account_id
        self.base_url = "https://api.harvestapp.com/v2"
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Harvest-Account-Id": str(account_id),
            "User-Agent": "Airtable-Harvest Integration (user@example.com)"
        }
        
        # Default project and task IDs (you may need to adjust these)
        self.default_project_id = None
        self.default_task_id = None
        
    def get_projects(self):
        """Get all available projects"""
        url = f"{self.base_url}/projects"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            projects = data.get('projects', [])
            
            print("📋 Available projects:")
            for project in projects:
                print(f"  - {project['name']} (ID: {project['id']})")
                
            return projects
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching projects: {e}")
            return []
    
    def get_tasks(self):
        """Get all available tasks"""
        url = f"{self.base_url}/tasks"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            tasks = data.get('tasks', [])
            
            print("📋 Available tasks:")
            for task in tasks:
                print(f"  - {task['name']} (ID: {task['id']})")
                
            return tasks
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching tasks: {e}")
            return []
    
    def start_timer(self, ticket_id, notes, project_id=None, task_id=None):
        """Start a timer for a ticket"""
        url = f"{self.base_url}/time_entries"
        
        # Use default project/task if not specified
        if not project_id:
            project_id = self.default_project_id or self._get_default_project_id()
        if not task_id:
            task_id = self.default_task_id or self._get_default_task_id()
            
        if not project_id or not task_id:
            print("❌ Error: Project ID and Task ID are required")
            print("Run with --list-projects and --list-tasks to see available options")
            return None
        
        data = {
            "project_id": project_id,
            "task_id": task_id,
            "notes": f"Ticket #{ticket_id}: {notes}",
            "external_reference": {
                "id": str(ticket_id),
                "group_id": "airtable-tickets",
                "permalink": f"https://airtable.com/ticket/{ticket_id}"
            }
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=data)
            response.raise_for_status()
            
            entry = response.json()
            timer_id = entry.get('id')
            
            print(f"⏱️ Started timer for ticket #{ticket_id}")
            print(f"📝 Notes: {notes}")
            print(f"🆔 Timer ID: {timer_id}")
            
            return entry
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error starting timer: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            return None
    
    def stop_timer(self, ticket_id=None):
        """Stop the currently running timer"""
        # First, get running timers
        running_timer = self._get_running_timer(ticket_id)
        
        if not running_timer:
            print("❌ No running timer found" + (f" for ticket #{ticket_id}" if ticket_id else ""))
            return None
        
        timer_id = running_timer.get('id')
        url = f"{self.base_url}/time_entries/{timer_id}/stop"
        
        try:
            response = requests.patch(url, headers=self.headers)
            response.raise_for_status()
            
            entry = response.json()
            hours = entry.get('hours', 0)
            notes = entry.get('notes', '')
            
            print(f"⏹️ Stopped timer (ID: {timer_id})")
            print(f"⏱️ Time logged: {hours} hours")
            print(f"📝 Notes: {notes}")
            
            return entry
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error stopping timer: {e}")
            return None
    
    def log_time_entry(self, ticket_id, hours, notes, project_id=None, task_id=None, entry_date=None):
        """Log a completed time entry"""
        url = f"{self.base_url}/time_entries"
        
        # Use default project/task if not specified
        if not project_id:
            project_id = self.default_project_id or self._get_default_project_id()
        if not task_id:
            task_id = self.default_task_id or self._get_default_task_id()
            
        if not project_id or not task_id:
            print("❌ Error: Project ID and Task ID are required")
            return None
        
        # Use today if no date specified
        if not entry_date:
            entry_date = date.today().strftime('%Y-%m-%d')
        
        data = {
            "project_id": project_id,
            "task_id": task_id,
            "spent_date": entry_date,
            "hours": hours,
            "notes": f"Ticket #{ticket_id}: {notes}",
            "external_reference": {
                "id": str(ticket_id),
                "group_id": "airtable-tickets",
                "permalink": f"https://airtable.com/ticket/{ticket_id}"
            }
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=data)
            response.raise_for_status()
            
            entry = response.json()
            entry_id = entry.get('id')
            
            print(f"📊 Logged {hours} hours for ticket #{ticket_id}")
            print(f"📝 Notes: {notes}")
            print(f"📅 Date: {entry_date}")
            print(f"🆔 Entry ID: {entry_id}")
            
            return entry
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error logging time entry: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            return None
    
    def _get_running_timer(self, ticket_id=None):
        """Get currently running timer, optionally filtered by ticket"""
        url = f"{self.base_url}/time_entries"
        params = {"is_running": "true"}
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            timers = data.get('time_entries', [])
            
            if not timers:
                return None
            
            # If ticket_id specified, find timer for that ticket
            if ticket_id:
                for timer in timers:
                    external_ref = timer.get('external_reference', {})
                    if external_ref.get('id') == str(ticket_id):
                        return timer
                return None
            
            # Return first running timer
            return timers[0] if timers else None
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error getting running timers: {e}")
            return None
    
    def _get_default_project_id(self):
        """Try to find a default project (you may want to customize this)"""
        projects = self.get_projects()
        
        # Look for common project names
        for project in projects:
            name = project['name'].lower()
            if any(keyword in name for keyword in ['development', 'dev', 'tickets', 'airtable', 'default']):
                print(f"🎯 Using default project: {project['name']} (ID: {project['id']})")
                return project['id']
        
        # If no default found, use first active project
        active_projects = [p for p in projects if p.get('is_active', True)]
        if active_projects:
            project = active_projects[0]
            print(f"🎯 Using first active project: {project['name']} (ID: {project['id']})")
            return project['id']
        
        return None
    
    def _get_default_task_id(self):
        """Try to find a default task (you may want to customize this)"""
        tasks = self.get_tasks()
        
        # Look for common task names
        for task in tasks:
            name = task['name'].lower()
            if any(keyword in name for keyword in ['development', 'programming', 'coding', 'ticket', 'default']):
                print(f"🎯 Using default task: {task['name']} (ID: {task['id']})")
                return task['id']
        
        # If no default found, use first active task
        active_tasks = [t for t in tasks if t.get('is_active', True)]
        if active_tasks:
            task = active_tasks[0]
            print(f"🎯 Using first active task: {task['name']} (ID: {task['id']})")
            return task['id']
        
        return None

def main():
    parser = argparse.ArgumentParser(description='Harvest time tracking for Airtable tickets')
    parser.add_argument('--ticket', type=int, help='Ticket ID (numeric)')
    parser.add_argument('--start', help='Start timer with notes')
    parser.add_argument('--stop', action='store_true', help='Stop running timer')
    parser.add_argument('--log-time', type=float, help='Log completed time (hours)')
    parser.add_argument('--notes', help='Notes for time entry')
    parser.add_argument('--project-id', type=int, help='Harvest project ID')
    parser.add_argument('--task-id', type=int, help='Harvest task ID')
    parser.add_argument('--date', help='Date for time entry (YYYY-MM-DD)')
    parser.add_argument('--list-projects', action='store_true', help='List available projects')
    parser.add_argument('--list-tasks', action='store_true', help='List available tasks')
    
    args = parser.parse_args()
    
    # Load environment variables
    load_dotenv()
    
    # Harvest credentials (from environment or credentials.env)
    ACCESS_TOKEN = os.getenv('HARVEST_ACCESS_TOKEN')
    ACCOUNT_ID = os.getenv('HARVEST_ACCOUNT_ID')
    
    if not ACCESS_TOKEN or not ACCOUNT_ID:
        print("❌ Error: Harvest credentials not found")
        print("Please set HARVEST_ACCESS_TOKEN and HARVEST_ACCOUNT_ID environment variables")
        return
    
    # Initialize tracker
    tracker = HarvestTimeTracker(ACCESS_TOKEN, ACCOUNT_ID)
    
    # Handle listing operations
    if args.list_projects:
        tracker.get_projects()
        return
    
    if args.list_tasks:
        tracker.get_tasks()
        return
    
    # Handle timer operations
    if args.start:
        if not args.ticket:
            print("❌ Error: --ticket is required for --start")
            return
        tracker.start_timer(args.ticket, args.start, args.project_id, args.task_id)
        return
    
    if args.stop:
        tracker.stop_timer(args.ticket)
        return
    
    if args.log_time:
        if not args.ticket or not args.notes:
            print("❌ Error: --ticket and --notes are required for --log-time")
            return
        tracker.log_time_entry(args.ticket, args.log_time, args.notes, args.project_id, args.task_id, args.date)
        return
    
    # If no action specified, show help
    parser.print_help()

if __name__ == "__main__":
    main() 