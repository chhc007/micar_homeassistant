"""门锁实体：车门锁（2.1.3，DoorLockStatus 1=解锁 2=锁定）。"""
from __future__ import annotations

import logging

from homeassistant.components.lock import LockEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MicarDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

LOCK_IID = "2.1.3"
LOCKED_VALUE = 2
UNLOCKED_VALUE = 1


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: MicarDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MicarLock(coordinator)])


class MicarLock(CoordinatorEntity, LockEntity):
    def __init__(self, coordinator: MicarDataUpdateCoordinator):
        super().__init__(coordinator)
        self._attr_name = "车门锁"
        self._attr_unique_id = "micar_base_lock_doors"
        from .const import icon_for_name
        self._attr_icon = icon_for_name("车门锁")

    @property
    def is_locked(self) -> bool | None:
        val = self.coordinator.properties.get(LOCK_IID)
        if val is None:
            return None
        return int(val) == LOCKED_VALUE

    async def async_lock(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(self.coordinator.api.control, LOCK_IID, LOCKED_VALUE)
        await self.coordinator.async_request_refresh()

    async def async_unlock(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(self.coordinator.api.control, LOCK_IID, UNLOCKED_VALUE)
        await self.coordinator.async_request_refresh()

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, "car")}, "name": "小米汽车", "manufacturer": "Xiaomi", "model": "SU7"}
