"""空调气候实体：开关（7.1.1）+ 目标温度（7.2.3）。"""
from __future__ import annotations

import logging

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MicarDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SWITCH_IID = "7.1.1"
TEMP_IID = "7.2.3"
MIN_TEMP = 16.0
MAX_TEMP = 32.0


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: MicarDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MicarClimate(coordinator)])


class MicarClimate(CoordinatorEntity, ClimateEntity):
    def __init__(self, coordinator: MicarDataUpdateCoordinator):
        super().__init__(coordinator)
        # 实体名带车牌后缀（多车不重名）；旧条目无车牌 → 原名不变
        self._attr_name = f"空调 {coordinator.plate_suffix}".strip()
        self._attr_unique_id = f"micar_base_climate_ac{coordinator.uid_suffix}"
        from .const import icon_for_name
        self._attr_icon = icon_for_name("空调")

        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT_COOL]
        self._attr_min_temp = MIN_TEMP
        self._attr_max_temp = MAX_TEMP
        self._attr_target_temperature_step = 0.5
        # 声明支持目标温度调节（否则 HA 不显示温度滑块、不读取 temperature 属性）
        self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    @property
    def hvac_mode(self) -> HVACMode:
        val = self.coordinator.properties.get(SWITCH_IID)
        if val is None:
            return HVACMode.OFF
        return HVACMode.HEAT_COOL if int(val) == 1 else HVACMode.OFF

    @property
    def current_temperature(self) -> float | None:
        val = self.coordinator.properties.get("7.2.1")  # 车内温度
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def target_temperature(self) -> float | None:
        """空调设定温度（HA ClimateEntity 标准属性名 target_temperature；读 7.2.3 目标温度）。"""
        val = self.coordinator.properties.get(TEMP_IID)
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        value = 1 if hvac_mode != HVACMode.OFF else 0
        await self.hass.async_add_executor_job(self.coordinator.api.control, SWITCH_IID, value)
        # 控制后确认生效（服务端状态同步延迟，连续刷新避免 UI 显示旧状态）
        await self.coordinator.async_confirm_control(SWITCH_IID, {float(value)})

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get("temperature")
        if temp is not None:
            await self.hass.async_add_executor_job(self.coordinator.api.control, TEMP_IID, float(temp))
            await self.coordinator.async_confirm_control(TEMP_IID, {float(temp)})

    @property
    def device_info(self):
        return self.coordinator.device_info
