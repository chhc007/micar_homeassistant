"""数据协调器：定时轮询车辆状态 + passToken 自动续期（Base 版——无 license）。"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL, CONTROL_KNOWN
from .api import MicarAPI, MicarAPIError

_LOGGER = logging.getLogger(__name__)

# 车窗位置 iid（车窗控制 5.5.1 的状态回读/确认源；5.5.1 本身是纯控制 iid，不在订阅列表）
WINDOW_POSITION_IIDS = ("5.1.1", "5.2.1", "5.3.1", "5.4.1")
# 车窗控制 5.5.1 position 发送值 → 车窗状态标签
WINDOW_POSITION_LABELS = {0: "全关", 1: "通风", 8: "全开"}
# position → 四车窗位置百分比区间（全关≈0、通风≈10-20、全开≈100，区间留余量）
WINDOW_POSITION_BANDS = {0: (0, 2), 1: (3, 45), 8: (95, 100)}


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
        self.control_known = CONTROL_KNOWN
        self.properties: dict[str, object] = {}
        # 车位号（独立端点 parking-spot/query，主轮询一并更新；失败不影响主状态）
        self.parking_spot: str | None = None

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
        # 车位号（独立端点，失败只告警，不影响主状态回读）
        try:
            parking = await self.hass.async_add_executor_job(self.api.get_parking_spot)
            spot = (parking or {}).get("parkingSpotNumber")
            if spot is not None:
                self.parking_spot = str(spot)
        except Exception as err:  # noqa: BLE001 - 车位号失败不影响主状态
            _LOGGER.debug("车位号查询失败（忽略）: %s", err)
        return self.properties

    async def async_confirm_control(self, iid: str, expected: set, retries: int = 3, interval: float = 5.0) -> bool:
        """控制操作后确认生效：连续刷新多次，直到 iid 状态符合预期。

        服务端收到控制指令后状态同步有延迟（数秒），立即刷新会拿到旧值，
        导致 UI 显示与真实状态不符（如解锁后按钮仍显示上锁）。
        轮询直至命中 expected 集合，或达到重试上限。
        返回是否确认生效。
        """
        for attempt in range(retries):
            await asyncio.sleep(interval)
            try:
                await self.async_request_refresh()
            except UpdateFailed:
                _LOGGER.warning("micar 控制确认刷新失败（第 %d 次）", attempt + 1)
                continue
            val = self.properties.get(iid)
            if val is not None:
                try:
                    raw = str(val)
                    numeric = float(raw)
                    if numeric in expected or raw in expected:
                        return True
                except (TypeError, ValueError):
                    if val in expected:
                        return True
        return False

    def window_position_state(self) -> str | None:
        """由四车窗位置百分比（5.1.1-5.4.1）推导车窗控制状态：全关/通风/全开。

        任一车窗缺失、非法、或四窗未全部落入同一区间（如单窗半开）→ None（不误导）。
        区间见 WINDOW_POSITION_BANDS。
        """
        vals = []
        for iid in WINDOW_POSITION_IIDS:
            v = self.properties.get(iid)
            # 仅接受数值型（订阅返回 JSON number）；缺失/非数值 → 不判定
            if not isinstance(v, (int, float)):
                return None
            vals.append(float(v))
        for position, (lo, hi) in WINDOW_POSITION_BANDS.items():
            if all(lo <= v <= hi for v in vals):
                return WINDOW_POSITION_LABELS[position]
        return None

    async def async_confirm_windows(self, position: int, retries: int = 3, interval: float = 5.0) -> bool:
        """车窗控制（5.5.1）确认：5.5.1 无自身状态回读，轮询四车窗位置 5.1.1-5.4.1

        落入 position 对应区间即确认生效（position: 0=全关 1=通风 8=全开）。
        """
        if position not in WINDOW_POSITION_BANDS:
            return False
        label = WINDOW_POSITION_LABELS[position]
        for attempt in range(retries):
            await asyncio.sleep(interval)
            try:
                await self.async_request_refresh()
            except UpdateFailed:
                _LOGGER.warning("micar_base 车窗控制确认刷新失败（第 %d 次）", attempt + 1)
                continue
            if self.window_position_state() == label:
                return True
        return False
