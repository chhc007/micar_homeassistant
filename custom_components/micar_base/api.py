"""小米汽车 API 客户端（Base 版——无 license、纯 HTTP）。

登录流程（验证码短信）：
  login_start(username, password) → session（需要验证码）
  login_verify(code, session) → passToken/cUserId/userId

续期：passToken + App 风格 deviceId → 280 字符 App 式 serviceToken。
查询：subscriptions（iid 属性系统）。控制：properties / actions 双通道。
"""
from __future__ import annotations

import base64
import hashlib
import http.cookiejar
import json
import logging
import uuid
from urllib.parse import urlencode, urlparse, parse_qs, quote
import urllib.request
import urllib.error

from .const import (
    BASE_URL, PASSPORT_URL, SID, APP_DEVICE_ID, UA,
    EP_SUBSCRIPTIONS, EP_PROPERTIES, EP_ACTIONS, EP_USER_CAR_LIST,
)

_LOGGER = logging.getLogger(__name__)


class MicarAPIError(Exception):
    """API 错误（含用户可读消息）。"""


class MicarAPI:
    """小米汽车 API 客户端（Base 版）。"""

    def __init__(self):
        self.cookies = {}  # serviceToken/cUserId/mobileId/ph/slh
        self.vid = ""
        self.mobile_id = ""
        self.car_model = ""
        # passport 登录会话（CookieJar 自动管理 identity_session 等）
        self._cj = http.cookiejar.CookieJar()
        self._cj_opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cj))
        self.device_headers = {
            "deviceappversioncode": "26072022",
            "deviceappversionname": "2.7.0",
            "deviceappversion": "2.7.0",
            "deviceostype": "android",
            "androidsdkversion": "36",
            "accept-language": "zh-CN",
            "devicevendor": "Xiaomi",
            "devicemodel": "2509FPN0BC",
            "deviceosversion": "BP2A.250605.031.A3",
            "devicereleasechannel": "1",
            "devicepackagetype": "1",
        }

    # ---------- 内部 HTTP ----------
    def _request(self, url, data=None, method=None, headers=None, timeout=30):
        h = {"User-Agent": UA}
        if data is not None:
            h["Content-Type"] = "application/x-www-form-urlencoded"
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode(errors="replace"), dict(resp.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(errors="replace"), dict(e.headers)

    def _form(self, url, params=None, data=None, headers=None):
        if params:
            url = url + "?" + urlencode(params)
        body = urlencode(data or {}).encode() if data else None
        return self._request(url, body, headers=headers)

    def _passport_request(self, url, data=None, headers=None, timeout=30):
        """passport 会话请求（CookieJar 自动管理 cookie）"""
        h = {"User-Agent": UA}
        if data is not None:
            h["Content-Type"] = "application/x-www-form-urlencoded"
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, data=data, headers=h)
        try:
            with self._cj_opener.open(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode(errors="replace"), dict(resp.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(errors="replace"), dict(e.headers)

    def _passport_form(self, url, params=None, data=None):
        if params:
            url = url + "?" + urlencode(params)
        body = urlencode(data or {}).encode() if data else None
        return self._passport_request(url, body)

    @staticmethod
    def _parse_json(body):
        if body.startswith("&&&START&&&"):
            body = body[11:]
        return json.loads(body)

    def _set_cookies(self, cookie_str):
        """从 Set-Cookie / cookie 字符串更新内部 cookie 存储"""
        for part in cookie_str.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            k, _, v = part.partition("=")
            self.cookies[k] = v

    def _cookie_header(self):
        parts = []
        for k in ("serviceToken", "cUserId", "mobileId",
                  f"{SID}_ph", f"{SID}_slh"):
            if self.cookies.get(k):
                parts.append(f"{k}={self.cookies[k]}")
        return ";".join(parts)

    # ---------- 登录（验证码流程） ----------
    def login_start(self, username, password):
        """发起登录：密码登录 → 返回会话（需要验证码则带 context）。"""
        st, body, _ = self._passport_request(
            f"{PASSPORT_URL}/pass/serviceLogin?sid={SID}&_json=true")
        resp = self._parse_json(body)
        qs, sign, callback = resp["qs"], resp["_sign"], resp["callback"]

        data = {"_json": "true", "qs": qs, "sid": SID, "_sign": sign,
                "callback": callback, "user": username,
                "hash": hashlib.md5(password.encode()).hexdigest().upper()}
        st, body, hdrs = self._passport_request(
            f"{PASSPORT_URL}/pass/serviceLoginAuth2",
            urlencode(data).encode())
        resp = self._parse_json(body)
        if resp.get("code") != 0:
            raise MicarAPIError(f"登录失败: {resp.get('description')}")

        notify_url = resp.get("notificationUrl", "")
        if not notify_url:
            return {"need_code": False, "session": None}

        st, body, _ = self._passport_request(notify_url)
        context = parse_qs(urlparse(notify_url).query).get("context", [""])[0]

        st, body, _ = self._passport_form(
            f"{PASSPORT_URL}/identity/list",
            params={"sid": SID, "supportedMask": "0", "_locale": "zh_CN", "context": context})
        try:
            self._parse_json(body)
        except Exception:
            pass

        st, body, _ = self._passport_request(
            f"{PASSPORT_URL}/identity/auth/verifyPhone?_flag=4&_json=true")

        st, body, _ = self._passport_form(
            f"{PASSPORT_URL}/identity/auth/sendPhoneTicket",
            params={"sid": SID, "context": context, "_locale": "zh_CN"},
            data={"retry": "0", "icode": "", "_json": "true"})
        try:
            jv = self._parse_json(body)
            if jv.get("code") != 0:
                raise MicarAPIError(f"验证码发送失败: {jv.get('desc') or jv.get('description') or body[:80]}")
        except MicarAPIError:
            raise
        except Exception:
            _LOGGER.debug("sendPhoneTicket 响应解析失败: %s", body[:120])

        return {
            "need_code": True,
            "session": {"context": context, "cookie": self.cookies.copy()},
        }

    def login_verify(self, code, session):
        """提交验证码 → 完成登录 → 返回 passToken/cUserId/userId。"""
        context = session["context"]
        vp = {"_flag": "8", "_json": "true", "sid": SID,
              "context": context, "mask": "0", "_locale": "zh_CN"}
        vd = {"_flag": "8", "ticket": code, "trust": "false", "_json": "true", "ick": ""}
        st, body, hdrs = self._passport_form(
            f"{PASSPORT_URL}/identity/auth/verifyPhone",
            params=vp, data=vd)
        try:
            jv = self._parse_json(body)
        except Exception:
            jv = {}
        loc = jv.get("location") or hdrs.get("Location", "")
        if not loc:
            raise MicarAPIError(f"验证码错误或会话过期: {body[:120]}")

        cur = loc
        for _ in range(6):
            st, body, hdrs = self._passport_request(cur)
            nxt = hdrs.get("Location", "")
            if not nxt:
                break
            cur = nxt
        for c in self._cj:
            self.cookies[c.name] = c.value

        pass_token = self.cookies.get("passToken", "")
        c_user_id = self.cookies.get("cUserId", "")
        user_id = self.cookies.get("userId", "")
        if not pass_token:
            raise MicarAPIError("登录完成但未拿到 passToken")
        return {
            "passToken": pass_token,
            "cUserId": c_user_id,
            "userId": user_id,
        }

    # ---------- 续期（passToken → 280 token） ----------
    def refresh_token(self, pass_token, user_id="", device_id=APP_DEVICE_ID):
        """passToken → serviceLogin → clientSign → 280 token + ph/slh"""
        if not user_id:
            user_id = self.cookies.get("userId", "")
        cookie_str = f"passToken={pass_token};userId={user_id};deviceId={device_id}"
        url = (f"{PASSPORT_URL}/pass/serviceLogin?_json=true"
               f"&appName=com.mi.car.mobile&sid={SID}&_locale=zh_CN")
        st, body, hdrs = self._request(url, headers={"Cookie": cookie_str})
        resp = self._parse_json(body)
        if resp.get("code") != 0:
            raise MicarAPIError(f"passToken 续期失败: {resp.get('description')}")
        nonce, ssec, loc = resp.get("nonce"), resp.get("ssecurity"), resp.get("location")
        if not (nonce and ssec and loc):
            raise MicarAPIError(f"续期响应缺字段: {list(resp.keys())}")
        nsec = f"nonce={nonce}&{ssec}"
        client_sign = base64.b64encode(hashlib.sha1(nsec.encode()).digest()).decode()
        sts_url = loc + "&clientSign=" + quote(client_sign)
        st, body, hdrs = self._request(sts_url)
        for key in ("Set-Cookie",):
            if hdrs.get(key):
                self._set_cookies(hdrs[key])
        service_token = self.cookies.get(f"{SID}_serviceToken") or self.cookies.get("serviceToken", "")
        if not service_token:
            raise MicarAPIError("续期完成但未拿到 serviceToken")
        if len(service_token) != 280:
            _LOGGER.warning("serviceToken 长度 %s（预期 280）", len(service_token))
        return {
            "serviceToken": service_token,
            "cUserId": self.cookies.get("cUserId", ""),
            "ph": self.cookies.get(f"{SID}_ph", ""),
            "slh": self.cookies.get(f"{SID}_slh", ""),
        }

    # ---------- 车辆 ----------
    def get_vehicles(self):
        """车辆列表 → vid（服务端要求 camelCase 键）。"""
        body = {
            "viewList": ["SIDE_VIEW_DARK", "TOP_VIEW_DARK", "OBLIQUE_VIEW_HALF"],
            "deviceAppVersion": "2.7.0",
            "deviceModel": "2509FPN0BC",
            "deviceOsType": "android",
            "deviceOsVersion": "BP2A.250605.031.A3",
            "deviceVendor": "Xiaomi",
        }
        data = self._api_post(EP_USER_CAR_LIST, body)
        return data.get("data") or {}

    def get_vehicles_list(self):
        """车辆列表（ownCarList）"""
        data = self.get_vehicles()
        return data.get("ownCarList") or []

    def query_status(self, iids):
        """查询车辆状态（subscriptions）"""
        body = {
            "ignoreSessionDurationLimit": False,
            "iids": iids,
            "mobileId": self.mobile_id,
            "subId": self.mobile_id + "carControl",
            "topics": ["naviReportRegular"],
            "vid": self.vid,
            **self.device_headers,
        }
        data = self._api_post(EP_SUBSCRIPTIONS, body)
        return data.get("data", {}).get("properties", [])

    def control(self, iid, value):
        """控制车辆（properties 通道——Base 版仅空调温度/开关）。"""
        from .const import CONTROL_KNOWN
        item = CONTROL_KNOWN.get(iid, {})
        channel = item.get("channel", "properties")
        request_id = str(uuid.uuid4()) + "-mobile"
        if channel == "actions":
            # actions 通道请求体需包含 vid 与设备字段（与 App 请求一致），缺失会导致指令不被执行
            body = {
                "iid": iid,
                "in": ([{"name": item.get("param", ""), "value": value}] if item.get("param") else []),
                "mobileId": self.mobile_id,
                "requestId": request_id,
                "vid": self.vid,
                "deviceAppVersion": self.device_headers.get("deviceappversion", "2.7.0"),
                "deviceModel": self.device_headers.get("devicemodel", "2509FPN0BC"),
                "deviceOsType": "android",
                "deviceOsVersion": self.device_headers.get("deviceosversion", "BP2A.250605.031.A3"),
                "deviceVendor": self.device_headers.get("devicevendor", "Xiaomi"),
            }
            return self._api_post(EP_ACTIONS, body)
        body = {
            "mobileId": self.mobile_id,
            "params": [{"iid": iid, "value": value, "vid": self.vid}],
            "requestId": request_id,
            "deviceAppVersion": self.device_headers["deviceappversion"],
            "deviceModel": self.device_headers["devicemodel"],
            "deviceOsType": "android",
            "deviceOsVersion": self.device_headers["deviceosversion"],
            "deviceVendor": self.device_headers["devicevendor"],
        }
        return self._api_post(EP_PROPERTIES, body)

    def _api_post(self, path, body):
        """API POST（无 license 校验——Base 版直接放行）。"""
        headers = dict(self.device_headers)
        headers["cookie"] = self._cookie_header()
        headers["request-source"] = "app"
        headers["Content-Type"] = "application/json; charset=utf-8"
        payload = json.dumps(body).encode()
        headers["Content-Length"] = str(len(payload))
        req = urllib.request.Request(BASE_URL + path, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body_txt = e.read().decode(errors="replace")
            if e.code == 401:
                raise MicarAPIError(f"token 失效(401): {body_txt[:100]}") from e
            raise MicarAPIError(f"HTTP {e.code}: {body_txt[:150]}") from e
