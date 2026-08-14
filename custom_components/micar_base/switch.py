"""开关实体：开关类控制（空调除霜 13.10.1，actions 通道，status 0=关 2=开）。"""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MicarDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: MicarDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for iid, item in coordinator.control_known.items():
        # 仅创建显式声明 platform=switch 的控制（如 13.10.1 空调除霜）
        if item.get("platform") == "switch":
            entities.append(MicarSwitch(coordinator, iid))
    async_add_entities(entities)


class MicarSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator: MicarDataUpdateCoordinator, iid: str):
        super().__init__(coordinator)
        self._iid = iid
        item = coordinator.control_known[iid]
        self._attr_name = item["name"]
        self._attr_unique_id = f"micar_base_switch_{iid}"
        from .const import icon_for_name
        self._attr_icon = icon_for_name(item["name"])

        # 从 values 找"开"/"关"对应的值（13.10.1 除霜：status=2 开、0 关）
        self._on_value = next((v for v, l in item["values"].items() if l == "开"), 2)
        self._off_value = next((v for v, l in item["values"].items() if l == "关"), 0)

        # 纯控制 iid（13.10.1 hvacDefrostRequest）不在订阅列表、无自身状态回读 →
        # 用 status_iid（7.1.4 hvacDefrostStatus）反映开关状态
        self._status_iid = item.get("status_iid", iid)

    @property
    def is_on(self):
        val = self.coordinator.properties.get(self._status_iid)
        if val is None:
            return None
        try:
            v = int(val)
        except (TypeError, ValueError):
            return None
        if v == self._on_value:
            return True
        if v == self._off_value:
            return False
        # 中间态（如 7.1.4=1 除雾）既非本开关的"开"也非"关" → 返回未知，不误导
        return None

    async def async_turn_on(self, **kwargs):
        await self.hass.async_add_executor_job(self.coordinator.api.control, self._iid, self._on_value)
        # 控制后确认生效（服务端状态同步延迟，连续刷新避免 UI 显示旧状态）
        if not await self.coordinator.async_confirm_control(self._status_iid, {float(self._on_value)}):
            _LOGGER.warning("micar_base 开关 %s（%s）开启指令已发送但状态未确认", self._iid, self._attr_name)

    async def async_turn_off(self, **kwargs):
        await self.hass.async_add_executor_job(self.coordinator.api.control, self._iid, self._off_value)
        if not await self.coordinator.async_confirm_control(self._status_iid, {float(self._off_value)}):
            _LOGGER.warning("micar_base 开关 %s（%s）关闭指令已发送但状态未确认", self._iid, self._attr_name)

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, "car")}, "name": "小米汽车", "manufacturer": "Xiaomi", "model": "SU7"}
