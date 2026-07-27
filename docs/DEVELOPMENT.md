# Development

## 运行基线

V1 正式基线为 macOS、Python 3.9.6、pip 和 venv。`pyproject.toml` 必须保持 `>=3.9,<3.10`，不得引入 `str | None`、结构化模式匹配或其他 Python 3.10+ 语法。Docker 可选且当前未验证，uv 不是默认安装工具。

## 代码规范

保持 Data → Feature → Strategy → Decision → Execution 依赖方向。新增外部集成应实现抽象接口，并以超时、失败记录和最小权限为默认行为。

## 测试规范

每个安全边界必须有负向测试。修复缺陷时先添加复现测试；提交前运行 `pytest`、环境检查和 smoke test。测试不得访问真实 Telegram、OpenD 或交易账户。

## 数据库迁移

模型变更必须新增 Alembic revision，不得改写已发布迁移。开发环境执行 `alembic upgrade head`；迁移需同时验证全新数据库。

## 新模块接入

1. 定义清晰接口和输入输出模型。
2. 配置通过 `Settings` 注入，禁止模块直接读取 Secret 并打印。
3. 外部 I/O 设置超时与有限重试。
4. 交易模块只允许 `INTERNAL_PAPER` 或 `MOOMOO_PAPER`。
5. 添加单元、集成及安全回归测试。

Moomoo 模块测试必须使用 Mock，不依赖真实 OpenD。新增 SDK 调用时必须验证 Context 关闭，并扫描确认没有解锁或订单相关调用。

历史行情新增周期或数据源时，必须先扩展统一枚举和映射，禁止将SDK常量散布到业务层。价格使用`Decimal`/数据库`Numeric`；datetime必须带时区。默认测试不得连接OpenD，真实检查应标记为`live_moomoo`并单独运行。

实时行情默认测试使用Mock Provider，不依赖OpenD。回调禁止执行数据库事务，只允许轻量标准化和有界队列入队。真实只读验收可运行 `python scripts/start_realtime.py --symbols US.QQQ US.SOXL --duration 60`；夜盘和扩展时段无成交不视为代码失败。

## Git 提交

保持小而明确的提交，使用 Conventional Commits，例如 `feat: initialize safe paper trading platform foundation`。提交前检查 `.env`、数据库和日志均未进入暂存区。
