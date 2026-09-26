from suzent.tools.creative.voice_tool import SpeakTool as CreativeSpeakTool
from suzent.tools.voice_tool import SpeakTool


def test_legacy_voice_tool_path_exports_creative_tool():
    assert SpeakTool is CreativeSpeakTool
