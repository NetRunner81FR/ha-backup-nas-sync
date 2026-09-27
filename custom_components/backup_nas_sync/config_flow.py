"""Config flow for Backup NAS Sync.

Ne demande jamais d'identifiants NAS : reutilise la connexion DSM deja
authentifiee d'une entree ``synology_dsm`` existante (meme compte que
celui deja configure pour la surveillance NAS), pour une installation
simple et identique sur toutes les instances Home Assistant qui
partagent le meme NAS distant.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState

from .const import (
    CONF_LOCAL_BACKUP_DIR,
    CONF_POLL_INTERVAL,
    CONF_REMOTE_BASE_DIR,
    CONF_RETENTION_COUNT,
    CONF_SITE_NAME,
    CONF_STABLE_SECONDS,
    CONF_SYNOLOGY_ENTRY_ID,
    DEFAULT_LOCAL_BACKUP_DIR,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_RETENTION_COUNT,
    DEFAULT_STABLE_SECONDS,
    DOMAIN,
    SYNOLOGY_DSM_DOMAIN,
)


def _schema(synology_entries: dict[str, str], defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_SYNOLOGY_ENTRY_ID, default=defaults.get(CONF_SYNOLOGY_ENTRY_ID)
            ): vol.In(synology_entries),
            vol.Required(CONF_SITE_NAME, default=defaults.get(CONF_SITE_NAME, "")): str,
            vol.Required(
                CONF_REMOTE_BASE_DIR, default=defaults.get(CONF_REMOTE_BASE_DIR, "")
            ): str,
            vol.Optional(
                CONF_LOCAL_BACKUP_DIR, default=defaults.get(CONF_LOCAL_BACKUP_DIR, DEFAULT_LOCAL_BACKUP_DIR)
            ): str,
            vol.Optional(
                CONF_POLL_INTERVAL, default=defaults.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            ): int,
            vol.Optional(
                CONF_RETENTION_COUNT, default=defaults.get(CONF_RETENTION_COUNT, DEFAULT_RETENTION_COUNT)
            ): int,
            vol.Optional(
                CONF_STABLE_SECONDS, default=defaults.get(CONF_STABLE_SECONDS, DEFAULT_STABLE_SECONDS)
            ): int,
        }
    )


class BackupNasSyncConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Backup NAS Sync."""

    VERSION = 1

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
            if not site_name:
                errors["base"] = "invalid_site_name"
            elif not remote_dir.startswith("/"):
                errors["base"] = "invalid_remote_dir"
            else:
                user_input[CONF_SITE_NAME] = site_name
                user_input[CONF_REMOTE_BASE_DIR] = remote_dir
                await self.async_set_unique_id(site_name)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Backup NAS Sync - {site_name}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(synology_entries, user_input),
            errors=errors,
        )
