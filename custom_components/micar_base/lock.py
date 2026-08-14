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
        # 实体名带车牌后缀（多车不重名）；旧条目无车牌 → 原名不变
        self._attr_name = f"车门锁 {coordinator.plate_suffix}".strip()
        self._attr_unique_id = f"micar_base_lock_doors{coordinator.uid_suffix}"
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
        # 控制后确认生效（服务端状态同步延迟，连续刷新避免 UI 显示旧状态）
        await self.coordinator.async_confirm_control(LOCK_IID, {float(LOCKED_VALUE)})

    async def async_unlock(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(self.coordinator.api.control, LOCK_IID, UNLOCKED_VALUE)
        await self.coordinator.async_confirm_control(LOCK_IID, {float(UNLOCKED_VALUE)})

    @property
    def device_info(self):
        return self.coordinator.device_info
