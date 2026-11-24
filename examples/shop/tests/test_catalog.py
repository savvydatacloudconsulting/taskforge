import pytest

from shop import Catalog, Product


def test_get_returns_product(catalog):
    assert catalog.get("PEN").name == "Pen"


def test_get_unknown_sku_raises(catalog):
    with pytest.raises(KeyError):
        catalog.get("NOPE")


def test_duplicate_sku_rejected(catalog):
    with pytest.raises(ValueError):
        catalog.add(Product("PEN", "Other pen", 100))


def test_by_category(catalog):
    assert [p.sku for p in catalog.by_category("office")] == ["PEN", "BOOK"]
    assert catalog.by_category("garden") == []
