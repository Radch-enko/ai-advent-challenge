from datetime import UTC, datetime

from copia.common.domain.services.llm_context_builder import LLMContextBuilder
from copia.common.domain.services.prompt_builder import PromptBuilder
from copia.sessions.domain.models.chat_message import ChatMessage


def test_prompt_builder_preserves_named_section_order_and_skips_blank_values() -> None:
    builder = PromptBuilder().add("base", "  Base instruction  ").add("empty", " \n")
    builder.add("invariants", "Keep this constraint")

    assert builder.section_names == ("base", "invariants")
    assert builder.build() == "  Base instruction  \n\nKeep this constraint"


def test_llm_context_builder_exposes_ordered_context_and_history() -> None:
    history = [ChatMessage(role="user", content="Question")]

    messages = LLMContextBuilder.build(
        system_prompt="Base instruction",
        invariants="Constraint",
        user_profile="Preferences",
        long_term_memory="Long term facts",
        summary="Earlier conversation",
        working_memory="Current working facts",
        current_time=datetime(2026, 9, 29, 12, 30, tzinfo=UTC),
        history=history,
    )

    assert messages[0].role == "system"
    assert messages[0].content.index("Base instruction") < messages[0].content.index("Constraint")
    assert messages[0].content.index("Constraint") < messages[0].content.index("Preferences")
    assert messages[0].content.index("Long term facts") < messages[0].content.index(
        "Earlier conversation"
    )
    assert messages[0].content.index("Earlier conversation") < messages[0].content.index(
        "Current working facts"
    )
    assert "<current_datetime_context>" in messages[0].content
    assert "12:30:00+00:00" in messages[0].content
    assert messages[1] is history[0]


def test_llm_context_builder_omits_empty_system_message() -> None:
    history = [ChatMessage(role="user", content="Question")]

    assert LLMContextBuilder.build(history=history) == history


def test_prompt_resource_values_are_not_interpreted_as_template_syntax() -> None:
    from copia.common.domain.services.prompt_resources import render_prompt

    rendered = render_prompt(
        "copia.sessions", "context_sections.md", summary="literal {{summary}} content"
    )

    assert "literal {{summary}} content" in rendered
