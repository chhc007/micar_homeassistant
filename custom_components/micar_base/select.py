"""选择实体：多档位控制（电动后备箱 2.8.3 直接回读；车窗控制 5.5.1，actions 通道，position 0=全关 1=通风 8=全开）。"""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MicarDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: MicarDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for iid, item in coordinator.control_known.items():
        # 仅创建显式声明 platform=select 的控制（如 2.8.3 电动后备箱、5.5.1 车窗控制）
        if item.get("platform") == "select":
            entities.append(MicarSelect(coordinator, iid))
    async_add_entities(entities)


class MicarSelect(CoordinatorEntity, SelectEntity):
    def __init__(self, coordinator: MicarDataUpdateCoordinator, iid: str):
        super().__init__(coordinator)
        self._iid = iid
        item = coordinator.control_known[iid]
        # 实体名带车牌后缀（多车不重名）；旧条目无车牌 → 原名不变
        self._attr_name = f"{item['name']} {coordinator.plate_suffix}".strip()
        self._attr_unique_id = f"micar_base_select_{iid}{coordinator.uid_suffix}"
        from .const import icon_for_name
        self._attr_icon = icon_for_name(item["name"])

        self._value_map = item["values"]
        self._attr_options = list(self._value_map.values())

        # 车窗控制（5.5.1）是纯控制 iid，无自身状态回读 → 状态由四车窗位置 5.1.1-5.4.1 推导
        self._status_mode = item.get("status_mode")

    @property
    def current_option(self):
        if self._status_mode == "windows":
            return self.coordinator.window_position_state()
        val = self.coordinator.properties.get(self._iid)
        if val is None:
            return None
        return self._value_map.get(int(val))

    async def async_select_option(self, option: str, **kwargs):
        value = next((v for v, label in self._value_map.items() if label == option), None)
        if value is None:
            return
        await self.hass.async_add_executor_job(self.coordinator.api.control, self._iid, value)
        warn_msg = f"micar_base 选择控制 {self._iid}（{self._attr_name}）指令已发送但状态未确认"
        if self._status_mode == "windows":
            # 车窗控制确认：后台轮询四车窗位置落入对应区间（5.5.1 无自身状态回读）
            self.coordinator.schedule_confirm_windows(value, warn_msg=warn_msg)
        else:
            self.coordinator.schedule_confirm_control(self._iid, {value}, warn_msg=warn_msg)

    @property
    def device_info(self):
        return self.coordinator.device_info
