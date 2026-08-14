"""Config Flow：选择登录模式 → 小米账号登录 → 短信验证码 → passToken → 完成（Base 版——无 license）。

两种登录模式：
- 主账号模式（master）：车主本人账号，需填写手机小米汽车 App 的设备 ID（deviceId）
- 共享账号模式（shared）：车主把车辆授权共享给新账号，设备 ID 自动生成
"""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN, CONF_USERNAME, CONF_PASSWORD, CONF_CODE, CONF_DEVICE_ID, CONF_MODE,
    CONF_PASS_TOKEN, CONF_CUSER_ID, CONF_USER_ID, CONF_MOBILE_ID, CONF_VID,
    CONF_CAR_MODEL, CONF_CAR_PLATE, CONF_CAR_NAME, MODE_MASTER, MODE_SHARED,
)
from .api import MicarAPI, MicarAPIError, generate_device_id

_LOGGER = logging.getLogger(__name__)

# App 风格设备 ID：字母/数字/-/_ 组合（如 YSFTVmttfxS0t_G-）
DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

# 第一步：选择登录模式
STEP_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MODE, default=MODE_MASTER): vol.In(
            {
                MODE_MASTER: "主账号模式（车主本人，需抓包获取设备 ID）",
                MODE_SHARED: "共享账号模式（无需抓包，设备 ID 自动生成）",
            }
        ),
    }
)
# 主账号模式：账号+密码+设备 ID（必填）
STEP_MASTER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_DEVICE_ID): str,
    }
)
# 共享账号模式：账号+密码（设备 ID 自动生成）
STEP_SHARED_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)
STEP_CODE_SCHEMA = vol.Schema({vol.Required(CONF_CODE): str})


class MicarConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """micar_base 配置流程（Base 版——无 license）。"""

    VERSION = 1

    def __init__(self):
        self._api = MicarAPI()
        self._session = None
        self._username = ""
        self._creds = {}
        self._mode = MODE_MASTER
        # 车辆列表（ownCarList + authorizedCarList 合并，每辆带 _source）
        self._cars = []

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """第一步：选择登录模式（主账号 / 共享账号）。"""
        errors = {}
        if user_input is not None:
            self._mode = user_input.get(CONF_MODE, MODE_MASTER)
            if self._mode == MODE_SHARED:
                return await self.async_step_shared()
            return await self.async_step_master()
        return self.async_show_form(
            step_id="user", data_schema=STEP_MODE_SCHEMA, errors=errors,
            description_placeholders={},
        )

    async def async_step_master(self, user_input: dict | None = None) -> FlowResult:
        """主账号模式：账号密码登录（短信验证码），设备 ID 必填。"""
        errors = {}
        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            device_id = (user_input.get(CONF_DEVICE_ID) or "").strip()
            if not DEVICE_ID_RE.fullmatch(device_id):
                errors[CONF_DEVICE_ID] = "invalid_device_id"
            else:
                self._api.device_id = device_id
                try:
                    result = await self.hass.async_add_executor_job(
                        self._api.login_start,
                        user_input[CONF_USERNAME],
                        user_input[CONF_PASSWORD],
                    )
                except MicarAPIError as err:
                    errors["base"] = str(err)
                else:
                    if result.get("need_code"):
                        self._session = result["session"]
                        return await self.async_step_code()
                    return await self._finish({})
        return self.async_show_form(
            step_id="master", data_schema=STEP_MASTER_SCHEMA, errors=errors,
            description_placeholders={},
        )

    async def async_step_shared(self, user_input: dict | None = None) -> FlowResult:
        """共享账号模式：账号密码登录（短信验证码），设备 ID 自动生成。"""
        errors = {}
        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            # 自动生成 App 风格设备 ID（登录/续期/查询均绑定该 ID）
            self._api.device_id = generate_device_id()
            try:
                result = await self.hass.async_add_executor_job(
                    self._api.login_start,
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
            except MicarAPIError as err:
                errors["base"] = str(err)
            else:
                if result.get("need_code"):
                    self._session = result["session"]
                    return await self.async_step_code()
                return await self._finish({})
        return self.async_show_form(
            step_id="shared", data_schema=STEP_SHARED_SCHEMA, errors=errors,
            description_placeholders={},
        )

    async def async_step_code(self, user_input: dict | None = None) -> FlowResult:
        """短信验证码校验 → 登录完成。"""
        errors = {}
        if user_input is not None:
            try:
                creds = await self.hass.async_add_executor_job(
                    self._api.login_verify,
                    user_input[CONF_CODE],
                    self._session,
                )
            except MicarAPIError as err:
                errors["base"] = str(err)
            else:
                self._creds = creds
                return await self._finish(creds)
        return self.async_show_form(
            step_id="code", data_schema=STEP_CODE_SCHEMA, errors=errors,
            description_placeholders={"username": self._username},
        )

    async def _finish(self, creds: dict) -> FlowResult:
        """保存凭据 → 换 token → 探测全部车辆 → 选车（多车时）→ 完成配置。

        车辆列表为 ownCarList + authorizedCarList 合并（自己的车 + 被授权共享的车），
        全部可选。单车自动选中；多车弹出选车步骤，每辆车一个配置条目，
        添加多辆车 = 重复"添加集成"流程选择不同的车。
        """
        try:
            if not creds:
                creds = {"passToken": self._api.cookies.get("passToken", "")}
            pass_token = creds.get("passToken")
            if not pass_token:
                raise MicarAPIError("未拿到 passToken")
            tokens = await self.hass.async_add_executor_job(
                self._api.refresh_token, pass_token, creds.get("userId", ""))
            self._api.cookies.update(tokens)

            # mobileId 必须与 deviceId 一致（token 绑定该设备，App 亦如此）
            self._api.mobile_id = self._api.device_id
            self._api.cookies["mobileId"] = self._api.mobile_id

            self._cars = await self.hass.async_add_executor_job(
                self._api.get_vehicles_list)
            if not self._cars:
                raise MicarAPIError("未找到车辆（请确认账号已绑定车辆，或车主已在 App 中授权共享）")
            # cUserId 兜底取续期结果（旧逻辑 tokens 优先）
            creds = dict(creds)
            creds.setdefault("cUserId", tokens.get("cUserId", ""))
            self._creds = creds
        except MicarAPIError as err:
            return self.async_abort(reason=str(err))

        if len(self._cars) == 1:
            return await self._create_entry(self._cars[0])
        return await self.async_step_car()

    @staticmethod
    def _car_label(car: dict) -> str:
        """车辆选项显示名：车牌 + 车名（被授权共享的车标注来源）。"""
        plate = car.get("carPlate", "") or ""
        name = car.get("carName", "") or car.get("carModel", "") or ""
        label = f"{plate} {name}".strip() or car.get("vid", "")
        if car.get("_source") == "authorized":
            label += "（共享）"
        return label

    async def async_step_car(self, user_input: dict | None = None) -> FlowResult:
        """选车步骤：列出账号下全部车辆（自己的 + 共享授权的），用户选一辆添加。

        每辆车一个配置条目：添加多辆车需重复"添加集成"流程，每次选不同的车。
        """
        errors = {}
        if user_input is not None:
            vid = user_input.get(CONF_VID)
            car = next((c for c in self._cars if c.get("vid") == vid), None)
            if car is None:
                errors["base"] = "所选车辆无效，请重试"
            else:
                return await self._create_entry(car)
        options = {c["vid"]: self._car_label(c) for c in self._cars if c.get("vid")}
        schema = vol.Schema({vol.Required(CONF_VID): vol.In(options)})
        return self.async_show_form(
            step_id="car", data_schema=schema, errors=errors,
            description_placeholders={"count": str(len(self._cars))},
        )

    async def _create_entry(self, car: dict) -> FlowResult:
        """按选定的车辆创建配置条目（vid 唯一标识该车）。"""
        # 同一辆车已添加过 → 中止（避免 unique_id 冲突）
        vid = car.get("vid", "")
        for entry in self._async_current_entries():
            if entry.data.get(CONF_VID) == vid:
                return self.async_abort(
                    reason="already_configured",
                    description_placeholders={"car": self._car_label(car)},
                )
        self._api.vid = vid
        car_model = car.get("carModel", "") or car.get("carName", "")
        self._api.car_model = car_model
        creds = self._creds

        data = {
            CONF_USERNAME: self._username,
            CONF_MODE: self._mode,
            CONF_PASS_TOKEN: creds.get("passToken", ""),
            CONF_CUSER_ID: creds.get("cUserId", ""),
            CONF_USER_ID: creds.get("userId", ""),
            CONF_DEVICE_ID: self._api.device_id,
            CONF_MOBILE_ID: self._api.mobile_id,
            CONF_VID: self._api.vid,
            CONF_CAR_MODEL: car_model,
            CONF_CAR_PLATE: car.get("carPlate", ""),
            CONF_CAR_NAME: car.get("carName", ""),
        }
        # 条目标题：车牌优先，无车牌用车名（多车条目可区分）
        title = car.get("carPlate", "") or car.get("carName", "") or self._username
        return self.async_create_entry(title=f"小米汽车 {title}", data=data)
