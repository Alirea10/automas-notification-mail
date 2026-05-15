from __future__ import annotations

from functools import lru_cache
from typing import Any

from jinja2 import Environment, PackageLoader


@lru_cache(maxsize=1)
def _get_environment() -> Environment:
    return Environment(loader=PackageLoader("notification_mail", "templates"))


def render_template(template_name: str, context: dict[str, Any] | None = None) -> str:
    template = _get_environment().get_template(template_name)
    return template.render(**(context or {}))
