"""设备追踪器：车辆 GPS 位置（经纬度 iid 13.1.9/13.1.10）→ 地图显示。

坐标直接使用 API 返回值，不做转换（API 返回标准 WGS-84 坐标）。
"""
from __future__ import annotations

import logging

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MicarDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

LATITUDE_IID = "13.1.10"
LONGITUDE_IID = "13.1.9"


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: MicarDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MicarDeviceTracker(coordinator)])


class MicarDeviceTracker(CoordinatorEntity, TrackerEntity):
    def __init__(self, coordinator: MicarDataUpdateCoordinator):
        super().__init__(coordinator)
        self._attr_name = "车辆位置"
        self._attr_unique_id = "micar_base_tracker_location"
        from .const import icon_for_name
        self._attr_icon = icon_for_name("车辆位置")

        self._attr_has_entity_name = True

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        val = self.coordinator.properties.get(LATITUDE_IID)
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def longitude(self) -> float | None:
        val = self.coordinator.properties.get(LONGITUDE_IID)
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, "car")}, "name": "小米汽车", "manufacturer": "Xiaomi", "model": "SU7"}
