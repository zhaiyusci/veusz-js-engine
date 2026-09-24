# Veusz 内置 Python ↔ HTTP ↔ Firefox：独立端到端实验

此实验将此前 `../browser-http/` 的 HTTP 服务、请求队列和 MathJax 验收套件直接加载到
已安装的 `veusz.exe` 进程内。没有外部 Python 服务进程，也不调用 QuickJS 后端。
不修改生产插件或现有 feature；用命令行临时加载实验插件，不将其加入插件偏好设置。

## 运行

在项目根目录的 PowerShell 中：

```powershell
.\experiments\veusz-browser-http\run.ps1
```

默认使用 `C:\Program Files\Veusz\veusz.exe` 和
`C:\Program Files\Mozilla Firefox\firefox.exe`，可通过 `-Veusz`、`-Browser` 指定路径。
PowerShell 仅启动 Veusz、等待退出并检查 JSON 状态；不需要独立 Python 安装。

启动器为这个子进程设置 `QT_QPA_PLATFORM=offscreen`，避免打开实验 Veusz 窗口，
并通过 `--veusz-plugin` 临时加载 `plugin.py`。Firefox 使用新的独立配置目录和无头模式。
不要把 `plugin.py` 添加到正常使用的 Veusz 偏好设置：它会在验收后退出所处的 Veusz 进程。

已有 Firefox/Veusz 会话不被选中或关闭。实验只清理自己创建的进程树。
当前启动与进程清理实现面向 Windows。受限沙箱中的 Firefox 曾无法连接且清理被拒，
因此本次运行经批准在沙箱外进行；没有关闭 Firefox 自身的安全沙箱。

## 实际调用链

```text
PowerShell（只启动和检查结果）
  └─ veusz.exe，内置 Python 3.13.12
       ├─ Qt 主线程事件循环 + 完成后的 SVG 验证/绘图
       ├─ 实验调度线程：复用 Bridge / run_suite
       ├─ Python ThreadingHTTPServer，127.0.0.1 随机端口
       └─ 独立 Firefox 156.0.1
            └─ HTTP 页面 + Worker + 原样 MathJax feature/bundle/fonts
```

HTTP 服务及调度线程都在 Veusz 内；等待浏览器的阻塞 RPC 不占用 Qt 主线程。
Qt 定时器检测实验完成，在主线程使用 `QSvgRenderer`、`QImage`、`QPainter` 保存 PNG。
不会把收到的 SVG 自动插入用户文档。

## 已验证

在本机 Veusz 4.2.1 / Firefox 156.0.1 上完整通过：

- `sys.executable` 为 `C:\Program Files\Veusz\veusz.exe`，`sys.frozen=true`。
- HTTP 模块来自 Veusz 打包环境，服务所有者 PID 与 Veusz PID 相同。
- `veuszDescribe()` 正常返回；`veuszRender()` 返回有效 SVG。
- 首次按需加载 `mathjax.js`，切换 Asana 时按需加载 `fonts/mathjax-asana.js`。
- 分式、积分、重复分式、Asana 公式四份 SVG 与之前独立 Firefox 实验逐字节一致。
- Veusz 自带 Qt 接受全部四份 SVG，并成功生成 PNG；已人工查看积分和 Asana 预览。
- 实验期间 Qt 定时器持续触发；完成后 HTTP 关闭、专用 Firefox 退出、实验 Veusz 正常退出。

`output/results.json` 是总验收报告，包含宿主 Python、PID、浏览器 UA、请求耗时、
字节一致性、Qt 绘图结果和进程清理状态。`output/suite/` 保存原始 SVG 与复用套件结果，
`output/*.png` 为 Veusz Qt 实际绘制的预览。
复用套件的原始报告仍沿用旧版 standalone scope 描述，以总验收报告的 scope 为准。

第一次整链运行的四项端到端时间约为 212 / 18 / 8 / 66 ms，分别对应首次分式、积分、
缓存命中的重复分式和外部字体公式。仅作一次运行记录，不是统计基准，不含浏览器启动。
复跑会更新 `output/` 文件；以当次总报告的 `status=passed` 为准，不以旧 PNG 是否存在判断。

## 尚未验证的部分

这证明了“Veusz 内部 HTTP → 浏览器计算 → Veusz 收回 SVG → Qt 能画”整条技术路径，
**不等于已经接入 Veusz 文档绘制回调**。未实现：

- `{measure: ...}` 请求对应的 Qt 字体测量；当前样例不依赖它。
- 正式 `Runtime` 后端选择、文档异步重绘、跨窗口并发、缓存策略。
- 浏览器断线恢复、标签页休眠、运行中取消、批量性能测试。
- 不可信第三方 JS 的安全隔离（只加载本仓库可信脚本）。

HTTP 访问控制和资源白名单沿用 `../browser-http/server.py`。
若之前的 standalone SVG 基线文件存在则逐字节比较；缺失时仍可执行 SVG/Qt 验证，
但 `baseline_byte_matches` 不会包含相应项目，不能据此声称做过基线比较。
