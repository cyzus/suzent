import json

from suzent.mobile.media import find_media, media_id, tool_media_paths, with_media


def tool(name: str, metadata: dict, success: bool = True) -> dict:
    return {
        "type": "tool",
        "toolName": name,
        "output": json.dumps(
            {"success": success, "message": "done", "metadata": metadata}
        ),
    }


def test_media_paths_come_only_from_successful_media_tools() -> None:
    assert tool_media_paths(tool("check_video", {"saved_paths": ["/a/clip.mp4"]})) == [
        "/a/clip.mp4"
    ]
    assert tool_media_paths(tool("analyze_visual", {"visual_path": "/a/x.MOV"})) == [
        "/a/x.MOV"
    ]
    assert tool_media_paths(
        tool("generate_image", {"saved_paths": ["/a/1.png", "/a/1.png", "/a/n.txt"]})
    ) == ["/a/1.png"]
    assert (
        tool_media_paths(tool("check_video", {"saved_paths": ["/a/c.mp4"]}, False))
        == []
    )
    assert tool_media_paths(tool("read_file", {"saved_paths": ["/a/c.mp4"]})) == []
    assert (
        tool_media_paths({"type": "tool", "toolName": "speak", "output": "oops"}) == []
    )


def test_with_media_annotates_by_id_without_paths() -> None:
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "parts": [tool("speak", {"saved_paths": ["/a/s.mp3"]})]},
    ]
    annotated = with_media(messages)
    assert annotated[0] == messages[0]
    assert annotated[1]["parts"][0]["media"] == [
        {"id": media_id("/a/s.mp3"), "kind": "audio", "name": "s.mp3"}
    ]
    assert "media" not in messages[1]["parts"][0]
    assert find_media(messages, media_id("/a/s.mp3")) == ("/a/s.mp3", "audio/mpeg")
    assert find_media(messages, media_id("/etc/passwd")) is None


def test_send_file_shares_any_file_type() -> None:
    part = tool(
        "send_file", {"saved_paths": ["/a/report.pdf", "/a/clip.mp4", "/a/blob"]}
    )
    assert [
        item["kind"] for item in with_media([{"parts": [part]}])[0]["parts"][0]["media"]
    ] == [
        "file",
        "video",
        "file",
    ]
    assert find_media([{"parts": [part]}], media_id("/a/report.pdf")) == (
        "/a/report.pdf",
        "application/pdf",
    )
    assert find_media([{"parts": [part]}], media_id("/a/blob")) == (
        "/a/blob",
        "application/octet-stream",
    )
    # Other tools still only count media.
    assert (
        tool_media_paths(tool("check_video", {"saved_paths": ["/a/report.pdf"]})) == []
    )


def test_send_file_shows_files_even_when_the_chat_app_upload_failed() -> None:
    failed = tool("send_file", {"saved_paths": ["/a/report.pdf"]}, success=False)
    rejected = tool("send_file", {}, success=False)
    assert tool_media_paths(failed) == ["/a/report.pdf"]
    assert tool_media_paths(rejected) == []


def test_uploaded_images_are_previewable_without_tool_calls() -> None:
    path = "/workspace/uploads/photo.png"
    messages = [{"role": "user", "files": [{"filename": "photo.png", "path": path}]}]
    annotated = with_media(messages)
    assert annotated[0]["files"][0]["media"] == {
        "id": media_id(path),
        "kind": "image",
        "name": "photo.png",
    }
    assert "media" not in messages[0]["files"][0]
    assert find_media(messages, media_id(path)) == (path, "image/png")
    assert find_media([], media_id(path)) is None


def test_attachment_media_ignores_invalid_files_and_non_user_messages() -> None:
    files = [None, {}, {"path": 42}, {"path": ""}, {"path": "/workspace/a.pdf"}]
    messages = [{"role": "user", "files": files}]
    assert with_media(messages) == messages
    assert find_media(messages, media_id("/workspace/a.pdf")) is None
    other = [{"role": "assistant", "files": [{"path": "/workspace/a.png"}]}]
    assert with_media(other) == other
    assert find_media(other, media_id("/workspace/a.png")) is None
