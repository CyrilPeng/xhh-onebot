from xhh_onebot.xhh.models import LinkContext, XhhMessage
from xhh_onebot.xhh.poller import build_context_message, html_to_text


def test_html_to_text_extracts_images_and_removes_tags():
    html = '<p>Hello <b>world</b></p><p><img data-original="https://img.test/a.png"/></p>'

    text = html_to_text(html)

    assert "Hello world" in text
    assert "[Image] https://img.test/a.png" in text
    assert "<p>" not in text


def test_build_context_message_prioritizes_user_comment_and_cleans_body():
    message = XhhMessage(
        comment_id=1,
        comment_text='<a href="x">@bot</a> user question',
        message_id=2,
        root_comment_id=3,
        link_id=4,
        user_id=5,
    )
    context = LinkContext(
        title="Title",
        parts=[{"type": "html", "text": '<p>Body <span data-emoji="x"></span></p>'}],
        topics=["Topic"],
    )

    text = build_context_message(message, context, 1000, post_context_max_chars=100)

    assert text.startswith("[User Comment - Reply To This]\n@bot user question")
    assert "[Reference Post Context - Use Only As Background]" in text
    assert "Body" in text
    assert "<span" not in text
    assert text.endswith("@bot user question")


def test_build_context_message_limits_post_body_before_final_user_comment():
    message = XhhMessage(
        comment_id=1,
        comment_text="final question",
        message_id=2,
        root_comment_id=3,
        link_id=4,
        user_id=5,
    )
    context = LinkContext(parts=[{"type": "text", "text": "x" * 500}])

    text = build_context_message(message, context, 1000, post_context_max_chars=80)

    assert "...[truncated]" in text
    assert text.endswith("final question")
    assert text.count("final question") == 2
