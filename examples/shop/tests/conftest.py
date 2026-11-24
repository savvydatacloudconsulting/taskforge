import pytest

from shop import Cart, Catalog, Product


@pytest.fixture
def catalog():
    return Catalog([
        Product("PEN", "Pen", 150, "office"),
        Product("BOOK", "Notebook", 1200, "office"),
        Product("MUG", "Mug", 800, "kitchen"),
    ])


@pytest.fixture
def cart(catalog):
    return Cart(catalog)
