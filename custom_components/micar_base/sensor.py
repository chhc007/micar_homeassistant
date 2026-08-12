"""只读传感器：电量、剩余续航（Free 版核心状态）。"""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import PERCENTAGE, UnitOfLength
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MicarDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# (iid, key, 显示名, device_class, unit)
FREE_SENSORS = [
    ("4.4.1", "battery", "电量", SensorDeviceClass.BATTERY, PERCENTAGE),
    ("4.4.3", "range", "剩余续航", SensorDeviceClass.DISTANCE, UnitOfLength.KILOMETERS),
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
