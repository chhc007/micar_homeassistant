"""micar_base 集成入口：空调 + GPS 定位（无 license、无统计）。"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN, CONF_PASS_TOKEN, CONF_CUSER_ID, CONF_USER_ID,
    CONF_MOBILE_ID, CONF_VID, CONF_CAR_MODEL, FREE_IIDS,
)
from .api import MicarAPI
from .coordinator import MicarDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["climate", "device_tracker", "sensor", "lock"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """建立 API 客户端 + 协调器（Base 版——无 license）。"""
    api = MicarAPI()
    data = entry.data
    api.cookies["cUserId"] = data.get(CONF_CUSER_ID, "")
    api.cookies["userId"] = data.get(CONF_USER_ID, "")
    api.mobile_id = data.get(CONF_MOBILE_ID, "")
    api.vid = data.get(CONF_VID, "")
    # 首次同步 token（passToken → 280 token + ph/slh + mobileId）
    try:
        tokens = await hass.async_add_executor_job(
            api.refresh_token, data.get(CONF_PASS_TOKEN, ""), data.get(CONF_USER_ID, ""))
        api.cookies.update(tokens)
        api.cookies["mobileId"] = api.mobile_id
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("micar_base 启动续期失败: %s", err)

    car_model = data.get(CONF_CAR_MODEL, "")
    iids = list(FREE_IIDS)

    coordinator = MicarDataUpdateCoordinator(
        hass, api, iids, data.get(CONF_PASS_TOKEN, ""), car_model=car_model)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载平台。"""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
