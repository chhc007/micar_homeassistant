"""常量：API 端点、配置键（Base 版——精简，无 control/license）。"""

DOMAIN = "micar_base"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_CODE = "code"
CONF_PASS_TOKEN = "passToken"
CONF_CUSER_ID = "cUserId"
CONF_USER_ID = "userId"
CONF_MOBILE_ID = "mobileId"
CONF_VID = "vid"
CONF_CAR_MODEL = "carModel"

DEFAULT_SCAN_INTERVAL = 120  # 秒

# API
BASE_URL = "https://mobile.iccc.xiaomiev.com"
PASSPORT_URL = "https://account.xiaomi.com"
SID = "iccc_app_api"
APP_DEVICE_ID = "YSFTVmttfxS0t_G-"
UA = "Mozilla/5.0 (Linux; Android 16; 2509FPN0BC) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

# 端点
EP_SUBSCRIPTIONS = "/mobile/clientbusiness/IcccCarControlService/subscriptions"
EP_PROPERTIES = "/mobile/clientbusiness/IcccCarControlService/properties"
EP_ACTIONS = "/mobile/clientbusiness/IcccCarControlService/actions"
EP_USER_CAR_LIST = "/mobile/clientbusiness/IcccUserAuthService/getUserCarListV3"

# Free 版轮询 iid（空调 + 电量/续航 + 门锁 + GPS 定位，8 个）
FREE_IIDS = [
    "7.1.1",   # 空调开关
    "7.2.3",   # 目标温度
    "7.2.1",   # 车内温度
    "4.4.1",   # 电量(%)
    "4.4.3",   # 剩余续航(km)
    "2.1.3",   # 门锁状态
    "13.1.9",  # 经度
    "13.1.10", # 纬度
]

# 控制字典（仅 Free 版公开的控制；支持 api.control 路由）
# ⚠️ 值域来自 App 枚举（2026-08-12 确认）：
#   DoorLockStatus（门锁）: 1=解锁 2=锁定
#   OperateSwitchStatus（空调）: 0=CLOSE 1=OPEN
CONTROL_KNOWN = {
    "7.1.1": {"name": "空调开关", "channel": "properties", "values": {0: "关", 1: "开"}},
    "7.2.3": {"name": "目标温度", "channel": "properties", "values": {}},
    "2.1.3": {"name": "车门锁", "channel": "properties", "values": {1: "解锁", 2: "锁定"}},
}

# 实体图标（按名称关键词匹配，mdi）
ICON_RULES = [
    (("空调",), "mdi:air-conditioner"),
    (("位置",), "mdi:map-marker"),
]


def icon_for_name(name: str) -> str:
    """按名称返回 mdi 图标"""
    for keywords, icon in ICON_RULES:
        if any(k in name for k in keywords):
            return icon
    return "mdi:car-electric"
