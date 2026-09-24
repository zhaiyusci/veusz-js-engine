# 浏览器后端：实验性默认部署指南

当前默认后端已从 QuickJS 改为**实验性系统浏览器后端**。保留 `qjs.dll` 和直接 C API 绑定，但只有显式选择 `quickjs` 才使用它。浏览器不可用、启动失败或会话出错时，**不会自动降级到 QuickJS，也不会自动重连**。

**升级、修改环境变量或切换后端后必须完全退出并重启 Veusz。** 不支持在已运行的 Veusz 中热重载或更换后端。

## 部署文件与依赖

将以下文件作为同一套部署，不要只复制插件 `.py`：

```text
veusz-js-engine/
  veusz_js_engine.py       Veusz 注册的唯一插件
  browser_backend.py      Veusz 内置 Python 加载的浏览器桥接
  browser_host/
    index.html
    page.js
    worker.js
  jsapi.js                feature API
  features/               保留各 feature 的脚本、bundle、fonts 等配套内容
  qjs.dll                 显式 QuickJS 回退使用，仍保留
```

在 Veusz 的 **Edit → Preferences → Plugins → Add…** 中只添加 `veusz_js_engine.py`。不要把 `browser_backend.py` 或浏览器资源分别注册为插件。功能仍从 `features/` 自动发现，可通过 **Tools → JS Engine Features…** 管理下一次启动启用的功能。

浏览器模式需要本机安装 Firefox、Edge 或 Chrome。它直接使用系统浏览器，不要求安装浏览器自动化框架，不使用 CDP，也不需要另装 Python 或启动额外 server：HTTP 服务运行在 **Veusz 内置 Python 的线程**中。`qjs.dll` 不是浏览器模式的运行依赖，但应保留以便显式回退。

## 环境变量

环境变量须由新启动的 Veusz 进程继承，不能只在其他终端设置后继续使用已打开的 Veusz。

| 变量 | 值与默认行为 |
|---|---|
| `VEUSZ_JS_ENGINE_BACKEND` | 默认 `browser`；显式设为 `quickjs` 使用回退 |
| `VEUSZ_JS_ENGINE_BROWSER` | 可选，浏览器 **exe 的完整路径**，不是目录、URL 或带参数的命令行。未设置时自动查找 Firefox，之后 Edge，最后 Chrome |
| `VEUSZ_JS_ENGINE_BROWSER_MODE` | 默认 `headless`；可设 `visible` 显示专用浏览器窗口排查问题 |
| `VEUSZ_JS_ENGINE_BROWSER_TIMEOUT` | RPC 超时秒数，默认 `30`；必须是有限正数，不允许 0、负数或无穷大 |
| `VEUSZ_JS_ENGINE_QUICKJS` | QuickJS 模式可选的库路径，例如完整 `qjs.dll` 路径 |

浏览器启动等待另有 **60 秒**上限，不随 RPC timeout 改变。显式指定了不存在的浏览器可执行文件会报错，不会悄悄忽略该路径再自动查找。浏览器自动发现包括 PATH 与常见安装位置；自定义安装优先指定完整路径。

原有 `VEUSZ_JS_ENGINE_FEATURES`（额外功能目录）、`VEUSZ_JS_ENGINE_DEFER=1`（测试用，加载时不自动安装）仍保留。旧插件的 `VEUSZ_JSENGINES_*` 不是这些变量的别名。

## PowerShell 启动示例

先退出已打开的 Veusz。以下变量仅修改当前 PowerShell 及它启动的子进程，不会永久更改系统配置；路径请按实际安装调整。

### 指定 Firefox，使用默认无头模式

```powershell
$env:VEUSZ_JS_ENGINE_BACKEND = 'browser'
$env:VEUSZ_JS_ENGINE_BROWSER = 'C:\Program Files\Mozilla Firefox\firefox.exe'
$env:VEUSZ_JS_ENGINE_BROWSER_MODE = 'headless'
$env:VEUSZ_JS_ENGINE_BROWSER_TIMEOUT = '30'
& 'C:\Program Files\Veusz\veusz.exe'
```

若需观察专用浏览器页面，将 mode 改为 `visible`，再重启 Veusz。若希望自动查找浏览器，在启动前清除显式设置：

```powershell
Remove-Item Env:VEUSZ_JS_ENGINE_BROWSER -ErrorAction SilentlyContinue
$env:VEUSZ_JS_ENGINE_BACKEND = 'browser'
& 'C:\Program Files\Veusz\veusz.exe'
```

### 显式回退 QuickJS

```powershell
$env:VEUSZ_JS_ENGINE_BACKEND = 'quickjs'
# 可选：若不使用默认搜索到的库，指定实际部署路径。
$env:VEUSZ_JS_ENGINE_QUICKJS = 'C:\tools\veusz-js-engine\qjs.dll'
& 'C:\Program Files\Veusz\veusz.exe'
```

QuickJS 模式不需要浏览器。库默认先从 feature 的 JavaScript 附近查找，再从插件附近及上一级目录查找；显式库路径覆盖搜索。其内存/栈限制和 C ABI 细节见根 README 的 QuickJS fallback 章节。QuickJS 当前没有执行超时/中断处理，死循环仍可能挂住 Veusz，不应把回退理解为超时恢复机制。

## 进程、通信与绘制路径

- 一个平台浏览器 session 使用**专用浏览器进程及临时 profile**。不复用或修改用户平时使用的 browser profile，也不依赖用户已登录的浏览器窗口。
- HTTP 只监听 `127.0.0.1` 的随机端口；使用随机会话令牌以及 Host / Origin 检查，并只允许一个已绑定的 client。不要手动复制 host URL 到其他浏览器窗口。
- 一次 session 承载多个 Worker，每个 feature runtime 一个 Worker，分别保存脚本状态。它们不是给用户访问的普通网页功能。
- 现有同步调用、`load` 延迟脚本加载、Qt `measure` 字形测量、SVG 绘制和原生委托路径保留。浏览器执行 JavaScript，并不接管 Veusz 的 Qt 绘制，也不把 feature 改成异步 Promise 协议。
- 各 feature 的 RPC 串行执行；多个 Worker 不代表多个绘制请求并行完成。首次启动浏览器和等待 RPC 超时期间，同步等待可能阻塞 Veusz UI。

## JavaScript 兼容性与安全边界

仅加载**可信本地 JavaScript**。这是减少意外能力暴露的执行环境，**不是运行恶意脚本的安全沙箱**，不能把 localhost、令牌或 Worker 当成完整隔离保证。

Worker 禁用这些面向 feature 的全局 API：`fetch`、`XMLHttpRequest`（XHR）、`WebSocket`、`EventSource`、`Worker`、`SharedWorker`、`importScripts`。Worker CSP 使用 `connect-src 'none'`。后端预先捕获自己的脚本 loader，因此禁用公共 `importScripts` 并不妨碍后端加载 feature、bundle 或按需字体脚本。host 页面仍需要本地通信；不要把 Worker 的 connect-none 理解为整个 host 页面不联网。

运行语义需要特别注意：

- `run(source)` 使用 **indirect eval**；其中顶层 `let` / `const` 不会在后续调用中持久存在。不要用它建立跨调用的顶层词法声明。
- 后端 `run_file` 通过经典脚本加载，顶层词法声明可持久保留。平台的文件加载路径（包括 `runtime.eval_file(...)`）应保留这种文件语义。
- `call(name, payload)` 是同步字符串接口，**不会 await Promise**。异步函数不等同于一个可被平台等待的 renderer；feature 仍应按现有同步协议返回。

## 故障、关闭与清理

浏览器进程退出、页面失联或 RPC 超时会使当前会话失败。**不自动重连，不自动回退 QuickJS；重启 Veusz 才能建立新会话。** 需要切换时先退出 Veusz，再设置 `VEUSZ_JS_ENGINE_BACKEND=quickjs` 并重新启动。

`Platform.close_all()` 是永久 dispose，不是“释放后下次调用自动重建”的按钮。关闭后的平台不能继续使用；热重载不受支持。

Windows 正常关闭时，在浏览器主 PID 尚存活的情况下可用 `taskkill` 结束其进程树；若父进程先崩溃，可能留下孤儿进程。清理是 best effort，不能承诺在崩溃、权限问题或进程退出竞态下绝对清理干净。清理失败会记录在 session `report()` 中，并保留临时目录（包括 profile/日志）供排查，而不是宣称已全部删除。排查时只识别本次专用进程/profile，不要结束或删除用户自己的浏览器会话。

建议故障排查顺序：确认全部配套文件存在 → 确认 exe 路径及环境变量 → 重启后用 `visible` 检查启动 → 查看 session report/保留的日志 → 必要时显式切换 QuickJS 并再次重启。

## 已验证的功能与复现

已在 Windows 的 Firefox 156.0.1、Edge 153，以及安装版 Veusz 4.2.1（内置 Python 3.13.12）上验证。

- Firefox、Edge 的后端测试各 37 项通过（其中 10 项为真实浏览器测试），覆盖隔离、HTTP 访问控制、异常传递、超时失效、关闭竞争、自动发现、经典脚本全局变量和离线 API。
- 延迟加载 7 项、功能管理器 9 项通过。
- 平台 48 项、MathJax 双层接口 11 项、MathJax Qt 文字排版 12 项、KaTeX 10 项、SMILES 17 项、3D 分子 19 项、3D 原生面板 11 项通过。
- 安装版 Veusz 中，MathJax 外部 Asana 字体、Qt 文字轮廓、KaTeX 原生 MathML、2D 分子和带标签的 3D 分子共同完成真实文档导出。
- 测试启动时故意为浏览器模式设置不存在的 QuickJS DLL 路径；绘制仍成功，证明未暗中调用该回退。
- 测试后 HTTP 关闭、浏览器进程退出、临时目录删除，报告中无 cleanup_errors。
- 显式 QuickJS 回退也完成同一份真实文档导出。Firefox、Edge、QuickJS 的最终 PNG 逐字节相同；MathJax 原始 SVG 和 KaTeX 委托结果相同。分子 SVG 的序列化并非逐字相同，不承诺所有引擎都生成相同字符串。

源码级测试需要可导入的 Veusz、PyQt 和相应依赖。Windows 字体测试应使用 `QT_QPA_PLATFORM=windows`，而不是 offscreen：本机 offscreen 的字体轮廓断言在 QuickJS/浏览器两种后端均失败，改用原生字体环境后通过。

```powershell
$env:VEUSZ_TEST_BROWSER = '1'
$env:VEUSZ_JS_ENGINE_BROWSER = 'C:\Program Files\Mozilla Firefox\firefox.exe'
python -S -m unittest discover -s test -p test_browser_backend.py -v

# 使用已安装 Veusz，导出真实文档；无需另装 Python。
.\test\run_browser_veusz.ps1
.\test\run_browser_veusz.ps1 -Browser 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
.\test\run_browser_veusz.ps1 -Backend quickjs
```

安装版输出位于 `build-test-browser-veusz/<backend>-<browser>/`：`results.json`、`browser-document.vsz`、PNG、SVG，以及各 feature 的原始结果。启动脚本只在独立 Veusz 进程中加载一次性测试插件；**不要把 `test/browser_veusz_plugin.py` 加入偏好设置**，它会在测试结束后退出。

### 本机已有同名 widget 的注意事项

本机安装版 Veusz 在加载当前插件前已经注册了一个无本平台标记的 `molecule3d` widget。正式插件会记录 `widget type 'molecule3d' is already registered`，并拒绝覆盖它；这不是浏览器运算失败。

为独立验收本项目的 3D feature，安装版测试程序仅在其一次性进程内移除冲突注册，并临时启用测试所需 feature；不修改保存的插件/功能偏好设置。生产使用时应检查并避免同时加载两个注册同名 widget 的插件或定制组件；未处理冲突前，不能把测试中的四-feature成功当成当前普通启动已经启用四个 feature 的保证。

本机 KaTeX 原先在功能管理器中禁用，验收时仅在测试进程内启用；正常使用仍尊重用户的禁用选项。

这些结果不是跨平台普遍兼容性或速度排名的保证；未测试 Safari、所有浏览器版本、系统休眠或强制崩溃后的所有进程回收路径。
