"""Asset type categories and the names that map onto them.

An asset's `type` is one of a small fixed set of categories, so scoring,
filters and the dashboard stay consistent. Real inventories use many more
names (laptop, VM, Lambda, bucket...): those resolve to a category through an
alias list, and the original name is kept as the asset's `subtype`.

The alias list is layered like the Nessus domain map: built-in, then .env
additions, then the org's own (see org_settings.py), then a profile's own.
"""

import re

ASSET_TYPES = ("server", "workstation", "network_device", "database", "cloud_resource", "application")

BUILTIN_TYPE_ALIASES: dict[str, str] = {
    **dict.fromkeys(
        ("vm", "virtual machine", "instance", "ec2", "ec2 instance", "host", "physical server"), "server"
    ),
    **dict.fromkeys(("laptop", "desktop", "pc", "notebook", "endpoint", "mac", "macbook"), "workstation"),
    **dict.fromkeys(
        ("router", "switch", "firewall", "load balancer", "access point", "gateway", "vpn gateway"),
        "network_device",
    ),
    **dict.fromkeys(("db", "rds", "sql database", "dynamodb", "cosmos db"), "database"),
    **dict.fromkeys(
        (
            "lambda", "function", "cloud function", "azure function",
            "bucket", "s3", "s3 bucket", "storage", "storage account", "blob", "volume", "ebs", "disk",
            "container", "kubernetes", "k8s", "vpc", "queue",
        ),
        "cloud_resource",
    ),
    **dict.fromkeys(("app", "web app", "saas", "website", "api"), "application"),
}


def normalize_type_name(name: str) -> str:
    """Case, spacing, '-' and '_' don't matter: "Virtual_Machine" == "virtual machine"."""
    return re.sub(r"[\s_-]+", " ", name).strip().lower()


_CANONICAL = {normalize_type_name(t): t for t in ASSET_TYPES}


def resolve_asset_type(raw: str, aliases: dict[str, str]) -> tuple[str, str | None]:
    """(category, subtype). A category name passes through with no subtype; an
    alias resolves to its category with the original name as the subtype.
    Raises ValueError listing the accepted values otherwise."""
    name = raw.strip()
    key = normalize_type_name(name)
    if key in _CANONICAL:
        return _CANONICAL[key], None
    lookup = {normalize_type_name(alias): target for alias, target in aliases.items()}
    if key in lookup:
        return lookup[key], name
    raise ValueError(
        f"type {name!r} must be one of: {', '.join(ASSET_TYPES)}, or a known name for one "
        "(see Settings > Asset type names)"
    )


def check_alias_targets(aliases: dict[str, str]) -> dict[str, str]:
    """Validate an alias map (for settings/profile schemas): every target must
    be a category, and names can't be blank."""
    for alias, target in aliases.items():
        if not alias.strip():
            raise ValueError("type names can't be blank")
        if target not in ASSET_TYPES:
            raise ValueError(f"{alias!r} maps to {target!r}, which must be one of: {', '.join(ASSET_TYPES)}")
    return aliases
