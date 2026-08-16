# 免费版补 coordinateType iid（13.1.8）——GPS 转换不生效修复

## 项目
/home/hermes/workspace/projects/python/micar_homeassistant/（免费版，custom_components/micar_base）

## 背景（部署验证发现）
GPS 坐标修复（46c0571，按 coordinateType 条件转换 GCJ→WGS）部署后 device_tracker
仍显示原始坐标（未转换）。**根因**：免费版 `FREE_IIDS`（const.py）只含 13.1.9（经度）/
13.1.10（纬度），**不含 13.1.8（coordinateType）** → subscriptions 响应没有 13.1.8 →
coordinator.properties.get("13.1.8") = None → device_tracker 转换条件（==2 才转）不满足。

## 修改
- const.py `FREE_IIDS` 增加 `"13.1.8"`（坐标类型，注释：coordinateType 用于 GPS 坐标
  GCJ→WGS 条件转换判断），放在 13.1.9/13.1.10 旁边。
- 其他不动。

## 验证
- python -m py_compile；git 提交中文信息。
- 部署由 Hermes 负责（同步 NAS + HA 重启 + 验证 device_tracker 显示转换后坐标）。

## 完成后报告
- 改动摘要 + git 提交哈希。
