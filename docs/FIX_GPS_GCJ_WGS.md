# GPS 坐标偏移修复：按 coordinateType 条件转换 GCJ→WGS

## 项目
/home/hermes/workspace/projects/python/micar_homeassistant/（免费版，custom_components/micar_base，device_tracker.py）
/home/hermes/workspace/projects/python/micar-ha/（完整版，custom_components/micar，device_tracker.py 及坐标相关）

## 根因（抓包实证，2026-08-16 15:18）
- 小米 API 返回的坐标 **coordinateType（13.1.8）= 2 时为高德 GCJ-02 加密坐标**，= 0 时为标准 WGS-84。
- 集成当前**不转换**直接当 WGS-84 用 → coordinateType=2 时地图位置偏东南约 480 米
  （嘉兴一带 GCJ→WGS 偏移 ≈ 北 260m + 西 410m）。
- 用户实测确认：转换后位置（西北 480 米）正是实际位置。
- 历史折线问题（08-14）同为 coordinateType 跳变（0↔2）导致——**条件转换后输出统一 WGS，
  无论 coordinateType 怎么跳，位置稳定，偏移+折线同时解决**。

## 修复（免费版 + 完整版 device_tracker.py 同步）

1. 新增 **GCJ-02 → WGS-84 转换函数**（标准近似算法，~30 行，免费版/完整版各内置一份，
   或放公共 util 由 device_tracker 引用）：
   - 输入 lat/lon（GCJ），输出 WGS-84 lat/lon。
   - 经典算法（6378245 / 0.00669342162296594323 / transformLat/transformLon，含境外判断）。
2. **device_tracker latitude/longitude 属性**：
   - 读取原始值后，检查 `coordinator.properties.get("13.1.8")`（coordinateType）：
     - `== 2`（高德 GCJ）→ 调用 gcj2wgs 转换后返回；
     - `== 0`（标准）或 None/未知 → 直接返回原始值（不转换）。
3. 完整版如有坐标 sensor（经度/纬度）同样处理（如存在对应属性/实体）。
4. 免费版 device_tracker 当前 iid：LATITUDE_IID="13.1.10" / LONGITUDE_IID="13.1.9"
   （完整版可能不同，按各自代码现状）。

## 验证
- python -m py_compile；git 提交中文信息（两个仓库分开）。
- 部署由 Hermes 负责（同步 NAS + HA 重启 + 地图验证：当前位置应显示在
  （30.775856, 120.672364）附近（秀园路1551号一带），不再偏东南 480 米）。

## 完成后报告
- 改动摘要 + git 提交哈希（两个仓库）。
