# ScopeReceipt

**AI 说它读完了所有文件？让它拿出访问记录。**

ScopeReceipt 用于“请完整审阅这份文件夹”这样的任务。它清点材料，记录通过工具
输出的文本行或 PDF 页，列出遗漏范围。它不能证明模型已经理解、记住或核实内容。

## 30 秒演示

在项目目录运行：

```bash
python scripts/demo.py
```

演示使用虚构材料：读取 6 行中的 2 行后，严格验收失败；补读剩余 4 行后通过。
无需 API Key、模型或安装依赖。演示会自动清理临时记录。

## 使用

```bash
python -m pip install -e .
# PDF 支持可选
python -m pip install -e '.[pdf]'

python -m scopereceipt --state C:/reviews/receipts scan C:/reviews/documents
python -m scopereceipt --state C:/reviews/receipts read notes.md --start 1 --end 20
python -m scopereceipt --state C:/reviews/receipts report --strict
```

支持文件夹、单文件和 ZIP。文本按行、PDF 按页计数；序号从 1 开始，包含结束位置。
`--strict` 返回 0 表示覆盖通过、1 表示不完整、2 表示错误。

## MCP 接入

完成扫描后，让 MCP 客户端启动：

```bash
python -m scopereceipt.mcp_server --state C:/reviews/receipts
```

提供 `scope_inventory`、`scope_read`、`scope_report` 三个工具。Agent 不需要手填
访问记录，也不能通过 MCP 重新扫描或缩小审计范围。具体配置见 [MCP.md](MCP.md)。

## v0.2.0 的变化

- 新增无需第三方运行依赖的 MCP stdio 服务。
- 报告列出缺失行/页的连续范围，重叠读取不会重复计数。
- 检测扫描后新增、删除、修改的文件，避免误报完整。
- 每次扫描生成新 run_id，旧记录无法混入新一轮审阅。
- 输出成功写入并刷新后才保存记录；输出失败不能增加覆盖率。
- 新增跨平台演示、真实子进程协议测试和可重建的 README 演示图。

## 能力边界

COMPLETE 只表示当前清单中的可支持文本单元已经通过接口输出。它不证明客户端
或模型确实收到了全部内容；客户端仍可能截断输出。PDF 图片、图表、扫描页不在
文本读取的验证能力内。空白/扫描 PDF 页保持未覆盖；空文本文件为 0 个单元。

软链接、`.git`、`.venv`、`venv`、`node_modules`、`__pycache__` 和
`.scopereceipt` 目录不进入文件夹清单。不支持的文件格式会列出并阻止完整覆盖。

工具本身不联网，但 MCP 客户端可能把返回的文本发送给模型提供商。
本地记录没有签名；拥有文件系统权限的 Agent 可以绕过工具或改写记录。
每个记录目录只支持一个写入者。尚未完成桌面客户端的逐一兼容性验证。

[English README](../README.md) · [MIT License](../LICENSE)
