"""设备追踪器：车辆 GPS 位置（经纬度 iid 13.1.9/13.1.10）→ 地图显示。

⚠️ 不进行任何坐标转换（2026-08-14 最终结论）：
  - API 返回的就是 WGS-84 标准坐标（f1fe468 实测：OSM 反查与 API 地址同区域）
  - coordinateType(13.1.8) 不可信：实测频繁在 0(STANDARD)/2(AMAP) 之间跳变（20-40分钟一次），
    按它做 GCJ-02→WGS-84 转换会把正确位置推偏 ~470m，导致地图历史轨迹出现锯齿折线
    （2026-08-14 用户在地图上发现 12:54:45 错点，偏移量与 470m 量级一致）
  - 历史教训：加转换（错）→ 移除（对）→ 按 coordinateType 自动转换（错，已回退）
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
