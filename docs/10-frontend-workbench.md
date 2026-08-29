# 第 10 步：Vue 企业知识工作台

## 1. 本步目标

前 9 步已经形成完整后端链路，但普通用户不能依赖接口调试页面工作。本步增加一个可以直接操作的企业工作台：

```text
浏览器
├─ 登录 / 注册
├─ 选择或创建知识库
├─ 上传 PDF、DOCX、Markdown
├─ 查看摄取任务进度
└─ 提问并展开引用
        ↓  /api 同源请求
Vite 开发代理
        ↓
FastAPI + PostgreSQL + DeepSeek
```

本步实现：

1. Vue 3 + TypeScript + Vite 前端工程。
2. 登录、注册和受保护工作台路由。
3. Pinia 登录状态和浏览器会话存储。
4. 知识库列表、切换和创建。
5. 文档列表、上传、摄取任务进度轮询。
6. 校验后流式问答和可展开引用。
7. 后端统一错误的中文展示和请求编号保留。
8. 桌面、平板和手机响应式布局。
9. 单元测试、组件测试、浏览器端到端测试和生产构建。
10. Vite 到真实 FastAPI 健康检查的代理联调。

## 2. 新名词解释

### 前端与后端

前端运行在用户浏览器中，负责页面、交互和展示。后端运行在服务器中，负责身份、权限、数据库、文档处理、检索和模型调用。前端不能代替后端权限检查，因为浏览器代码可被用户查看和修改。

### 单页应用

Single-Page Application，常简称 SPA。浏览器先加载一个 HTML 外壳，之后由 JavaScript 切换页面内容，不需要每次导航都重新下载完整网页。本项目的 `/login`、`/register` 和 `/app` 都由前端路由管理。

### 组件

组件是可以独立维护和复用的页面单元。项目把身份外壳、知识库侧栏、文档面板和问答面板拆成组件，避免一个文件同时承担所有业务。

### 单文件组件

Vue Single-File Component，文件扩展名是 `.vue`。一个文件可以包含脚本、页面模板和局部样式。本项目把公共视觉规则集中到 `src/styles/main.css`，组件保留自己的结构和逻辑。

### TypeScript

TypeScript 在 JavaScript 上增加静态类型。项目为用户、知识库、文档、任务和引用定义接口；前端若把 `document_title` 写错，类型检查能在构建前发现。

### Composition API

Vue 组织组件状态和逻辑的一套函数式接口，例如 `ref`、`computed`、`watch` 和生命周期函数。`<script setup>` 是单文件组件中更简洁的使用方式。

### 响应式状态

状态变化后，Vue 自动更新依赖它的页面。例如流式回答每收到一段就修改 `answer`，页面无需手工查找和修改文档对象模型节点。

### 属性与事件

父组件通过属性把数据传给子组件，英文称 Props；子组件通过事件通知父组件，英文称 Emits。知识库侧栏接收列表和当前编号，选择或创建时向工作台发出事件。

### 前端路由与路由守卫

前端路由把地址映射到组件。路由守卫在导航前检查条件：未登录访问 `/app` 会转到 `/login`；已经登录访问登录页会回到工作台。它改善用户体验，但真正安全边界仍在后端。

### Pinia Store

Pinia 是 Vue 的状态管理库。Store 是多个页面共享状态和动作的容器。本项目只把当前用户、访问令牌、登录、恢复和退出放入认证 Store；知识库和文档仍以服务器返回为准，避免复制过多服务器状态。

### 会话存储

`sessionStorage` 是浏览器当前标签页的键值存储，标签页关闭后数据清除。本项目把访问令牌放在会话存储，不使用长期 `localStorage`。JavaScript 仍能读取它，因此必须继续防御跨站脚本攻击。生产系统可评估安全、仅 HTTP Cookie 与跨站请求伪造防御。

### Fetch API

浏览器原生网络请求接口。`src/services/api.ts` 统一构造请求、添加 Bearer 令牌、解析 JSON 和服务器发送事件，并把后端错误转换为 `ApiError`。

### 开发代理

浏览器只访问 `127.0.0.1:5173`。Vite 收到 `/api` 请求后转发到 `127.0.0.1:8000`。这让页面和接口对浏览器表现为同一来源，不必在后端开放任意跨域来源。

### 同源策略与跨域资源共享

浏览器把协议、主机和端口共同定义为“来源”。不同来源的脚本默认不能随意读取响应。Cross-Origin Resource Sharing 是服务器声明允许哪些外部来源读取资源的机制，常简称 CORS。本地使用代理绕过开发端口差异；生产使用反向代理统一域名。

### 热更新

开发服务器检测代码变化后只更新受影响模块，尽量保留页面状态，不需要每次手动刷新。Vite 提供这项开发能力。

### 生产构建

Vite 把 TypeScript 和 Vue 文件转换、压缩并拆分为浏览器资源，输出到 `dist`。生产服务器部署的是构建产物，不是开发服务器。

### 代码拆分

登录、注册和工作台通过动态导入形成独立 JavaScript 文件。用户打开登录页时不需要立即下载完整工作台逻辑，降低初始加载体积。

### 响应式布局

页面根据屏幕宽度改变排列。桌面工作台使用侧栏和两列面板；小屏把侧栏、文档和问答改为纵向，同时防止文字和表单横向溢出。

### 可访问性

让键盘、屏幕阅读器、低视力或减少动画偏好的用户也能使用页面。本项目使用语义标题、表单标签、可读错误区域、隐藏辅助文字、焦点输入和 `prefers-reduced-motion`。

### Mock

Mock 是测试中模拟外部依赖行为的对象。前端浏览器测试模拟后端响应，验证页面交互时不清空数据库、不调用 DeepSeek，也不受网络波动影响。

### 单元、组件与端到端测试

- 单元测试：验证网络解析或 Store 等较小逻辑。
- 组件测试：挂载 Vue 组件，模拟输入和点击。
- 端到端测试：真实启动页面并用 Chrome 完成登录、创建知识库和问答流程。

## 3. 技术和锁定版本

官方 `create-vue 3.23.0` 脚手架生成工程，实际锁定版本包括：

| 依赖 | 版本 | 职责 |
|---|---:|---|
| Node.js | 24.19.0 | 执行前端工具 |
| Vue | 3.5.42 | 组件和响应式页面 |
| Vue Router | 5.3.0 | 页面路由与导航守卫 |
| Pinia | 4.0.3 | 登录会话状态 |
| Vite | 8.2.2 | 开发服务器和生产构建 |
| TypeScript | 6.0.x | 静态类型检查 |
| Vitest | 4.1.11 | 单元与组件测试 |
| Playwright | 1.62.1 | Chrome 端到端测试 |

`package.json` 声明直接依赖范围，`package-lock.json` 保存本次完整依赖树的确切版本和完整性摘要。企业构建应使用锁文件，不应每次安装不可预测的最新版。

脚手架安装时发现 `eslint-plugin-oxlint 1.73.0` 要求 `oxlint 1.73.x`，而范围解析到了 1.74.0。项目把 `oxlint` 对齐到 `1.73.0`，没有使用 `--force` 绕过不兼容约束。

## 4. 目录设计

```text
frontend/
├─ src/
│  ├─ components/       可复用业务组件
│  ├─ views/            登录、注册、工作台页面
│  ├─ services/api.ts   后端请求与流式事件解析
│  ├─ stores/auth.ts    Pinia 登录状态
│  ├─ types/api.ts      后端响应类型
│  ├─ router/index.ts   路由和登录守卫
│  ├─ styles/main.css   设计系统与响应式规则
│  └─ __tests__/        单元和组件测试
├─ e2e/                 Playwright 浏览器测试
├─ package.json         命令和直接依赖
├─ package-lock.json    完整锁定依赖树
├─ vite.config.ts       Vite 与开发代理
└─ playwright.config.ts 浏览器测试配置
```

## 5. 登录数据流

```text
填写邮箱和密码
      ↓ 表单编码
POST /api/v1/auth/login
      ↓ 返回访问令牌
保存到当前标签页 sessionStorage
      ↓
GET /api/v1/auth/me
      ↓
加载用户成功后进入工作台
```

只有取得当前用户信息后，`isAuthenticated` 才为真。如果令牌存在但 `/auth/me` 失败，Store 会清除令牌，防止页面停留在半登录状态。

页面刷新时先执行 `restore()`。恢复结束后才启动路由，避免工作台短暂闪回登录页。

## 6. 网络和错误处理

网络层统一处理：

1. 默认发送 `Accept: application/json`。
2. 有令牌时添加 `Authorization: Bearer`。
3. JSON 请求添加内容类型；文件上传使用浏览器自动生成的 multipart 边界，不能手工覆盖。
4. 后端错误保留 `code`、HTTP 状态和请求编号。
5. 常见错误码翻译为中文，未知错误保留安全后端消息。
6. 代理返回 HTML 等非 JSON 内容时使用安全兜底。

请求编号会显示给用户，便于把页面错误与后端结构化日志关联。

## 7. 文档上传和任务轮询

上传表单只选择 PDF、DOCX 和 Markdown，并提示 20 MB 上限。前端限制只改善体验，后端仍会重新验证真实文件结构和大小。

上传成功后，页面每 2 秒读取一次 `/ingestion-jobs/{id}`：

```text
queued → parsing → chunking → embedding → indexing → completed
```

当前 Windows 学习环境没有常驻 Celery，`queued` 时页面提示运行：

```powershell
cd "E:\codex项目\rag1\backend"
.\.venv\Scripts\python.exe -m app.cli.process_ingestion_jobs --max-jobs 10
```

组件销毁或切换知识库时会取消计时器，避免旧页面继续发送请求。

## 8. 流式问答页面

问题通过 `POST /answers/stream` 发送。浏览器读取 `ReadableStream`，使用 `TextDecoder` 把二进制块转换为文字。一个服务器事件可能跨越多个网络块，因此解析器保留不完整缓冲区，直到出现空行分隔符。

页面处理三种事件：

- `answer_delta`：追加回答文字。
- `citations`：保存结构化引用。
- `done`：保存回答编号、模型和拒答状态。

如果连接结束却没有 `done`，前端不会把它当成完整成功，而是报告 `incomplete_stream`。引用使用 `<details>` 展开生成时快照。

第 9 步后端采用校验后流式，所以页面会逐段渲染，但首段仍需等待 DeepSeek 完整生成与引用校验。

## 9. 安全边界

1. DeepSeek 密钥和数据库密码只在后端，浏览器永远不接收。
2. 所有 `VITE_` 变量都会进入浏览器构建，不能放秘密。
3. 前端隐藏按钮不是授权；后端继续检查所有者、编辑者和查看者权限。
4. 访问令牌不打印、不放地址、不写长期本地存储。
5. 引用正文来自文档，Vue 默认转义插值，不使用危险的原始 HTML 渲染。
6. 开发代理只监听 `127.0.0.1`，不默认暴露到局域网。
7. 生产环境仍需内容安全策略、加密连接、安全 Cookie 评估和依赖供应链扫描。

## 10. 三个终端启动完整系统

### 终端一：后端

```powershell
cd "E:\codex项目\rag1\backend"
.\.venv\Scripts\python.exe -m app.server --reload
```

### 终端二：前端

在项目根目录运行：

```powershell
cd "E:\codex项目\rag1"
powershell -ExecutionPolicy Bypass -File .\scripts\start-frontend.ps1
```

打开 <http://127.0.0.1:5173>。

### 终端三：文档处理

上传文件后执行：

```powershell
cd "E:\codex项目\rag1\backend"
.\.venv\Scripts\python.exe -m app.cli.process_ingestion_jobs --max-jobs 10
```

页面会自动查询进度。文档完成后，在右侧输入问题并展开来源。

## 11. 自动化验证结果

- npm 官方注册表审计：391 个安装包，0 个已知漏洞。
- Vitest：12 个单元和组件测试全部通过。
- 关键网络与登录逻辑覆盖率：语句 94.33%、分支 80%、函数 100%、行 100%。
- Playwright：2 个 Chrome 端到端流程全部通过。
- Prettier、Oxlint、ESLint 和 `vue-tsc` 严格类型检查通过。
- Vite 生产构建成功，41 个模块完成转换。
- 主入口 JavaScript 约 100.71 KB，gzip 压缩后约 39.67 KB。
- 登录、1440 像素工作台和 390 像素手机布局均完成截图检查。
- 真实前端代理到 FastAPI 存活检查返回 HTTP 200。

## 12. 当前边界

1. 还没有知识库成员管理页面。
2. 还没有文档版本、解析预览、完整任务历史和失败重试页面。
3. 当前只展示本次回答，没有多轮会话和历史查询。
4. 前端端到端测试使用模拟后端；真实联调只执行无副作用健康检查。
5. 生产静态资源托管、反向代理、内容安全策略和 Docker 仍未实现。
6. Playwright 本机使用已安装的 Chrome；持续集成环境需要安装对应浏览器。
7. 页面展示“DeepSeek 已连接”是当前本地配置说明，未来应由后端就绪能力动态返回模型状态。

## 13. 官方学习资料

- [Vue 官方快速开始](https://vuejs.org/guide/quick-start.html)
- [Vue 与 TypeScript](https://vuejs.org/guide/typescript/overview.html)
- [Vue Router 官方安装](https://router.vuejs.org/installation)
- [Pinia 官方介绍](https://pinia.vuejs.org/introduction.html)
- [Vite 官方指南](https://vite.dev/guide/)
- [Vitest 官方指南](https://vitest.dev/guide/)
- [Playwright 官方测试介绍](https://playwright.dev/docs/intro)
- [浏览器 Fetch API](https://developer.mozilla.org/docs/Web/API/Fetch_API)
- [浏览器会话存储](https://developer.mozilla.org/docs/Web/API/Window/sessionStorage)
- [服务器发送事件标准](https://html.spec.whatwg.org/multipage/server-sent-events.html)

## 14. 本步完成标准

- [x] Vue 3 + TypeScript 标准工程和锁文件。
- [x] 登录、注册、会话恢复和路由保护。
- [x] 知识库列表、选择与创建。
- [x] 文档列表、上传和任务进度。
- [x] 校验后流式问答和引用展开。
- [x] 统一错误、请求编号和网络失败处理。
- [x] 桌面与手机响应式布局。
- [x] 单元、组件、端到端测试和覆盖率门槛。
- [x] 生产构建和真实前后端代理联调。
- [ ] 成员管理、文档详情、会话历史和生产部署。

下一步是第 11 步质量评测：用固定问题集分别测量检索能否找到正确证据，以及 DeepSeek 回答是否忠实于引用。
