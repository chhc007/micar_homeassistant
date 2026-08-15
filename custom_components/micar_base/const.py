"""常量：API 端点、配置键（Base 版——精简）。"""

DOMAIN = "micar_base"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_CODE = "code"
CONF_PASS_TOKEN = "passToken"
CONF_CUSER_ID = "cUserId"
CONF_USER_ID = "userId"
CONF_MOBILE_ID = "mobileId"
CONF_DEVICE_ID = "deviceId"
CONF_VID = "vid"
CONF_CAR_MODEL = "carModel"
CONF_CAR_PLATE = "carPlate"
CONF_CAR_NAME = "carName"
CONF_MODE = "mode"
# 登录模式：master=主账号（填手机 App 设备 ID）；shared=共享账号（设备 ID 自动生成）
MODE_MASTER = "master"
MODE_SHARED = "shared"

DEFAULT_SCAN_INTERVAL = 20  # 秒（免费版测试期 20s 轮询）

# API
BASE_URL = "https://mobile.iccc.xiaomiev.com"
PASSPORT_URL = "https://account.xiaomi.com"
SID = "iccc_app_api"
# 历史遗留：开发者自己的 App 设备 ID。仅用于旧版配置（缺少 deviceId 时）的兜底兼容。
# 新配置：主账号模式填写用户手机小米汽车 App 的 deviceId；共享账号模式自动生成 App 风格 deviceId。
APP_DEVICE_ID = "YSFTVmttfxS0t_G-"
UA = "Mozilla/5.0 (Linux; Android 16; 2509FPN0BC) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

# 端点
EP_SUBSCRIPTIONS = "/mobile/clientbusiness/IcccCarControlService/subscriptions"
EP_PROPERTIES = "/mobile/clientbusiness/IcccCarControlService/properties"
EP_ACTIONS = "/mobile/clientbusiness/IcccCarControlService/actions"
EP_REFRESH_RESULTS = "/mobile/clientbusiness/IcccCarControlService/refreshResults"
EP_USER_CAR_LIST = "/mobile/clientbusiness/IcccUserAuthService/getUserCarListV3"
EP_PARKING_SPOT = "/mobile/datasync/widget/parking-spot/query"

# Free 版轮询 iid（空调 + 电量/续航 + 累计里程/档位 + 门锁 + 胎压 + 车窗 + 除霜状态 + GPS 定位 + 远程启动状态/时间，22 个）
FREE_IIDS = [
    "7.1.1",   # 空调开关
    "7.1.4",   # 空调除霜状态
    "7.2.3",   # 目标温度
    "7.2.1",   # 车内温度
    "4.4.1",   # 电量(%)
    "4.4.3",   # 剩余续航(km)
    "2.1.3",   # 门锁状态
    "2.8.3",   # 电动后备箱状态
    "9.1.1",   # 主驾胎压(bar)
    "9.2.1",   # 副驾胎压(bar)
    "9.3.1",   # 左后胎压(bar)
    "9.4.1",   # 右后胎压(bar)
    "5.1.1",   # 主驾车窗位置(%)
    "5.2.1",   # 副驾车窗位置(%)
    "5.3.1",   # 左后车窗位置(%)
    "5.4.1",   # 右后车窗位置(%)
    "13.1.9",  # 经度
    "13.1.10", # 纬度
    "13.2.1",  # 累计里程(km)
    "13.6.1",  # 档位(P/R/N/D)
    "13.11.4", # 远程启动状态(0=未启动 1=已启动)
    "13.11.5", # 最近启动时间(毫秒时间戳)
]

# 控制字典（仅 Free 版公开的控制；支持 api.control 路由）
CONTROL_KNOWN = {
    "7.1.1": {"name": "空调开关", "channel": "properties", "values": {0: "关", 1: "开"}},
    "7.2.3": {"name": "目标温度", "channel": "properties", "values": {}},
    "2.1.3": {"name": "车门锁", "channel": "properties", "values": {1: "解锁", 2: "锁定"}},
    # 电动后备箱（properties 通道）：0=关 6=开启；2.8.3 在 FREE_IIDS 订阅列表内，select 直接回读状态
    "2.8.3": {"name": "电动后备箱", "channel": "properties", "platform": "select",
              "values": {0: "关", 6: "开启"}},
    # 寻车（actions 通道，workMode）：闪灯 / 鸣笛两种动作
    "13.1.1": {"name": "寻车", "channel": "actions", "param": "workMode", "platform": "button",
               "values": {1: "闪灯", 3: "鸣笛"},
               "buttons": [
                   {"name": "寻车闪灯", "value": 1},
                   {"name": "寻车鸣笛", "value": 3},
               ]},
    # 车窗控制（actions 通道，position）：0=全关 1=通风 8=全开；
    # 无自身状态回读，select 状态由四车窗位置（5.1.1-5.4.1）推导（status_mode=windows）
    "5.5.1": {"name": "车窗控制", "channel": "actions", "param": "position", "platform": "select",
              "values": {0: "全关", 1: "通风", 8: "全开"},
              "status_mode": "windows"},
    # 空调除霜（actions 通道，status）：0=关 2=开；无自身状态回读，
    # switch 状态由 7.1.4 hvacDefrostStatus 反映（status_iid）
    "13.10.1": {"name": "空调除霜", "channel": "actions", "param": "status", "platform": "switch",
                "values": {0: "关", 2: "开"},
                "status_iid": "7.1.4"},
    # 远程启动（actions 通道，无参数 in:[]）；状态回读 13.11.4 remoteBootStatus（0=未启动 1=已启动）
    "13.11.3": {"name": "远程启动", "channel": "actions", "platform": "button",
                "values": {1: "启动"}},
}

# sensor 值域映射（iid → {原始值: 显示文字}）
SENSOR_VALUE_MAPS = {
    # 档位 GearStatus：0=P 1=R 2=N 3=D
    "13.6.1": {0: "P", 1: "R", 2: "N", 3: "D"},
    # 远程启动状态 RemoteBootStatus：0=未启动 1=已启动
    "13.11.4": {0: "未启动", 1: "已启动"},
}

# 实体图标（按名称关键词匹配，mdi）
ICON_RULES = [
    (("空调",), "mdi:air-conditioner"),
    (("车窗", "窗"), "mdi:car-side"),
    (("后备箱", "箱"), "mdi:car-back"),
    (("除霜",), "mdi:car-defrost-front"),
    (("鸣笛", "喇叭"), "mdi:bullhorn"),
    (("寻车",), "mdi:map-marker"),
    (("位置",), "mdi:map-marker"),
    (("里程",), "mdi:counter"),
    (("档位",), "mdi:car-shift-pattern"),
    (("启动",), "mdi:power"),
    (("车位",), "mdi:parking"),
]


def icon_for_name(name: str) -> str:
    """按名称返回 mdi 图标"""
    for keywords, icon in ICON_RULES:
        if any(k in name for k in keywords):
            return icon
    return "mdi:car-electric"
