"""Custom requirements must coexist with the host's package constraints."""

import json
from pathlib import Path

from homeassistant.requirements import pip_kwargs
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def test_runtime_dependencies_accept_home_assistant_constraints():
    """Catch pins that work preinstalled but fail during a fresh HA install."""
    constraints = {}
    for line in Path(pip_kwargs(None)["constraints"]).read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            requirement = Requirement(line)
            constraints[canonicalize_name(requirement.name)] = requirement

    manifest = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "custom_components/overhead/manifest.json"
        ).read_text()
    )
    for text in manifest["requirements"]:
        requirement = Requirement(text)
        host = constraints.get(canonicalize_name(requirement.name))
        if host is None:
            continue
        for specifier in host.specifier:
            if specifier.operator == "==" and "*" not in specifier.version:
                assert specifier.version in requirement.specifier, (
                    f"{requirement} conflicts with Home Assistant's {host}"
                )
