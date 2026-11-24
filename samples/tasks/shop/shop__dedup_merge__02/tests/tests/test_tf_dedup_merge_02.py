import pytest

from shop import Cart, Catalog, Product


def test_catalog_add_all_counts_new_products():
    catalog = Catalog()
    added = catalog.add_all([
        Product("PEN", "Pen", 150, "office"),
        Product("MUG", "Mug", 800, "kitchen"),
    ])
    assert added == 2
    assert "PEN" in catalog
    assert catalog.get("MUG").price_cents == 800


def test_catalog_add_all_ignores_identical_existing_product(catalog):
    added = catalog.add_all([
        Product("PEN", "Pen", 150, "office"),
        Product("LAMP", "Lamp", 2500),
    ])
    assert added == 1
    assert catalog.get("LAMP").name == "Lamp"
    assert catalog.get("PEN").price_cents == 150


def test_catalog_add_all_ignores_identical_repeat_in_input():
    catalog = Catalog()
    added = catalog.add_all([
        Product("MUG", "Mug", 800),
        Product("MUG", "Mug", 800),
        Product("MUG", "Mug", 800),
    ])
    assert added == 1
    assert len(catalog.by_category("general")) == 1


def test_catalog_add_all_conflict_with_existing_product(catalog):
    with pytest.raises(ValueError, match="conflicting sku: PEN"):
        catalog.add_all([Product("PEN", "Pen", 175, "office")])


def test_catalog_add_all_conflict_within_input_is_atomic(catalog):
    with pytest.raises(ValueError, match="conflicting sku: LAMP"):
        catalog.add_all([
            Product("DESK", "Desk", 9000),
            Product("LAMP", "Lamp", 2500),
            Product("LAMP", "Lamp", 2600),
        ])
    assert "DESK" not in catalog
    assert "LAMP" not in catalog


def test_catalog_add_all_conflict_on_non_price_field(catalog):
    with pytest.raises(ValueError, match="conflicting sku: MUG"):
        catalog.add_all([Product("MUG", "Mug", 800, "office")])


def test_catalog_add_all_empty_input(catalog):
    assert catalog.add_all([]) == 0
    assert catalog.get("BOOK").price_cents == 1200


def test_cart_add_all_merges_repeated_skus(cart):
    distinct = cart.add_all([("PEN", 2), ("MUG", 1), ("PEN", 3)])
    assert distinct == 2
    assert cart.quantity("PEN") == 5
    assert cart.quantity("MUG") == 1
    assert cart.subtotal_cents() == 5 * 150 + 800


def test_cart_add_all_adds_to_existing_quantity(cart):
    cart.add("PEN", 4)
    assert cart.add_all([("PEN", 1), ("PEN", 2)]) == 1
    assert cart.quantity("PEN") == 7


def test_cart_add_all_empty_input(cart):
    assert cart.add_all([]) == 0
    assert cart.is_empty()


def test_cart_add_all_invalid_quantity_is_atomic(cart):
    cart.add("BOOK", 1)
    with pytest.raises(ValueError, match="quantity must be positive"):
        cart.add_all([("PEN", 2), ("MUG", 0)])
    assert cart.quantity("PEN") == 0
    assert cart.quantity("MUG") == 0
    assert cart.quantity("BOOK") == 1


def test_cart_add_all_negative_quantity_rejected(cart):
    with pytest.raises(ValueError, match="quantity must be positive"):
        cart.add_all([("PEN", -1)])
    assert cart.is_empty()


def test_cart_add_all_unknown_sku_is_atomic(cart):
    with pytest.raises(KeyError):
        cart.add_all([("PEN", 2), ("NOPE", 1)])
    assert cart.is_empty()
