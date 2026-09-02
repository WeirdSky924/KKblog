from apps.learning.services.source_units import (
    batch_source_knowledge_units,
    extract_source_knowledge_units,
)


def test_structured_document_keeps_fine_grained_heading_order() -> None:
    units = extract_source_knowledge_units(
        "# 手册\n\n## A-001 | Token\n内容一。\n\n## A-002 | 上下文\n内容二。\n"
    )
    assert [unit.logical_id for unit in units] == ["src-0001", "src-0002"]
    assert [unit.heading for unit in units] == ["A-001 | Token", "A-002 | 上下文"]
    assert [unit.ordinal for unit in units] == [1, 2]


def test_unstructured_document_uses_ordered_paragraph_units() -> None:
    units = extract_source_knowledge_units("第一点说明。\n\n第二点说明。\n")
    assert [unit.logical_id for unit in units] == ["src-0001", "src-0002"]
    assert all(unit.heading == "未命名知识点" for unit in units)


def test_source_units_are_batched_without_merging_units() -> None:
    units = extract_source_knowledge_units(
        "\n".join(f"## P-{index}\n内容 {index}\n" for index in range(5))
    )
    batches = batch_source_knowledge_units(units, maximum_units=2)
    assert [[unit.logical_id for unit in batch] for batch in batches] == [
        ["src-0001", "src-0002"],
        ["src-0003", "src-0004"],
        ["src-0005"],
    ]
