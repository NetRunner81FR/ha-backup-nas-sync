"""Push-only diagnostics shared by entities and the native backup agent."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.backup import BackupAgentError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_REMOTE_BASE_DIR, CONF_RETENTION_COUNT, CONF_SYNOLOGY_ENTRY_ID,
    DEFAULT_RETENTION_COUNT, DOMAIN, NOTIFY_CATEGORY,
    NOTIFY_DOMAIN, NOTIFY_MODULE, NOTIFY_ROLES, NOTIFY_SERVICE,
    STATUS_ERROR, STATUS_IDLE, STATUS_OK,
)

_LOGGER = logging.getLogger(__name__)


def normalize_retention(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_RETENTION_COUNT
    return max(1, value)


class BackupNasSyncCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """No interval, no filesystem scan; updated by verified agent operations."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self.entry = entry
        self.lock = asyncio.Lock()
        self._store = Store(hass, 1, f"{DOMAIN}_agent_state_{entry.entry_id}")
        from .backup import BackupNasSyncAgent
        self.agent = BackupNasSyncAgent(self)

    @property
    def remote_dir(self) -> str:
        return self.entry.data[CONF_REMOTE_BASE_DIR].rstrip("/")

    @property
    def retention_count(self) -> int:
        return normalize_retention(self.entry.data.get(CONF_RETENTION_COUNT, DEFAULT_RETENTION_COUNT))

    @property
    def file_station(self):
        entry = self.hass.config_entries.async_get_entry(self.entry.data[CONF_SYNOLOGY_ENTRY_ID])
        if entry is None or entry.state != ConfigEntryState.LOADED:
            raise BackupAgentError("Intégration Synology DSM indisponible")
        try:
            api = entry.runtime_data.api.file_station
        except AttributeError as err:
            raise BackupAgentError("Version Synology DSM incompatible") from err
        if api is None:
            raise BackupAgentError("FileStation indisponible")
        return api

    async def async_initialize(self) -> None:
        stored = await self._store.async_load()
        self.async_set_updated_data(stored or {"status": STATUS_IDLE, "consecutive_failures": 0})

    async def async_record_result(
        self, *, backup_name: str, checksum_source: str | None = None,
        checksum_nas: str | None = None, error: str | None = None,
        retention_warning: str | None = None,
    ) -> None:
        previous = self.data or {}
        problem_before = bool(previous.get("error") or previous.get("retention_warning"))
        data = {
            "status": STATUS_ERROR if error else STATUS_OK,
            "last_checked": dt_util.utcnow().isoformat(), "backup_name": backup_name,
            "checksum_source": checksum_source, "checksum_nas": checksum_nas,
            "consecutive_failures": previous.get("consecutive_failures", 0) + 1 if error else 0,
            "error": error, "retention_warning": retention_warning,
        }
        self.async_set_updated_data(data)
        await self._store.async_save(data)
        problem = bool(error or retention_warning)
        if problem == problem_before or not self.hass.services.has_service(NOTIFY_DOMAIN, NOTIFY_SERVICE):
            return
        await self.hass.services.async_call(
            NOTIFY_DOMAIN, NOTIFY_SERVICE,
            {"title": "Backup NAS Sync - anomalie" if problem else "Backup NAS Sync - retour à la normale",
             "message": error or retention_warning or "Le transfert NAS est de nouveau vérifié.",
             "category": NOTIFY_CATEGORY, "roles": NOTIFY_ROLES, "module": NOTIFY_MODULE},
            blocking=True,
        )
