"""Binary sensor platform for Backup NAS Sync."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SITE_NAME, DOMAIN, STATUS_ERROR
from .coordinator import BackupNasSyncCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: BackupNasSyncCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BackupNasSyncProblemBinarySensor(coordinator, entry)])


class BackupNasSyncProblemBinarySensor(
    CoordinatorEntity[BackupNasSyncCoordinator], BinarySensorEntity
):
    """ON si le dernier cycle de synchronisation a echoue."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_has_entity_name = True

    def __init__(self, coordinator: BackupNasSyncCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        site_name = entry.data[CONF_SITE_NAME]
        self._attr_unique_id = f"{entry.entry_id}_probleme"
        self._attr_name = f"Backup NAS Sync {site_name} - Probleme"

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data or {}
        return data.get("status") == STATUS_ERROR or (data.get("consecutive_failures") or 0) > 0
