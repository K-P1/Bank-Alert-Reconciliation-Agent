"""
Tests for the natural language command interpreter.
"""

import pytest
from app.a2a.command_interpreter import CommandInterpreter


@pytest.fixture
def interpreter():
    """Create a test interpreter with sample commands."""
    interp = CommandInterpreter()

    # Register test commands
    async def test_handler(params):
        return {"status": "success", "params": params}

    interp.register_command(
        name="test_reconcile",
        patterns=[
            r"\breconcile\b",
            r"\brun\s+(the\s+)?reconciliation\b",
            r"\bmatch\s+emails?\b",
            r"\bstart\s+matching\b",
            r"\bprocess\s+(emails?|alerts?)\b",
        ],
        handler=test_handler,
        description="Test reconciliation command",
        examples=["reconcile", "run reconciliation"],
    )

    interp.register_command(
        name="test_summary",
        patterns=[
            r"\bshow\s+(me\s+)?(the\s+)?summary\b",
            r"\b(get|give)\s+(me\s+)?(the\s+)?status\b",
        ],
        handler=test_handler,
        description="Test summary command",
        examples=["show summary", "get status"],
    )

    interp.register_command(
        name="help",
        patterns=[r"\bhelp\b", r"\bcommands?\b"],
        handler=test_handler,
        description="Show help",
        examples=["help"],
    )

    return interp


class TestCommandInterpreter:
    """Test suite for CommandInterpreter."""

    def test_register_command(self, interpreter):
        """Test command registration."""
        assert "test_reconcile" in interpreter.commands
        assert "test_summary" in interpreter.commands
        assert "help" in interpreter.commands

        # Check compiled patterns
        assert "test_reconcile" in interpreter._compiled_patterns
        assert (
            len(interpreter._compiled_patterns["test_reconcile"]) == 5
        )  # Updated from 3 to 5

    def test_interpret_exact_match(self, interpreter):
        """Test interpretation of exact command matches."""
        match = interpreter.interpret("reconcile")
        assert match.command_name == "test_reconcile"
        assert match.confidence >= 0.5

        match = interpreter.interpret("show summary")
        assert match.command_name == "test_summary"

    def test_interpret_case_insensitive(self, interpreter):
        """Test case-insensitive matching."""
        for text in ["Reconcile", "RECONCILE", "rEcOnCiLe"]:
            match = interpreter.interpret(text)
            assert match.command_name == "test_reconcile"

    def test_interpret_with_context(self, interpreter):
        """Test interpretation with surrounding context."""
        match = interpreter.interpret("Please run reconciliation now")
        assert match.command_name == "test_reconcile"

        match = interpreter.interpret("Can you show summary for me?")
        assert match.command_name == "test_summary"

    def test_interpret_fallback_to_help(self, interpreter):
        """Test fallback to help on unrecognized input."""
        match = interpreter.interpret("qwerty asdfgh zxcvbn")  # Truly gibberish text
        assert match.command_name == "help"
        assert match.params.get("reason") == "unrecognized"

    def test_interpret_multiple_patterns(self, interpreter):
        """Test matching against multiple patterns for same command."""
        test_cases = [
            ("reconcile", "test_reconcile"),
            ("run reconciliation", "test_reconcile"),
            ("match emails", "test_reconcile"),
        ]

        for text, expected_cmd in test_cases:
            match = interpreter.interpret(text)
            assert match.command_name == expected_cmd

    def test_confidence_scoring(self, interpreter):
        """Test confidence score calculation."""
        # Exact short match should have high confidence
        match1 = interpreter.interpret("reconcile")

        # Match with lots of surrounding text should have lower confidence
        match2 = interpreter.interpret(
            "I would like to reconcile all the things please thank you"
        )

        # Both should match but first should have higher confidence
        assert match1.command_name == "test_reconcile"
        assert match2.command_name == "test_reconcile"
        assert match1.confidence >= match2.confidence

    def test_get_help_text(self, interpreter):
        """Test help text generation."""
        help_text = interpreter.get_help_text()
        assert "BARA" in help_text
        assert "/test reconcile" in help_text.lower() or "/Test Reconcile" in help_text
        assert "/test summary" in help_text.lower() or "/Test Summary" in help_text
        assert "help" in help_text.lower()


class TestCommandPhrases:
    """Test realistic command phrases."""

    def test_reconciliation_phrases(self, interpreter):
        """Test various ways to ask for reconciliation."""
        phrases = [
            "run reconciliation",
            "reconcile now",
            "match emails",
            "start matching",
            "can you reconcile?",
            "please run the reconciliation",
        ]

        for phrase in phrases:
            match = interpreter.interpret(phrase)
            assert match.command_name == "test_reconcile", f"Failed on: {phrase}"

    def test_summary_phrases(self, interpreter):
        """Test various ways to ask for summary."""
        phrases = [
            "show summary",
            "get status",
            "show me the summary",
            "can you get status?",
        ]

        for phrase in phrases:
            match = interpreter.interpret(phrase)
            assert match.command_name == "test_summary", f"Failed on: {phrase}"

    def test_help_phrases(self, interpreter):
        """Test various ways to ask for help."""
        phrases = [
            "help",
            "commands",
            "show commands",
            "what commands are available",
        ]

        for phrase in phrases:
            match = interpreter.interpret(phrase)
            assert match.command_name == "help", f"Failed on: {phrase}"


class TestParameterExtraction:
    """Test parameter extraction from messages."""

    def test_extract_with_custom_extractor(self):
        """Test parameter extraction using custom extractor."""
        from app.a2a.command_handlers import extract_limit
        import re

        # Test limit extraction
        message = "reconcile 50 emails"
        match = re.search(r"\breconcile\b", message)
        limit = extract_limit(message, match)
        assert limit == 50

        message = "match 100 alerts"
        match = re.search(r"\bmatch\b", message)
        limit = extract_limit(message, match)
        assert limit == 100

    def test_extract_days(self):
        """Test days extraction."""
        from app.a2a.command_handlers import extract_days
        import re

        message = "show summary for last 7 days"
        match = re.search(r"\bshow\b", message)
        days = extract_days(message, match)
        assert days == 7

        message = "get stats for 30 days"
        match = re.search(r"\bget\b", message)
        days = extract_days(message, match)
        assert days == 30

    def test_extract_rematch_flag(self):
        """Test rematch flag extraction."""
        from app.a2a.command_handlers import extract_rematch_flag
        import re

        message = "rematch all emails"
        match = re.search(r"\brematch\b", message)
        rematch = extract_rematch_flag(message, match)
        assert rematch is True

        message = "reconcile normally"
        match = re.search(r"\breconcile\b", message)
        rematch = extract_rematch_flag(message, match)
        assert rematch is False


@pytest.mark.asyncio
class TestEndToEndCommands:
    """Test end-to-end command execution flow."""

    async def test_command_with_params(self):
        """Test command execution with parameter extraction."""
        from app.a2a.command_handlers import extract_limit

        interp = CommandInterpreter()

        async def mock_handler(params):
            return {"status": "success", "limit": params.get("limit")}

        interp.register_command(
            name="test_cmd",
            patterns=[r"\btest\b"],
            handler=mock_handler,
            description="Test",
            examples=["test"],
            param_extractors={"limit": extract_limit},
        )

        match = interp.interpret("test 25 items")
        assert match.command_name == "test_cmd"
        assert match.params.get("limit") == 25


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
