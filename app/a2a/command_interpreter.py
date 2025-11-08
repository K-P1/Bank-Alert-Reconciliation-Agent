"""
Command interpreter for natural language routing in A2A endpoint.

This module provides a lightweight, regex-based command interpreter that maps
plain text messages from Telex to specific backend functions without requiring
LLM dependencies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Any

import structlog


logger = structlog.get_logger("a2a.command_interpreter")


@dataclass
class CommandMatch:
    """Result of a command interpretation attempt."""

    command_name: str
    handler: Optional[
        Callable
    ]  # Optional - not used since handlers instantiated with db session
    params: Dict[str, Any]
    confidence: float  # 0.0 to 1.0
    matched_pattern: str


@dataclass
class CommandDefinition:
    """Definition of a recognized command."""

    name: str
    patterns: List[str]  # Regex patterns
    handler: Optional[
        Callable
    ]  # Optional because handlers are set at runtime with db session
    description: str
    examples: List[str]
    param_extractors: Optional[Dict[str, Callable]] = None


class CommandInterpreter:
    """
    Regex-based command interpreter for natural language routing.

    Features:
    - Zero LLM dependency
    - Deterministic pattern matching
    - Parameter extraction via regex groups
    - Fallback to help command
    - <100ms response latency
    """

    def __init__(self) -> None:
        self.commands: Dict[str, CommandDefinition] = {}
        self._compiled_patterns: Dict[str, List[re.Pattern]] = {}

    def register_command(
        self,
        name: str,
        patterns: List[str],
        handler: Optional[
            Callable
        ],  # Optional - handlers set at runtime with db session
        description: str,
        examples: List[str],
        param_extractors: Optional[Dict[str, Callable]] = None,
    ) -> None:
        """Register a new command with its patterns and handler."""
        cmd = CommandDefinition(
            name=name,
            patterns=patterns,
            handler=handler,
            description=description,
            examples=examples,
            param_extractors=param_extractors,
        )
        self.commands[name] = cmd

        # Pre-compile regex patterns for performance
        self._compiled_patterns[name] = [
            re.compile(pattern, re.IGNORECASE) for pattern in patterns
        ]

        logger.info(
            "command.registered",
            command=name,
            pattern_count=len(patterns),
            has_extractors=param_extractors is not None,
        )

    def interpret(self, message: str) -> CommandMatch:
        """
        Interpret a plain text message and return the best matching command.

        Args:
            message: User's plain text message from Telex

        Returns:
            CommandMatch with the matched command, handler, and extracted params
        """
        message = message.strip()
        logger.debug("command.interpret.start", message_length=len(message))

        # Try each registered command
        for cmd_name, cmd_def in self.commands.items():
            patterns = self._compiled_patterns[cmd_name]

            for i, pattern in enumerate(patterns):
                match = pattern.search(message)
                if match:
                    # Extract parameters if extractors are defined
                    params = {}
                    if cmd_def.param_extractors:
                        for param_name, extractor in cmd_def.param_extractors.items():
                            try:
                                params[param_name] = extractor(message, match)
                            except Exception as exc:  # noqa: BLE001
                                logger.warning(
                                    "command.param_extraction.failed",
                                    command=cmd_name,
                                    param=param_name,
                                    error=str(exc),
                                )

                    # Calculate confidence based on match quality
                    confidence = self._calculate_confidence(match, message)

                    logger.info(
                        "command.matched",
                        command=cmd_name,
                        pattern_index=i,
                        confidence=confidence,
                        params=params,
                    )

                    return CommandMatch(
                        command_name=cmd_name,
                        handler=cmd_def.handler,
                        params=params,
                        confidence=confidence,
                        matched_pattern=cmd_def.patterns[i],
                    )

        # No match found - return help command
        logger.info("command.no_match", message=message)

        # Ensure help command exists before returning it
        if "help" not in self.commands:
            raise ValueError("Help command must be registered")

        return CommandMatch(
            command_name="help",
            handler=self.commands["help"].handler,
            params={"reason": "unrecognized"},
            confidence=1.0,  # Help is always confident
            matched_pattern="default",
        )

    def _calculate_confidence(self, match: re.Match, message: str) -> float:
        """
        Calculate confidence score based on match quality.

        Factors:
        - Length of matched text vs total message length
        - Position of match (earlier is better)
        - Presence of multiple keywords
        """
        matched_text = match.group(0)
        match_length_ratio = len(matched_text) / max(len(message), 1)
        position_score = 1.0 - (match.start() / max(len(message), 1))

        # Weighted combination
        confidence = (match_length_ratio * 0.6) + (position_score * 0.4)
        return min(max(confidence, 0.5), 1.0)  # Clamp between 0.5 and 1.0

    def get_help_text(self) -> str:
        """Generate formatted help text listing all available commands with parameters."""
        lines = [
            "🤖 **BARA - Bank Alert Reconciliation Agent**",
            "",
            "Available Commands:",
            "",
        ]

        for cmd_name, cmd_def in self.commands.items():
            if cmd_name == "help":
                continue  # Skip help in the list

            # Command title
            lines.append(f"**/{cmd_name.replace('_', ' ')}**")
            lines.append(f"  {cmd_def.description}")

            # Show parameters if any
            if cmd_def.param_extractors:
                lines.append("  Parameters:")
                for param_name in cmd_def.param_extractors.keys():
                    if param_name == "limit":
                        lines.append(
                            f"    • {param_name}: Number of items to process (e.g., '50 emails', 'limit 20')"
                        )
                    elif param_name == "days":
                        lines.append(
                            f"    • {param_name}: Number of days to look back (e.g., 'last 14 days', 'for 7 days')"
                        )
                    elif param_name == "rematch":
                        lines.append(
                            f"    • {param_name}: Force re-matching of already matched items (mention 'rematch' or 'force')"
                        )
                    else:
                        lines.append(f"    • {param_name}: Optional parameter")

            # Show examples
            lines.append("  Examples:")
            for example in cmd_def.examples:
                lines.append(f"    • {example}")
            lines.append("")

        lines.extend(
            [
                "**/help**",
                "  Show this list of commands",
                "  Examples:",
                "    • help",
                "    • show commands",
                "    • what can you do",
                "",
                "💡 *Tip: Commands are case-insensitive and flexible - try natural phrasing!*",
                "💡 *Parameters can be mentioned anywhere in your message (e.g., 'reconcile 50 emails' or 'show summary for last 30 days')*",
            ]
        )

        return "\n".join(lines)

    def extract_text(self, payload: Dict[str, Any]) -> str:
        """
        Extract user message text from A2A payload.
        Extracts only parts[1].data[-1].text (latest user message from conversation history).
        Falls back to parts[0].text if parts[1] doesn't exist.
        """
        params = payload.get("params", {})
        msg_obj = params.get("message", {})
        parts = msg_obj.get("parts") if isinstance(msg_obj, dict) else None

        # Extract parts[1].data[-1] text (latest user message from conversation history)
        if isinstance(parts, list) and len(parts) > 1:
            second = parts[1]
            if isinstance(second, dict) and second.get("kind") == "data":
                data = second.get("data")
                if isinstance(data, list) and data:
                    # Get the last item in the data array
                    last_item = data[-1]
                    if isinstance(last_item, dict) and last_item.get("kind") == "text":
                        hist_text = last_item.get("text", "")
                        if isinstance(hist_text, str) and hist_text.strip():
                            return hist_text.strip()

        # Fallback: Extract parts[0] text (for simple payloads or when parts[1] is unavailable)
        if isinstance(parts, list) and len(parts) > 0:
            first = parts[0]
            if isinstance(first, dict) and first.get("kind") == "text":
                text = first.get("text", "")
                if isinstance(text, str) and text.strip():
                    return text.strip()

        # Final fallback to message.text or params.text
        text = msg_obj.get("text") or params.get("text") or ""
        return str(text).strip()


# Global interpreter instance
_interpreter: Optional[CommandInterpreter] = None


def get_interpreter() -> CommandInterpreter:
    """Get the global command interpreter instance (singleton)."""
    global _interpreter
    if _interpreter is None:
        _interpreter = CommandInterpreter()
    return _interpreter
