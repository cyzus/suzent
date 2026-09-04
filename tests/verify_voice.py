import asyncio

from suzent.tools.voice_tool import SpeakTool


def test_speak():
    print("Initializing SpeakTool...")
    tool = SpeakTool()

    print("Speaking...")
    # ctx first, as the registry passes it. SpeakTool does not read it, but the
    # signature has to match the one the wrapper calls.
    result = asyncio.run(tool.forward(None, "Hello, I am Suzent. I can speak now."))
    print(f"Result: {result}")


if __name__ == "__main__":
    try:
        test_speak()
    except Exception as e:
        print(f"Error: {e}")
