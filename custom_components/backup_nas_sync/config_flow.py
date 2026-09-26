"""Config flow for Backup NAS Sync."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    AUTH_KEY_FILE,
    AUTH_PASSWORD,
    CONF_AUTH_METHOD,
    CONF_ENVIRONMENT,
    CONF_HOST,
    CONF_KEY_FILE,
    CONF_LOCAL_BACKUP_DIR,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_POLL_INTERVAL,
    CONF_REMOTE_BASE_DIR,
    CONF_RETENTION_COUNT,
    CONF_STABLE_SECONDS,
    CONF_USERNAME,
    DEFAULT_LOCAL_BACKUP_DIR,
    DEFAULT_PORT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_REMOTE_BASE_DIR,
    DEFAULT_RETENTION_COUNT,
    DEFAULT_STABLE_SECONDS,
    DOMAIN,
    ENVIRONMENTS,
)

_LOGGER = logging.getLogger(__name__)


class CannotConnect(HomeAssistantError):
    """Erreur de connexion SSH au NAS lors du test du config_flow."""


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_ENVIRONMENT, default=defaults.get(CONF_ENVIRONMENT, ENVIRONMENTS[0])): vol.In(
                ENVIRONMENTS
            ),
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): int,
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
            vol.Required(
                CONF_AUTH_METHOD, default=defaults.get(CONF_AUTH_METHOD, AUTH_PASSWORD)
            ): vol.In([AUTH_PASSWORD, AUTH_KEY_FILE]),
            vol.Optional(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): str,
            vol.Optional(CONF_KEY_FILE, default=defaults.get(CONF_KEY_FILE, "")): str,
            vol.Optional(
                CONF_REMOTE_BASE_DIR, default=defaults.get(CONF_REMOTE_BASE_DIR, DEFAULT_REMOTE_BASE_DIR)
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


def _test_connection(data: dict[str, Any]) -> None:
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=data[CONF_HOST],
            port=data.get(CONF_PORT, DEFAULT_PORT),
            username=data[CONF_USERNAME],
            password=data.get(CONF_PASSWORD) if data.get(CONF_AUTH_METHOD) == AUTH_PASSWORD else None,
            key_filename=data.get(CONF_KEY_FILE) if data.get(CONF_AUTH_METHOD) == AUTH_KEY_FILE else None,
            timeout=15,
        )
    except Exception as err:  # noqa: BLE001
        raise CannotConnect(str(err)) from err
    finally:
        client.close()


class BackupNasSyncConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Backup NAS Sync."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_ENVIRONMENT])
            self._abort_if_unique_id_configured()

            try:
                await self.hass.async_add_executor_job(_test_connection, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"Backup NAS Sync - {user_input[CONF_ENVIRONMENT]}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input),
            errors=errors,
        )
