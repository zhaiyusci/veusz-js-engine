# 浏览器 HTTP 计算服务：独立实验

不修改、不导入 `veusz_js_engine.py`，不修改任何已有 feature，也不使用 `qjs.dll`。
Python 标准库启动本地 HTTP 服务，真实浏览器的 Web Worker 执行仓库现有 JS，
通过 HTTP 长轮询取任务、POST 返回 JSON/SVG。没有 CDP、WebDriver、Node 或另行下载的浏览器。

## 手动打开默认浏览器

在项目根目录运行：

```powershell
python -S experiments/browser-http/server.py --open
```

也可以不加 `--open`，手动打开终端输出的完整私有 URL（包含 `#token=...`）。
请在 60 秒内连接。页面显示运行状态和最后一个公式的 SVG 预览；目前不是交互式公式编辑器。
Python 会自动发出测试请求，把结果保存到本目录 `output/`，测试通过后服务保持运行。
Ctrl+C 停止服务；关闭自行打开的浏览器标签页。刷新页面或重新连接需要重启服务器。

`-S` 仅跳过本机 Python 的 site 初始化（本机存在无关的 `_distutils_hack` 启动警告），
本实验不依赖第三方 Python 包。

## 自动验收：已安装的真实 Edge

```powershell
python -S experiments/browser-http/server.py --browser 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' --headless --once
```

使用本机 Edge 的独立配置目录，不接触日常浏览器个人资料。
这里的无头模式仍是真实浏览器加载 HTTP 页面并启动 Worker，不是模拟 JS 执行。
去掉 `--headless` 可用可见浏览器验证；去掉 `--once` 可在测试后保留服务和页面。
显式 `--browser` 启动的进程树在服务器退出时关闭（当前清理实现面向 Windows）。
浏览器配置目录和日志位于忽略版本控制的 `output/` 中，可在退出后删除。
受限沙箱若禁止 Chromium 的 IPC，会使浏览器启动失败；此次验收是在批准后于沙箱外运行的。

## Firefox 验收

启动器按可执行文件名识别 Firefox，使用 `-no-remote -profile` 创建独立会话，
而不是 Chromium 的启动参数。使用独立输出目录保留此前 Edge 结果：

```powershell
python -S experiments/browser-http/server.py --browser 'C:\Program Files\Mozilla Firefox\firefox.exe' --headless --once --output-dir experiments/browser-http/output/firefox
```

去掉 `--headless` 可显示 Firefox 窗口。计算页面、Worker 和现有 MathJax 脚本共用同一份，
没有 Firefox 专用的渲染代码。`--output-dir` 同样可用于其他浏览器或重复运行。

协议测试：

```powershell
python -S -W error::ResourceWarning -m unittest discover -s experiments/browser-http -p test_server.py -v
```

## 验证内容与本机结果

已在 Edge 153 / Windows 上通过：

1. 原样加载仓库 `jsapi.js` 和 `features/mathjax/feature.js`，调用 `veuszDescribe()`。
2. Python 发起 `veuszRender()`；按 `{load: "mathjax.js"}` 延迟加载现有 MathJax bundle。
3. 分式、积分返回 SVG；Python 验证 XML 根节点和路径元素，并保存原始 SVG。
4. 重复公式返回逐字相同的 SVG（这包含 feature 自己的缓存命中，不代表重新排版耗时）。
5. 切换 Asana 字体，按 `{load: "fonts/mathjax-asana.js"}` 加载外部字体数据并返回 SVG。
6. 四项协议测试通过：令牌/Host/Origin/资源白名单、单客户端/请求对应、超时/畸形回复、浏览器错误回传。

一次测量（不是统计基准）：

| 请求 | Python 端到端耗时 |
|---|---:|
| 首次分式，含 MathJax bundle 加载 | 140.0 ms |
| 已加载引擎后的积分 | 10.1 ms |
| 同一分式，feature 缓存命中 | 4.7 ms |
| Asana 公式，含外部字体加载 | 35.7 ms |

这些时间从浏览器连接并完成 feature 初始化后开始，**不包含浏览器启动和初始页面加载**。
端到端时间包含所需的多轮请求和资源加载；`js_call_ms` 只累计 feature 函数调用，
不包含脚本下载/解析/加载，不能简单相减解释成纯网络耗时。
没有与 QuickJS 做同条件性能比较，也未验证其他 feature 或 Veusz/Qt 绘制集成。

Firefox 156.0.1 / Windows 的同组无头验收也通过，结果保存在 `output/firefox/results.json`。
首次沙箱内运行未连接且进程清理被拒；清理该独立实验进程后，经批准在沙箱外重试通过。
此次 Firefox 的四份 SVG 与此前 Edge 的对应文件逐字节完全一致（另用 Python 比较确认），
包括外部 Asana 字体，浏览器计算 JS 无需任何兼容性改动。

| 请求 | Firefox 本次端到端耗时 |
|---|---:|
| 首次分式，含 MathJax bundle 加载 | 207.3 ms |
| 已加载引擎后的积分 | 15.5 ms |
| 同一分式，feature 缓存命中 | 13.8 ms |
| Asana 公式，含外部字体加载 | 52.3 ms |

两个浏览器的数据均为单次运行，不是统计性能比较，不能据此判定引擎速度优劣。
测试后已关闭专用浏览器进程和 HTTP 服务；日常 Firefox 会话未被关闭。

`output/results.json` 给出当前运行状态、浏览器 UA 和测量；运行开始写 `running`，
异常写 `failed`，全部完成才写 `passed`。SVG 文件可能来自较早的运行，应以本次结果状态为准。

## 边界与限制

- 仅监听 `127.0.0.1` 随机端口；校验 Host、Origin、随机会话令牌；没有 CORS 开放。
- 只提供本实验页面、仓库 API、MathJax feature/bundle 和字体白名单；不提供任意文件读取或执行接口。
- 任务只允许调用 `veuszDescribe` / `veuszRender` 或加载白名单脚本；原型只允许一个浏览器客户端。
- SVG 预览通过 Blob 图片，而不是把 SVG 插入页面 DOM；CSP 限制外部资源。
- Worker 只负责 JS 计算，不依赖 DOM，也不是不可信脚本安全沙箱：只运行可信仓库代码。
- 每个 RPC 最多等待 30 秒；超时即此次实验失败，**不支持取消后继续或自动重连**。
- 页面关闭、休眠、Worker 同步死循环等仍需生产版生命周期设计。
  默认浏览器/手动模式下 Python 无法强制关闭浏览器 Worker；卡住时关闭该标签页。
- 未实现 Qt 文字测量；出现 `{measure: ...}` 会明确失败，不偷偷换浏览器字体。
- 未接入 Veusz 绘图线程，尚未解决正式插件的异步重绘/缓存/断线恢复。

结论：已验证“本地 HTTP 服务 + 用户安装的浏览器 + 现有 feature 协议”能返回有效 SVG，
包括 bundle 和外部字体的多轮加载；没有理由为这次验证改动现有 QuickJS 实现。
