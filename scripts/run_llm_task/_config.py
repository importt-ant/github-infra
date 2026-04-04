from __future__ import annotations

GITHUB_MODELS_URL = "https://models.inference.ai.azure.com"
DEFAULT_MODEL = "gpt-4o-mini"

# Low-tier models (gpt-4o-mini, Phi-4, Llama, etc.) allow 15 req/min on the
# free plan → one request every 4 seconds minimum.
REQUEST_DELAY = 4.0

# If the LLM returns a file substantially shorter than the original it likely
# truncated the output (free tier caps at 4 000 output tokens). Abort the
# write rather than silently corrupt the file.
TRUNCATION_RATIO = 0.75

# Files shorter than this (in chars) are never truncated by token limits, so
# the ratio check is skipped for them entirely. 4 000 output tokens ≈ 16 000
# chars, but even conservatively a 1 000-char file cannot be cut off mid-way.
TRUNCATION_MIN_SOURCE_CHARS = 1_000

# Number of additional attempts after the first failure (delay doubles each time).
MAX_RETRIES = 1

# Comment written at the top of any file that could not be processed after all
# retries, so it can be found easily with grep.
FAILURE_COMMENT = "# LLM-REVIEW-FAILED"
