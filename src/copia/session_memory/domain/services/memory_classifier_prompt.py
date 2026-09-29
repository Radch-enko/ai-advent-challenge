from copia.common.domain.services.prompt_resources import load_prompt

MEMORY_CLASSIFIER_SYSTEM_PROMPT = load_prompt("copia.session_memory", "memory_classifier.md")
