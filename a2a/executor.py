

#Handles incoming A2A messages, routes them to agent methods, and manages execution.


from typing import Dict, Any, Callable, Optional
from datetime import datetime
from uuid import uuid4

from .protocol import A2AMessage, A2AResponse, A2AError, AgentCard, A2AConversation
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
    tracer = None  # Phoenix disabled - no tracing
    StatusCode = None


class A2AAgentExecutor:
    
    def __init__(self, agent: Any, agent_card: AgentCard):
       
        self.agent = agent
        self.agent_card = agent_card
        self.conversations: Dict[str, A2AConversation] = {}
        self.method_handlers: Dict[str, Callable] = {}
        
        self._register_handlers()
    
    def _register_handlers(self):
        #Register method handlers based on agent card skills
        for skill in self.agent_card.capabilities.skills:
            # Map skill name to agent method
            # skill name "create_visualization" -> agent.create_visualization()
            # or fallback to agent.run() for default handling
            method_name = skill.name
            if hasattr(self.agent, method_name):
                self.method_handlers[method_name] = getattr(self.agent, method_name)
            elif hasattr(self.agent, 'run'):
                # Default fallback to run method
                self.method_handlers[method_name] = self.agent.run
    
    def execute(self, message: A2AMessage) -> A2AResponse:
        if tracer is not None:
            with tracer.start_as_current_span(
                f"a2a_execute_{message.method}",
                openinference_span_kind="agent"
            ) as span:
                span.set_attribute("a2a.message_id", message.id)
                span.set_attribute("a2a.method", message.method)
                span.set_attribute("a2a.agent_id", self.agent_card.id)
                span.set_input(message.params)
                
                try:
                    result = self._execute_internal(message)
                    span.set_output(result.result or result.error)
                    if result.error:
                        span.set_status(StatusCode.ERROR)
                    else:
                        span.set_status(StatusCode.OK)
                    return result
                except Exception as e:
                    span.set_status(StatusCode.ERROR)
                    span.record_exception(e)
                    raise
        else:
            
            return self._execute_internal(message)
    
    def _execute_internal(self, message: A2AMessage) -> A2AResponse:
        #Internal execution 
        # Track conversation
        conv_id = message.params.get("conversation_id", str(uuid4()))
        if conv_id not in self.conversations:
            self.conversations[conv_id] = A2AConversation(
                conversation_id=conv_id,
                from_agent=message.params.get("from_agent", "unknown"),
                to_agent=self.agent_card.id,
                started_at=datetime.utcnow()
            )
        
        conversation = self.conversations[conv_id]
        conversation.messages.append({
            "type": "request",
            "message_id": message.id,
            "method": message.method,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Validate method exists
        if message.method not in self.method_handlers:
            error = A2AError(
                code=-32601,
                message=f"Method not found: {message.method}",
                data={"available_methods": list(self.method_handlers.keys())}
            )
            response = A2AResponse(id=message.id, error=error)
            conversation.messages.append({
                "type": "error",
                "message_id": message.id,
                "error": error.dict(),
                "timestamp": datetime.utcnow().isoformat()
            })
            conversation.status = "failed"
            return response
        
        # Execute method
        try:
            handler = self.method_handlers[message.method]
            
            # Call handler with params
            # Try to unpack params based on handler signature
            result = self._call_handler(handler, message.params)
            
            response = A2AResponse(id=message.id, result=result)
            conversation.messages.append({
                "type": "response",
                "message_id": message.id,
                "result_keys": list(result.keys()) if isinstance(result, dict) else None,
                "timestamp": datetime.utcnow().isoformat()
            })
            conversation.status = "completed"
            conversation.completed_at = datetime.utcnow()
            
            return response
            
        except Exception as e:
            error = A2AError(
                code=-32603,
                message=f"Internal error: {str(e)}",
                data={"exception_type": type(e).__name__}
            )
            response = A2AResponse(id=message.id, error=error)
            conversation.messages.append({
                "type": "error",
                "message_id": message.id,
                "error": error.dict(),
                "timestamp": datetime.utcnow().isoformat()
            })
            conversation.status = "failed"
            return response
    
    def _call_handler(self, handler: Callable, params: Dict[str, Any]) -> Dict[str, Any]:
        
       #Call handler with appropriate parameter unpacking
       # Tries to intelligently match params to handler signature
    
        import inspect
        
        sig = inspect.signature(handler)
        param_names = list(sig.parameters.keys())
        
        # If handler expects specific named parameters, extract them
        if len(param_names) > 0 and param_names[0] != 'self':
            # Try to match params
            kwargs = {}
            for param_name in param_names:
                if param_name in params:
                    kwargs[param_name] = params[param_name]
                elif 'data' in params and param_name in params['data']:
                    # Try to extract from nested 'data' object
                    kwargs[param_name] = params['data'][param_name]
            
            # Special handling for common patterns
            if 'data' in params and 'rows' not in kwargs and 'rows' in params['data']:
                kwargs['rows'] = params['data']['rows']
            if 'data' in params and 'columns' not in kwargs and 'columns' in params['data']:
                kwargs['columns'] = params['data']['columns']
            if 'chart_config' not in kwargs and 'preferences' in params:
                kwargs['chart_config'] = params.get('preferences', {})
            if 'chart_config' not in kwargs and 'chart_config' in params:
                kwargs['chart_config'] = params.get('chart_config', {})
            
            result = handler(**kwargs)
        else:
            
            result = handler(**params)
        
        # Ensure result is a dict
        if not isinstance(result, dict):
            result = {"result": result}
        
        
        if "status" not in result:
            result["status"] = "completed"
        
        return result
    
    def get_conversation(self, conversation_id: str) -> Optional[A2AConversation]:
        """Get conversation by ID"""
        return self.conversations.get(conversation_id)
    
    def get_active_conversations(self) -> list:
        """Get all active conversations"""
        return [conv for conv in self.conversations.values() if conv.status == "active"]

