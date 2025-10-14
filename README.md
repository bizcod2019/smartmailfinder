# 智能邮件搜索工具

基于AI的语义搜索邮件工具，支持自然语言查询，快速找到您需要的邮件。

## 🚀 功能特性

- **智能语义搜索**: 使用AI理解自然语言查询，如"上周客户A的报价邮件"
- **多邮箱支持**: 支持Gmail、Outlook、QQ邮箱、163邮箱等主流邮箱
- **混合搜索模式**: 结合语义搜索和关键词搜索，提供更准确的结果
- **高级筛选**: 按时间范围、发件人、附件等条件过滤
- **结果导出**: 支持CSV和Excel格式导出搜索结果
- **云端存储**: 基于阿里云OSS的数据持久化
- **快速部署**: 支持Vercel一键部署

## 🏗️ 技术架构

- **前端**: Streamlit - 纯Python Web框架
- **部署**: Vercel - 支持Python运行时
- **AI模型**: Sentence Transformers - 多语言语义嵌入
- **向量搜索**: FAISS - 高效相似度搜索
- **邮件协议**: IMAP - 支持主流邮箱服务
- **云存储**: 阿里云OSS - 邮件索引持久化

## 📦 安装部署

### 本地开发

1. **克隆项目**
```bash
git clone <repository-url>
cd email_research
```

2. **安装依赖**
```bash
pip install -r requirements.txt
```

3. **配置环境变量**
```bash
cp .env.example .env
# 编辑 .env 文件，填入您的配置信息
```

4. **运行应用**
```bash
streamlit run app.py
```

### Vercel部署

1. **准备代码**
   - 将代码推送到GitHub仓库

2. **连接Vercel**
   - 在Vercel控制台导入GitHub项目
   - 选择Python运行时

3. **配置环境变量**
```bash
vercel env add ALIYUN_OSS_ACCESS_KEY
vercel env add ALIYUN_OSS_SECRET_KEY
vercel env add ALIYUN_OSS_ENDPOINT
vercel env add ALIYUN_OSS_BUCKET
```

4. **部署**
```bash
vercel --prod
```

## ⚙️ 配置说明

### 环境变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `ALIYUN_OSS_ACCESS_KEY` | 阿里云OSS访问密钥 | `LTAI***` |
| `ALIYUN_OSS_SECRET_KEY` | 阿里云OSS密钥 | `***` |
| `ALIYUN_OSS_ENDPOINT` | OSS端点 | `oss-cn-hangzhou.aliyuncs.com` |
| `ALIYUN_OSS_BUCKET` | OSS存储桶名称 | `email-search-bucket` |
| `SENTENCE_TRANSFORMER_MODEL` | AI模型名称 | `paraphrase-multilingual-MiniLM-L12-v2` |
| `MAX_EMAILS` | 最大邮件数量 | `30000` |
| `DEBUG` | 调试模式 | `False` |

### 邮箱配置

#### Gmail
- 开启两步验证
- 生成应用专用密码
- IMAP服务器: `imap.gmail.com:993`

#### Outlook
- 使用Microsoft账户密码
- 确保IMAP已启用
- IMAP服务器: `outlook.office365.com:993`

#### QQ邮箱
- 开启IMAP服务
- 使用授权码
- IMAP服务器: `imap.qq.com:993`

## 📖 使用指南

### 1. 邮箱配置
1. 在左侧边栏选择邮箱服务商
2. 输入邮箱地址和密码
3. 点击"测试连接"验证配置

### 2. 邮件同步
1. 切换到"邮件管理"标签页
2. 点击"同步邮件"按钮
3. 等待邮件索引构建完成

### 3. 智能搜索
1. 在"邮件搜索"标签页输入查询
2. 支持自然语言描述：
   - "上周客户A的报价邮件"
   - "包含PDF附件的邮件"
   - "来自boss的紧急邮件"
3. 选择搜索模式和筛选条件
4. 查看搜索结果

### 4. 结果导出
1. 在搜索结果页面选择导出格式
2. 点击"导出结果"按钮
3. 下载生成的文件

## 🔍 搜索技巧

### 智能搜索示例
- **时间相关**: "昨天的邮件"、"上周的会议邮件"
- **人员相关**: "来自张三的邮件"、"发给客户的邮件"
- **内容相关**: "关于项目进度的讨论"、"包含报价的邮件"
- **类型相关**: "有附件的邮件"、"紧急邮件"

### 搜索模式
- **智能搜索**: 基于AI语义理解，适合自然语言查询
- **关键词搜索**: 传统关键词匹配，适合精确查找
- **混合搜索**: 结合两种模式，提供更全面的结果

## 📊 性能指标

- **支持邮件数量**: 最大30,000封
- **搜索响应时间**: <3秒
- **存储空间**: <5GB (OSS)
- **并发用户**: 10人同时使用

## 🛠️ 开发说明

### 项目结构
```
email_research/
├── app.py                 # 主应用文件
├── requirements.txt       # Python依赖
├── vercel.json           # Vercel配置
├── .env.example          # 环境变量示例
├── src/                  # 源代码目录
│   ├── __init__.py
│   ├── email_connector.py    # 邮件连接器
│   ├── semantic_search.py    # 语义搜索引擎
│   ├── oss_storage.py        # OSS存储管理
│   └── utils.py              # 工具函数
└── README.md             # 项目文档
```

### 核心模块

#### EmailConnector
- IMAP邮件连接和获取
- 支持多种邮箱服务
- 邮件解析和格式化

#### SemanticSearchEngine
- 基于Sentence Transformers的语义搜索
- FAISS向量索引管理
- 混合搜索算法

#### OSSStorage
- 阿里云OSS集成
- 索引文件上传下载
- 数据备份和恢复

## 🔒 安全说明

- 所有敏感信息通过环境变量管理
- 邮件数据仅存储索引，不存储原始内容
- 传输过程全程TLS加密
- OSS存储桶采用最小权限原则

## 📝 更新日志

### v1.0.0 (2024-01-XX)
- 初始版本发布
- 支持基础邮件搜索功能
- 集成阿里云OSS存储
- 支持Vercel部署

## 🤝 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

## 🆘 支持

如果您遇到问题或有建议，请：

1. 查看 [常见问题](docs/FAQ.md)
2. 提交 [Issue](issues)
3. 联系开发团队

## 🙏 致谢

- [Streamlit](https://streamlit.io/) - 优秀的Python Web框架
- [Sentence Transformers](https://www.sbert.net/) - 强大的语义嵌入模型
- [FAISS](https://github.com/facebookresearch/faiss) - 高效的向量搜索库
- [Vercel](https://vercel.com/) - 便捷的部署平台
- [阿里云OSS](https://www.aliyun.com/product/oss) - 可靠的云存储服务