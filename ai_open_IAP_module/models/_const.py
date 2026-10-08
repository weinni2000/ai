# Models offered by the providers' /models endpoints (checked 2026-10-07).
# Value: API model id, label: provider display name.
CLAUDE_MODELS = [
    ("claude-opus-5-5", "Claude Opus 5.5"),
    ("claude-sonnet-5-5", "Claude Sonnet 5.5"),
    ("claude-haiku-5-5", "Claude Haiku 5.5"),
    ("claude-fable-5-1", "Claude Fable 5.1"),
    ("claude-opus-5", "Claude Opus 5"),
    ("claude-sonnet-5", "Claude Sonnet 5"),
    ("claude-fable-5", "Claude Fable 5"),
    ("claude-opus-4-8", "Claude Opus 4.8"),
    ("claude-opus-4-7", "Claude Opus 4.7"),
    ("claude-opus-4-6", "Claude Opus 4.6"),
    ("claude-sonnet-4-6", "Claude Sonnet 4.6"),
    ("claude-opus-4-5-20251101", "Claude Opus 4.5"),
    ("claude-sonnet-4-5-20250929", "Claude Sonnet 4.5"),
    ("claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
]
DEEPSEEK_MODELS = [
    ("deepseek-flash", "DeepSeek V4.1 Flash"),
    ("deepseek-v4-pro", "DeepSeek V4 Pro"),
]
# Chat models only; TTS, image generation, music and agent models are left out.
GEMINI_MODELS = [
    ("gemini-3.8-flash", "Gemini 3.8 Flash"),
    ("gemini-3.7-flash", "Gemini 3.7 Flash"),
    ("gemini-3.6-flash", "Gemini 3.6 Flash"),
    ("gemini-3.5-flash", "Gemini 3.5 Flash"),
    ("gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite"),
    ("gemini-3.1-pro-preview", "Gemini 3.1 Pro Preview"),
    ("gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite"),
    ("gemini-3-flash-preview", "Gemini 3 Flash Preview"),
    ("gemini-2.5-pro", "Gemini 2.5 Pro"),
    ("gemini-2.5-flash", "Gemini 2.5 Flash"),
    ("gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite"),
    ("gemini-pro-latest", "Gemini Pro Latest"),
    ("gemini-flash-latest", "Gemini Flash Latest"),
    ("gemini-flash-lite-latest", "Gemini Flash-Lite Latest"),
]
MODELS_BY_KIND = {
    "claude": CLAUDE_MODELS,
    "deepseek": DEEPSEEK_MODELS,
    "gemini": GEMINI_MODELS,
}
# Models accepting image input; every listed Claude and Gemini model does.
IMAGE_MODELS = {model for model, _label in CLAUDE_MODELS + GEMINI_MODELS} | {
    "deepseek-flash"
}
