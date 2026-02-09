#!/usr/bin/env python3
"""
Team Check-in Agent - Main Entry Point

Runs the team check-in agent either:
1. As a one-time run (for cron/systemd)
2. As a long-running daemon with scheduling

Usage:
    # One-time run (for cron/systemd)
    python main.py

    # Long-running daemon
    python main.py --daemon

    # Run with custom config
    python main.py --config /path/to/team.json
"""

import argparse
import sys
import time
import signal
from pathlib import Path
from datetime import datetime
import pytz

# Add parent directories to path
AGENT_ROOT = Path(__file__).parent
ORCHESTRATOR_ROOT = AGENT_ROOT.parent.parent
sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from agents.team_checkin.agent import TeamCheckinAgent


class AgentDaemon:
    """Daemon wrapper for the agent."""
    
    def __init__(self, agent: TeamCheckinAgent, interval_hours: float = 2.0):
        self.agent = agent
        self.interval_seconds = interval_hours * 3600
        self.running = True
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print(f"\n🛑 Received signal {signum}, shutting down...")
        self.running = False
    
    def run(self):
        """Run the daemon loop."""
        print("🚀 Starting Team Check-in Agent Daemon")
        print(f"⏰ Check interval: {self.interval_seconds / 3600:.1f} hours")
        print("Press Ctrl+C to stop\n")
        
        while self.running:
            try:
                # Run check-in cycle
                self.agent.run()
                
                # Wait for next interval
                if self.running:
                    print(f"\n⏳ Next check in {self.interval_seconds / 3600:.1f} hours...")
                    time.sleep(self.interval_seconds)
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.agent.logger.error(f"Error in daemon loop: {e}", exc_info=True)
                # Wait a bit before retrying
                time.sleep(60)
        
        print("\n✅ Agent daemon stopped")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Team Check-in and Time Tracking Agent"
    )
    parser.add_argument(
        '--daemon',
        action='store_true',
        help='Run as long-running daemon (default: one-time run)'
    )
    parser.add_argument(
        '--config',
        type=Path,
        help='Path to team.json config file'
    )
    parser.add_argument(
        '--state',
        type=Path,
        help='Path to state.json file'
    )
    parser.add_argument(
        '--log',
        type=Path,
        help='Path to log file'
    )
    parser.add_argument(
        '--interval',
        type=float,
        default=2.0,
        help='Check interval in hours (default: 2.0)'
    )
    parser.add_argument(
        '--no-auto-detect',
        action='store_true',
        help='Disable auto-detection of team members from ClickUp'
    )
    parser.add_argument(
        '--refresh-team-cache',
        action='store_true',
        help='Force refresh of team member cache from ClickUp'
    )
    
    args = parser.parse_args()
    
    # Initialize agent
    try:
        agent = TeamCheckinAgent(
            config_path=args.config,
            state_path=args.state,
            log_path=args.log,
            auto_detect=not args.no_auto_detect,
            refresh_team_cache=args.refresh_team_cache
        )
    except Exception as e:
        print(f"❌ Failed to initialize agent: {e}")
        sys.exit(1)
    
    # Run agent
    if args.daemon:
        daemon = AgentDaemon(agent, interval_hours=args.interval)
        daemon.run()
    else:
        # One-time run
        print("🔄 Running one-time check-in cycle...")
        agent.run()
        print("✅ Check-in cycle complete")


if __name__ == '__main__':
    main()
