from suzent.core.citation_codec import (
    CitationStreamRenderer,
    namespace_sources,
    render_citations_plain_text,
    rewrite_citation_ids,
    truncate_citation_text,
)


SOURCES = [
    {
        "id": "t0_src_1",
        "type": "webpage",
        "title": "Example",
        "url": "https://example.com/source",
    }
]


def test_renders_every_supported_marker_without_protocol_glyphs():
    variants = (
        "Fact\ue200cite\ue202t0_src_1\ue201.",
        "Fact [[cite:t0_src_1]].",
        "Fact\ufffccite\ufffct0_src_1\ufffc.",
        "Fact cite:t0_src_1.",
    )

    for text in variants:
        rendered = render_citations_plain_text(text, SOURCES)
        assert "Fact [1]." in rendered
        assert "[1] Example — https://example.com/source" in rendered
        assert "\ue200" not in rendered
        assert "\ue201" not in rendered
        assert "\ue202" not in rendered
        assert "\ufffc" not in rendered


def test_namespaces_colliding_subagent_source_ids_and_rewrites_markers():
    first_sources, first_map = namespace_sources(SOURCES, "sub-a")
    second_sources, _ = namespace_sources(SOURCES, "sub-b")

    assert first_sources[0]["id"] == "sa_sub_a_src_1"
    assert second_sources[0]["id"] == "sa_sub_b_src_1"
    assert (
        rewrite_citation_ids("Fact\ue200cite\ue202t0_src_1\ue201.", first_map)
        == "Fact[[cite:sa_sub_a_src_1]]."
    )


def test_truncation_never_leaves_a_partial_marker():
    text = "A" * 20 + "\ue200cite\ue202t0_src_1\ue201" + "tail"
    truncated = truncate_citation_text(text, 25)

    assert truncated.endswith("…")
    assert "\ue200" not in truncated


def test_stream_renderer_handles_marker_split_at_every_boundary():
    text = "Fact\ue200cite\ue202t0_src_1\ue201."
    for boundary in range(1, len(text)):
        renderer = CitationStreamRenderer()
        renderer.add_sources(SOURCES)
        output = renderer.feed(text[:boundary])
        output += renderer.feed(text[boundary:])
        output += renderer.finish()

        assert output == (
            "Fact [1].\n\nSources:\n[1] Example — https://example.com/source"
        )


def test_stream_renderer_holds_split_ascii_opener():
    renderer = CitationStreamRenderer()
    renderer.add_sources(SOURCES)

    output = renderer.feed("Fact [")
    output += renderer.feed("[cite:t0_src_1]].")
    output += renderer.finish()

    assert output.startswith("Fact [1].")
    assert "[[cite" not in output


def test_malformed_marker_never_leaks_reserved_delimiters():
    rendered = render_citations_plain_text("Fact\ue200cite\ue202broken")

    assert "\ue200" not in rendered
    assert "\ue202" not in rendered
