"""
A2A Client

Sends A2A messages to other agents with dynamic AgentCard discovery.

"""

import requests
from typing import Dict, Any, Optional
from uuid import uuid4
from datetime import datetime
import json
import time as time_module

from .protocol import A2AMessage, A2AResponse, AgentCard
import os

# Only import tracer if Phoenix is enabled (prevents Phoenix startup in Env2)
if os.getenv("PHOENIX_ENABLED", "true") != "false":
    try:
        from utils_copy import tracer
        from opentelemetry.trace import StatusCode
    except Exception:
        tracer = None
        StatusCode = None
else:
    tracer = None  # Phoenix disabled 
    StatusCode = None


class A2AClient:
    
    def __init__(self, base_url: str = "http://localhost:8000", timeout: int = 600):
        #Initialize A2A client
    
        
        self.base_url = base_url.rstrip('/') #Base URL for agent endpoints
        self.timeout = timeout #HTTP request timeout in seconds
        self.agent_card_cache: Dict[str, AgentCard] = {}
    
    def discover_agent(self, agent_id: str) -> Optional[AgentCard]:

        #Dynamically discover an agent by fetching its AgentCard.
        
        # Check cache first
        if agent_id in self.agent_card_cache:
            print(f"[A2A Client] Using cached AgentCard for {agent_id}")
            return self.agent_card_cache[agent_id]
        
        # Try local registry
        try:
            from a2a.agent_cards import get_agent_card as get_local_card
            local_card = get_local_card(agent_id)
            if local_card:
                print(f"[A2A Client] Found AgentCard for '{agent_id}' in local registry")
                print(f"[A2A Client] Endpoint: {local_card.endpoints.a2a}")
                self.agent_card_cache[agent_id] = local_card
                return local_card
        except Exception as e:
            print(f"[A2A Client] Local registry check failed: {e}, falling back to HTTP")
        
        # Fetch AgentCard from well-known endpoint (for remote agents)
        card_url = f"{self.base_url}/.well-known/agent-card.json?agent={agent_id}"
        
        if tracer is not None:
            with tracer.start_as_current_span(
                "a2a_discover_agent",
                openinference_span_kind="tool"
            ) as span:
                span.set_attribute("a2a.agent_id", agent_id)
                span.set_attribute("a2a.card_url", card_url)
                
                try:
                    print(f"[A2A Client] Discovering agent '{agent_id}' at {card_url}")
                    response = requests.get(card_url, timeout=10)
                    response.raise_for_status()
                    
                    card_data = response.json()
                    agent_card = AgentCard(**card_data)
                    
                    # Cache the card
                    self.agent_card_cache[agent_id] = agent_card
                    
                    span.set_output({"agent_name": agent_card.name, "version": agent_card.version})
                    span.set_status(StatusCode.OK)
                    
                    print(f"[A2A Client] ✅ Discovered agent: {agent_card.name} v{agent_card.version}")
                    return agent_card
                    
                except Exception as e:
                    span.set_status(StatusCode.ERROR)
                    span.record_exception(e)
                    print(f"[A2A Client] ❌ Failed to discover agent '{agent_id}': {e}")
                    return None
        else:
            # No tracing
            try:
                print(f"[A2A Client] Discovering agent '{agent_id}' at {card_url}")
                response = requests.get(card_url, timeout=10)
                response.raise_for_status()
                
                card_data = response.json()
                agent_card = AgentCard(**card_data)
                self.agent_card_cache[agent_id] = agent_card
                
                print(f"[A2A Client] ✅ Discovered agent: {agent_card.name} v{agent_card.version}")
                return agent_card
            except Exception as e:
                print(f"[A2A Client] ❌ Failed to discover agent '{agent_id}': {e}")
                return None
    
    def send_message(
        self,
        to_agent: str,
        method: str,
        params: Dict[str, Any],
        from_agent: Optional[str] = None,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None
    ) -> Dict[str, Any]:

        # Generate IDs if not provided
        if conversation_id is None:
            conversation_id = str(uuid4())
        if message_id is None:
            message_id = f"msg_{uuid4().hex[:12]}"
        
        # Discover target agent
        agent_card = self.discover_agent(to_agent)
        if agent_card is None:
            raise RuntimeError(f"Failed to discover agent: {to_agent}")
        
        # Add conversation metadata to params
        params_with_meta = {
            **params,
            "conversation_id": conversation_id,
            "from_agent": from_agent or "unknown",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Create A2A message
        message = A2AMessage(
            id=message_id,
            method=method,
            params=params_with_meta
        )
        
        # Check if agent is local, use direct execution to avoid HTTP deadlock
        if self._is_local_agent(to_agent):
            try:
                print(f"[A2A Client] Using LOCAL execution for {agent_card.name} (endpoint={agent_card.endpoints.a2a})")
                return self._send_message_local(to_agent, message, agent_card, conversation_id)
            except Exception as e:
                print(f"[A2A Client] Local execution failed: {e}")
                # Don't fall back to HTTP - it will deadlock
                raise RuntimeError(f"Local A2A execution failed: {e}")
        
        # Send message to agent's A2A endpoint (for remote agents)
        a2a_url = agent_card.endpoints.a2a
        print(f"[A2A Client] Using HTTP A2A to {agent_card.name} at {a2a_url}")
        
        if tracer is not None:
            with tracer.start_as_current_span(
                f"a2a_send_message_{method}",
                openinference_span_kind="tool"
            ) as span:
                span.set_attribute("a2a.to_agent", to_agent)
                span.set_attribute("a2a.from_agent", from_agent or "unknown")
                span.set_attribute("a2a.method", method)
                span.set_attribute("a2a.conversation_id", conversation_id)
                span.set_attribute("a2a.message_id", message_id)
                span.set_attribute("a2a.endpoint", a2a_url)
                span.set_input(params)
                
                try:
                    print(f"[A2A Client] Sending message to {agent_card.name}: {method}")
                    print(f"[A2A Client] Endpoint: {a2a_url}")
                    print(f"[A2A Client] Conversation ID: {conversation_id}")
                    
                    # Calculate request size
                    request_payload = message.dict()
                    request_json = json.dumps(request_payload)
                    request_size_bytes = len(request_json.encode('utf-8'))
                    
                    
                    a2a_start_time = time_module.time()
                    
                    response = requests.post(
                        a2a_url,
                        json=request_payload,
                        timeout=self.timeout,
                        headers={"Content-Type": "application/json"}
                    )
                    response.raise_for_status()
                    
                    # Total round-trip time (includes env2 processing + network I/O)
                    # env1_a2a_graph.py will subtract env2's processing time to get pure overhead
                    a2a_network_time = time_module.time() - a2a_start_time
                    
                    # Calculate response size
                    response_data = response.json()
                    response_json = json.dumps(response_data)
                    response_size_bytes = len(response_json.encode('utf-8'))
                    
                    a2a_response = A2AResponse(**response_data)
                    
                    if a2a_response.error:
                        span.set_status(StatusCode.ERROR)
                        span.set_attribute("a2a.error_code", a2a_response.error.code)
                        span.set_attribute("a2a.error_message", a2a_response.error.message)
                        print(f"[A2A Client] ❌ Agent returned error: {a2a_response.error.message}")
                        raise RuntimeError(f"A2A error: {a2a_response.error.message}")
                    
                    # Add A2A metrics to response (time + payload sizes only)
                    
                    if a2a_response.result:
                        a2a_response.result.update({
                            "a2a_request_size_bytes": request_size_bytes,
                            "a2a_response_size_bytes": response_size_bytes,
                            "a2a_total_size_bytes": request_size_bytes + response_size_bytes,
                            "a2a_network_time_seconds": a2a_network_time,
                        })
                    
                    span.set_attribute("a2a.round_trip_seconds", a2a_network_time)
                    span.set_attribute("a2a.request_size_bytes", request_size_bytes)
                    span.set_attribute("a2a.response_size_bytes", response_size_bytes)
                    span.set_status(StatusCode.OK)
                    
                    print(f"[A2A Client] ✅ Received response from {agent_card.name}")
                    print(f"[A2A Client] A2A Metrics: Request={request_size_bytes}B, Response={response_size_bytes}B, RoundTrip={a2a_network_time:.3f}s")
                    
                    # Return result with conversation metadata and A2A metrics
                    result = {
                        **a2a_response.result,
                        "a2a_conversation_id": conversation_id,
                        "a2a_message_id": message_id,
                        "a2a_agent": to_agent
                    }
                    return result
                    
                except Exception as e:
                    span.set_status(StatusCode.ERROR)
                    span.record_exception(e)
                    print(f"[A2A Client] ❌ Failed to send message: {e}")
                    raise
        else:
            try:
                print(f"[A2A Client] Sending message to {agent_card.name}: {method}")
                print(f"[A2A Client] Endpoint: {a2a_url}")
                
                # Calculate request size
                request_payload = message.dict()
                request_json = json.dumps(request_payload)
                request_size_bytes = len(request_json.encode('utf-8'))
                
                # Only measure wall-clock time 
                a2a_start_time = time_module.time()
                
                response = requests.post(
                    a2a_url,
                    json=request_payload,
                    timeout=self.timeout,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                
                a2a_network_time = time_module.time() - a2a_start_time
                
                # Calculate response size
                response_data = response.json()
                response_json = json.dumps(response_data)
                response_size_bytes = len(response_json.encode('utf-8'))
                
                a2a_response = A2AResponse(**response_data)
                
                if a2a_response.error:
                    print(f"[A2A Client] ❌ Agent returned error: {a2a_response.error.message}")
                    raise RuntimeError(f"A2A error: {a2a_response.error.message}")
                
                # Add A2A metrics to response (time + payload sizes only)
                if a2a_response.result:
                    a2a_response.result.update({
                        "a2a_request_size_bytes": request_size_bytes,
                        "a2a_response_size_bytes": response_size_bytes,
                        "a2a_total_size_bytes": request_size_bytes + response_size_bytes,
                        "a2a_network_time_seconds": a2a_network_time,
                    })
                
                print(f"[A2A Client] ✅ Received response from {agent_card.name}")
                print(f"[A2A Client] A2A Metrics: Request={request_size_bytes}B, Response={response_size_bytes}B, RoundTrip={a2a_network_time:.3f}s")
                
                # Return result with conversation metadata and A2A metrics
                result = {
                    **a2a_response.result,
                    "a2a_conversation_id": conversation_id,
                    "a2a_message_id": message_id,
                    "a2a_agent": to_agent
                }
                return result
            except Exception as e:
                print(f"[A2A Client] ❌ Failed to send message: {e}")
                raise
    
    def _is_local_agent(self, agent_id: str) -> bool:
        
        #Check if agent is local (same process) to avoid HTTP self-request deadlock.
        
       
        from a2a.agent_cards import AGENT_CARDS
        
        card = AGENT_CARDS.get(agent_id)
        if not card:
            return False
        
        # Only agents with endpoint="local" will use local execution
        # PlotAgent has HTTP URL (localhost:8001), so will use A2A
        return card.endpoints.a2a == "local"
    
    def _send_message_local(
        self,
        to_agent: str,
        message: A2AMessage,
        agent_card: AgentCard,
        conversation_id: str
    ) -> Dict[str, Any]:
        if tracer is not None:
            with tracer.start_as_current_span(
                f"a2a_local_execute_{message.method}",
                openinference_span_kind="tool"
            ) as span:
                span.set_attribute("a2a.to_agent", to_agent)
                span.set_attribute("a2a.method", message.method)
                span.set_attribute("a2a.conversation_id", conversation_id)
                span.set_attribute("a2a.execution_mode", "local")
                span.set_input(message.params)
                
                try:
                    result = self._execute_local_agent(to_agent, message, conversation_id)
                    span.set_output(result)
                    span.set_status(StatusCode.OK)
                    return result
                except Exception as e:
                    span.set_status(StatusCode.ERROR)
                    span.record_exception(e)
                    raise
        else:
            return self._execute_local_agent(to_agent, message, conversation_id)
    
    def _execute_local_agent(self, to_agent: str, message: A2AMessage, conversation_id: str) -> Dict[str, Any]:
        # Local execution fallback (only used when agent card has endpoint="local")
        # In the A2A setup, PlotAgent runs on env2 (remote HTTP), so this path is not used for "plot".
        if to_agent == "plot":
            raise RuntimeError("PlotAgent local execution is not supported in A2A mode. Use HTTP A2A to env2.")
        
        elif to_agent == "insight":
            from agents.insight_agent import InsightAgent
            from a2a.executor import A2AAgentExecutor
            from a2a.agent_cards import INSIGHT_AGENT_CARD
            
            print(f"[A2A Client] Executing locally on InsightAgent")
            
            # Parallel analysis for richer insights
            insight_agent = InsightAgent(use_parallel_analysis=True)
            executor = A2AAgentExecutor(insight_agent, INSIGHT_AGENT_CARD)
            response = executor.execute(message)
            
            if response.error:
                raise RuntimeError(f"A2A error: {response.error.message}")
            
            print(f"[A2A Client] ✅ Local execution completed")
            
            return {
                **response.result,
                "a2a_conversation_id": conversation_id,
                "a2a_message_id": message.id,
                "a2a_agent": to_agent,
                "a2a_execution_mode": "local"
            }
        
        else:
            raise ValueError(f"Unknown local agent: {to_agent}")
    
    def clear_cache(self):
        """Clear AgentCard cache"""
        self.agent_card_cache.clear()
        print("[A2A Client] AgentCard cache cleared")

