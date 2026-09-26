from io import BytesIO
from types import SimpleNamespace

from litellm.llms.gemini.videos.transformation import GeminiVideoConfig

from suzent.tools.creative.video_tool import (
    _ensure_gemini_image_input_compatibility,
)


def test_gemini_starting_image_is_sent_in_video_instance():
    _ensure_gemini_image_input_compatibility()
    config = GeminiVideoConfig()
    image = BytesIO(b"\x89PNG\r\n\x1a\nreference")
    mapped = config.map_openai_params(
        {"input_reference": image, "seconds": "8"},
        "veo-3.1-generate-preview",
        drop_params=False,
    )

    request, _, _ = config.transform_video_create_request(
        model="veo-3.1-generate-preview",
        prompt="Animate the clouds",
        api_base="https://example.invalid",
        video_create_optional_request_params=mapped,
        litellm_params=SimpleNamespace(),
        headers={},
    )

    assert request["instances"][0]["image"]["mimeType"] == "image/png"
    assert "image" not in request["parameters"]
    assert request["parameters"]["durationSeconds"] == 8
