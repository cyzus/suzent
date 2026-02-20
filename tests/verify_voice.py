from suzent.tools.voice_tool import SpeakTool


def test_speak():
    print("Initializing SpeakTool...")
    tool = SpeakTool()

    print("Speaking...")
    result = tool.forward("Hello, I am Suzent. I can speak now.")
    print(f"Result: {result}")


if __name__ == "__main__":
    try:
        test_speak()
    except Exception as e:
        print(f"Error: {e}")
