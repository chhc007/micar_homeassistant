"""设备追踪器：车辆 GPS 位置（经纬度 13.1.9/13.1.10）→ 地图显示。

坐标自动识别：API 返回 coordinateType(13.1.8) 指示坐标系，
  0=STANDARD（标准/WGS-84 可用）→ 直接用
  1=BAIDU（百度 BD-09）→ 转 WGS-84
  2=AMAP（高德 GCJ-02）→ 转 WGS-84
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
COORD_TYPE_IID = "13.1.8"

# CoordinateType 枚举（反编译 CoordinateType.java 确认）：0=STANDARD 1=BAIDU 2=AMAP
COORD_STANDARD = 0
COORD_BAIDU = 1
COORD_AMAP = 2

_A = 6378245.0  # 克拉索夫斯基椭球长半轴
_EE = 0.00669342162296594323  # 偏心率平方


def _out_of_china(lat: float, lng: float) -> bool:
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def gcj02_to_wgs84(lat: float, lng: float) -> tuple[float, float]:
    """GCJ-02（火星坐标）→ WGS-84。"""
    if _out_of_china(lat, lng):
        return lat, lng
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - _EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (_A / sqrtmagic * math.cos(radlat) * math.pi)
    return lat * 2 - (lat + dlat), lng * 2 - (lng + dlng)


def bd09_to_gcj02(lat: float, lng: float) -> tuple[float, float]:
    """BD-09（百度）→ GCJ-02。"""
    x = lng - 0.0065
    y = lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * math.pi * 3000.0 / 180.0)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * math.pi * 3000.0 / 180.0)
    return z * math.sin(theta), z * math.cos(theta)


def bd09_to_wgs84(lat: float, lng: float) -> tuple[float, float]:
    """BD-09（百度）→ WGS-84（经 GCJ-02 中转）。"""
    gcj_lat, gcj_lng = bd09_to_gcj02(lat, lng)
    return gcj02_to_wgs84(gcj_lat, gcj_lng)


def coord_to_wgs84(lat: float, lng: float, coord_type) -> tuple[float, float]:
    """按 coordinateType 把坐标统一到 WGS-84。0=标准直接用；1=百度转；2=高德转。"""
    try:
        ct = int(coord_type)
    except (TypeError, ValueError):
        ct = COORD_STANDARD  # 未知类型默认标准（不转换）
    if ct == COORD_BAIDU:
        return bd09_to_wgs84(lat, lng)
    if ct == COORD_AMAP:
        return gcj02_to_wgs84(lat, lng)
    return lat, lng


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
    def _wgs84(self) -> tuple[float, float] | None:
        """返回统一后的 WGS-84 坐标（按 coordinateType 自动转换）。"""
        lat_val = self.coordinator.properties.get(LATITUDE_IID)
        lng_val = self.coordinator.properties.get(LONGITUDE_IID)
        coord_type = self.coordinator.properties.get(COORD_TYPE_IID)
        try:
            lat = float(lat_val) if lat_val is not None else None
            lng = float(lng_val) if lng_val is not None else None
        except (TypeError, ValueError):
            return None
        if lat is None or lng is None:
            return None
        return coord_to_wgs84(lat, lng, coord_type)

    @property
    def latitude(self) -> float | None:
        pos = self._wgs84
        return pos[0] if pos else None

    @property
    def longitude(self) -> float | None:
        pos = self._wgs84
        return pos[1] if pos else None

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, "car")}, "name": "小米汽车", "manufacturer": "Xiaomi", "model": "SU7"}
