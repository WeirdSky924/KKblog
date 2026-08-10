from apps.discovery.queries.article import _tiptap_outline
from apps.media.public import TipTapOutlineItem


def test_tiptap_outline_uses_json_projection_without_rewriting_rendered_ids() -> None:
    html = (
        '<h1 id="kaj-h-first">开篇</h1>'
        '<h2 id="kaj-h-second">重复标题</h2>'
        '<h2 id="kaj-h-third">重复标题</h2>'
    )
    projected = (
        TipTapOutlineItem("kaj-h-first", 1, "开篇"),
        TipTapOutlineItem("kaj-h-second", 2, "重复标题"),
        TipTapOutlineItem("kaj-h-third", 2, "重复标题"),
        TipTapOutlineItem("kaj-h-empty", 2, ""),
    )

    body, toc = _tiptap_outline(html, projected)

    assert str(body) == html
    assert [(item.anchor, item.label) for item in toc] == [
        ("kaj-h-second", "重复标题"),
        ("kaj-h-third", "重复标题"),
    ]
