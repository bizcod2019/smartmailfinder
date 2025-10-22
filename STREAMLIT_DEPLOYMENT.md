# Streamlit Cloud 部署指南

## 概述

本项目现在支持在 Streamlit Cloud 上部署。主要修改包括：

1. 创建了 `app.py` 作为 Streamlit Cloud 的入口文件
2. 添加了 `.streamlit/config.toml` 配置文件
3. 修改了路径处理逻辑以兼容不同部署环境
4. 提供了 Streamlit Cloud 专用的环境变量配置示例

## 部署步骤

### 1. 准备代码

确保你的代码已经推送到 GitHub 仓库。

### 2. 在 Streamlit Cloud 创建应用

1. 访问 [Streamlit Cloud](https://streamlit.io/cloud)
2. 使用 GitHub 账号登录
3. 点击 "New app"
4. 选择你的 GitHub 仓库
5. 设置以下参数：
   - **Main file path**: `app.py`
   - **Python version**: 3.9 或更高版本

### 3. 配置环境变量

在 Streamlit Cloud 的应用设置中，进入 "Secrets" 页面，添加以下配置：

```toml
# 阿里云OSS配置
ALIYUN_OSS_ACCESS_KEY = "your_access_key_id"
ALIYUN_OSS_SECRET_KEY = "your_access_key_secret"
ALIYUN_OSS_BUCKET = "your_bucket_name"
ALIYUN_OSS_ENDPOINT = "oss-cn-hangzhou.aliyuncs.com"

# AI模型配置
SENTENCE_TRANSFORMER_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# 应用配置
MAX_EMAILS = "30000"
CACHE_DIR = "./cache"
DEBUG = "false"

# 索引控制
INDEX_ASYNC = "false"
INDEX_BATCH_SIZE = "500"
INDEX_TIME_SLICE_SEC = "20"
```

### 4. 部署应用

1. 点击 "Deploy" 按钮
2. 等待应用构建和部署完成
3. 访问提供的 URL 测试应用

## 文件结构变化

```
email_research/
├── app.py                          # Streamlit Cloud 入口文件 (新增)
├── .streamlit/
│   ├── config.toml                 # Streamlit 配置 (新增)
│   └── secrets.toml.example        # Secrets 示例 (新增)
├── .env.streamlit.example          # 环境变量示例 (新增)
├── api/
│   └── index.py                    # 主应用逻辑 (已修改路径处理)
├── requirements.txt                # 依赖列表 (已存在)
└── ...
```

## 与 Vercel 部署的区别

| 特性 | Vercel | Streamlit Cloud |
|------|--------|-----------------|
| 入口文件 | `api/index.py` | `app.py` |
| 配置文件 | `vercel.json` | `.streamlit/config.toml` |
| 环境变量 | Vercel 环境变量 | Streamlit Secrets |
| 部署方式 | Serverless 函数 | 持续运行的应用 |

## 注意事项

1. **资源限制**: Streamlit Cloud 有资源使用限制，请注意应用的内存和CPU使用
2. **文件存储**: Streamlit Cloud 的文件系统是临时的，重要数据应存储在 OSS 中
3. **环境变量**: 所有敏感信息都应通过 Streamlit Secrets 配置，不要硬编码在代码中
4. **依赖管理**: 确保 `requirements.txt` 包含所有必要的依赖

## 故障排除

### 常见问题

1. **模块导入失败**: 检查 `requirements.txt` 是否包含所有依赖
2. **OSS 连接失败**: 检查 Secrets 中的 OSS 配置是否正确
3. **应用启动慢**: 首次启动时需要下载 AI 模型，这是正常现象

### 日志查看

在 Streamlit Cloud 的应用管理页面可以查看实时日志，用于调试问题。

## 支持

如果遇到部署问题，请检查：
1. GitHub 仓库是否公开或已授权给 Streamlit Cloud
2. `requirements.txt` 是否完整
3. Secrets 配置是否正确
4. 应用日志中的错误信息