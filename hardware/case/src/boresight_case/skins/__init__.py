"""The skin styles. Each style module draws its outlines; `base` turns them
into printable halves that attach to the core."""

from __future__ import annotations

from functools import cache

from boresight_case.config import Config
from boresight_case.interfaces import Fit
from boresight_case.model import Module
from boresight_case.skins import blaster, minimal
from boresight_case.skins.base import build_style, placed

STYLE_MODULES = {"minimal": minimal, "blaster": blaster}


@cache
def _skins(style: str, params, fit: Fit) -> Module:
    drawing = STYLE_MODULES[style].style(params, fit)
    return build_style(style, drawing, fit)


def skin_module(cfg: Config) -> Module:
    """The skins of `cfg`'s style. They do not depend on the board kit,
    drawer or switch plate: one set fits every configuration."""
    return placed(_skins(cfg.style, cfg.style_params, Fit.of(cfg.printer)), cfg.barrels)
