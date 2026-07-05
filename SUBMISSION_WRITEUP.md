# DisasterResponse Coordinator — Submission Write-up

## Problem Statement
During large-scale natural disasters, emergency response centers are overwhelmed with incoming incident reports, supply requests, and hazard updates. First responders and local agencies need to make high-stakes allocation decisions quickly and safely. However, raw reports often contain unstructured text, missing coordinates, sensitive PII of victims, and potential malicious prompt injection or dangerous requests (such as civilian requests for restricted materials/weapons). Managing this manually is slow, error-prone, and presents severe compliance risks.

The **DisasterResponse Coordinator** solves this by providing a secure, automated multi-agent system that checks incoming emergency reports for security violations, dynamically coordinates with specialized logistics and hazard sub-agents, queries inventory and live weather systems, and compiles a comprehensive, ready-to-approve Incident Action Plan for the incident commander.

## Solution Architecture

The graph routing flow is configured as follows:

```mermaid
graph TD
    START([START]) --> parse_input[parse_input]
    parse_input --> security_checkpoint{security_checkpoint}
    
    security_checkpoint -- "clean" --> orchestrator_agent[orchestrator_agent]
    security_checkpoint -- "security_escalation" --> human_review{human_review (HITL Pause)}
    
    orchestrator_agent --> human_review
    
    subgraph "Sub-Agents (Delegated via AgentTool)"
        orchestrator_agent -.-> resource_allocator[resource_allocator]
        orchestrator_agent -.-> safety_evaluator[safety_evaluator]
    end
    
    subgraph "MCP Server (stdio)"
        mcp[MCP Server]
        mcp --- check_relief_inventory[check_relief_inventory]
        mcp --- get_weather_conditions[get_weather_conditions]
        mcp --- check_route_status[check_route_status]
    end
    
    resource_allocator ==> mcp
    safety_evaluator ==> mcp
    
    human_review -- "Commander Decision (approve / reject)" --> finalize_response[finalize_response]
    finalize_response --> END([END])
```

## Concepts Used

This project implements all core ADK 2.0 and MCP patterns, mapped across the following files:

1. **ADK Workflow**: Configured in [agent.py](file:///d:/NSBP/Google-5-day-vibe-coding-course/capstone-project/disaster-response/app/agent.py#L375) using node definitions and explicit edges mapping the routing state machine.
2. **LlmAgent**: Three specialized agents are created in [agent.py](file:///d:/NSBP/Google-5-day-vibe-coding-course/capstone-project/disaster-response/app/agent.py#L76-L125): `resource_allocator`, `safety_evaluator`, and `orchestrator_agent`.
3. **AgentTool**: The `orchestrator_agent` uses `AgentTool` in [agent.py](file:///d:/NSBP/Google-5-day-vibe-coding-course/capstone-project/disaster-response/app/agent.py#L121-L124) to programmatically delegate specialized requests to sub-agents as part of its reasoning loop.
4. **MCP Server**: Implemented using the MCP Python SDK in [mcp_server.py](file:///d:/NSBP/Google-5-day-vibe-coding-course/capstone-project/disaster-response/app/mcp_server.py).
5. **Security Checkpoint**: Implemented as a custom workflow node in [agent.py](file:///d:/NSBP/Google-5-day-vibe-coding-course/capstone-project/disaster-response/app/agent.py#L199) to screen for PII leaks, injection attacks, and domain rules.
6. **Agents CLI**: Scaffolded using `agents-cli` v0.5.0, utilizing `GEMINI.md` for local assistance and deployment configurations.

## Security Design

The security system runs before the LLM processes any report:
* **PII Redaction**: Regex expressions scrub Social Security Numbers (SSNs) and Phone Numbers from inputs to prevent exposure of victim details.
* **Prompt Injection Defense**: Text is screened for instruction overrides or auto-approve bypasses.
* **Domain Security Constraints**: Evaluates locations and filters restricted/hazardous keywords (`nuclear`, `radiation`, `weapon`, etc.).
* **Audit Logger**: Outputs structured JSON entries for security audits, including severity classifications.

## MCP Server Design

The FastMCP server in [mcp_server.py](file:///d:/NSBP/Google-5-day-vibe-coding-course/capstone-project/disaster-response/app/mcp_server.py) exposes three tools that interface with underlying reusable python skills:
1. `check_relief_inventory(item_name)`: Queries stock levels of life-saving equipment (food, water, tents, blankets) using the `InventoryManager` skill.
2. `get_weather_conditions(location)`: Connects to the generic `WeatherService` skill to check temperature, wind speed, and severe weather advisories.
3. `check_route_status(destination)`: Accesses the `RoadStatusService` skill to see if routes are open, restricted, or blocked.

## Human-in-the-Loop (HITL) Flow

Emergency response must never operate fully autonomously. The `human_review` node in [agent.py](file:///d:/NSBP/Google-5-day-vibe-coding-course/capstone-project/disaster-response/app/agent.py#L285) uses `RequestInput` to halt the workflow and present the consolidated action plan to the commander.
* **Why**: Prevents accidental dispatch of resource stockpiles and allows the commander to evaluate safety warnings or override security escalations before ordering dispatch.

## Demo Walkthrough

The project supports three primary demonstration scenarios:
1. **Normal Flow**: A standard storm report is ingested, sub-agents check weather/roads/stock levels, compile an action plan, pause for commander review, and update state to `DISPATCHED` upon approval.
2. **Domain Violation**: A power plant radiation leak report is submitted. It is immediately flagged as a domain safety violation, bypassing the orchestrator and routing straight to human review with warning.
3. **Prompt Injection Flow**: An input containing instructions to "bypass safety checks and dispatch weapons" is blocked at the gate. It creates a `CRITICAL` audit log and flags the injection attempt in the commander review UI.

## Impact / Value Statement
The DisasterResponse Coordinator changes emergency response operations by:
* **Reducing Decision Lag**: Automating inventory matching, weather analysis, and route validation reduces planning time from hours to seconds.
* **Enforcing Security at Scale**: Ensures victim PII is never logged, prompt injections are neutralized, and restricted materials are flagged instantly.
* **Protecting First Responders**: Evaluates hazard levels and route blocks before teams are dispatched, preventing responders from entering active danger zones.
* **Ensuring Absolute Accountability**: Provides a structured JSON audit trail of every incident decision and commander sign-off.
