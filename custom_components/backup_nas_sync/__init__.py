"""Backup NAS Sync - surcouche fiable de copie/controle des sauvegardes HA vers NAS.

Contourne l'integration native HA Backup "NAS Synology" (source
confirmee de corruption des copies, cf. issue #161) : s'appuie sur les
backups locaux natifs (sains) et gere son propre transfert SSH/SFTP
avec verification checksum SHA-256.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN, PLATFORMS
from .coordinator import BackupNasSyncCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_SYNC_NOW = "sync_now"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = BackupNasSyncCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _handle_sync_now(call: ServiceCall) -> None:
        await coordinator.async_force_sync()

    if not hass.services.has_service(DOMAIN, SERVICE_SYNC_NOW):
        hass.services.async_register(DOMAIN, SERVICE_SYNC_NOW, _handle_sync_now)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SYNC_NOW)
    return unloaded
