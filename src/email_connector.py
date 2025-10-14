"""
邮件连接器模块
负责连接各种邮箱服务，获取和同步邮件数据
"""

import imaplib
import email
import ssl
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import re
from email.header import decode_header
from email.utils import parsedate_to_datetime
import logging
from dataclasses import dataclass

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class EmailMessage:
    """邮件消息数据类"""
    uid: str
    subject: str
    sender: str
    recipient: str
    date: datetime
    body_text: str
    body_html: str
    attachments: List[str]
    message_id: str
    folder: str

class EmailConnector:
    """邮件连接器类"""
    
    def __init__(self, config: Dict):
        """
        初始化邮件连接器
        
        Args:
            config: 邮箱配置字典，包含server, port, email, password等
        """
        self.config = config
        self.connection = None
        self.is_connected = False
        
        # 预定义的邮箱服务器配置
        self.server_configs = {
            "Gmail": {
                "server": "imap.gmail.com",
                "port": 993,
                "use_ssl": True
            },
            "Outlook": {
                "server": "outlook.office365.com", 
                "port": 993,
                "use_ssl": True
            },
            "QQ邮箱": {
                "server": "imap.qq.com",
                "port": 993,
                "use_ssl": True
            },
            "163邮箱": {
                "server": "imap.163.com",
                "port": 993,
                "use_ssl": True
            }
        }
    
    def test_connection(self) -> bool:
        """
        测试邮箱连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            # 创建SSL上下文
            context = ssl.create_default_context()
            
            # 检查是否禁用SSL验证
            if self.config.get('disable_ssl_verify', False):
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                logger.warning("SSL证书验证已禁用")
            
            # 连接到IMAP服务器
            server = self.config.get('server')
            port = self.config.get('port', 993)
            
            logger.info(f"正在连接到 {server}:{port}")
            
            # 建立连接
            mail = imaplib.IMAP4_SSL(server, port, ssl_context=context)
            
            # 登录
            email_addr = self.config.get('email')
            password = self.config.get('password')
            
            result = mail.login(email_addr, password)
            
            if result[0] == 'OK':
                logger.info("邮箱连接成功")
                mail.logout()
                return True
            else:
                logger.error(f"登录失败: {result}")
                return False
                
        except Exception as e:
            logger.error(f"连接失败: {str(e)}")
            return False
    
    def connect(self) -> bool:
        """
        建立邮箱连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            if self.is_connected:
                return True
            
            # 创建SSL上下文
            context = ssl.create_default_context()
            
            # 检查是否禁用SSL验证
            if self.config.get('disable_ssl_verify', False):
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                logger.warning("SSL证书验证已禁用")
            
            # 连接到IMAP服务器
            server = self.config.get('server')
            port = self.config.get('port', 993)
            
            self.connection = imaplib.IMAP4_SSL(server, port, ssl_context=context)
            
            # 登录
            email_addr = self.config.get('email')
            password = self.config.get('password')
            
            result = self.connection.login(email_addr, password)
            
            if result[0] == 'OK':
                self.is_connected = True
                logger.info("邮箱连接建立成功")
                return True
            else:
                logger.error(f"登录失败: {result}")
                return False
                
        except Exception as e:
            logger.error(f"连接失败: {str(e)}")
            self.is_connected = False
            return False
    
    def disconnect(self):
        """断开邮箱连接"""
        try:
            if self.connection and self.is_connected:
                self.connection.logout()
                self.is_connected = False
                logger.info("邮箱连接已断开")
        except Exception as e:
            logger.error(f"断开连接时出错: {str(e)}")
    
    def get_folders(self) -> List[str]:
        """
        获取邮箱文件夹列表
        
        Returns:
            List[str]: 文件夹名称列表
        """
        if not self.is_connected:
            if not self.connect():
                return []
        
        try:
            result, folders = self.connection.list()
            if result == 'OK':
                folder_list = []
                for folder in folders:
                    # 解析文件夹名称
                    folder_str = folder.decode('utf-8', errors='ignore')
                    
                    # 提取文件夹名称（处理IMAP LIST响应格式）
                    # 格式通常是: (flags) "delimiter" "folder_name"
                    parts = folder_str.split('"')
                    if len(parts) >= 3:
                        folder_name = parts[-2]  # 倒数第二个引号内的内容
                    else:
                        # 如果没有引号，尝试提取最后一部分
                        parts = folder_str.split()
                        folder_name = parts[-1] if parts else folder_str
                    
                    # 处理Modified UTF-7编码（IMAP标准编码）
                    folder_name = self._decode_folder_name(folder_name)
                    folder_list.append(folder_name)
                return folder_list
            return []
        except Exception as e:
            logger.error(f"获取文件夹失败: {str(e)}")
            return []
    
    def get_emails(self, folder: str = "INBOX", limit: Optional[int] = 100, 
                   days_back: Optional[int] = 30) -> List[EmailMessage]:
        """
        获取邮件列表
        
        Args:
            folder: 邮箱文件夹名称
            limit: 获取邮件数量限制，None表示无限制
            days_back: 获取多少天前的邮件，None表示获取所有邮件
            
        Returns:
            List[EmailMessage]: 邮件消息列表
        """
        if not self.is_connected:
            if not self.connect():
                return []

        try:
            # 选择文件夹
            result = self.connection.select(folder)
            if result[0] != 'OK':
                logger.error(f"无法选择文件夹: {folder}")
                return []
            
            # 构建搜索条件
            if days_back is not None:
                since_date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
                search_criteria = f'(SINCE "{since_date}")'
            else:
                search_criteria = 'ALL'  # 获取所有邮件
            
            # 搜索邮件
            result, message_ids = self.connection.search(None, search_criteria)
            if result != 'OK':
                logger.error("搜索邮件失败")
                return []
            
            # 获取邮件ID列表
            email_ids = message_ids[0].split()
            
            # 限制邮件数量
            if limit is not None and limit > 0:
                email_ids = email_ids[-limit:]  # 获取最新的邮件
            
            emails = []
            
            for email_id in email_ids:
                try:
                    email_msg = self._fetch_email(email_id, folder)
                    if email_msg:
                        emails.append(email_msg)
                except Exception as e:
                    logger.error(f"获取邮件 {email_id} 失败: {str(e)}")
                    continue
            
            logger.info(f"成功获取 {len(emails)} 封邮件")
            return emails
            
        except Exception as e:
            logger.error(f"获取邮件失败: {str(e)}")
            return []
    
    def search_emails_realtime(self, query: str, limit: int = 50) -> List[EmailMessage]:
        """
        实时搜索邮件（直接查询邮件服务器）
        
        Args:
            query: 搜索查询字符串
            limit: 返回结果数量限制
            
        Returns:
            List[EmailMessage]: 匹配的邮件列表
        """
        if not self.is_connected:
            if not self.connect():
                return []
        
        try:
            # 获取所有文件夹进行搜索
            folders = self.get_folders()
            all_results = []
            
            for folder in folders[:5]:  # 限制搜索前5个文件夹以提高性能
                try:
                    # 选择文件夹
                    result = self.connection.select(folder)
                    if result[0] != 'OK':
                        continue
                    
                    # 构建IMAP搜索条件
                    search_criteria = []
                    
                    # 简单的关键词搜索
                    keywords = query.split()
                    for keyword in keywords[:3]:  # 限制关键词数量
                        if len(keyword) > 2:  # 忽略太短的词
                            # 搜索主题和正文
                            search_criteria.append(f'OR SUBJECT "{keyword}" BODY "{keyword}"')
                    
                    if not search_criteria:
                        # 如果没有有效关键词，搜索主题
                        search_criteria = [f'SUBJECT "{query}"']
                    
                    # 组合搜索条件
                    final_criteria = ' '.join(search_criteria)
                    
                    # 执行搜索
                    result, message_ids = self.connection.search(None, final_criteria)
                    if result == 'OK' and message_ids[0]:
                        email_ids = message_ids[0].split()
                        
                        # 限制每个文件夹的结果数量
                        folder_limit = min(limit // len(folders) + 1, 20)
                        email_ids = email_ids[-folder_limit:]  # 获取最新的邮件
                        
                        for email_id in email_ids:
                            try:
                                email_msg = self._fetch_email(email_id, folder)
                                if email_msg:
                                    all_results.append(email_msg)
                            except Exception as e:
                                logger.error(f"获取搜索结果邮件失败: {str(e)}")
                                continue
                                
                except Exception as e:
                    logger.error(f"搜索文件夹 {folder} 失败: {str(e)}")
                    continue
            
            # 按日期排序，最新的在前
            all_results.sort(key=lambda x: x.date, reverse=True)
            
            # 应用总体限制
            final_results = all_results[:limit]
            
            logger.info(f"实时搜索找到 {len(final_results)} 封邮件")
            return final_results
            
        except Exception as e:
            logger.error(f"实时搜索失败: {str(e)}")
            return []
    
    def _fetch_email(self, email_id: bytes, folder: str) -> Optional[EmailMessage]:
        """
        获取单封邮件的详细信息
        
        Args:
            email_id: 邮件ID
            folder: 文件夹名称
            
        Returns:
            Optional[EmailMessage]: 邮件消息对象
        """
        try:
            # 获取邮件数据
            result, msg_data = self.connection.fetch(email_id, '(RFC822)')
            if result != 'OK':
                return None
            
            # 解析邮件
            email_body = msg_data[0][1]
            email_message = email.message_from_bytes(email_body)
            
            # 提取邮件信息
            subject = self._decode_header(email_message.get('Subject', ''))
            sender = self._decode_header(email_message.get('From', ''))
            recipient = self._decode_header(email_message.get('To', ''))
            date_str = email_message.get('Date', '')
            message_id = email_message.get('Message-ID', '')
            
            # 解析日期
            try:
                date = parsedate_to_datetime(date_str)
            except (ValueError, TypeError, OverflowError) as e:
                logger.debug(f"日期解析失败，使用当前时间: {date_str}, 错误: {str(e)}")
                date = datetime.now()
            
            # 提取邮件正文
            body_text, body_html = self._extract_body(email_message)
            
            # 提取附件信息
            attachments = self._extract_attachments(email_message)
            
            return EmailMessage(
                uid=email_id.decode(),
                subject=subject,
                sender=sender,
                recipient=recipient,
                date=date,
                body_text=body_text,
                body_html=body_html,
                attachments=attachments,
                message_id=message_id,
                folder=folder
            )
            
        except Exception as e:
            logger.error(f"解析邮件失败: {str(e)}")
            return None
    
    def _decode_header(self, header: str) -> str:
        """
        解码邮件头部信息
        
        Args:
            header: 邮件头部字符串
            
        Returns:
            str: 解码后的字符串
        """
        if not header:
            return ""
        
        try:
            decoded_parts = decode_header(header)
            decoded_string = ""
            
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    if encoding:
                        decoded_string += part.decode(encoding)
                    else:
                        decoded_string += part.decode('utf-8', errors='ignore')
                else:
                    decoded_string += part
            
            return decoded_string
        except Exception as e:
            logger.error(f"解码头部失败: {str(e)}")
            return header
    
    def _extract_body(self, email_message) -> Tuple[str, str]:
        """
        提取邮件正文
        
        Args:
            email_message: 邮件消息对象
            
        Returns:
            Tuple[str, str]: (纯文本正文, HTML正文)
        """
        body_text = ""
        body_html = ""
        
        try:
            if email_message.is_multipart():
                for part in email_message.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition"))
                    
                    # 跳过附件
                    if "attachment" in content_disposition:
                        continue
                    
                    if content_type == "text/plain":
                        charset = part.get_content_charset() or 'utf-8'
                        body_text += part.get_payload(decode=True).decode(charset, errors='ignore')
                    elif content_type == "text/html":
                        charset = part.get_content_charset() or 'utf-8'
                        body_html += part.get_payload(decode=True).decode(charset, errors='ignore')
            else:
                content_type = email_message.get_content_type()
                charset = email_message.get_content_charset() or 'utf-8'
                body = email_message.get_payload(decode=True).decode(charset, errors='ignore')
                
                if content_type == "text/plain":
                    body_text = body
                elif content_type == "text/html":
                    body_html = body
                else:
                    body_text = body
        
        except Exception as e:
            logger.error(f"提取邮件正文失败: {str(e)}")
        
        return body_text, body_html
    
    def _extract_attachments(self, email_message) -> List[str]:
        """
        提取附件信息
        
        Args:
            email_message: 邮件消息对象
            
        Returns:
            List[str]: 附件文件名列表
        """
        attachments = []
        
        try:
            if email_message.is_multipart():
                for part in email_message.walk():
                    content_disposition = str(part.get("Content-Disposition"))
                    
                    if "attachment" in content_disposition:
                        filename = part.get_filename()
                        if filename:
                            # 解码文件名
                            filename = self._decode_header(filename)
                            attachments.append(filename)
        
        except Exception as e:
            logger.error(f"提取附件信息失败: {str(e)}")
        
        return attachments
    
    def get_email_count(self, folder: str = "INBOX") -> int:
        """
        获取指定文件夹中的邮件数量
        
        Args:
            folder: 文件夹名称
            
        Returns:
            int: 邮件数量
        """
        if not self.is_connected:
            if not self.connect():
                return 0
        
        try:
            result = self.connection.select(folder)
            if result[0] == 'OK':
                return int(result[1][0])
            return 0
        except Exception as e:
            logger.error(f"获取邮件数量失败: {str(e)}")
            return 0
    
    def __enter__(self):
        """上下文管理器入口"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.disconnect()
    
    def _decode_folder_name(self, folder_name: str) -> str:
        """
        解码文件夹名称，处理Modified UTF-7编码和其他编码格式
        
        Args:
            folder_name: 原始文件夹名称
            
        Returns:
            str: 解码后的文件夹名称
        """
        if not folder_name:
            return folder_name
        
        try:
            # 首先尝试处理Modified UTF-7编码（IMAP标准）
            if '&' in folder_name:
                try:
                    # 使用Python的内置Modified UTF-7解码器
                    import codecs
                    
                    # 将Modified UTF-7转换为标准UTF-7格式
                    # Modified UTF-7使用&和-作为转义字符，而标准UTF-7使用+和-
                    utf7_name = folder_name.replace('&', '+').replace(',', '/')
                    
                    # 如果以-结尾，确保正确的UTF-7格式
                    if utf7_name.endswith('-'):
                        utf7_name = utf7_name[:-1] + '-'
                    elif not utf7_name.endswith('-') and '+' in utf7_name:
                        utf7_name += '-'
                    
                    # 尝试UTF-7解码
                    try:
                        decoded = utf7_name.encode('ascii').decode('utf-7')
                        if decoded and decoded != folder_name:
                            logger.info(f"成功解码文件夹名称: {folder_name} -> {decoded}")
                            return decoded
                    except (UnicodeDecodeError, UnicodeEncodeError):
                        pass
                    
                    # 如果UTF-7失败，尝试imap4-utf-7
                    try:
                        decoded = folder_name.encode('ascii').decode('imap4-utf-7')
                        if decoded and decoded != folder_name:
                            logger.info(f"成功解码文件夹名称: {folder_name} -> {decoded}")
                            return decoded
                    except (UnicodeDecodeError, UnicodeEncodeError, LookupError):
                        pass
                        
                except Exception as e:
                    logger.debug(f"Modified UTF-7解码失败: {folder_name}, 错误: {str(e)}")
            
            # 如果不是Modified UTF-7或解码失败，尝试其他常见编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'shift_jis', 'euc-jp', 'iso-2022-jp']
            
            for encoding in encodings:
                try:
                    # 如果已经是字符串，先编码为bytes再解码
                    if isinstance(folder_name, str):
                        # 尝试不同的编码方式
                        decoded = folder_name.encode('latin1').decode(encoding)
                        if decoded != folder_name:
                            logger.info(f"使用{encoding}编码解码文件夹名称: {folder_name} -> {decoded}")
                            return decoded
                    else:
                        decoded = folder_name.decode(encoding)
                        if decoded != folder_name:
                            logger.info(f"使用{encoding}编码解码文件夹名称: {folder_name} -> {decoded}")
                            return decoded
                except (UnicodeDecodeError, UnicodeEncodeError, AttributeError):
                    continue
            
            # 如果所有编码都失败，返回一个友好的显示名称
            if '&' in folder_name and folder_name.startswith('&') and folder_name.endswith('-'):
                # 对于无法解码的Modified UTF-7，提供一个描述性名称
                logger.warning(f"无法解码文件夹名称: {folder_name}，使用描述性名称")
                return f"[编码文件夹: {folder_name}]"
            
            return folder_name
            
        except Exception as e:
            logger.error(f"解码文件夹名称失败: {folder_name}, 错误: {str(e)}")
            return f"[解码失败: {folder_name}]"