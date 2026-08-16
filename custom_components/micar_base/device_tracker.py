"""设备追踪器：车辆 GPS 位置（经纬度 iid 13.1.9/13.1.10）→ 地图显示。

坐标按 coordinateType（13.1.8）条件转换：
  - =2 时为高德 GCJ-02 加密坐标 → 转 WGS-84；
  - =0 / None / 未知 → 原样返回（API 即为 WGS-84）。
统一输出 WGS-84，避免 coordinateType 跳变（0↔2）导致位置漂移/历史折线。
"""
from __future__ import annotations

import logging
import math

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MicarDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

LATITUDE_IID = "13.1.10"
LONGITUDE_IID = "13.1.9"
COORDINATE_TYPE_IID = "13.1.8"

# Krasovsky 1940 椭球参数（GCJ-02 → WGS-84 逆变换）
_AXIS = 6378245.0
_OFFSET = 0.00669342162296594323


def _out_of_china(lat: float, lng: float) -> bool:
    """境外坐标不参与 GCJ-02 偏移（无需转换）。"""
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320.0 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def _gcj02_to_wgs84(lat: float, lng: float) -> tuple[float, float]:
    """GCJ-02（高德/火星坐标）→ WGS-84 标准坐标（标准近似逆变换）。"""
    if _out_of_china(lat, lng):
        return lat, lng
    d_lat = _transform_lat(lng - 105.0, lat - 35.0)
    d_lng = _transform_lng(lng - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * math.pi
    magic = math.sin(rad_lat)
    magic = 1.0 - _OFFSET * magic * magic
    sqrt_magic = math.sqrt(magic)
    d_lat = (d_lat * 180.0) / ((_AXIS * (1.0 - _OFFSET)) / (magic * sqrt_magic) * math.pi)
    d_lng = (d_lng * 180.0) / (_AXIS / sqrt_magic * math.cos(rad_lat) * math.pi)
    return lat - d_lat, lng - d_lng


def _to_float(val):
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _conditional_coords(properties: dict) -> tuple[float | None, float | None]:
    """读取原始经纬度，按 coordinateType 条件转换，返回统一 WGS-84 的 (lat, lng)。"""
    lat = _to_float(properties.get(LATITUDE_IID))
    lng = _to_float(properties.get(LONGITUDE_IID))
    coord_type = _to_float(properties.get(COORDINATE_TYPE_IID))
    coord_type = int(coord_type) if coord_type is not None else None
    # coordinateType == 2（高德 GCJ-02）才转换；0/None/未知一律原样
    if coord_type == 2 and lat is not None and lng is not None:
        lat, lng = _gcj02_to_wgs84(lat, lng)
    return lat, lng


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: MicarDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MicarDeviceTracker(coordinator)])


class MicarDeviceTracker(CoordinatorEntity, TrackerEntity):
    def __init__(self, coordinator: MicarDataUpdateCoordinator):
        super().__init__(coordinator)
        # has_entity_name：设备名（小米汽车 + 车牌）自动拼接，实体名保持简短
        self._attr_name = "车辆位置"
        self._attr_unique_id = f"micar_base_tracker_location{coordinator.uid_suffix}"
        from .const import icon_for_name
        self._attr_icon = icon_for_name("车辆位置")

        self._attr_has_entity_name = True

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        return _conditional_coords(self.coordinator.properties)[0]

    @property
    def longitude(self) -> float | None:
        return _conditional_coords(self.coordinator.properties)[1]

    @property
    def device_info(self):
        return self.coordinator.device_info
