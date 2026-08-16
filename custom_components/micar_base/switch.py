"""开关实体：开关类控制（空调极速制冷 7.7.13 / 制热 7.7.12、电动后备箱 2.8.3，properties 通道；空调除霜 13.10.1，actions 通道）。"""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    BACKBOX_ELECTRIC_IID,
    BACKBOX_CONFIRM_EXPECTED,
    BACKBOX_TRANSITION_VALUES,
)
from .coordinator import MicarDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: MicarDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for iid, item in coordinator.control_known.items():
        # 仅创建显式声明 platform=switch 的控制（如 13.10.1 空调除霜、2.8.3 电动后备箱）
        if item.get("platform") == "switch":
            if iid == BACKBOX_ELECTRIC_IID:
                entities.append(MicarBackBoxSwitch(coordinator, iid))
            else:
                entities.append(MicarSwitch(coordinator, iid))
    async_add_entities(entities)


class MicarSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator: MicarDataUpdateCoordinator, iid: str):
        super().__init__(coordinator)
        self._iid = iid
        item = coordinator.control_known[iid]
        # 实体名带车牌后缀（多车不重名）；旧条目无车牌 → 原名不变
        self._attr_name = f"{item['name']} {coordinator.plate_suffix}".strip()
        self._attr_unique_id = f"micar_base_switch_{iid}{coordinator.uid_suffix}"
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
        # 乐观置值：本地立即置意图状态，UI 立即显示 on；confirm 快速刷新（refreshResults）随后覆盖真实状态
        self._apply_optimistic(self._on_value)
        self.coordinator.schedule_confirm_control(
            self._status_iid, {float(self._on_value)},
            warn_msg=f"micar_base 开关 {self._iid}（{self._attr_name}）开启指令已发送但状态未确认")

    async def async_turn_off(self, **kwargs):
        await self.hass.async_add_executor_job(self.coordinator.api.control, self._iid, self._off_value)
        # 乐观置值：本地立即置意图状态，UI 立即显示 off；confirm 快速刷新（refreshResults）随后覆盖真实状态
        self._apply_optimistic(self._off_value)
        self.coordinator.schedule_confirm_control(
            self._status_iid, {float(self._off_value)},
            warn_msg=f"micar_base 开关 {self._iid}（{self._attr_name}）关闭指令已发送但状态未确认")

    def _apply_optimistic(self, value: int) -> None:
        """乐观置值：本地立即置 status_iid 为目标值并通知监听器即时刷新 UI。

        控制指令下发后服务端状态同步有延迟，先本地置意图状态让 UI 立即显示目标状态；
        后台 confirm 快速刷新（refreshResults <1s）随后用真实状态覆盖，失败走补偿回退。
        （仅在 api.control 正常返回后调用——控制失败抛异常不会走到这里。）
        """
        self.coordinator.properties[self._status_iid] = value
        self.coordinator.async_update_listeners()

    @property
    def device_info(self):
        return self.coordinator.device_info


class MicarBackBoxSwitch(CoordinatorEntity, SwitchEntity):
    """电动后备箱（2.8.3）开关：turn_on 开 / turn_off 关，过渡态按方向映射开关状态。

    - is_on：6 → True；0 → False；过渡值按方向（5/4 正在开启/开启停止 → True；
      2/3 正在关闭/关闭停止 → False；1 仅开启区域 → True）。
    - async_turn_on：control(2.8.3, 6) + 本地乐观置 5（正在开启）+ 后台 confirm {6,5,4}。
    - async_turn_off：control(2.8.3, 0) + 本地乐观置 2（正在关闭）+ 后台 confirm {0,2,3}。
    """

    def __init__(self, coordinator: MicarDataUpdateCoordinator, iid: str):
        super().__init__(coordinator)
        self._iid = iid
        item = coordinator.control_known[iid]
        self._attr_name = f"{item['name']} {coordinator.plate_suffix}".strip()
        self._attr_unique_id = f"micar_base_switch_{iid}{coordinator.uid_suffix}"
        from .const import icon_for_name
        self._attr_icon = icon_for_name(item["name"])

    @property
    def is_on(self):
        val = self.coordinator.properties.get(self._iid)
        if val is None:
            return None
        try:
            v = int(val)
        except (TypeError, ValueError):
            return None
        if v == 6:
            return True
        if v == 0:
            return False
        # 过渡值按方向：5/4 正在开启/开启停止、1 仅开启区域 → True；2/3 正在关闭/关闭停止 → False
        if v in (5, 4, 1):
            return True
        if v in (2, 3):
            return False
        return None

    async def async_turn_on(self, **kwargs):
        await self.hass.async_add_executor_job(self.coordinator.api.control, self._iid, 6)
        self._apply_transition(6)
        self.coordinator.schedule_confirm_control(
            self._iid, BACKBOX_CONFIRM_EXPECTED.get(6, {6}),
            warn_msg=f"micar_base 开关 {self._iid}（{self._attr_name}）开启指令已发送但状态未确认")

    async def async_turn_off(self, **kwargs):
        await self.hass.async_add_executor_job(self.coordinator.api.control, self._iid, 0)
        self._apply_transition(0)
        self.coordinator.schedule_confirm_control(
            self._iid, BACKBOX_CONFIRM_EXPECTED.get(0, {0}),
            warn_msg=f"micar_base 开关 {self._iid}（{self._attr_name}）关闭指令已发送但状态未确认")

    def _apply_transition(self, value: int) -> None:
        """本地乐观置过渡值（开→5 正在开启 / 关→2 正在关闭），通知监听器即时刷新 UI。"""
        transitional = BACKBOX_TRANSITION_VALUES.get(value)
        if transitional is not None:
            self.coordinator.properties[self._iid] = transitional
            self.coordinator.async_update_listeners()

    @property
    def device_info(self):
        return self.coordinator.device_info
