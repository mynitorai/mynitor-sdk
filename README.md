# MyNitor AI SDKs

Official SDKs for MyNitor AI - Production safety and observability for AI systems.

## 🚀 One-Line Magic

MyNitor provides auto-instrumentation for popular AI libraries. Just initialize it at the start of your application.

### Python
```bash
pip install mynitor
```
```python
import mynitor
mynitor.init(api_key="your_api_key").instrument()
```

### TypeScript / Node.js
```bash
npm install @mynitor/sdk
```
```typescript
import { MyNitor } from '@mynitor/sdk';
MyNitor.init({ apiKey: 'your_api_key' }).instrument();
```

## 📦 Supported Libraries
- ✅ OpenAI (Sync & Async)
- ✅ Anthropic (Coming Soon)
- ✅ LangChain (Coming Soon)

## 🛡 License
MIT
