from datetime import date

import pytest

from library import Book, Library, Member

TODAY = date(2026, 3, 1)


@pytest.fixture
def lib():
    library = Library()
    library.add_book(Book("111", "Dune", copies=2))
    library.add_book(Book("222", "Emma", copies=1))
    library.add_member(Member("m1", "Ana"))
    library.add_member(Member("m2", "Ben"))
    return library


@pytest.fixture
def today():
    return TODAY
