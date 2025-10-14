"""
工具函数模块
包含各种辅助函数和工具类
"""

import re
import os
import json
import pandas as pd
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import email.utils
import hashlib
import logging
from email_validator import validate_email, EmailNotValidError

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def validate_email_config(config: Dict) -> bool:
    """
    验证邮件配置
    
    Args:
        config: 邮件配置字典
        
    Returns:
        bool: 配置是否有效
    """
    # 检查config是否为None或空
    if not config or not isinstance(config, dict):
        logger.error("配置为空或不是字典类型")
        return False
        
    required_fields = ['email', 'password', 'server', 'port']
    
    # 检查必需字段
    for field in required_fields:
        if not config.get(field):
            logger.error(f"缺少必需字段: {field}")
            return False
    
    # 验证邮箱地址格式
    try:
        validate_email(config['email'])
    except EmailNotValidError as e:
        logger.error(f"邮箱地址格式无效: {str(e)}")
        return False
    
    # 验证端口号
    port = config.get('port')
    if not isinstance(port, int) or port < 1 or port > 65535:
        logger.error(f"端口号无效: {port}")
        return False
    
    return True

def format_email_preview(email_data: Dict, max_length: int = 200) -> str:
    """
    格式化邮件预览文本
    
    Args:
        email_data: 邮件数据字典
        max_length: 最大预览长度
        
    Returns:
        str: 格式化的预览文本
    """
    subject = email_data.get('subject', '无主题')
    body = email_data.get('body_text', email_data.get('body_html', ''))
    
    # 清理HTML标签
    if body:
        body = clean_html_tags(body)
        body = body.strip()
    
    if not body:
        return subject
    
    # 限制长度
    if len(body) > max_length:
        body = body[:max_length] + "..."
    
    return body

def clean_html_tags(html_text: str) -> str:
    """
    清理HTML标签，保留纯文本
    
    Args:
        html_text: HTML文本
        
    Returns:
        str: 清理后的纯文本
    """
    if not html_text:
        return ""
    
    # 统一为字符串
    clean_text = str(html_text)
    
    # 先替换HTML实体为对应字符
    html_entities = {
        '&nbsp;': ' ',
        '&lt;': '<',
        '&gt;': '>',
        '&amp;': '&',
        '&quot;': '"',
        '&#39;': "'",
        '&hellip;': '...',
        '&mdash;': '—',
        '&ndash;': '–'
    }
    
    for entity, replacement in html_entities.items():
        clean_text = clean_text.replace(entity, replacement)
    
    # 再移除HTML标签（包括可能因实体解码重新出现的标签）
    clean_text = re.sub(r'<[^>]+>', '', clean_text)
    
    # 额外移除可能的删除线Markdown标记（~~文本~~）
    clean_text = re.sub(r'~~([^~]+)~~', r'\1', clean_text)
    
    # 移除Unicode组合删除线字符（常见：U+0335/U+0336等）
    clean_text = re.sub(r'[\u0335\u0336\u0337\u0338]', '', clean_text)
    
    # 清理多余的空白字符
    clean_text = re.sub(r'\s+', ' ', clean_text)
    
    return clean_text.strip()

def extract_email_address(email_string: str) -> str:
    """
    从邮件地址字符串中提取纯邮箱地址
    
    Args:
        email_string: 邮件地址字符串，可能包含姓名
        
    Returns:
        str: 纯邮箱地址
    """
    if not email_string:
        return ""
    
    # 使用正则表达式提取邮箱地址
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    matches = re.findall(email_pattern, email_string)
    
    if matches:
        return matches[0]
    
    # 如果正则表达式失败，尝试使用email.utils
    try:
        name, addr = email.utils.parseaddr(email_string)
        return addr if addr else email_string
    except (ValueError, TypeError) as e:
        logger.debug(f"解析邮箱地址失败: {str(e)}")
        return email_string

def format_file_size(size_bytes: int) -> str:
    """
    格式化文件大小为可读格式
    
    Args:
        size_bytes: 字节数
        
    Returns:
        str: 格式化的文件大小
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def parse_time_range(time_range: str) -> tuple:
    """
    解析时间范围字符串
    
    Args:
        time_range: 时间范围描述
        
    Returns:
        tuple: (开始时间, 结束时间)
    """
    now = datetime.now()
    
    if time_range == "最近一周":
        start_date = now - timedelta(days=7)
        end_date = now
    elif time_range == "最近一个月":
        start_date = now - timedelta(days=30)
        end_date = now
    elif time_range == "最近三个月":
        start_date = now - timedelta(days=90)
        end_date = now
    elif time_range == "最近一年":
        start_date = now - timedelta(days=365)
        end_date = now
    else:
        # 默认返回全部时间
        start_date = datetime(1970, 1, 1)
        end_date = now
    
    return start_date, end_date

def generate_email_hash(email_data: Dict) -> str:
    """
    生成邮件的唯一哈希值
    
    Args:
        email_data: 邮件数据字典
        
    Returns:
        str: 邮件哈希值
    """
    # 使用邮件的关键信息生成哈希
    hash_string = f"{email_data.get('message_id', '')}" \
                 f"{email_data.get('subject', '')}" \
                 f"{email_data.get('sender', '')}" \
                 f"{email_data.get('date', '')}"
    
    return hashlib.md5(hash_string.encode('utf-8')).hexdigest()

def export_emails_to_csv(emails: List, filename: str = None) -> bytes:
    """
    导出邮件数据到CSV文件
    
    Args:
        emails: 邮件数据列表 (SearchResult对象或字典)
        filename: 输出文件名 (可选)
        
    Returns:
        bytes: CSV数据
    """
    try:
        # 准备数据
        export_data = []
        for email in emails:
            # 跳过无效的数据类型
            if isinstance(email, str):
                logger.warning(f"跳过字符串类型的邮件数据: {email[:100]}...")
                continue
                
            # 处理SearchResult对象或字典
            if hasattr(email, 'subject'):  # SearchResult对象
                export_data.append({
                    '主题': email.subject,
                    '发件人': extract_email_address(email.sender),
                    '日期': email.date,
                    '文件夹': email.folder,
                    '附件': ', '.join(email.attachments),
                    '正文预览': email.preview,
                    '相关度': f"{email.score:.2%}"
                })
            elif isinstance(email, dict):  # 字典对象
                export_data.append({
                    '主题': email.get('subject', ''),
                    '发件人': extract_email_address(email.get('sender', '')),
                    '收件人': extract_email_address(email.get('recipient', '')),
                    '日期': email.get('date', ''),
                    '文件夹': email.get('folder', ''),
                    '附件': ', '.join(email.get('attachments', [])),
                    '正文预览': format_email_preview(email, 100)
                })
            else:
                logger.warning(f"跳过未知类型的邮件数据: {type(email)}")
        
        # 创建DataFrame并导出
        df = pd.DataFrame(export_data)
        
        # 如果提供了文件名，保存到文件
        if filename:
            df.to_csv(filename, index=False, encoding='utf-8-sig')
            logger.info(f"邮件数据已导出到: {filename}")
        
        # 返回CSV字节数据
        csv_data = df.to_csv(index=False, encoding='utf-8-sig')
        return csv_data.encode('utf-8-sig')
        
    except Exception as e:
        logger.error(f"导出CSV失败: {str(e)}")
        return b""

def export_emails_to_excel(emails: List, filename: str = None) -> bytes:
    """
    导出邮件数据到Excel文件
    
    Args:
        emails: 邮件数据列表 (SearchResult对象或字典)
        filename: 输出文件名 (可选)
        
    Returns:
        bytes: Excel数据
    """
    try:
        # 准备数据
        export_data = []
        for email in emails:
            # 跳过无效的数据类型
            if isinstance(email, str):
                logger.warning(f"跳过字符串类型的邮件数据: {email[:100]}...")
                continue
                
            # 处理SearchResult对象或字典
            if hasattr(email, 'subject'):  # SearchResult对象
                # 处理日期时间，移除时区信息
                date_value = email.date
                if hasattr(date_value, 'replace') and hasattr(date_value, 'tzinfo') and date_value.tzinfo is not None:
                    date_value = date_value.replace(tzinfo=None)
                
                export_data.append({
                    '主题': email.subject,
                    '发件人': extract_email_address(email.sender),
                    '日期': date_value,
                    '文件夹': email.folder,
                    '附件数量': len(email.attachments),
                    '附件列表': ', '.join(email.attachments),
                    '正文预览': email.preview,
                    '相关度': f"{email.score:.2%}"
                })
            elif isinstance(email, dict):  # 字典对象
                # 处理日期时间，移除时区信息
                date_value = email.get('date', '')
                if hasattr(date_value, 'replace') and hasattr(date_value, 'tzinfo') and date_value.tzinfo is not None:
                    date_value = date_value.replace(tzinfo=None)
                
                export_data.append({
                    '主题': email.get('subject', ''),
                    '发件人': extract_email_address(email.get('sender', '')),
                    '收件人': extract_email_address(email.get('recipient', '')),
                    '日期': date_value,
                    '文件夹': email.get('folder', ''),
                    '附件数量': len(email.get('attachments', [])),
                    '附件列表': ', '.join(email.get('attachments', [])),
                    '正文预览': format_email_preview(email, 200)
                })
            else:
                logger.warning(f"跳过未知类型的邮件数据: {type(email)}")
        
        # 创建DataFrame并导出
        df = pd.DataFrame(export_data)
        
        # 创建内存中的Excel文件
        from io import BytesIO
        excel_buffer = BytesIO()
        
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='邮件数据', index=False)
            
            # 调整列宽
            worksheet = writer.sheets['邮件数据']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                
                for cell in column:
                    try:
                        if cell.value is not None and len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except (AttributeError, TypeError) as e:
                        logger.debug(f"计算列宽时跳过单元格: {str(e)}")
                        continue
                
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        # 如果提供了文件名，保存到文件
        if filename:
            with open(filename, 'wb') as f:
                f.write(excel_buffer.getvalue())
            logger.info(f"邮件数据已导出到: {filename}")
        
        # 返回Excel字节数据
        excel_buffer.seek(0)
        return excel_buffer.getvalue()
        
    except Exception as e:
        logger.error(f"导出Excel失败: {str(e)}")
        return b""

def load_config_from_env() -> Dict:
    """
    从环境变量加载配置
    
    Returns:
        Dict: 配置字典
    """
    config = {}
    
    # OSS配置（与 README / .env.vercel.example 保持一致）
    config['oss'] = {
        'access_key_id': os.getenv('ALIYUN_OSS_ACCESS_KEY'),
        'access_key_secret': os.getenv('ALIYUN_OSS_SECRET_KEY'),
        'endpoint': os.getenv('ALIYUN_OSS_ENDPOINT', 'oss-cn-hangzhou.aliyuncs.com'),
        'bucket_name': os.getenv('ALIYUN_OSS_BUCKET', 'email-search-bucket')
    }
    
    # AI模型配置
    config['ai'] = {
        'model_name': os.getenv('SENTENCE_TRANSFORMER_MODEL', 'paraphrase-multilingual-MiniLM-L12-v2'),
        'openai_api_key': os.getenv('OPENAI_API_KEY')
    }
    
    # 应用配置（扩展索引与健康检查、错误告警）
    config['app'] = {
        'max_emails': int(os.getenv('MAX_EMAILS', '30000')),
        'cache_dir': os.getenv('CACHE_DIR', './cache'),
        'debug': os.getenv('DEBUG', 'False').lower() == 'true',
        # 索引控制
        'index_async': os.getenv('INDEX_ASYNC', 'false').lower() == 'true',
        'index_batch_size': int(os.getenv('INDEX_BATCH_SIZE', '500')),
        'index_time_slice_sec': int(os.getenv('INDEX_TIME_SLICE_SEC', '20')),
        # 错误告警
        'error_webhook_url': os.getenv('APP_ERROR_WEBHOOK_URL'),
        # 健康检查
        'healthcheck_token': os.getenv('HEALTHCHECK_TOKEN')
    }
    
    return config

def save_search_history(query: str, results_count: int, 
                       history_file: str = "search_history.json"):
    """
    保存搜索历史
    
    Args:
        query: 搜索查询
        results_count: 结果数量
        history_file: 历史文件路径
    """
    try:
        # 加载现有历史
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
        else:
            history = []
        
        # 添加新记录
        new_record = {
            'query': query,
            'results_count': results_count,
            'timestamp': datetime.now().isoformat(),
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        history.append(new_record)
        
        # 限制历史记录数量
        if len(history) > 100:
            history = history[-100:]
        
        # 保存历史
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        logger.error(f"保存搜索历史失败: {str(e)}")

def load_search_history(history_file: str = "search_history.json") -> List[Dict]:
    """
    加载搜索历史
    
    Args:
        history_file: 历史文件路径
        
    Returns:
        List[Dict]: 搜索历史列表
    """
    try:
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except Exception as e:
        logger.error(f"加载搜索历史失败: {str(e)}")
        return []

def create_cache_dir(cache_dir: str = "./cache") -> str:
    """
    创建缓存目录
    
    Args:
        cache_dir: 缓存目录路径
        
    Returns:
        str: 创建的缓存目录路径
    """
    try:
        os.makedirs(cache_dir, exist_ok=True)
        
        # 创建子目录
        subdirs = ['indices', 'metadata', 'temp', 'exports']
        for subdir in subdirs:
            os.makedirs(os.path.join(cache_dir, subdir), exist_ok=True)
        
        return cache_dir
    except Exception as e:
        logger.error(f"创建缓存目录失败: {str(e)}")
        return cache_dir

def cleanup_temp_files(temp_dir: str, max_age_hours: int = 24):
    """
    清理临时文件
    
    Args:
        temp_dir: 临时文件目录
        max_age_hours: 文件最大保留时间（小时）
    """
    try:
        if not os.path.exists(temp_dir):
            return
        
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        deleted_count = 0
        
        for filename in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, filename)
            
            if os.path.isfile(file_path):
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                
                if file_time < cutoff_time:
                    os.remove(file_path)
                    deleted_count += 1
        
        logger.info(f"清理临时文件完成，删除了 {deleted_count} 个文件")
        
    except Exception as e:
        logger.error(f"清理临时文件失败: {str(e)}")

def validate_search_query(query: str) -> bool:
    """
    验证搜索查询是否有效
    
    Args:
        query: 搜索查询字符串
        
    Returns:
        bool: 查询是否有效
    """
    if not query or not query.strip():
        return False
    
    # 检查查询长度
    if len(query.strip()) < 2:
        return False
    
    # 检查是否只包含特殊字符
    if re.match(r'^[^\w\u4e00-\u9fff]+$', query.strip()):
        return False
    
    return True

def highlight_search_terms(text: str, query: str,
                          highlight_tag: str = "**") -> str:
    """
    在文本中高亮搜索关键词
    
    Args:
        text: 原始文本
        query: 搜索查询
        highlight_tag: 高亮标签
        
    Returns:
        str: 高亮后的文本
    """
    if not query or not text:
        return text
    
    # 分割查询词
    terms = query.split()
    highlighted_text = text
    
    # 计算结束标签（支持HTML标签，如<mark>或<span ...>）
    end_tag = highlight_tag
    if highlight_tag.startswith("<"):
        # 提取标签名
        m = re.match(r"<\s*(\w+)", highlight_tag)
        if m:
            end_tag = f"</{m.group(1)}>"
    
    for term in terms:
        if len(term) > 1:  # 忽略单字符
            # 使用正则表达式进行不区分大小写的替换
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            highlighted_text = pattern.sub(
                f"{highlight_tag}{term}{end_tag}",
                highlighted_text
            )
    
    return highlighted_text

def save_email_config(config: Dict, config_name: str = "default", 
                     config_dir: str = "./configs") -> bool:
    """
    保存邮箱配置到本地文件
    
    Args:
        config: 邮箱配置字典
        config_name: 配置名称
        config_dir: 配置文件目录
        
    Returns:
        bool: 保存是否成功
    """
    try:
        # 创建配置目录
        os.makedirs(config_dir, exist_ok=True)
        
        # 过滤敏感信息，只保存必要的配置
        safe_config = {
            'provider': config.get('provider', ''),
            'server': config.get('server', ''),
            'port': config.get('port', 993),
            'email': config.get('email', ''),
            'use_ssl': config.get('use_ssl', True),
            'disable_ssl_verify': config.get('disable_ssl_verify', False),
            'saved_at': datetime.now().isoformat()
        }
        
        # 配置文件路径
        config_file = os.path.join(config_dir, f"{config_name}.json")
        
        # 保存配置
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(safe_config, f, indent=2, ensure_ascii=False)
        
        logger.info(f"邮箱配置已保存到: {config_file}")
        return True
        
    except Exception as e:
        logger.error(f"保存邮箱配置失败: {str(e)}")
        return False

def load_email_config(config_name: str = "default", 
                     config_dir: str = "./configs") -> Optional[Dict]:
    """
    从本地文件加载邮箱配置
    
    Args:
        config_name: 配置名称
        config_dir: 配置文件目录
        
    Returns:
        Optional[Dict]: 加载的配置字典，失败时返回None
    """
    try:
        config_file = os.path.join(config_dir, f"{config_name}.json")
        
        if not os.path.exists(config_file):
            logger.warning(f"配置文件不存在: {config_file}")
            return None
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        logger.info(f"邮箱配置已加载: {config_file}")
        return config
        
    except Exception as e:
        logger.error(f"加载邮箱配置失败: {str(e)}")
        return None

def list_saved_configs(config_dir: str = "./configs") -> List[str]:
    """
    列出所有已保存的配置
    
    Args:
        config_dir: 配置文件目录
        
    Returns:
        List[str]: 配置名称列表
    """
    try:
        if not os.path.exists(config_dir):
            return []
        
        config_files = [f for f in os.listdir(config_dir) if f.endswith('.json')]
        config_names = [os.path.splitext(f)[0] for f in config_files]
        
        return sorted(config_names)
        
    except Exception as e:
        logger.error(f"列出配置文件失败: {str(e)}")
        return []

def delete_email_config(config_name: str, config_dir: str = "./configs") -> bool:
    """
    删除保存的邮箱配置
    
    Args:
        config_name: 配置名称
        config_dir: 配置文件目录
        
    Returns:
        bool: 删除是否成功
    """
    try:
        config_file = os.path.join(config_dir, f"{config_name}.json")
        
        if os.path.exists(config_file):
            os.remove(config_file)
            logger.info(f"配置文件已删除: {config_file}")
            return True
        else:
            logger.warning(f"配置文件不存在: {config_file}")
            return False
            
    except Exception as e:
        logger.error(f"删除配置文件失败: {str(e)}")
        return False

def email_message_to_dict(email_obj) -> Dict:
    """
    将EmailMessage对象转换为字典
    
    Args:
        email_obj: EmailMessage对象
        
    Returns:
        Dict: 邮件字典数据
    """
    if hasattr(email_obj, '__dict__'):
        # 如果是EmailMessage对象，转换为字典
        email_dict = {
            'uid': email_obj.uid,
            'subject': email_obj.subject,
            'sender': email_obj.sender,
            'recipient': email_obj.recipient,
            'date': email_obj.date.isoformat() if hasattr(email_obj.date, 'isoformat') else str(email_obj.date),
            'body_text': email_obj.body_text,
            'body_html': email_obj.body_html,
            'attachments': email_obj.attachments,
            'message_id': email_obj.message_id,
            'folder': email_obj.folder
        }
        return email_dict
    else:
        # 如果已经是字典，直接返回
        return email_obj

def save_emails_to_cache(emails: List, cache_dir: str = "./cache") -> bool:
    """
    保存邮件数据到本地缓存
    
    Args:
        emails: 邮件数据列表
        cache_dir: 缓存目录
        
    Returns:
        bool: 保存是否成功
    """
    try:
        # 确保缓存目录存在
        os.makedirs(cache_dir, exist_ok=True)
        
        # 生成缓存文件名（包含时间戳）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cache_file = os.path.join(cache_dir, f"emails_cache_{timestamp}.json")
        
        # 转换邮件数据为字典格式
        email_dicts = [email_message_to_dict(email) for email in emails]
        
        # 保存邮件数据
        cache_data = {
            "timestamp": timestamp,
            "email_count": len(emails),
            "emails": email_dicts,
            "sync_time": datetime.now().isoformat()
        }
        
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2, default=str)
        
        # 保存最新缓存文件的引用
        latest_cache_file = os.path.join(cache_dir, "latest_emails_cache.json")
        with open(latest_cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2, default=str)
        
        logger.info(f"邮件数据已保存到缓存: {cache_file}")
        return True
        
    except Exception as e:
        logger.error(f"保存邮件数据到缓存失败: {str(e)}")
        return False

def dict_to_email_message(email_dict: Dict) -> 'EmailMessage':
    """
    将字典数据转换为EmailMessage对象
    
    Args:
        email_dict: 邮件字典数据
        
    Returns:
        EmailMessage: 邮件对象
    """
    from .email_connector import EmailMessage
    
    # 处理日期字段
    date_value = email_dict.get('date')
    if isinstance(date_value, str):
        try:
            # 尝试解析ISO格式的日期字符串
            date_value = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            # 如果解析失败，使用当前时间
            date_value = datetime.now()
    elif not isinstance(date_value, datetime):
        date_value = datetime.now()
    
    return EmailMessage(
        uid=email_dict.get('uid', ''),
        subject=email_dict.get('subject', ''),
        sender=email_dict.get('sender', ''),
        recipient=email_dict.get('recipient', ''),
        date=date_value,
        body_text=email_dict.get('body_text', ''),
        body_html=email_dict.get('body_html', ''),
        attachments=email_dict.get('attachments', []),
        message_id=email_dict.get('message_id', ''),
        folder=email_dict.get('folder', '')
    )

def load_emails_from_cache(cache_dir: str = "./cache") -> Optional[List]:
    """
    从本地缓存加载邮件数据
    
    Args:
        cache_dir: 缓存目录
        
    Returns:
        Optional[List]: 邮件数据列表（EmailMessage对象），如果加载失败则返回None
    """
    try:
        latest_cache_file = os.path.join(cache_dir, "latest_emails_cache.json")
        
        if not os.path.exists(latest_cache_file):
            logger.info("未找到邮件缓存文件")
            return None
        
        with open(latest_cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        email_dicts = cache_data.get("emails", [])
        sync_time = cache_data.get("sync_time", "未知")
        
        # 将字典转换为EmailMessage对象
        emails = [dict_to_email_message(email_dict) for email_dict in email_dicts]
        
        logger.info(f"从缓存加载了 {len(emails)} 封邮件，同步时间: {sync_time}")
        return emails
        
    except Exception as e:
        logger.error(f"从缓存加载邮件数据失败: {str(e)}")
        return None

def get_cache_info(cache_dir: str = "./cache") -> Optional[Dict]:
    """
    获取缓存信息
    
    Args:
        cache_dir: 缓存目录
        
    Returns:
        Optional[Dict]: 缓存信息，如果获取失败则返回None
    """
    try:
        latest_cache_file = os.path.join(cache_dir, "latest_emails_cache.json")
        
        if not os.path.exists(latest_cache_file):
            return None
        
        with open(latest_cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        return {
            "email_count": cache_data.get("email_count", 0),
            "sync_time": cache_data.get("sync_time", "未知"),
            "timestamp": cache_data.get("timestamp", "未知"),
            "file_size": os.path.getsize(latest_cache_file)
        }
        
    except Exception as e:
        logger.error(f"获取缓存信息失败: {str(e)}")
        return None