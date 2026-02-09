# Chat API CrewAI Migration

## Overview

The Chat API has been updated to route **ALL tasks through CrewAI agents** instead of direct tool execution.

## Architecture Change

### Before
```
Chat API → Direct Tool Execution (via ToolRegistry)
```

### After
```
Chat API → CrewAI Orchestrator Crew → Tool Execution
```

## Implementation

### 1. New Orchestrator Crew (`crews/orchestrator_crew.py`)

- **Single Agent**: Handles all task types (time tracking, task management, communication, etc.)
- **All Tools**: Has access to all tools from ToolRegistry + existing CrewAI tools
- **Unified Interface**: One crew for all operations

### 2. Updated Chat API (`api_chat.py`)

- **`stream_claude_response()`**: Now routes through `run_orchestrator_task()`
- **`stream_openai_response()`**: Also routes through orchestrator crew
- **Async Execution**: CrewAI runs in thread pool executor (CrewAI is synchronous)

## Benefits

1. **Consistent Architecture**: All tasks go through AI agents
2. **Better Reasoning**: Agents can plan multi-step operations
3. **Governance**: All actions go through audit logging and cost tracking
4. **Unified Experience**: Same agent behavior for all task types

## Tool Access

The orchestrator agent has access to:
- **Existing CrewAI Tools**: From `tools/` directory (Harvest, ClickUp, Gmail, etc.)
- **ToolRegistry Tools**: Wrapped dynamically for CrewAI compatibility
- **All New Tools**: Automatically available (e.g., new ClickUp tools we just added)

## Usage

No changes needed for users - the Chat API interface remains the same. All requests are now processed through CrewAI agents.

## Example Flow

**User Request**: "Log 2 hours to Phytto project"

**Flow**:
1. Chat API receives request
2. Routes to `run_orchestrator_task()`
3. Orchestrator crew creates task
4. Agent uses `harvest_log_time` tool
5. Result returned to user

## Migration Notes

- **Backward Compatible**: ToolRegistry still exists and works
- **Tool Wrapping**: ToolRegistry tools are automatically wrapped for CrewAI
- **Performance**: Slight overhead from CrewAI, but better reasoning capabilities
- **Error Handling**: Improved error messages from agent reasoning

## Future Enhancements

- Multi-agent crews for complex tasks
- Specialized agents for different domains
- Better tool selection reasoning
- Improved streaming responses
