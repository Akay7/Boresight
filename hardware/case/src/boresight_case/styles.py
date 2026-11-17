"""The skin styles and their parameters, without any geometry.

Each style declares its shape options here with a type, a default and a
range, so a configuration can be checked before any modelling starts.
The skins themselves (`boresight_case.skins`) read the checked values.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


class StyleParamError(ValueError):
    pass


@dataclass(frozen=True)
class StyleParam:
    name: str
    default: Any
    doc: str
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] | None = None

    @property
    def range_text(self) -> str:
        if self.choices is not None:
            return "one of " + ", ".join(repr(c) for c in self.choices)
        if isinstance(self.default, bool):
            return "true or false"
        return f"{self.minimum:g} to {self.maximum:g}"

    def check(self, value: Any) -> Any:
        """The value, or StyleParamError naming the parameter and range."""
        problem = f"style parameter {self.name!r} must be {self.range_text}"
        if self.choices is not None:
            if value not in self.choices:
                raise StyleParamError(f"{problem}, not {value!r}")
            return value
        if isinstance(self.default, bool):
            if not isinstance(value, bool):
                raise StyleParamError(f"{problem}, not {value!r}")
            return value
        # bool is an int; a number parameter never accepts one.
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise StyleParamError(f"{problem}, not {value!r}")
        assert self.minimum is not None and self.maximum is not None
        if not self.minimum <= value <= self.maximum:
            raise StyleParamError(f"{problem}, not {value!r}")
        return float(value)


# Every skin is 2.4 mm thick at its flank, so no chamfer may exceed that.
STYLE_PARAMS: dict[str, tuple[StyleParam, ...]] = {
    "minimal": (
        StyleParam(
            "shroud_length",
            0.0,
            "How far the barrel skins reach past the muzzle, in mm. The "
            "opening widens with the camera's view.",
            minimum=0.0,
            maximum=20.0,
        ),
        StyleParam(
            "chamfer",
            1.2,
            "The 45-degree chamfer on every outer edge, in mm.",
            minimum=0.4,
            maximum=2.0,
        ),
        StyleParam(
            "grip_texture",
            "grooves",
            "Grip flank texture: shallow horizontal grooves, or plain.",
            choices=("grooves", "none"),
        ),
    ),
    "blaster": (
        StyleParam(
            "shroud_length",
            16.0,
            "How far the flared muzzle shroud reaches past the muzzle, in mm.",
            minimum=6.0,
            maximum=30.0,
        ),
        StyleParam(
            "fin_height",
            7.0,
            "Height of the dorsal fin above the barrel, in mm. 0 removes it.",
            minimum=0.0,
            maximum=12.0,
        ),
        StyleParam(
            "chamfer",
            2.0,
            "The faceting chamfer on every outer edge, in mm.",
            minimum=1.0,
            maximum=2.2,
        ),
        StyleParam(
            "accents",
            True,
            "Separate accent parts (side stripes, muzzle ring) for a second "
            "filament colour.",
        ),
    ),
}

STYLES: tuple[str, ...] = tuple(STYLE_PARAMS)


def resolve_style_params(style: str, given: Mapping[str, Any]) -> dict[str, Any]:
    """Every parameter of `style`, checked, with defaults filled in."""
    params = {p.name: p for p in STYLE_PARAMS[style]}
    unknown = sorted(set(given) - set(params))
    if unknown:
        raise StyleParamError(
            f"style {style!r} has no parameter {unknown[0]!r}; it has "
            + ", ".join(sorted(params))
        )
    return {
        name: p.check(given[name]) if name in given else p.default
        for name, p in params.items()
    }
