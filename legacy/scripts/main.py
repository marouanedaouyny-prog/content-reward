#!/usr/bin/env python3
"""
Automation Empire OS — Main Entry Point
Run the empire as a money printer with full agent autonomy.
"""

import argparse
import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.getcwd())

from scripts.empire_coordinator import run_empire, EmpireCoordinator
from scripts.agent_runner import main as agent_runner_main

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Automation Empire OS - Autonomous Money Printer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run empire autonomously (continuous cycles)
  python -m scripts.main
  
  # Run one cycle and exit
  python -m scripts.main --once
  
  # Run with custom cycle interval (10 minutes)
  python -m scripts.main --cycle-interval 600
  
  # Run specific agent only
  python -m scripts.main --agent researcher
  
  # Run all agents in threads (no orchestrator cycles)
  python -m scripts.main --agents-only
  
  # Demo agent collaboration
  python -m scripts.main --demo
        """
    )
    
    # Empire coordinator options
    parser.add_argument("--once", action="store_true", help="Run one empire cycle and exit")
    parser.add_argument("--cycle-interval", type=int, default=300, help="Cycle interval in seconds (default: 300)")
    parser.add_argument("--max-jobs", type=int, default=10, help="Max concurrent jobs (default: 10)")
    parser.add_argument("--max-campaigns", type=int, default=3, help="Max campaigns per cycle (default: 3)")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode - no actual publishing")
    
    # Agent runner options
    parser.add_argument("--agent", help="Run a specific agent (researcher, planner, builder, qa, publisher, analytics, fixer)")
    parser.add_argument("--agents-only", action="store_true", help="Run all agents in threads without empire coordinator")
    parser.add_argument("--demo", action="store_true", help="Run demo workflow showing agent collaboration")
    parser.add_argument("--list-agents", action="store_true", help="List available agents")
    
    args = parser.parse_args()
    
    if args.list_agents:
        from scripts.agents import register_all_agents
        from scripts.agent_base import get_agent_registry
        register_all_agents()
        registry = get_agent_registry()
        print("Available agents:")
        for name in registry.list():
            agent = registry.get(name)
            print(f"  {name}: {agent.capabilities}")
        return 0
    
    if args.demo:
        # Run demo through agent runner
        sys.argv = [sys.argv[0], "--demo"]
        return agent_runner_main()
    
    if args.agent:
        # Run specific agent through agent runner
        sys.argv = [sys.argv[0], "--agent", args.agent]
        return agent_runner_main()
    
    if args.agents_only:
        # Run all agents in threads
        sys.argv = [sys.argv[0], "--all"]
        return agent_runner_main()
    
    # Default: Run empire coordinator
    config = {
        "cycle_interval": args.cycle_interval,
        "max_concurrent_jobs": args.max_jobs,
        "max_campaigns_per_cycle": args.max_campaigns,
        "dry_run": args.dry_run,
    }
    
    if args.once:
        coordinator = EmpireCoordinator(config)
        coordinator.initialize()
        coordinator.run_cycle()
        return 0
    
    run_empire(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())