from typing import Any

from pydantic import BaseModel

from app.services.security_policy import SecuritySettings


class SecuritySettingsRead(BaseModel):
    """One layer of the security settings: platform defaults, or an org's."""

    # The settings in effect at this layer.
    values: SecuritySettings
    # The ones this layer changes; the rest follow the layer below.
    changed: list[str]
    # The layer below: the built-in values under the platform defaults, the
    # platform defaults under an org's.
    below: SecuritySettings


# PATCH: setting -> value, or null to follow the layer below again; settings
# left out are unchanged.
SecuritySettingsUpdate = dict[str, Any]
