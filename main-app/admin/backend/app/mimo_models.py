"""MiMo text and multimodal model identifiers supported by the API."""

DEFAULT_MIMO_MODEL = "mimo-v2.6-flash"
MIMO_TEXT_MODELS = (DEFAULT_MIMO_MODEL, "mimo-v2.6-pro", "mimo-v2.6-pro-ultraspeed")

# Xiaomi's retired-model replacements, including the earlier V2 generation.
RETIRED_MIMO_MODELS = {
    "mimo-v2.5": DEFAULT_MIMO_MODEL,
    "mimo-v2.5-pro": "mimo-v2.6-pro",
    "mimo-v2-omni": DEFAULT_MIMO_MODEL,
    "mimo-v2-flash": DEFAULT_MIMO_MODEL,
    "mimo-v2-pro": "mimo-v2.6-pro",
}


def normalize_mimo_model(model: str) -> str:
    """Replace retired text models without touching ASR, TTS, or custom IDs."""
    return RETIRED_MIMO_MODELS.get(model, model)
