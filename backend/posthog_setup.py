from posthog import Posthog
from posthog.ai.prompts import Prompts

from .config import (
    POSTHOG_API_KEY,
    POSTHOG_HOST,
    POSTHOG_APP_HOST,
    POSTHOG_PERSONAL_API_KEY,
)

posthog_client = Posthog(
    project_api_key=POSTHOG_API_KEY,
    host=POSTHOG_HOST,
    personal_api_key=POSTHOG_PERSONAL_API_KEY,
    super_properties={"app": "hot-hog"},
)

# Prompts client uses the app host (not ingestion host) for reads.
# Falls back gracefully if personal_api_key is not set.
prompts = Prompts(
    personal_api_key=POSTHOG_PERSONAL_API_KEY,
    project_api_key=POSTHOG_API_KEY,
    host=POSTHOG_APP_HOST,
)
