"""Native backup destination reusing an authenticated Synology DSM entry."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from awesomeversion import AwesomeVersion

from .const import DOMAIN, PLATFORMS, DATA_AGENT_LISTENERS, CONF_RETENTION_COUNT, DEFAULT_RETENTION_COUNT
from .coordinator import BackupNasSyncCoordinator, normalize_retention

MIN_HA_VERSION = "2026.9.3"
_OBSOLETE = {"local_backup_dir", "poll_interval", "stable_seconds"}


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove polling options without changing NAS identity or native HA settings."""
    if entry.version > 2:
        return False
    if entry.version == 1:
        data = {key: value for key, value in entry.data.items() if key not in _OBSOLETE}
        options = {key: value for key, value in entry.options.items() if key not in _OBSOLETE}
        data[CONF_RETENTION_COUNT] = normalize_retention(data.get(CONF_RETENTION_COUNT, DEFAULT_RETENTION_COUNT))
        hass.config_entries.async_update_entry(entry, data=data, options=options, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if AwesomeVersion(HA_VERSION) < AwesomeVersion(MIN_HA_VERSION):
        raise ConfigEntryError(f"Home Assistant {MIN_HA_VERSION} minimum requis")
    coordinator = BackupNasSyncCoordinator(hass, entry)
    await coordinator.async_initialize()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    @callback
    def notify_listeners() -> None:
        for listener in tuple(hass.data.get(DATA_AGENT_LISTENERS, [])):
            listener()

    entry.async_on_unload(entry.async_on_state_change(notify_listeners))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        for listener in tuple(hass.data.get(DATA_AGENT_LISTENERS, [])):
            listener()
    return unloaded
