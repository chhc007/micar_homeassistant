"""数据协调器：定时轮询车辆状态 + passToken 自动续期（Base 版——无 license）。"""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL
from .api import MicarAPI, MicarAPIError

_LOGGER = logging.getLogger(__name__)


class MicarDataUpdateCoordinator(DataUpdateCoordinator[dict]):
    """获取并缓存车辆状态（properties by iid）。401 时自动续期。"""

    def __init__(self, hass: HomeAssistant, api: MicarAPI, iids: list[str], pass_token: str,
                 car_model: str = ""):
        super().__init__(
            hass, _LOGGER, name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api
        self.iids = iids
        self.pass_token = pass_token
        self.car_model = car_model
        self.properties: dict[str, object] = {}

    async def _async_update_data(self) -> dict:
        try:
            props = await self.hass.async_add_executor_job(self.api.query_status, self.iids)
        except MicarAPIError as err:
            if "401" in str(err) or "token 失效" in str(err):
                _LOGGER.warning("token 失效，passToken 自动续期中...")
                try:
                    tokens = await self.hass.async_add_executor_job(
                        self.api.refresh_token, self.pass_token)
                    self.api.cookies.update(tokens)
                    props = await self.hass.async_add_executor_job(self.api.query_status, self.iids)
                except MicarAPIError as err2:
                    raise UpdateFailed(f"续期失败: {err2}") from err2
            else:
                raise UpdateFailed(str(err)) from err
        self.properties = {p.get("iid"): p.get("value") for p in props}
        return self.properties
