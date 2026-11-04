"""Multi-column blocks are read down each column."""

from app.ingest.columns import TextBlock, grounded, order_blocks


def test_interleaved_columns_are_reordered() -> None:
    blocks = [
        TextBlock("Right top torque.", 400, 80, 560, 100),
        TextBlock("Left top brakes.", 40, 80, 200, 100),
        TextBlock("Right bottom 8 Nm.", 400, 140, 560, 180),
        TextBlock("Left bottom 4.2 mm.", 40, 140, 200, 180),
    ]
    text, multi = order_blocks(blocks, page_width=600)
    assert multi
    assert text.index("Left top") < text.index("Left bottom")
    assert text.index("Left bottom") < text.index("Right top")
    assert text.index("Right top") < text.index("Right bottom")


def test_added_tokens_are_rejected() -> None:
    source = "Left column brake inspection."
    assert grounded(source, "Left column brake inspection")
    assert not grounded(source, "Left column brake inspection invented")
