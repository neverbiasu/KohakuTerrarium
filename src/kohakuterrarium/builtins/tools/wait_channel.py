"""Wait channel tool - wait for a message on a named channel."""

import asyncio
import json
from typing import Any

from kohakuterrarium.builtins.tools.registry import register_builtin
from kohakuterrarium.core.channel import (
    AgentChannel,
    SubAgentChannel,
    get_channel_registry,
)
from kohakuterrarium.modules.tool.base import (
    BaseTool,
    ExecutionMode,
    ToolContext,
    ToolResult,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@register_builtin("wait_channel")
class WaitChannelTool(BaseTool):
    """Wait for a message on a named channel."""

    needs_context = True

    @property
    def tool_name(self) -> str:
        return "wait_channel"

    @property
    def description(self) -> str:
        return "Wait for a message on a named channel"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(
        self, args: dict[str, Any], context: ToolContext | None = None
    ) -> ToolResult:
        """Wait for channel message."""
        channel_name = args.get("channel", "")
        timeout = float(args.get("timeout", 30))

        if not channel_name:
            return ToolResult(error="Channel name is required")

        # Resolve channel: private session first, shared environment second
        channel = None

        # 1. Check creature's private channels (sub-agent channels)
        if context and context.session:
            channel = context.session.channels.get(channel_name)

        # 2. Check environment's shared channels (inter-creature channels)
        if channel is None and context and context.environment:
            channel = context.environment.shared_channels.get(channel_name)

        # 3. Fallback for no-context usage (standalone / testing)
        if channel is None and not context:
            channel = get_channel_registry().get_or_create(channel_name)

        # 4. Auto-create in private session if not found anywhere
        if channel is None and context and context.session:
            channel = context.session.channels.get_or_create(channel_name)

        if channel is None:
            return ToolResult(
                error=f"Channel '{channel_name}' not found and cannot be created"
            )

        subscription = None
        try:
            if isinstance(channel, AgentChannel):
                # For broadcast channels, subscribe using agent name
                subscriber_id = "unknown"
                if context:
                    subscriber_id = context.agent_name
                subscription = channel.subscribe(subscriber_id)
                msg = await subscription.receive(timeout=timeout)
            elif isinstance(channel, SubAgentChannel):
                msg = await channel.receive(timeout=timeout)
            else:
                msg = await channel.receive(timeout=timeout)

            # Format response
            content = msg.content
            if isinstance(content, dict):
                content = json.dumps(content, indent=2)

            output_parts = [
                f"From: {msg.sender}",
                f"Message-ID: {msg.message_id}",
                f"Content: {content}",
            ]
            if msg.reply_to:
                output_parts.append(f"Reply-To: {msg.reply_to}")
            if msg.metadata:
                output_parts.append(f"Metadata: {json.dumps(msg.metadata)}")

            logger.debug("Message received", channel=channel_name, sender=msg.sender)
            return ToolResult(output="\n".join(output_parts), exit_code=0)

        except asyncio.TimeoutError:
            return ToolResult(
                output=f"Timeout waiting for message on '{channel_name}' after {timeout}s",
                exit_code=1,
            )
        finally:
            if subscription is not None:
                subscription.unsubscribe()

    def get_full_documentation(self, tool_format: str = "native") -> str:
        return """# wait_channel

Wait for a message on a named internal channel. Primarily for
request-response patterns with your own sub-agents.

## IMPORTANT: Do NOT use this for team channels

In a terrarium, messages from team channels (tasks, review, feedback, etc.)
arrive AUTOMATICALLY via triggers. You do NOT need to call wait_channel
for them. Using wait_channel on a team queue channel would CONSUME the
message, potentially stealing it from the intended recipient.

Only use wait_channel for:
- Internal channels you created yourself
- Sub-agent response channels
- Custom request-response patterns within your own agent

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| channel | string | Internal channel name (required) |
| timeout | number | Seconds to wait (default: 30) |

## Behavior

- Checks private session channels first, then shared environment.
- For broadcast channels, subscribes and unsubscribes after receiving.
- Returns sender, message ID, and content of the received message.
- On timeout, returns a timeout notification with exit code 1.
"""
