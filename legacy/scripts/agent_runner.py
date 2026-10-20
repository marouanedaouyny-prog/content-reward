#!/usr/bin/env python3
"""
Automation Empire OS — Agent Runner
Entry point to run individual agents or the full agent system.
"""

import argparse
import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.getcwd())

from scripts.agent_base import get_agent_registry, AgentRegistry
from scripts.agents import register_all_agents

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_single_agent(agent_name: str):
    """Run a single agent."""
    # Register all agents
    register_all_agents()
    
    # Get the specific agent
    registry = get_agent_registry()
    agent = registry.get(agent_name)
    
    if not agent:
        logger.error(f"Agent {agent_name} not found. Available: {registry.list()}")
        return 1
    
    logger.info(f"Starting agent: {agent_name}")
    try:
        agent.run()
    except KeyboardInterrupt:
        logger.info(f"Agent {agent_name} stopped by user")
    except Exception as e:
        logger.error(f"Agent {agent_name} error: {e}")
        return 1
    
    return 0


def run_all_agents():
    """Run all agents in the current process (threaded)."""
    register_all_agents()
    
    registry = get_agent_registry()
    registry.start_all()
    
    logger.info(f"Started all agents: {registry.list()}")
    
    try:
        # Keep main thread alive
        import time
        while True:
            time.sleep(10)
            status = registry.get_all_status()
            logger.info(f"Agent status: {status}")
    except KeyboardInterrupt:
        logger.info("Shutting down all agents...")
    finally:
        registry.stop_all()
    
    return 0


def demo_workflow():
    """Run a demo workflow showing agent collaboration."""
    register_all_agents()
    
    registry = get_agent_registry()
    bus = registry.get_message_bus()
    
    # Start all agents
    registry.start_all()
    
    import time
    time.sleep(2)  # Let agents start
    
    # Demo: Researcher discovers campaigns
    researcher = registry.get("researcher")
    if researcher:
        logger.info("=== Demo: Researcher discovering campaigns ===")
        result = researcher.execute_task(type('Task', (), {
            'task_type': 'discover_campaigns',
            'payload': {'source_type': 'manual', 'manual_paste': 'Test campaign for demo'}
        })())
        logger.info(f"Researcher result: {result}")
    
    time.sleep(1)
    
    # Demo: Planner creates workflow
    planner = registry.get("planner")
    if planner:
        logger.info("=== Demo: Planner planning workflow ===")
        result = planner.execute_task(type('Task', (), {
            'task_type': 'plan_workflow',
            'payload': {'goal': 'Run content rewards pipeline', 'workflow_type': 'content_rewards'}
        })())
        logger.info(f"Planner result: {result}")
    
    time.sleep(1)
    
    # Demo: Analytics tracks revenue
    analytics = registry.get("analytics")
    if analytics:
        logger.info("=== Demo: Analytics tracking revenue ===")
        result = analytics.execute_task(type('Task', (), {
            'task_type': 'track_revenue',
            'payload': {}
        })())
        logger.info(f"Analytics result: {result}")
    
    time.sleep(1)
    
    # Demo: Fixer checks system health
    fixer = registry.get("fixer")
    if fixer:
        logger.info("=== Demo: Fixer system recovery check ===")
        result = fixer.execute_task(type('Task', (), {
            'task_type': 'system_recovery',
            'payload': {'action': 'check'}
        })())
        logger.info(f"Fixer result: {result}")
    
    # Stop all
    registry.stop_all()
    logger.info("Demo completed")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Empire OS Agent Runner")
    parser.add_argument("--agent", help="Run a specific agent (researcher, planner, builder, qa, publisher, analytics, fixer)")
    parser.add_argument("--all", action="store_true", help="Run all agents in threads")
    parser.add_argument("--demo", action="store_true", help="Run demo workflow")
    parser.add_argument("--list", action="store_true", help="List available agents")
    
    args = parser.parse_args()
    
    if args.list:
        register_all_agents()
        registry = get_agent_registry()
        print("Available agents:")
        for name in registry.list():
            agent = registry.get(name)
            print(f"  {name}: {agent.capabilities}")
        return 0
    
    if args.demo:
        return demo_workflow()
    
    if args.all:
        return run_all_agents()
    
    if args.agent:
        return run_single_agent(args.agent)
    
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())