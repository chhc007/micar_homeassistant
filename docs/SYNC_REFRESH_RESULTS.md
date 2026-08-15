# 免费版同步：refreshResults 快速刷新 + 补偿刷新

## 项目
/home/hermes/workspace/projects/python/micar_homeassistant/（免费版/正式版，domain `micar_base`，对外发布）
组件目录：custom_components/micar_base/

## 任务
把完整版（/home/hermes/workspace/projects/python/micar-ha/custom_components/micar/）
已实现并线上验证的「refreshResults 定向刷新 + 确认失败补偿刷新」机制同步移植到免费版。

## 完整版参考实现（已部署验证，按文件对照移植）

1. **api.py** → 新增 `refresh_results(iids)` 方法：
   - POST `/mobile/clientbusiness/IcccCarControlService/refreshResults`（常量 EP_REFRESH_RESULTS）
   - body: `{"iids": list, "mobileId": self.mobile_id, "vid": self.vid,
     "deviceAppVersion": ..., "deviceModel": ..., "deviceOsType": "android",
     "deviceOsVersion": ..., "deviceVendor": ...}`（与现有 control/query_status 一致，无 requestId）
   - 解析响应 `data.iids` → 返回 `{iid: value}` dict（value 保留原始类型，忽略 timestamp）
   - 失败返回 None 或抛 MicarAPIError（按 api.py 现有风格）
2. **const.py** → 加 `EP_REFRESH_RESULTS` 常量（端点路径）
3. **coordinator.py** → 加：
   - `_refresh_iids(iids)`：调 `refresh_results` 定向刷新 → 成功合并进 self.properties +
     `async_update_listeners()`；失败/None 回退一次 `async_request_refresh()`（subscriptions 全量兜底）
   - `schedule_control_refresh()`：确认失败补偿（hass.async_call_later +5/+15/+30s 各一次
     _refresh_iids，防抖：已有未执行计划时不重复排）
   - `async_confirm_control` / `_poll_confirm`：快路径与轮询改用 `_refresh_iids([iid])`
     替代每次全量 async_request_refresh；确认失败时记录 `_last_confirm_iids` 并调
     schedule_control_refresh()
   - 若免费版无 `_poll_confirm`（旧实现直接在 async_confirm_control 内轮询），
     参照完整版 coordinator.py 结构对齐
4. **lock.py / climate.py**：调用方式不变（async_confirm_control），自动受益

## 注意事项
- 免费版平台少（lock/climate 为主，另有 button/select/switch 文件——按现状存在与否处理），
  只改存在的文件；lock/climate 已接 confirm 的保持调用不变。
- **免费版是正式版（对外发布）**：代码质量要求高，不引入完整版专属逻辑
  （license、stats、iid_known 等免费版没有的不要搬）。
- 保持免费版其他功能不变（多车、双模式登录等）。
- 改动后 python -m py_compile 全量通过。
- git 提交中文信息，提交前 git status 确认只改本任务相关文件。

## 完成后报告
- 改动摘要 + git 提交哈希 + 说明免费版哪些平台受益。
- 部署由 Hermes 负责（同步 NAS + HA 重启验证），无需 coder 操作。
