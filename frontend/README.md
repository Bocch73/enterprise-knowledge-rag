# 知序前端工作台

Vue 3 + TypeScript 单页应用，为 Enterprise Knowledge RAG 后端提供登录、知识库、文档摄取和带引用问答界面。

## 本地启动

先在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-frontend.ps1
```

浏览器打开 <http://127.0.0.1:5173>。开发服务器把 `/api` 请求代理到 <http://127.0.0.1:8000>，因此还需要在另一个终端启动后端。

## 质量检查

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-frontend.ps1
```

包含浏览器端到端测试：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-frontend.ps1 -EndToEnd
```

## 目录职责

- `src/components`：可复用的知识库、文档和问答组件。
- `src/views`：登录、注册和工作台页面。
- `src/services`：统一后端网络访问与流式事件解析。
- `src/stores`：Pinia 登录会话状态。
- `src/types`：与后端响应对应的 TypeScript 类型。
- `src/__tests__`：Vitest 单元与组件测试。
- `e2e`：Playwright 浏览器端到端测试。

浏览器可读取所有 `VITE_` 开头的变量，所以这里永远不能保存 DeepSeek 密钥、数据库密码或身份令牌。
