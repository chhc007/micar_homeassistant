"""Config Flow：小米账号登录 → 短信验证码 → passToken → 完成（Base 版——无 license）。"""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN, CONF_USERNAME, CONF_PASSWORD, CONF_CODE, CONF_DEVICE_ID,
    CONF_PASS_TOKEN, CONF_CUSER_ID, CONF_USER_ID, CONF_MOBILE_ID, CONF_VID,
    CONF_CAR_MODEL,
)
from .api import MicarAPI, MicarAPIError

_LOGGER = logging.getLogger(__name__)

# App 风格设备 ID：字母/数字/-/_ 组合（如 YSFTVmttfxS0t_G-）
DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_DEVICE_ID): str,
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

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """账号密码登录（短信验证码）。"""
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
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors,
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
        """保存凭据 → 换 token → 探测车辆 → 完成配置。"""
        try:
            if not creds:
                creds = {"passToken": self._api.cookies.get("passToken", "")}
            pass_token = creds.get("passToken")
            if not pass_token:
                raise MicarAPIError("未拿到 passToken")
            tokens = await self.hass.async_add_executor_job(
                self._api.refresh_token, pass_token, creds.get("userId", ""))
            self._api.cookies.update(tokens)

            # mobileId 必须与用户填写的 deviceId 一致（token 绑定该设备，App 亦如此）
            self._api.mobile_id = self._api.device_id
            self._api.cookies["mobileId"] = self._api.mobile_id

            cars = await self.hass.async_add_executor_job(self._api.get_vehicles_list)
            if not cars:
                raise MicarAPIError("未找到车辆")
            self._api.vid = cars[0].get("vid", "")
            car_model = cars[0].get("carModel", "") or cars[0].get("carName", "")
            self._api.car_model = car_model
        except MicarAPIError as err:
            return self.async_abort(reason=str(err))

        data = {
            CONF_USERNAME: self._username,
            CONF_PASS_TOKEN: pass_token,
            CONF_CUSER_ID: tokens.get("cUserId") or creds.get("cUserId", ""),
            CONF_USER_ID: creds.get("userId", ""),
            CONF_DEVICE_ID: self._api.device_id,
            CONF_MOBILE_ID: self._api.mobile_id,
            CONF_VID: self._api.vid,
            CONF_CAR_MODEL: self._api.car_model,
        }
        return self.async_create_entry(title=f"小米汽车 {self._username}", data=data)
