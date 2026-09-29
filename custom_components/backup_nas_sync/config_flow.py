"""Config flow for Backup NAS Sync.

Ne demande jamais d'identifiants NAS : reutilise la connexion DSM deja
authentifiee d'une entree ``synology_dsm`` existante (meme compte que
celui deja configure pour la surveillance NAS), pour une installation
simple et identique sur toutes les instances Home Assistant qui
partagent le meme NAS distant.
"""
from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState

from .const import (
    CONF_REMOTE_BASE_DIR,
    CONF_RETENTION_COUNT,
    CONF_SITE_NAME,
    CONF_SYNOLOGY_ENTRY_ID,
    DEFAULT_RETENTION_COUNT,
    DOMAIN,
    SYNOLOGY_DSM_DOMAIN,
)


def _schema(
    synology_entries: dict[str, str],
    defaults: dict[str, Any] | None = None,
    *,
    include_site_name: bool = True,
) -> vol.Schema:
    defaults = defaults or {}
    schema: dict[Any, Any] = {
        vol.Required(
            CONF_SYNOLOGY_ENTRY_ID, default=defaults.get(CONF_SYNOLOGY_ENTRY_ID)
        ): vol.In(synology_entries),
    }
    if include_site_name:
        schema[vol.Required(CONF_SITE_NAME, default=defaults.get(CONF_SITE_NAME, ""))] = str
    schema.update(
        {
            vol.Required(
                CONF_REMOTE_BASE_DIR, default=defaults.get(CONF_REMOTE_BASE_DIR, "")
            ): str,
            vol.Optional(
                CONF_RETENTION_COUNT, default=defaults.get(CONF_RETENTION_COUNT, DEFAULT_RETENTION_COUNT)
            ): vol.All(vol.Coerce(int), vol.Range(min=1)),
        }
    )
    return vol.Schema(schema)


def _validate_remote_dir(remote_dir: str) -> str | None:
    """Return an error key, or None if the remote dir is valid."""
    if (not remote_dir.startswith("/") or remote_dir == "/"
            or any(part in {".", ".."} for part in remote_dir.split("/"))
            or "\\" in remote_dir or any(ord(c) < 32 for c in remote_dir)):
        return "invalid_remote_dir"
    if re.match(r"^/volume\d+(/|$)", remote_dir):
        # Erreur constatee en usage reel : un chemin systeme de fichiers
        # (/volumeN/...) n'est pas un chemin FileStation valide - le
        # dossier partage est adresse par son nom.
        return "remote_dir_has_volume_prefix"
    return None


class BackupNasSyncConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Backup NAS Sync."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        synology_entries = {
            entry.entry_id: entry.title
            for entry in self.hass.config_entries.async_entries(SYNOLOGY_DSM_DOMAIN)
            if entry.state == ConfigEntryState.LOADED
        }

        if not synology_entries:
            return self.async_abort(reason="no_synology_dsm")

        errors: dict[str, str] = {}

        if user_input is not None:
            site_name = user_input[CONF_SITE_NAME].strip()
            remote_dir = user_input[CONF_REMOTE_BASE_DIR].strip()
            error = None
            if not site_name:
                error = "invalid_site_name"
            else:
                error = _validate_remote_dir(remote_dir)
            if error:
                errors["base"] = error
            else:
                user_input[CONF_SITE_NAME] = site_name
                user_input[CONF_REMOTE_BASE_DIR] = remote_dir
                await self.async_set_unique_id(site_name)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"NR Backup NAS Sync - {site_name}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(synology_entries, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Let the user edit an existing entry's settings (except site_name,
        which doubles as the entry's unique_id - renaming a site remains a
        delete/recreate operation, out of scope here)."""
        reconfigure_entry = self._get_reconfigure_entry()
        synology_entries = {
            entry.entry_id: entry.title
            for entry in self.hass.config_entries.async_entries(SYNOLOGY_DSM_DOMAIN)
            if entry.state == ConfigEntryState.LOADED
        }

        if not synology_entries:
            return self.async_abort(reason="no_synology_dsm")

        errors: dict[str, str] = {}

        if user_input is not None:
            remote_dir = user_input[CONF_REMOTE_BASE_DIR].strip()
            error = _validate_remote_dir(remote_dir)
            if error:
                errors["base"] = error
            else:
                user_input[CONF_REMOTE_BASE_DIR] = remote_dir
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data={**reconfigure_entry.data, **user_input},
                )

        defaults = {**reconfigure_entry.data, **(user_input or {})}
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(synology_entries, defaults, include_site_name=False),
            errors=errors,
            description_placeholders={CONF_SITE_NAME: reconfigure_entry.data[CONF_SITE_NAME]},
        )
