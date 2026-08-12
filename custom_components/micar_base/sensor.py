"""只读传感器：电量、续航、四轮胎压、车窗状态（Free 版核心状态）。"""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfPressure
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MicarDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# (iid, key, 显示名, device_class, unit)
FREE_SENSORS = [
    ("4.4.1", "battery", "电量", SensorDeviceClass.BATTERY, PERCENTAGE),
    ("4.4.3", "range", "剩余续航", SensorDeviceClass.DISTANCE, UnitOfLength.KILOMETERS),
    ("9.1.1", "tire_fl", "主驾胎压", SensorDeviceClass.PRESSURE, UnitOfPressure.BAR),
    ("9.2.1", "tire_fr", "副驾胎压", SensorDeviceClass.PRESSURE, UnitOfPressure.BAR),
    ("9.3.1", "tire_rl", "左后胎压", SensorDeviceClass.PRESSURE, UnitOfPressure.BAR),
    ("9.4.1", "tire_rr", "右后胎压", SensorDeviceClass.PRESSURE, UnitOfPressure.BAR),
    ("5.1.1", "window_fl", "主驾车窗", None, PERCENTAGE),
    ("5.2.1", "window_fr", "副驾车窗", None, PERCENTAGE),
    ("5.3.1", "window_rl", "左后车窗", None, PERCENTAGE),
    ("5.4.1", "window_rr", "右后车窗", None, PERCENTAGE),
]


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: MicarDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [MicarSensor(coordinator, iid, key, name, dev_cls, unit)
                for iid, key, name, dev_cls, unit in FREE_SENSORS]
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
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, "car")}, "name": "小米汽车", "manufacturer": "Xiaomi", "model": "SU7"}
