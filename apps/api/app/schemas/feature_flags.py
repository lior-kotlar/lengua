"""DTOs for the feature-flag surfaces (task 6.9).

``GET /feature-flags`` returns a plain ``{name: enabled}`` boolean map (modelled inline as
``dict[str, bool]`` on the route), so the only DTO here is the payload of the experimental,
flag-gated ``GET /experimental/word-of-the-day`` route — a deliberately small, secret-free stub
that ships dark behind the ``word_of_the_day`` flag (off by default in every environment).
"""

from __future__ import annotations

from pydantic import BaseModel


class WordOfTheDayOut(BaseModel):
    """The experimental 'word of the day' payload (gated by the ``word_of_the_day`` flag).

    A placeholder shape for a not-yet-finished feature: it carries no user data and no secrets, so
    the route is safe to ship dark. When the flag is off the route 404s (as if absent); flipping the
    flag on exposes this payload.
    """

    word: str
    translation: str
    note: str
