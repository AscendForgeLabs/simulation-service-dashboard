# Simulation Service Dashboard

HIP 仿真管理台，用于操作 [simulation-service](https://github.com/AscendForgeLabs/simulation-service)：

- 上传包套 STEP 与目标零件 STEP，创建仿真任务
- 轮询任务状态和运行日志
- 展示烧制温度/压力过程
- 聚合展示 Ansys 结果、区域致密度和验收检查
- 下载 `model.inp`、报告和其他工件
- 逐条查看发往 Ansys 服务的 HTTP 请求与响应审计

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DASHBOARD_SIMULATION_SERVICE_URL` | `http://dev.htcmc.site` | simulation-service 地址 |
| `DASHBOARD_POLLING_INTERVAL_SECONDS` | `3` | 浏览器轮询间隔 |
| `DASHBOARD_REQUEST_TIMEOUT_SECONDS` | `30` | 后端代理请求超时 |

## 本地开发

```bash
uv sync
uv run simulation-service-dashboard
```

打开 `http://localhost:8080`。

如需连接本地 simulation-service：

```bash
DASHBOARD_SIMULATION_SERVICE_URL=http://localhost:8000 uv run simulation-service-dashboard
```

## Docker

```bash
docker build -t simulation-service-dashboard .
docker run --rm -p 8080:8080 \
  -e DASHBOARD_SIMULATION_SERVICE_URL=http://simulation-service:8000 \
  simulation-service-dashboard
```

## 验证

```bash
uv run pytest
uv run ruff check .
uv run mypy .
```
