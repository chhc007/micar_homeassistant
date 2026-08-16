# 正式版同步：空调极速制冷/制热 + 乐观置值 + confirm 防跳

## 项目
/home/hermes/workspace/projects/python/micar_homeassistant/（免费版/正式发布版，custom_components/micar_base）

## 背景（用户要求）
Pro 版（micar-ha）已实现并实车验证：空调极速制冷/制热开关 + 触发后乐观置值 +
confirm 不覆盖乐观值（防 on→off→on 跳）。用户要求**同步到正式版**。

参考 Pro 版实现（已部署验证）：
- const.py CONTROL_KNOWN 增加 7.7.13/7.7.12（Pro 提交 2778c90）
- switch.py 通用 MicarSwitch 乐观置值（Pro 提交 f0c038d）
- coordinator confirm 不覆盖乐观值（Pro 提交 cbaef1e）
可对照 /home/hermes/workspace/projects/python/micar-ha/custom_components/micar/ 对应实现。

## 需要改（micar_base）
1. **const.py CONTROL_KNOWN** 增加（参照 13.10.1 空调除霜的 switch 写法）：
   ```python
   "7.7.13": {"name": "空调极速制冷", "channel": "properties", "platform": "switch",
              "values": {0: "关", 1: "开"}},
   "7.7.12": {"name": "空调极速制热", "channel": "properties", "platform": "switch",
              "values": {0: "关", 1: "开"}},
   ```
2. **const.py FREE_IIDS** 增加 "7.7.13"（空调极速制冷状态）、"7.7.12"（空调极速制热状态）
   （不加则 subscriptions 拿不到状态，switch 无法回读）。
3. **switch.py** 通用 switch（MicarSwitch）async_turn_on/off 加**乐观置值**：
   控制后立即 `coordinator.properties[status_iid] = on_value/off_value` + `async_update_listeners()`
   （UI 立即显示意图状态；confirm 刷新覆盖真实状态）。参照 Pro 版 f0c038d 实现。
4. **coordinator.py** confirm 防跳：确认期间 **不覆盖乐观值**（先临时结果检查，匹配才写
   properties + update_listeners，重试耗尽失败才回退真实值）——参照 Pro 版 cbaef1e 实现。
   （免费版已有 _refresh_iids / async_confirm_control / schedule_confirm_control 结构，
   按 Pro 同样方式改造 confirm 内刷新逻辑。）

## 验证
- python -m py_compile；git 提交中文信息（仅 micar_homeassistant）。
- 部署由 Hermes 负责（同步 NAS + HA 重启 + 实车验证由用户执行）。

## 完成后报告
- 改动摘要 + git 提交哈希。
