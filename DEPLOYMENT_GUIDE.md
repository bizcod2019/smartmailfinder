# 📦 邮件搜索应用部署指南

本指南提供多个免费/低成本部署平台的详细说明，帮您快速部署邮件搜索应用。

## 🎯 推荐部署平台

### 1. Streamlit Community Cloud (最推荐) ⭐⭐⭐⭐⭐

**优势：** 完全免费，专为Streamlit设计，一键部署

**步骤：**
1. 访问 [share.streamlit.io](https://share.streamlit.io)
2. 用GitHub账号登录
3. 点击"New app"
4. 选择您的GitHub仓库
5. 设置：
   - Main file path: `api/index.py`
   - Python version: `3.9`
6. 点击"Deploy"

**配置文件：** 已创建 `.streamlit/config.toml`

---

### 2. Render (强烈推荐) ⭐⭐⭐⭐

**优势：** 750小时/月免费，支持自定义域名，自动扩容

**步骤：**
1. 访问 [render.com](https://render.com)
2. 连接GitHub账号
3. 选择"New Web Service"
4. 选择您的仓库
5. 设置：
   - Environment: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `streamlit run api/index.py --server.port $PORT --server.address 0.0.0.0`

**配置文件：** 已创建 `render.yaml`

---

### 3. PythonAnywhere ⭐⭐⭐

**优势：** 专为Python设计，在线IDE，512MB存储

**步骤：**
1. 访问 [pythonanywhere.com](https://pythonanywhere.com)
2. 注册免费账号
3. 上传代码到 `/home/yourusername/email_research/`
4. 在Web标签页创建新的Web app
5. 选择Python 3.9
6. 设置WSGI文件路径为 `pythonanywhere_setup.py`

**配置文件：** 已创建 `pythonanywhere_setup.py`

---

### 4. Railway ⭐⭐⭐

**优势：** $5免费额度，简单部署

**步骤：**
1. 访问 [railway.app](https://railway.app)
2. 连接GitHub
3. 选择"Deploy from GitHub repo"
4. Railway会自动检测Python项目
5. 添加环境变量：`PORT=8080`

---

### 5. Fly.io ⭐⭐

**优势：** $5注册额度，全球CDN

**步骤：**
1. 安装Fly CLI: `curl -L https://fly.io/install.sh | sh`
2. 注册账号: `fly auth signup`
3. 在项目目录运行: `fly launch`
4. 选择配置选项
5. 部署: `fly deploy`

---

## 🔧 部署前准备

### 环境变量设置
在部署平台添加以下环境变量：

```bash
# 必需的环境变量
STREAMLIT_SERVER_HEADLESS=true
STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# 可选的邮件配置（如果需要）
EMAIL_HOST=your_email_host
EMAIL_PORT=993
EMAIL_USERNAME=your_email
EMAIL_PASSWORD=your_password
```

### 内存优化设置
应用已包含内存优化功能：
- ✅ Vercel环境检测
- ✅ 严格内存限制（200MB）
- ✅ 邮件数量限制（200封）
- ✅ 缓存文件大小控制（50MB）
- ✅ 内存监控和清理

## 📊 平台对比

| 平台 | 免费额度 | 内存限制 | 自定义域名 | 难度 |
|------|----------|----------|------------|------|
| Streamlit Cloud | 无限制 | 1GB | ❌ | ⭐ |
| Render | 750h/月 | 512MB | ✅ | ⭐⭐ |
| PythonAnywhere | 24h/月 | 512MB | ❌ | ⭐⭐ |
| Railway | $5额度 | 512MB | ✅ | ⭐⭐⭐ |
| Fly.io | $5额度 | 256MB | ✅ | ⭐⭐⭐⭐ |

## 🚀 快速部署命令

### Git提交和推送
```bash
git add .
git commit -m "准备多平台部署"
git push origin main
```

### 本地测试
```bash
# 安装依赖
pip install -r requirements.txt

# 运行应用
streamlit run api/index.py
```

## 🔍 故障排除

### 常见问题
1. **内存不足：** 应用已优化内存使用，限制邮件数量和缓存大小
2. **依赖安装失败：** 检查 `requirements.txt` 中的版本号
3. **端口问题：** 确保使用 `$PORT` 环境变量

### 日志查看
- **Streamlit Cloud：** 在应用页面点击"Manage app"
- **Render：** 在Dashboard中查看Logs标签
- **PythonAnywhere：** 在Web标签页查看Error log

## 📞 技术支持

如果遇到部署问题，可以：
1. 查看平台官方文档
2. 检查应用日志
3. 确认所有配置文件正确
4. 验证环境变量设置

---

**推荐部署顺序：**
1. 🥇 Streamlit Community Cloud（最简单）
2. 🥈 Render（功能最全）
3. 🥉 PythonAnywhere（备选方案）