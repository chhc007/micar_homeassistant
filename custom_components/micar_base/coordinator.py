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
                 car_model: str = "", car_plate: str = "", car_name: str = ""):
        super().__init__(
            hass, _LOGGER, name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api
        self.iids = iids
        self.pass_token = pass_token
        self.car_model = car_model
        self.car_plate = car_plate
        self.car_name = car_name
        self.control_known = CONTROL_KNOWN
        self.properties: dict[str, object] = {}
        # 车位号（独立端点 parking-spot/query，主轮询一并更新；失败不影响主状态）
        self.parking_spot: str | None = None
        # 补偿刷新防抖标记（控制确认失败后 +5/+15/+30s 补偿刷新计划是否排队中）
        self._refresh_pending = False
        # 最近一次控制确认失败时记录的目标 iid 列表（补偿刷新复用，定向 refreshResults）
        self._last_confirm_iids: list[str] = []

    @property
    def vid(self) -> str:
        """当前车辆 vid（配置条目按 vid 区分，多车不冲突）。"""
        return self.api.vid

    @property
    def plate_suffix(self) -> str:
        """实体名车牌后缀：车牌优先，无车牌用车名（旧条目无此字段 → 空，原名不变）。"""
        return self.car_plate or self.car_name or ""

    @property
    def is_new_entry(self) -> bool:
        """是否为 v0.2.8+ 新条目（带车牌/车名字段）。

        旧条目（升级前添加）保持原 unique_id 与设备注册，实体不重建；
        新条目启用 vid 后缀与按车设备，多车互不冲突。
        """
        return bool(self.plate_suffix)

    @property
    def uid_suffix(self) -> str:
        """unique_id 后缀（_vid）：仅新条目启用；旧条目留空保持原 id。"""
        return f"_{self.vid}" if self.is_new_entry else ""

    @property
    def device_name(self) -> str:
        """设备名（每车一个 device）：小米汽车 + 车牌。"""
        suffix = self.plate_suffix
        return f"小米汽车 {suffix}" if suffix else "小米汽车"

    @property
    def device_info(self) -> dict:
        """设备注册信息。

        新条目 identifiers 按 vid 区分（多车各占一个设备）；
        旧条目保持原 (DOMAIN, "car") 标识，升级不重建设备。
        """
        if self.is_new_entry:
            return {
                "identifiers": {(DOMAIN, self.vid)},
                "name": self.device_name,
                "manufacturer": "Xiaomi",
                "model": self.car_model or "SU7",
            }
        return {
            "identifiers": {(DOMAIN, "car")},
            "name": "小米汽车",
            "manufacturer": "Xiaomi",
            "model": "SU7",
        }

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

    async def _refresh_iids(self, iids: list[str]) -> bool:
        """定向刷新：优先 refreshResults 端点（快，<1s），失败回退 subscriptions 全量。

        成功 → 把返回的 {iid: value} 合并进 self.properties 并 async_update_listeners()
        通知实体刷新；refreshResults 失败/返回 None → 回退一次 async_request_refresh()
        （subscriptions 全量兜底）。返回是否刷新成功（任一方式）。
        """
        try:
            result = await self.hass.async_add_executor_job(self.api.refresh_results, iids)
        except Exception as err:  # noqa: BLE001 - 网络/解析异常统一走回退
            _LOGGER.debug("micar_base refreshResults 异常（iids=%s）: %s", iids, err)
            result = None
        if result:
            self.properties.update(result)
            self.async_update_listeners()
            return True
        # 回退：subscriptions 全量兜底（refreshResults 失败或无数据）
        try:
            await self.async_request_refresh()
            return True
        except UpdateFailed as err:
            _LOGGER.warning("micar_base 定向刷新失败且全量回退失败（iids=%s）: %s", iids, err)
            return False

    async def _poll_confirm(self, iid: str, check, retries: int = 3, interval: float = 5.0,
                           refresh_iids: list[str] | None = None) -> tuple[bool, int]:
        """控制确认共享轮询：先立即刷新检查一次（快路径）→ 未达预期再按 interval 轮询至多 retries 次。

        小米服务端收到控制指令后状态同步有延迟（数秒），立即刷新可能拿到旧值，
        导致 UI 显示与真实状态不符（如解锁后按钮仍显示上锁）。
        刷新优先走 _refresh_iids（refreshResults 定向，快），不再每次全量 subscriptions。
        refresh_iids 缺省为 [iid]（纯控制 iid 如车窗 5.5.1 无回读时，由调用方传入
        实际回读 iid 列表，如 WINDOW_POSITION_IIDS）。
        返回 (是否确认, 尝试次数)；失败刷新同样消耗一次尝试（与原行为一致）。
        """
        if refresh_iids is None:
            refresh_iids = [iid]
        ok = False
        attempts = 0
        # 快路径：控制后立即定向刷新检查（不 sleep）
        await self._refresh_iids(refresh_iids)
        attempts = 1
        ok = check()
        while not ok and attempts <= retries:
            await asyncio.sleep(interval)
            await self._refresh_iids(refresh_iids)
            attempts += 1
            ok = check()
        return ok, attempts

    async def async_confirm_control(self, iid: str, expected: set, retries: int = 3, interval: float = 5.0) -> bool:
        """控制操作后确认生效：立即刷新检查（快路径）→ 未达预期再轮询重试。"""

        def _matches(val: object) -> bool:
            if val is None:
                return False
            try:
                raw = str(val)
                numeric = float(raw)
                return numeric in expected or raw in expected
            except (TypeError, ValueError):
                return val in expected

        ok, _ = await self._poll_confirm(iid, lambda: _matches(self.properties.get(iid)), retries, interval)
        if not ok:
            # 确认失败 = 云端状态同步慢，用补偿刷新兜底（保证实体最迟约 1 分钟内更新到真实状态）
            self._last_confirm_iids = [iid]
            self.schedule_control_refresh()
        return ok

    def schedule_control_refresh(self, delay_after: float = 30.0) -> None:
        """控制确认失败后的补偿刷新：+5s / +15s / +30s 各排一次状态刷新。

        用于确认失败（云端状态同步慢）兜底，保证实体最迟约 1 分钟内更新到真实状态。
        防抖：已有未执行的补偿刷新计划时跳过（多个平台连续控制不重复排一堆刷新）。
        补偿刷新复用 _refresh_iids（refreshResults 定向 + subscriptions 兜底），
        目标 iid 取 self._last_confirm_iids（确认失败时已记录），失败仅告警、不阻塞不抛异常。
        """
        if self._refresh_pending:
            _LOGGER.debug("micar_base 补偿刷新计划已在排队，跳过重复排定")
            return
        self._refresh_pending = True

        async def _refresh() -> None:
            iids = self._last_confirm_iids
            if iids:
                await self._refresh_iids(iids)
            else:
                # 兜底：无记录目标 iid 时全量刷新（防御性分支，正常不会走到）
                try:
                    await self.async_request_refresh()
                except UpdateFailed as err:
                    _LOGGER.warning("micar_base 补偿刷新失败: %s", err)

        delays = (5.0, 15.0, delay_after)
        for idx, delay in enumerate(delays):
            final = idx == len(delays) - 1

            def _fire(*_args, _final: bool = final) -> None:
                # 最后一个刷新点触发时解除防抖标记，允许后续控制重新排补偿
                if _final:
                    self._refresh_pending = False
                self.hass.async_create_task(_refresh())

            self.hass.async_call_later(delay, _fire)

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
        ok, _ = await self._poll_confirm(
            "5.5.1", lambda: self.window_position_state() == label, retries, interval,
            refresh_iids=list(WINDOW_POSITION_IIDS))
        if not ok:
            # 车窗确认失败同样走补偿刷新兜底（与 async_confirm_control 一致）
            self._last_confirm_iids = list(WINDOW_POSITION_IIDS)
            self.schedule_control_refresh()
        return ok
