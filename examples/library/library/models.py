from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Book:
    isbn: str
    title: str
    copies: int = 1


@dataclass(frozen=True)
class Member:
    member_id: str
    name: str
