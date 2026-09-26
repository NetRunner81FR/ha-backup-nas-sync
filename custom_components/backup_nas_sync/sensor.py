"""Sensor platform for Backup NAS Sync."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENVIRONMENT, DOMAIN
from .coordinator import BackupNasSyncCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: BackupNasSyncCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BackupNasSyncStatusSensor(coordinator, entry)])


class BackupNasSyncStatusSensor(CoordinatorEntity[BackupNasSyncCoordinator], SensorEntity):
    """Statut du dernier controle de synchronisation vers le NAS."""

    _attr_icon = "mdi:nas"
    _attr_has_entity_name = True
    _attr_translation_key = "dernier_controle"

    def __init__(self, coordinator: BackupNasSyncCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        environment = entry.data[CONF_ENVIRONMENT]
        self._attr_unique_id = f"{entry.entry_id}_dernier_controle"
        self._attr_name = f"Backup NAS Sync {environment} - Dernier controle"

    @property
    def native_value(self) -> str | None:
        return (self.coordinator.data or {}).get("last_checked")

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data or {}
        return {
            "resultat": data.get("status"),
            "backup_name": data.get("backup_name"),
            "checksum_source": data.get("checksum_source"),
            "checksum_nas": data.get("checksum_nas"),
            "echecs_consecutifs": data.get("consecutive_failures"),
            "erreur": data.get("error"),
        }
