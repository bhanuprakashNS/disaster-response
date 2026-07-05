# ruff: noqa
import os
import sys
import re
import datetime
import json
from typing import AsyncGenerator
from pydantic import BaseModel, Field
from google.adk.agents import LlmAgent
from google.adk.apps import App, ResumabilityConfig
from google.adk.models import Gemini
from google.adk.workflow import Workflow, START, Edge, node
from google.adk.agents.context import Context
from google.adk.events.event import Event
from google.adk.events import EventActions
from google.adk.events.request_input import RequestInput
from google.adk.tools import AgentTool
from google.genai import types
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StdioConnectionParams, StdioServerParameters

from app.config import config

# --- Pydantic Data Models ---

class ResourceRequestInput(BaseModel):
    location: str = Field(..., description="The name or coordinates of the disaster area")
    incident_details: str = Field(..., description="Description of the disaster event and situation")
    requested_supplies: list[str] = Field(..., description="List of requested resources (e.g. food, water, tents)")

class ResourceAllocationPlan(BaseModel):
    approved_items: list[str] = Field(..., description="Resources that are approved for immediate dispatch")
    denied_items: list[str] = Field(..., description="Resources that cannot be dispatched immediately")
    dispatch_notes: str = Field(..., description="Instructions for dispatch teams and logistics coordinators")

class SafetyEvaluationInput(BaseModel):
    location: str = Field(..., description="The name or coordinates of the disaster area")
    hazard_details: str = Field(..., description="Details about current hazards like fire, flood, blocked roads")

class SafetyAssessment(BaseModel):
    risk_level: str = Field(..., description="LOW, MEDIUM, HIGH, or CRITICAL risk")
    identified_hazards: list[str] = Field(..., description="List of specific safety risks detected")
    recommendations: list[str] = Field(..., description="Safety and evacuation recommendations for first responders")

class IncidentActionPlan(BaseModel):
    situation_summary: str = Field(..., description="Brief description of the disaster situation")
    safety_risk_level: str = Field(..., description="Risk level (LOW, MEDIUM, HIGH, CRITICAL)")
    safety_recommendations: list[str] = Field(..., description="First responder safety guidelines")
    allocated_supplies: list[str] = Field(..., description="List of items approved for dispatch")
    pending_approval_details: str = Field(..., description="Notes on denied or deferred items and logistics")


# --- Audit Logger ---

def write_audit_log(severity: str, action: str, details: dict):
    log_entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "severity": severity,
        "action": action,
        "details": details
    }
    print(f"[AUDIT_LOG] {json.dumps(log_entry)}")


# --- MCP Toolset Initialization ---

# Check if we are running as the MCP server to avoid infinite subprocess recursion loop
is_mcp_server = any("mcp_server" in arg for arg in sys.argv)

if not is_mcp_server:
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mcp_toolset = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=["-W", "ignore", "-m", "app.mcp_server"],
                cwd=project_dir
            )
        )
    )
else:
    mcp_toolset = None

# --- Specialized Agents ---

resource_allocator = LlmAgent(
    name="resource_allocator",
    model=Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are an Emergency Resource Logistics Officer. Evaluate the requested supplies against the disaster details. "
        "Call check_relief_inventory to verify stockpile availability in our emergency warehouse. "
        "Approve immediate dispatch of critical, life-saving items (water, food, medical kits, tents). "
        "Hold or deny non-critical items that require secondary vetting or pose transport challenges. "
        "Provide clear dispatch instructions."
    ),
    tools=[mcp_toolset] if mcp_toolset is not None else [],
    input_schema=ResourceRequestInput,
    output_schema=ResourceAllocationPlan,
)

safety_evaluator = LlmAgent(
    name="safety_evaluator",
    model=Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are a Disaster Safety Assessment Officer. Review the hazard details and location. "
        "Call get_weather_conditions and check_route_status to identify climate and road conditions that could affect safety and access. "
        "Determine the overall risk level (LOW, MEDIUM, HIGH, CRITICAL) and identify the specific active hazards. "
        "Generate safety guidelines and evacuation paths for field responders."
    ),
    tools=[mcp_toolset] if mcp_toolset is not None else [],
    input_schema=SafetyEvaluationInput,
    output_schema=SafetyAssessment,
)

# Lead Coordinator Agent
orchestrator_agent = LlmAgent(
    name="orchestrator_agent",
    model=Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are the Lead Coordinator for Disaster Response. You receive reports of emergency incidents. "
        "You must analyze the incident details. Call the resource_allocator tool and safety_evaluator tool to perform detailed reviews. "
        "Then, compile a complete Incident Action Plan containing: a situation summary, the overall risk level, safety guidelines, and a list of approved supplies."
    ),
    tools=[
        AgentTool(agent=resource_allocator),
        AgentTool(agent=safety_evaluator)
    ],
    output_schema=IncidentActionPlan,
    output_key="action_plan"
)


# --- Workflow Graph Nodes ---

@node
def parse_input(node_input: types.Content | dict | str) -> Event:
    """Parses raw input report (JSON or text) into a dictionary and puts it in context state."""
    raw_str = ""
    if isinstance(node_input, types.Content):
        if node_input.parts:
            raw_str = node_input.parts[0].text
    elif isinstance(node_input, str):
        raw_str = node_input
    elif isinstance(node_input, dict):
        raw_str = json.dumps(node_input)
    else:
        raw_str = str(node_input)

    # Try parsing as JSON
    parsed_report = None
    try:
        parsed_report = json.loads(raw_str)
    except Exception:
        # Fallback to plain text parsing
        parsed_report = {
            "location": "Sector 7-B",
            "incident_details": f"General report: {raw_str}",
            "requested_supplies": ["water", "first_aid_kits"],
            "hazard_details": "Moderate flooding reported in low-lying areas."
        }

    if not isinstance(parsed_report, dict):
        parsed_report = {
            "location": "Sector 7-B",
            "incident_details": f"General report: {raw_str}",
            "requested_supplies": ["water", "first_aid_kits"],
            "hazard_details": "Moderate flooding reported in low-lying areas."
        }

    # Normalize structure
    report = {
        "location": str(parsed_report.get("location", "Sector 7-B")),
        "incident_details": str(parsed_report.get("incident_details", "Emergency report received.")),
        "requested_supplies": list(parsed_report.get("requested_supplies", ["water", "first_aid_kits"])),
        "hazard_details": str(parsed_report.get("hazard_details", "None reported."))
    }

    return Event(
        output=report,
        actions=EventActions(state_delta={"report": report})
    )


@node
def security_checkpoint(ctx: Context, node_input: dict) -> Event:
    """Scrubs sensitive PII, detects prompt injection, runs domain security check, and logs audit."""
    report = ctx.state.get("report", {})
    incident_details = report.get("incident_details", "")
    hazard_details = report.get("hazard_details", "")
    location = report.get("location", "")

    # 1. PII Scrubbing (regex)
    redacted_categories = []
    
    # Phone number pattern
    phone_pattern = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
    if phone_pattern.search(incident_details):
        incident_details = phone_pattern.sub("[REDACTED PHONE]", incident_details)
        redacted_categories.append("Phone Number")
    if phone_pattern.search(hazard_details):
        hazard_details = phone_pattern.sub("[REDACTED PHONE]", hazard_details)
        redacted_categories.append("Phone Number")

    # SSN pattern
    ssn_pattern = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    if ssn_pattern.search(incident_details):
        incident_details = ssn_pattern.sub("[REDACTED SSN]", incident_details)
        redacted_categories.append("SSN")
    if ssn_pattern.search(hazard_details):
        hazard_details = ssn_pattern.sub("[REDACTED SSN]", hazard_details)
        redacted_categories.append("SSN")

    report["incident_details"] = incident_details
    report["hazard_details"] = hazard_details
    state_updates = {"report": report}

    if redacted_categories:
        existing = ctx.state.get("redacted_categories", [])
        state_updates["redacted_categories"] = list(set(existing + redacted_categories))
        write_audit_log("WARNING", "PII_REDACTION", {"categories": redacted_categories})

    # 2. Prompt Injection Detection
    injection_keywords = [
        "ignore previous instructions",
        "ignore instructions",
        "system prompt",
        "auto-approve",
        "bypass security",
        "override limits",
        "you must dispatch",
        "force dispatch"
    ]
    is_injection = any(kw in incident_details.lower() for kw in injection_keywords) or \
                   any(kw in hazard_details.lower() for kw in injection_keywords)

    # 3. Domain Specific Security Rule: Check for empty location or restricted emergency types
    domain_violation = False
    violation_reason = ""
    if not location or len(location.strip()) < 3:
        domain_violation = True
        violation_reason = "Invalid or empty location provided."
    
    restricted_keywords = ["nuclear", "radiation", "weapon", "biological agent"]
    if any(kw in incident_details.lower() for kw in restricted_keywords):
        domain_violation = True
        violation_reason = "Restricted hazardous material emergency. Requires special hazmat dispatch team."

    if is_injection:
        state_updates["security_event"] = True
        state_updates["risk_assessment"] = {
            "risk_level": "CRITICAL (SECURITY ALERT)",
            "risk_factors": ["PROMPT INJECTION DETECTED"],
            "justification": "The emergency report contains instruction override attempts.",
        }
        write_audit_log("CRITICAL", "PROMPT_INJECTION_DETECTED", {"report": report})
        return Event(
            output=report,
            actions=EventActions(route="security_escalation", state_delta=state_updates),
        )
    elif domain_violation:
        state_updates["security_event"] = True
        state_updates["risk_assessment"] = {
            "risk_level": "CRITICAL (DOMAIN VIOLATION)",
            "risk_factors": ["RESTRICTED EMERGENCY TYPE"],
            "justification": f"Domain security violation: {violation_reason}",
        }
        write_audit_log("WARNING", "DOMAIN_SECURITY_VIOLATION", {"reason": violation_reason})
        return Event(
            output=report,
            actions=EventActions(route="security_escalation", state_delta=state_updates),
        )
    else:
        write_audit_log("INFO", "SECURITY_CHECK_PASSED", {"location": location})
        return Event(
            output=report,
            actions=EventActions(route="clean", state_delta=state_updates),
        )


@node(rerun_on_resume=True)
async def human_review(
    ctx: Context, node_input: dict
) -> AsyncGenerator[Event | RequestInput, None]:
    """Pauses the workflow for a human commander to review the action plan."""
    action_plan = ctx.state.get("action_plan", {})
    report = ctx.state.get("report", {})
    
    is_security_event = ctx.state.get("security_event", False)
    title = (
        "🚨 **Security Escalation - Prompt Injection / Violation Detected!**"
        if is_security_event
        else "📋 **Incident Action Plan Review**"
    )

    redacted = ctx.state.get("redacted_categories", [])
    redacted_str = f" (Redacted PII: {', '.join(redacted)})" if redacted else ""

    # Pause and request input if human decision is not yet recorded in resume inputs
    if not ctx.resume_inputs or "decision" not in ctx.resume_inputs:
        message_text = (
            f"{title}\n\n"
            f"**Disaster Report Details:**\n"
            f"- **Location:** {report.get('location')}\n"
            f"- **Incident Details:** {report.get('incident_details')}{redacted_str}\n"
            f"- **Hazard Details:** {report.get('hazard_details')}\n\n"
        )
        if is_security_event:
            message_text += (
                f"**Risk Level:** {ctx.state.get('risk_assessment', {}).get('risk_level')}\n"
                f"**Justification:** {ctx.state.get('risk_assessment', {}).get('justification')}\n\n"
                f"This report has been flagged for a security check. Please review carefully.\n"
            )
        else:
            message_text += (
                f"**Generated Action Plan:**\n"
                f"- **Situation Summary:** {action_plan.get('situation_summary')}\n"
                f"- **Safety Risk Level:** {action_plan.get('safety_risk_level')}\n"
                f"- **Safety Recommendations:** {', '.join(action_plan.get('safety_recommendations', []))}\n"
                f"- **Allocated Supplies:** {', '.join(action_plan.get('allocated_supplies', []))}\n"
                f"- **Logistics Vetting Notes:** {action_plan.get('pending_approval_details')}\n\n"
            )
        message_text += "Respond with **approve** to dispatch the resources or **reject** to cancel."
        
        yield RequestInput(
            interrupt_id="decision",
            message=message_text,
        )
        return

    # Human decision returned, resume workflow and record outcome
    human_choice = ctx.resume_inputs["decision"].strip().lower()
    status = "DISPATCHED" if "approve" in human_choice else "CANCELLED"

    result = {
        "status": status,
        "method": "HUMAN_DECISION",
        "location": report.get("location"),
        "reason": f"Incident action plan reviewed by commander. Decision: {status}.",
        "action_plan": action_plan,
        "security_event": is_security_event,
    }

    yield Event(
        output=result,
        actions=EventActions(state_delta={"outcome": result}),
        content=types.Content(
            role="model",
            parts=[
                types.Part.from_text(
                    text=f"✍️ Commander decision: {status} for disaster response at {report.get('location')}."
                )
            ],
        ),
    )


@node
def finalize_response(ctx: Context, node_input: dict) -> Event:
    """Consolidates outcome and presents final status report."""
    outcome = ctx.state.get("outcome", {})
    return Event(
        output=outcome,
        content=types.Content(
            role="model",
            parts=[
                types.Part.from_text(
                    text=f"Finalizing Incident response. Status: {outcome.get('status')}. Info: {outcome.get('reason')}"
                )
            ]
        )
    )


# --- Workflow Definition ---

root_agent = Workflow(
    name="root_agent",
    edges=[
        Edge(from_node=START, to_node=parse_input),
        Edge(from_node=parse_input, to_node=security_checkpoint),
        Edge(from_node=security_checkpoint, to_node=orchestrator_agent, route="clean"),
        Edge(from_node=security_checkpoint, to_node=human_review, route="security_escalation"),
        Edge(from_node=orchestrator_agent, to_node=human_review),
        Edge(from_node=human_review, to_node=finalize_response),
    ],
)


# --- App Registration ---

app = App(
    root_agent=root_agent,
    name="app",
    resumability_config=ResumabilityConfig(is_resumable=True),
)
