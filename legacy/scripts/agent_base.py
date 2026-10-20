#!/usr/bin/env python3
"""
Automation Empire OS — Multi-Agent Framework
Base agent class, registry, and message bus for autonomous agent coordination.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone
import json
import uuid
import logging
import threading
import queue
import time
from pathlib import Path
from enum import Enum

from backend.app.core.config import get_settings
from backend.app.core.db import init_db, Job, JobStatus, SystemSettings

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    """Agent execution states."""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class AgentMessage:
    """Message between agents."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_agent: str = ""
    to_agent: str = ""
    message_type: str = ""  # task, result, status, request, broadcast
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None  # For request-response matching
    priority: int = 0  # Higher = more urgent


@dataclass
class AgentTask:
    """Task assigned to an agent."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str = ""
    task_type: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3


class MessageBus:
    """Central message bus for inter-agent communication."""
    
    def __init__(self):
        self.queues: Dict[str, queue.Queue] = {}
        self.subscriptions: Dict[str, List[str]] = {}  # topic -> agent_names
        self.lock = threading.Lock()
        self.broadcast_history: List[AgentMessage] = []
        self.max_history = 1000
    
    def register_agent(self, agent_name: str):
        """Register an agent's message queue."""
        with self.lock:
            if agent_name not in self.queues:
                self.queues[agent_name] = queue.Queue()
                logger.info(f"Registered agent queue: {agent_name}")
    
    def unregister_agent(self, agent_name: str):
        """Unregister an agent's message queue."""
        with self.lock:
            if agent_name in self.queues:
                del self.queues[agent_name]
            # Remove from subscriptions
            for topic, agents in self.subscriptions.items():
                if agent_name in agents:
                    agents.remove(agent_name)
    
    def send(self, message: AgentMessage) -> bool:
        """Send a message to a specific agent."""
        with self.lock:
            if message.to_agent in self.queues:
                self.queues[message.to_agent].put(message)
                return True
            logger.warning(f"Agent {message.to_agent} not registered")
            return False
    
    def broadcast(self, message: AgentMessage, topic: str = "broadcast"):
        """Broadcast a message to all agents subscribed to a topic."""
        with self.lock:
            agents = self.subscriptions.get(topic, [])
            for agent_name in agents:
                if agent_name in self.queues:
                    self.queues[agent_name].put(message)
            # Store in history
            self.broadcast_history.append(message)
            if len(self.broadcast_history) > self.max_history:
                self.broadcast_history = self.broadcast_history[-self.max_history:]
    
    def subscribe(self, agent_name: str, topic: str):
        """Subscribe an agent to a topic."""
        with self.lock:
            if topic not in self.subscriptions:
                self.subscriptions[topic] = []
            if agent_name not in self.subscriptions[topic]:
                self.subscriptions[topic].append(agent_name)
    
    def receive(self, agent_name: str, timeout: float = 1.0) -> Optional[AgentMessage]:
        """Receive a message for an agent."""
        with self.lock:
            q = self.queues.get(agent_name)
        if q:
            try:
                return q.get(timeout=timeout)
            except queue.Empty:
                return None
        return None
    
    def request_response(self, from_agent: str, to_agent: str, task_type: str, 
                         payload: Dict[str, Any], timeout: float = 30.0) -> Optional[AgentMessage]:
        """Send a request and wait for response."""
        correlation_id = str(uuid.uuid4())
        request = AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type="request",
            payload={"task_type": task_type, **payload},
            correlation_id=correlation_id
        )
        
        # Create a temporary queue for the response
        response_queue = queue.Queue()
        
        # We'll use a callback pattern - register a one-time handler
        def handle_response(msg: AgentMessage):
            if msg.correlation_id == correlation_id and msg.message_type == "response":
                response_queue.put(msg)
        
        # For simplicity, we'll poll the agent's queue
        self.send(request)
        
        start = time.time()
        while time.time() - start < timeout:
            msg = self.receive(from_agent, timeout=0.5)
            if msg and msg.correlation_id == correlation_id and msg.message_type == "response":
                return msg
        return None


class BaseAgent(ABC):
    """Base class for all Empire OS agents."""
    
    def __init__(self, name: str, message_bus: MessageBus, 
                 capabilities: List[str] = None,
                 config: Dict[str, Any] = None):
        self.name = name
        self.message_bus = message_bus
        self.capabilities = capabilities or []
        self.config = config or {}
        self.status = AgentStatus.IDLE
        self.current_task: Optional[AgentTask] = None
        self.session = init_db(get_settings().database_url)
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.task_handlers: Dict[str, Callable] = {}
        
        # Register with message bus
        self.message_bus.register_agent(self.name)
        self.message_bus.subscribe(self.name, "broadcast")
        
        # LLM capability
        self._llm_router = None
        
        # Register default handlers
        self._register_default_handlers()
    
    def _get_llm(self):
        """Lazy load LLM router"""
        if self._llm_router is None:
            from scripts.ai_router import get_router
            self._llm_router = get_router()
        return self._llm_router
    
    def llm_complete(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: Optional[Dict] = None,
        preferred_provider: Optional[str] = None
    ):
        """Call LLM with automatic provider fallback"""
        from scripts.ai_router import llm_complete
        return llm_complete(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            preferred_provider=preferred_provider
        )
    
    def _register_default_handlers(self):
        """Register default message handlers."""
        self.task_handlers["ping"] = self._handle_ping
        self.task_handlers["status"] = self._handle_status
        self.task_handlers["stop"] = self._handle_stop
    
    def _handle_ping(self, payload: Dict) -> Dict:
        return {"status": "pong", "agent": self.name, "capabilities": self.capabilities}
    
    def _handle_status(self, payload: Dict) -> Dict:
        return {
            "status": self.status.value,
            "agent": self.name,
            "current_task": self.current_task.id if self.current_task else None,
            "capabilities": self.capabilities
        }
    
    def _handle_stop(self, payload: Dict) -> Dict:
        self.stop()
        return {"status": "stopped", "agent": self.name}
    
    @abstractmethod
    def execute_task(self, task: AgentTask) -> Dict[str, Any]:
        """Execute a specific task. Must be implemented by subclass."""
        pass
    
    def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """Handle an incoming message."""
        if message.message_type == "task":
            task = AgentTask(
                agent_name=self.name,
                task_type=message.payload.get("task_type", "unknown"),
                payload=message.payload,
                correlation_id=message.correlation_id
            )
            result = self.execute_task(task)
            
            if message.correlation_id:
                # Send response
                response = AgentMessage(
                    from_agent=self.name,
                    to_agent=message.from_agent,
                    message_type="response",
                    payload={"result": result, "task_id": task.id},
                    correlation_id=message.correlation_id
                )
                return response
        
        elif message.message_type == "request":
            task_type = message.payload.get("task_type")
            handler = self.task_handlers.get(task_type)
            if handler:
                result = handler(message.payload)
                if message.correlation_id:
                    response = AgentMessage(
                        from_agent=self.name,
                        to_agent=message.from_agent,
                        message_type="response",
                        payload={"result": result},
                        correlation_id=message.correlation_id
                    )
                    return response
        
        return None
    
    def run(self):
        """Main agent loop."""
        self.running = True
        self.status = AgentStatus.RUNNING
        logger.info(f"Agent {self.name} started")
        
        while self.running:
            try:
                message = self.message_bus.receive(self.name, timeout=1.0)
                if message:
                    response = self.handle_message(message)
                    if response:
                        self.message_bus.send(response)
            except Exception as e:
                logger.error(f"Agent {self.name} error: {e}")
                self.status = AgentStatus.FAILED
                break
        
        self.status = AgentStatus.STOPPED
        logger.info(f"Agent {self.name} stopped")
    
    def start(self):
        """Start the agent in a background thread."""
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Stop the agent."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
    
    def register_handler(self, task_type: str, handler: Callable):
        """Register a custom task handler."""
        self.task_handlers[task_type] = handler
    
    def broadcast(self, message_type: str, payload: Dict[str, Any], topic: str = "broadcast"):
        """Broadcast a message to all agents."""
        message = AgentMessage(
            from_agent=self.name,
            to_agent="",
            message_type=message_type,
            payload=payload
        )
        self.message_bus.broadcast(message, topic)
    
    def send_task(self, to_agent: str, task_type: str, payload: Dict[str, Any], 
                  wait_response: bool = True, timeout: float = 30.0) -> Optional[Dict]:
        """Send a task to another agent."""
        message = AgentMessage(
            from_agent=self.name,
            to_agent=to_agent,
            message_type="task",
            payload={"task_type": task_type, **payload}
        )
        
        if wait_response:
            response = self.message_bus.request_response(
                self.name, to_agent, task_type, payload, timeout
            )
            if response:
                return response.payload.get("result")
            return None
        else:
            self.message_bus.send(message)
            return {"sent": True}


class AgentRegistry:
    """Registry for all agents in the empire."""
    
    _agents: Dict[str, BaseAgent] = {}
    _message_bus: Optional[MessageBus] = None
    _lock = threading.Lock()
    
    @classmethod
    def get_message_bus(cls) -> MessageBus:
        """Get or create the shared message bus."""
        with cls._lock:
            if cls._message_bus is None:
                cls._message_bus = MessageBus()
            return cls._message_bus
    
    @classmethod
    def register(cls, agent: BaseAgent):
        """Register an agent."""
        with cls._lock:
            cls._agents[agent.name] = agent
            logger.info(f"Registered agent: {agent.name}")
    
    @classmethod
    def get(cls, name: str) -> Optional[BaseAgent]:
        """Get an agent by name."""
        with cls._lock:
            return cls._agents.get(name)
    
    @classmethod
    def list(cls) -> List[str]:
        """List all registered agent names."""
        with cls._lock:
            return list(cls._agents.keys())
    
    @classmethod
    def get_all(cls) -> Dict[str, BaseAgent]:
        """Get all agents."""
        with cls._lock:
            return cls._agents.copy()
    
    @classmethod
    def start_all(cls):
        """Start all registered agents."""
        for agent in cls._agents.values():
            agent.start()
    
    @classmethod
    def stop_all(cls):
        """Stop all registered agents."""
        for agent in cls._agents.values():
            agent.stop()
    
    @classmethod
    def broadcast(cls, message_type: str, payload: Dict[str, Any], topic: str = "broadcast"):
        """Broadcast to all agents."""
        bus = cls.get_message_bus()
        # Create a system message
        message = AgentMessage(
            from_agent="system",
            to_agent="",
            message_type=message_type,
            payload=payload
        )
        bus.broadcast(message, topic)
    
    @classmethod
    def get_agent_status(cls, name: str) -> Optional[Dict]:
        """Get status of a specific agent."""
        agent = cls.get(name)
        if agent:
            return {
                "name": agent.name,
                "status": agent.status.value,
                "capabilities": agent.capabilities,
                "current_task": agent.current_task.id if agent.current_task else None
            }
        return None
    
    @classmethod
    def get_all_status(cls) -> List[Dict]:
        """Get status of all agents."""
        return [cls.get_agent_status(name) for name in cls.list()]


# Global registry instance
_agent_registry = AgentRegistry()

def get_agent_registry() -> AgentRegistry:
    return _agent_registry