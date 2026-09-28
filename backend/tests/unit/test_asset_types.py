import pytest

from app.services.asset_types import (
    ASSET_TYPES,
    BUILTIN_TYPE_ALIASES,
    check_alias_targets,
    normalize_type_name,
    resolve_asset_type,
)


@pytest.mark.parametrize("raw", ["server", "Server", " SERVER ", "network_device", "Network Device", "network-device"])
def test_categories_pass_through_without_a_subtype(raw):
    expected = "network_device" if "network" in raw.lower() else "server"
    assert resolve_asset_type(raw, {}) == (expected, None)


@pytest.mark.parametrize(
    "raw, category",
    [
        ("laptop", "workstation"),
        ("Laptop", "workstation"),
        ("VM", "server"),
        ("Virtual Machine", "server"),
        ("virtual_machine", "server"),
        ("Lambda", "cloud_resource"),
        ("Bucket", "cloud_resource"),
        ("Storage", "cloud_resource"),
        ("rds", "database"),
        ("Router", "network_device"),
        ("Firewall", "network_device"),
        ("SaaS", "application"),
    ],
)
def test_builtin_names_resolve_and_keep_the_original_as_subtype(raw, category):
    assert resolve_asset_type(raw, BUILTIN_TYPE_ALIASES) == (category, raw)


def test_database_is_a_category_itself():
    assert resolve_asset_type("Database", BUILTIN_TYPE_ALIASES) == ("database", None)


def test_unknown_type_lists_the_accepted_values():
    with pytest.raises(ValueError) as exc:
        resolve_asset_type("Hologram", BUILTIN_TYPE_ALIASES)
    message = str(exc.value)
    assert message.startswith("type 'Hologram' must be one of: ")
    for category in ASSET_TYPES:
        assert category in message


def test_extra_aliases_are_matched_the_same_loose_way():
    assert resolve_asset_type("Hyper-V Host", {"hyper v host": "server"}) == ("server", "Hyper-V Host")


def test_normalize_type_name():
    assert normalize_type_name("  Virtual__Machine - X ") == "virtual machine x"


def test_every_builtin_alias_targets_a_category():
    assert set(BUILTIN_TYPE_ALIASES.values()) <= set(ASSET_TYPES)
    assert check_alias_targets(BUILTIN_TYPE_ALIASES) == BUILTIN_TYPE_ALIASES


@pytest.mark.parametrize(
    "aliases, message",
    [({"pc": "desk"}, "must be one of"), ({" ": "server"}, "can't be blank")],
)
def test_check_alias_targets_rejects_bad_maps(aliases, message):
    with pytest.raises(ValueError, match=message):
        check_alias_targets(aliases)
