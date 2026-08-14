"""只读传感器：电量、续航、里程、档位、胎压、车窗、远程启动状态/时间、车位号（Free 版核心状态）。"""
from __future__ import annotations

import datetime
import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfPressure
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SENSOR_VALUE_MAPS
from .coordinator import MicarDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# (iid, key, 显示名, device_class, unit)
FREE_SENSORS = [
    ("4.4.1", "battery", "电量", SensorDeviceClass.BATTERY, PERCENTAGE),
    ("4.4.3", "range", "剩余续航", SensorDeviceClass.DISTANCE, UnitOfLength.KILOMETERS),
    ("13.2.1", "mileage", "累计里程", SensorDeviceClass.DISTANCE, UnitOfLength.KILOMETERS),
    ("13.6.1", "gear", "档位", None, None),
    ("9.1.1", "tire_fl", "主驾胎压", SensorDeviceClass.PRESSURE, UnitOfPressure.BAR),
    ("9.2.1", "tire_fr", "副驾胎压", SensorDeviceClass.PRESSURE, UnitOfPressure.BAR),
    ("9.3.1", "tire_rl", "左后胎压", SensorDeviceClass.PRESSURE, UnitOfPressure.BAR),
    ("9.4.1", "tire_rr", "右后胎压", SensorDeviceClass.PRESSURE, UnitOfPressure.BAR),
    ("5.1.1", "window_fl", "主驾车窗", None, PERCENTAGE),
    ("5.2.1", "window_fr", "副驾车窗", None, PERCENTAGE),
    ("5.3.1", "window_rl", "左后车窗", None, PERCENTAGE),
    ("5.4.1", "window_rr", "右后车窗", None, PERCENTAGE),
    ("13.11.4", "remote_boot_status", "远程启动状态", None, None),
    ("13.11.5", "start_last_time", "最近启动时间", None, None),
]


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: MicarDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [MicarSensor(coordinator, iid, key, name, dev_cls, unit)
                for iid, key, name, dev_cls, unit in FREE_SENSORS]
    # 车位号（独立端点 parking-spot/query，coordinator.parking_spot 轮询更新）
    entities.append(MicarParkingSpotSensor(coordinator))
    async_add_entities(entities)


class MicarSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator: MicarDataUpdateCoordinator, iid: str, key: str,
                 name: str, dev_cls, unit):
        super().__init__(coordinator)
        self._iid = iid
        self._attr_name = name
        self._attr_unique_id = f"micar_base_sensor_{key}"
        self._attr_device_class = dev_cls
        self._attr_native_unit_of_measurement = unit
        from .const import icon_for_name
        self._attr_icon = icon_for_name(name)

    @property
    def native_value(self):
        val = self.coordinator.properties.get(self._iid)
        # 13.11.5 startLastTime = 毫秒时间戳 → 可读时间
        if val is not None and self._iid == "13.11.5":
            try:
                return datetime.datetime.fromtimestamp(int(float(val)) / 1000).strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError, OSError):
                return val
        # 枚举值域映射（如档位 0/1/2/3 → P/R/N/D）
        if val is not None and self._iid in SENSOR_VALUE_MAPS:
            try:
                return SENSOR_VALUE_MAPS[self._iid].get(int(float(val)), val)
            except (ValueError, TypeError):
                return val
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, "car")}, "name": "小米汽车", "manufacturer": "Xiaomi", "model": "SU7"}


class MicarParkingSpotSensor(CoordinatorEntity, SensorEntity):
    """车位号（独立端点 parking-spot/query → data.parkingSpotNumber，如 "11-016"）。"""

    def __init__(self, coordinator: MicarDataUpdateCoordinator):
        super().__init__(coordinator)
        from .const import icon_for_name
        self._attr_icon = icon_for_name("车位号")
        self._attr_unique_id = "micar_base_sensor_parking_spot"
        self._attr_name = "车位号"

    @property
    def native_value(self):
        return self.coordinator.parking_spot

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, "car")}, "name": "小米汽车", "manufacturer": "Xiaomi", "model": "SU7"}
