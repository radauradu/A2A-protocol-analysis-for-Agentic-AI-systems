

#Implementation of JSON-RPC 2.0 based A2A messaging protocol


from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class A2AMessage(BaseModel):
    #A2A request message - JSON-RPC 2.0
    jsonrpc: str = "2.0"
    id: str = Field(..., description="Unique message ID")
    method: str = Field(..., description="Method/skill to invoke")
    params: Dict[str, Any] = Field(default_factory=dict, description="Method parameters")
    
    class Config:
        json_schema_extra = {
            "example": {
                "jsonrpc": "2.0",
                "id": "msg_123",
                "method": "create_visualization",
                "params": {
                    "data": {"rows": [[...]], "columns": [...]},
                    "context": "Revenue increased 40%",
                    "preferences": {"chart_type": "line"}
                }
            }
        }


class A2AError(BaseModel):
    #A2A error object
    code: int = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional error data")


class A2AResponse(BaseModel):
    """A2A response message following JSON-RPC 2.0"""
    jsonrpc: str = "2.0"
    id: str = Field(..., description="Message ID from request")
    result: Optional[Dict[str, Any]] = Field(None, description="Success result")
    error: Optional[A2AError] = Field(None, description="Error object if failed")
    
    class Config:
        json_schema_extra = {
            "example": {
                "jsonrpc": "2.0",
                "id": "msg_123",
                "result": {
                    "image_path": "./runs/20251031_120000/fig.png",
                    "status": "completed"
                }
            }
        }


class AgentCardSkill(BaseModel):
    #Description of an agent skill/capability
    name: str = Field(..., description="Skill name")
    description: str = Field(..., description="What this skill does")
    input_schema: Dict[str, str] = Field(..., description="Input parameter types")
    output_schema: Dict[str, str] = Field(..., description="Output field types")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "analyze_sales_data",
                "description": "Analyzes sales data and generates insights",
                "input_schema": {"rows": "array", "columns": "array", "prompt": "string"},
                "output_schema": {"analysis": "string", "chart_config": "object"}
            }
        }


class AgentCardCapabilities(BaseModel):
    #Agent capabilities definition
    input_modes: List[str] = Field(default=["application/json"])
    output_modes: List[str] = Field(default=["application/json"])
    skills: List[AgentCardSkill] = Field(default_factory=list)


class AgentCardEndpoints(BaseModel):
    #Agent communication endpoints
    a2a: str = Field(..., description="A2A message endpoint")
    health: Optional[str] = Field(None, description="Health check endpoint")
    card: Optional[str] = Field(None, description="AgentCard discovery endpoint")


class AgentCardAuthentication(BaseModel):
    #Authentication requirements
    type: str = Field(default="none", description="Authentication type (none, bearer, api_key)")
    required: bool = Field(default=False)


class AgentCard(BaseModel):
    id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Human-readable agent name")
    description: str = Field(..., description="What this agent does")
    version: str = Field(..., description="Agent version")
    capabilities: AgentCardCapabilities = Field(..., description="Agent capabilities")
    endpoints: AgentCardEndpoints = Field(..., description="Communication endpoints")
    authentication: AgentCardAuthentication = Field(default_factory=AgentCardAuthentication)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "plot_agent_v1",
                "name": "Sales Visualization Agent",
                "description": "Creates charts and visualizations from sales data",
                "version": "1.0.0",
                "capabilities": {
                    "input_modes": ["application/json"],
                    "output_modes": ["application/json", "image/png"],
                    "skills": [
                        {
                            "name": "create_visualization",
                            "description": "Creates chart from data",
                            "input_schema": {"data": "object", "preferences": "object"},
                            "output_schema": {"image_path": "string", "status": "string"}
                        }
                    ]
                },
                "endpoints": {
                    "a2a": "http://localhost:8000/agent/plot/a2a",
                    "health": "http://localhost:8000/agent/plot/health"
                },
                "authentication": {"type": "none", "required": False}
            }
        }


class A2AConversation(BaseModel):
    #Tracks an A2A conversation between agents
    conversation_id: str
    from_agent: str
    to_agent: str
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    status: str = "active"  # active, completed, failed
    metadata: Dict[str, Any] = Field(default_factory=dict)

