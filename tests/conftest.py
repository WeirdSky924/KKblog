def pytest_collection_modifyitems(items) -> None:
    import pytest

    for item in items:
        path = str(item.path)
        if "/tests/contracts/" in path:
            item.add_marker(pytest.mark.contract)
        elif "/tests/integration/" in path:
            item.add_marker(pytest.mark.integration)
