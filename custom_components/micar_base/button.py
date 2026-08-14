"""按钮实体：动作类控制（寻车 13.1.1，actions 通道，workMode 1=闪灯 3=鸣笛）。"""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MicarDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: MicarDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for iid, item in coordinator.control_known.items():
        # 仅创建显式声明 platform=button 的控制（如 13.1.1 寻车）
        if item.get("platform") != "button":
            continue
        buttons = item.get("buttons")
        if buttons:
            # 同一 iid 多值多按钮（寻车：闪灯 workMode=1 / 鸣笛 workMode=3）
            for btn in buttons:
                entities.append(MicarButton(coordinator, iid, value=btn["value"], name=btn["name"]))
        else:
            entities.append(MicarButton(coordinator, iid))
    async_add_entities(entities)


class MicarButton(CoordinatorEntity, ButtonEntity):
    def __init__(self, coordinator: MicarDataUpdateCoordinator, iid: str, value: int | None = None, name: str | None = None):
        super().__init__(coordinator)
        self._iid = iid
        item = coordinator.control_known[iid]
        # 按钮动作取第一个可用值；多按钮条目（buttons 列表）显式指定 value/name
        self._value = value if value is not None else next(iter(item["values"]))
        # 实体名带车牌后缀（多车不重名）；旧条目无车牌 → 原名不变
        self._attr_name = f"{name or item['name']} {coordinator.plate_suffix}".strip()
        # 多值按钮（同一 iid 多个动作）unique_id 带值区分
        self._attr_unique_id = (
            f"micar_base_button_{iid}{coordinator.uid_suffix}"
            if value is None
            else f"micar_base_button_{iid}_{value}{coordinator.uid_suffix}"
        )
        from .const import icon_for_name
        self._attr_icon = icon_for_name(self._attr_name)

    async def async_press(self) -> None:
        await self.hass.async_add_executor_job(self.coordinator.api.control, self._iid, self._value)
        await self.coordinator.async_request_refresh()

    @property
    def device_info(self):
        return self.coordinator.device_info
