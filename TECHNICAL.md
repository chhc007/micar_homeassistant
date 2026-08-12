# micar_homeassistant 技术文档（免费版）

## 1. 项目定位

| 项目 | 定位 | 仓库 |
|---|---|---|
| **micar_homeassistant（本仓库）** | 免费版引流（domain `micar_base`），无 license | `chhc007/micar_homeassistant`（**公开**） |
| micar-ha | 完整版/付费版（domain `micar`），license 授权 | `chhc007/micar-ha`（**私有**） |

两仓库完全独立、互不依赖，**不做迁移逻辑**（用户 2026-08-12 明确：升级=删免费版→装完整版→重新登录，unique_id 反正会变、登录不麻烦）。

## 2. 功能（免费版）

| 平台 | 内容 | iid |
|---|---|---|
| sensor | 电量(%)、剩余续航(km) | 4.4.1、4.4.3 |
| climate | 空调开关 + 目标温度 + 当前温度 | 7.1.1、7.2.3、7.2.1 |
| lock | 车门锁（1=解锁 2=锁定） | 2.1.3 |
| device_tracker | GPS 位置（**GCJ-02→WGS-84 转换后**） | 13.1.9/13.1.10 |

轮询间隔：**20 秒**（`DEFAULT_SCAN_INTERVAL = 20`，测试期）。

## 3. 关键坑点（2026-08-12 实测）

### 3.1 空调设定温度（ClimateEntity）
- HA 读取的目标温度属性名是 **`target_temperature`**（不是 `temperature`）——`ClimateEntity.state_attributes()` 输出 `ATTR_TEMPERATURE` 读 `self.target_temperature`（源码确认 2026.7.2）。
- 必须声明 `_attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE`，否则 UI 无温度滑块。
- **两处缺一不可**：属性名错 → 永远 None；不声明 feature → HA 不输出。
- API 设置温度：properties 通道设 7.2.3 传温度数值，key 用 `temperature`。

### 3.2 坐标转换（GCJ-02 → WGS-84）
- **小米 API 返回 GCJ-02（火星坐标）**，不是 WGS-84。
- App 用高德（GCJ-02 底图）直接显示 → 正确；HA/OSM（WGS-84 底图）直接显示 → **偏东南约 470m**。
- `device_tracker.py` 内置 `gcj02_to_wgs84()` 转换（标准算法），latitude/longitude 返回前转换。
- 验证教训：OSM 反查路名可能"看起来对"（路很长），必须用 App 实车对照。

### 3.3 轮询周期
- 120s → 20s（2026-08-12 测试期调整）。注意：20s 对小米 API 请求频率更高，注意限流。

## 4. 部署到 NAS

```bash
# 上传免费版组件
scp -r custom_components/micar_base/ shield@192.168.123.146:/vol4/1000/DockerConfig/homeassistant/config/custom_components/
# 重启 HA（REST API 更干净，无需 sudo）
curl -X POST -H "Authorization: Bearer $HASS_TOKEN" http://192.168.123.144:8123/api/services/homeassistant/restart -d '{}'
```

**免费版配置（config entry）可手动创建**（复制完整版凭证，免重新登录）：
- 备份 `.storage/core.config_entries` → 复制 micar entry 的 `passToken/cUserId/userId/mobileId/vid/username` → 新建 domain=`micar_base` entry（无 license）→ 重启 HA。
- 实体 entity_id 是中文拼音前缀（如 `sensor.xiao_mi_qi_che_dian_liang`），不是 `micar_base_*`！查实体用拼音 id。

## 5. 商业信息

- README 含打赏引导：60=高级版（300+ 属性全解锁）/ 200=远程安装调试 / 500=定制车型功能适配。
- 联系作者：B站 https://space.bilibili.com/27199707（用户本人）。
- 收款码：assets/alipay_qr.jpg（支付宝，240px 展示）。

## 6. License

MIT（LICENSE 文件）。注意：完整版（micar-ha）是私有付费的，勿把完整版代码公开。
