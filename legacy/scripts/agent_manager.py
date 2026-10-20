#!/usr/bin/env python3
"""
Automation Empire OS — Agent Manager
Spawns and manages agents in parallel using tmux for true isolation.
"""

import os
import subprocess
import time
import threading
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class AgentProcess:
    """Represents a running agent process."""
    name: str
    session_name: str
    tmux_session: str
    status: str = "starting"
    pid: Optional[int] = None
    started_at: float = 0


class AgentManager:
    """Manages agent processes using tmux for isolation."""
    
    def __init__(self, project_dir: str = None):
        self.project_dir = project_dir or os.getcwd()
        self.agents: Dict[str, AgentProcess] = {}
        self.lock = threading.Lock()
        self.tmux_prefix = "empire-agent"
    
    def _get_tmux_session_name(self, agent_name: str) -> str:
        """Get tmux session name for an agent."""
        return f"{self.tmux_prefix}-{agent_name}"
    
    def _tmux_exists(self, session_name: str) -> bool:
        """Check if tmux session exists."""
        result = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True
        )
        return result.returncode == 0
    
    def _run_tmux(self, *args, check=True) -> subprocess.CompletedProcess:
        """Run a tmux command."""
        return subprocess.run(["tmux", *args], capture_output=True, text=True, check=check)
    
    def spawn_agent(self, agent_name: str, agent_module: str = "scripts.agents",
                    agent_class: str = None, args: List[str] = None) -> bool:
        """Spawn an agent in a tmux session."""
        session_name = self._get_tmux_session_name(agent_name)
        
        with self.lock:
            if agent_name in self.agents:
                logger.warning(f"Agent {agent_name} already spawned")
                return False
            
            if self._tmux_exists(session_name):
                logger.warning(f"Tmux session {session_name} already exists")
                # Try to clean up
                self._run_tmux("kill-session", "-t", session_name, check=False)
                time.sleep(1)
        
        # Build the command to run the agent
        if agent_class:
            cmd = f"cd {self.project_dir} && python -c \"from {agent_module} import {agent_class}; import asyncio; {agent_class}().run()\""
        else:
            # Default: run the agent registry which starts all agents
            cmd = f"cd {self.project_dir} && python -m scripts.agent_runner --agent {agent_name}"
        
        # Create tmux session
        logger.info(f"Spawning agent {agent_name} in tmux session {session_name}")
        
        result = self._run_tmux("new-session", "-d", "-s", session_name, "-x", "120", "-y", "40", cmd)
        
        if result.returncode != 0:
            logger.error(f"Failed to create tmux session: {result.stderr}")
            return False
        
        # Wait a moment for startup
        time.sleep(2)
        
        # Capture initial output to verify it started
        capture = self._run_tmux("capture-pane", "-t", session_name, "-p", "-S", "-10")
        logger.info(f"Agent {agent_name} startup output: {capture.stdout[:200]}")
        
        with self.lock:
            self.agents[agent_name] = AgentProcess(
                name=agent_name,
                session_name=session_name,
                tmux_session=session_name,
                status="running",
                started_at=time.time()
            )
        
        return True
    
    def send_command(self, agent_name: str, command: str) -> bool:
        """Send a command to a running agent."""
        with self.lock:
            agent = self.agents.get(agent_name)
        
        if not agent:
            logger.error(f"Agent {agent_name} not found")
            return False
        
        session_name = agent.tmux_session
        
        # Send the command
        result = self._run_tmux("send-keys", "-t", session_name, command, "Enter")
        
        if result.returncode != 0:
            logger.error(f"Failed to send command to {agent_name}: {result.stderr}")
            return False
        
        return True
    
    def get_output(self, agent_name: str, lines: int = 50) -> str:
        """Get recent output from an agent."""
        with self.lock:
            agent = self.agents.get(agent_name)
        
        if not agent:
            return f"Agent {agent_name} not found"
        
        result = self._run_tmux("capture-pane", "-t", agent.tmux_session, "-p", "-S", f"-{lines}")
        return result.stdout
    
    def get_status(self, agent_name: str) -> Dict:
        """Get agent status."""
        with self.lock:
            agent = self.agents.get(agent_name)
        
        if not agent:
            return {"name": agent_name, "status": "not_found"}
        
        # Check if tmux session still exists
        alive = self._tmux_exists(agent.tmux_session)
        
        return {
            "name": agent.name,
            "status": agent.status if alive else "dead",
            "session": agent.tmux_session,
            "uptime": time.time() - agent.started_at,
            "alive": alive
        }
    
    def list_agents(self) -> List[Dict]:
        """List all managed agents."""
        with self.lock:
            agent_names = list(self.agents.keys())
        
        return [self.get_status(name) for name in agent_names]
    
    def stop_agent(self, agent_name: str) -> bool:
        """Stop an agent."""
        with self.lock:
            agent = self.agents.get(agent_name)
        
        if not agent:
            return False
        
        # Send Ctrl+C to gracefully stop
        self._run_tmux("send-keys", "-t", agent.tmux_session, "C-c", check=False)
        time.sleep(1)
        
        # Kill session if still alive
        self._run_tmux("kill-session", "-t", agent.tmux_session, check=False)
        
        with self.lock:
            agent.status = "stopped"
            if agent_name in self.agents:
                del self.agents[agent_name]
        
        return True
    
    def stop_all(self):
        """Stop all agents."""
        with self.lock:
            agent_names = list(self.agents.keys())
        
        for name in agent_names:
            self.stop_agent(name)
    
    def monitor_agents(self, interval: int = 10):
        """Monitor all agents and restart dead ones."""
        while True:
            time.sleep(interval)
            
            with self.lock:
                agent_names = list(self.agents.keys())
            
            for name in agent_names:
                status = self.get_status(name)
                if not status["alive"]:
                    logger.warning(f"Agent {name} died, restarting...")
                    self.stop_agent(name)
                    # Could auto-restart here


def run_agent_inline(agent_name: str):
    """Run a single agent inline (for tmux sessions)."""
    import sys
    sys.path.insert(0, os.getcwd())
    
    from scripts.agent_base import get_agent_registry
    from scripts.agents import register_all_agents
    
    # Register all agents
    register_all_agents()
    
    # Get the specific agent
    registry = get_agent_registry()
    agent = registry.get(agent_name)
    
    if not agent:
        print(f"Agent {agent_name} not found")
        return
    
    print(f"Starting agent: {agent_name}")
    agent.run()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Empire OS Agent Runner")
    parser.add_argument("--agent", help="Run a specific agent inline")
    parser.add_argument("--spawn", help="Spawn agent in tmux")
    parser.add_argument("--list", action="store_true", help="List running agents")
    parser.add_argument("--stop", help="Stop an agent")
    parser.add_argument("--status", help="Get agent status")
    parser.add_argument("--output", help="Get agent output")
    parser.add_argument("--project-dir", default=os.getcwd(), help="Project directory")
    
    args = parser.parse_args()
    
    if args.agent:
        run_agent_inline(args.agent)
    else:
        manager = AgentManager(args.project_dir)
        
        if args.spawn:
            manager.spawn_agent(args.spawn)
            print(f"Spawned {args.spawn}")
        elif args.list:
            agents = manager.list_agents()
            for a in agents:
                print(f"  {a['name']}: {a['status']} (alive={a['alive']})")
        elif args.stop:
            manager.stop_agent(args.stop)
            print(f"Stopped {args.stop}")
        elif args.status:
            status = manager.get_status(args.status)
            print(json.dumps(status, indent=2))
        elif args.output:
            output = manager.get_output(args.output)
            print(output)
        else:
            parser.print_help()