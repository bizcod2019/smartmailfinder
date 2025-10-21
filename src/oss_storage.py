"""
阿里云OSS存储模块
负责邮件索引和元数据的云端存储管理
"""

import oss2
import os
import json
import pickle
import tempfile
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging
import gzip
import io

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OSSStorage:
    """阿里云OSS存储管理类"""
    
    def __init__(self, access_key_id: str, access_key_secret: str, 
                 endpoint: str, bucket_name: str):
        """
        初始化OSS存储
        
        Args:
            access_key_id: 阿里云访问密钥ID
            access_key_secret: 阿里云访问密钥Secret
            endpoint: OSS服务端点
            bucket_name: 存储桶名称
        """
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.endpoint = endpoint
        self.bucket_name = bucket_name
        
        # 初始化OSS客户端
        try:
            auth = oss2.Auth(access_key_id, access_key_secret)
            self.bucket = oss2.Bucket(auth, endpoint, bucket_name)
            self.is_connected = True
            logger.info(f"OSS连接成功: {bucket_name}")
        except Exception as e:
            logger.error(f"OSS连接失败: {str(e)}")
            self.is_connected = False
            self.bucket = None
        
        # 定义存储路径结构
        self.paths = {
            'indices': 'emails/indices/',
            'metadata': 'emails/metadata/',
            'cache': 'emails/cache/',
            'config': 'emails/config/'
        }
    
    def test_connection(self) -> bool:
        """
        测试OSS连接
        
        Returns:
            bool: 连接是否正常
        """
        if not self.is_connected:
            return False
        
        try:
            # 尝试列出存储桶中的对象
            result = self.bucket.list_objects(prefix='emails/', max_keys=1)
            logger.info("OSS连接测试成功")
            return True
        except Exception as e:
            logger.error(f"OSS连接测试失败: {str(e)}")
            return False
    
    def upload_index(self, local_index_path: str, index_name: str = None) -> bool:
        """
        上传邮件索引到OSS
        
        Args:
            local_index_path: 本地索引文件路径前缀
            index_name: 索引名称，默认使用时间戳
            
        Returns:
            bool: 上传是否成功
        """
        if not self.is_connected:
            logger.error("OSS未连接")
            return False
        
        if index_name is None:
            index_name = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        try:
            # 上传FAISS索引文件
            faiss_file = f"{local_index_path}.faiss"
            if os.path.exists(faiss_file):
                oss_key = f"{self.paths['indices']}{index_name}.faiss"
                self._upload_file_with_compression(faiss_file, oss_key)
                logger.info(f"FAISS索引已上传: {oss_key}")
            
            # 上传元数据文件
            metadata_file = f"{local_index_path}.metadata"
            if os.path.exists(metadata_file):
                oss_key = f"{self.paths['metadata']}{index_name}.metadata"
                self._upload_file_with_compression(metadata_file, oss_key)
                logger.info(f"元数据已上传: {oss_key}")
            
            # 上传配置文件
            config_file = f"{local_index_path}.config"
            if os.path.exists(config_file):
                oss_key = f"{self.paths['config']}{index_name}.config"
                self.bucket.put_object_from_file(oss_key, config_file)
                logger.info(f"配置文件已上传: {oss_key}")
            
            # 更新索引列表
            self._update_index_list(index_name)
            
            logger.info(f"索引 {index_name} 上传完成")
            return True
            
        except Exception as e:
            logger.error(f"上传索引失败: {str(e)}")
            return False
    
    def download_index(self, index_name: str, local_path: str) -> bool:
        """
        从OSS下载邮件索引
        
        Args:
            index_name: 索引名称
            local_path: 本地保存路径前缀
            
        Returns:
            bool: 下载是否成功
        """
        if not self.is_connected:
            logger.error("OSS未连接")
            return False
        
        try:
            # 创建本地目录
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # 下载FAISS索引文件
            faiss_key = f"{self.paths['indices']}{index_name}.faiss"
            faiss_file = f"{local_path}.faiss"
            if self._download_file_with_decompression(faiss_key, faiss_file):
                logger.info(f"FAISS索引已下载: {faiss_file}")
            
            # 下载元数据文件
            metadata_key = f"{self.paths['metadata']}{index_name}.metadata"
            metadata_file = f"{local_path}.metadata"
            if self._download_file_with_decompression(metadata_key, metadata_file):
                logger.info(f"元数据已下载: {metadata_file}")
            
            # 下载配置文件
            config_key = f"{self.paths['config']}{index_name}.config"
            config_file = f"{local_path}.config"
            try:
                self.bucket.get_object_to_file(config_key, config_file)
                logger.info(f"配置文件已下载: {config_file}")
            except oss2.exceptions.NoSuchKey:
                logger.warning(f"配置文件不存在: {config_key}")
            
            logger.info(f"索引 {index_name} 下载完成")
            return True
            
        except Exception as e:
            logger.error(f"下载索引失败: {str(e)}")
            return False
    
    def _upload_file_with_compression(self, local_file: str, oss_key: str):
        """
        压缩并上传文件
        
        Args:
            local_file: 本地文件路径
            oss_key: OSS对象键
        """
        with open(local_file, 'rb') as f:
            # 压缩文件内容
            compressed_data = gzip.compress(f.read())
            
            # 上传压缩后的数据
            self.bucket.put_object(oss_key + '.gz', compressed_data)
    
    def _download_file_with_decompression(self, oss_key: str, local_file: str) -> bool:
        """
        下载并解压文件
        
        Args:
            oss_key: OSS对象键
            local_file: 本地文件路径
            
        Returns:
            bool: 下载是否成功
        """
        try:
            # 尝试下载压缩文件
            compressed_key = oss_key + '.gz'
            try:
                compressed_data = self.bucket.get_object(compressed_key).read()
                # 解压数据
                decompressed_data = gzip.decompress(compressed_data)
                
                # 保存到本地文件
                with open(local_file, 'wb') as f:
                    f.write(decompressed_data)
                
                return True
            except oss2.exceptions.NoSuchKey:
                # 如果压缩文件不存在，尝试下载原始文件
                self.bucket.get_object_to_file(oss_key, local_file)
                return True
                
        except oss2.exceptions.NoSuchKey:
            logger.warning(f"文件不存在: {oss_key}")
            return False
        except Exception as e:
            logger.error(f"下载文件失败: {str(e)}")
            return False
    
    def list_indices(self) -> List[Dict]:
        """
        列出所有可用的索引
        
        Returns:
            List[Dict]: 索引信息列表
        """
        if not self.is_connected:
            return []
        
        try:
            indices = []
            
            # 列出索引文件
            for obj in oss2.ObjectIterator(self.bucket, prefix=self.paths['indices']):
                if obj.key.endswith('.faiss') or obj.key.endswith('.faiss.gz'):
                    # 提取索引名称
                    filename = os.path.basename(obj.key)
                    index_name = filename.replace('.faiss.gz', '').replace('.faiss', '')
                    
                    # 获取文件信息
                    index_info = {
                        'name': index_name,
                        'size': obj.size,
                        'last_modified': obj.last_modified,
                        'key': obj.key
                    }
                    
                    # 尝试获取配置信息
                    config_key = f"{self.paths['config']}{index_name}.config"
                    try:
                        config_obj = self.bucket.get_object(config_key)
                        config_data = json.loads(config_obj.read().decode('utf-8'))
                        index_info.update(config_data)
                    except (oss2.exceptions.NoSuchKey, json.JSONDecodeError) as e:
                        logger.debug(f"无法加载索引配置 {config_key}: {str(e)}")
                    except Exception as e:
                        logger.warning(f"加载索引配置时出错 {config_key}: {str(e)}")
                    
                    indices.append(index_info)
            
            # 按修改时间排序
            indices.sort(key=lambda x: x['last_modified'], reverse=True)
            
            return indices
            
        except Exception as e:
            logger.error(f"列出索引失败: {str(e)}")
            return []
    
    def delete_index(self, index_name: str) -> bool:
        """
        删除指定的索引
        
        Args:
            index_name: 索引名称
            
        Returns:
            bool: 删除是否成功
        """
        if not self.is_connected:
            return False
        
        try:
            # 删除相关文件
            files_to_delete = [
                f"{self.paths['indices']}{index_name}.faiss",
                f"{self.paths['indices']}{index_name}.faiss.gz",
                f"{self.paths['metadata']}{index_name}.metadata",
                f"{self.paths['metadata']}{index_name}.metadata.gz",
                f"{self.paths['config']}{index_name}.config"
            ]
            
            deleted_count = 0
            for file_key in files_to_delete:
                try:
                    self.bucket.delete_object(file_key)
                    deleted_count += 1
                except oss2.exceptions.NoSuchKey:
                    pass  # 文件不存在，忽略
            
            # 更新索引列表
            self._update_index_list(index_name, remove=True)
            
            logger.info(f"索引 {index_name} 已删除，删除了 {deleted_count} 个文件")
            return True
            
        except Exception as e:
            logger.error(f"删除索引失败: {str(e)}")
            return False
    
    def _update_index_list(self, index_name: str, remove: bool = False):
        """
        更新索引列表文件
        
        Args:
            index_name: 索引名称
            remove: 是否从列表中移除
        """
        try:
            list_key = f"{self.paths['config']}index_list.json"
            
            # 获取现有列表
            try:
                existing_data = self.bucket.get_object(list_key).read()
                index_list = json.loads(existing_data.decode('utf-8'))
            except oss2.exceptions.NoSuchKey:
                index_list = {'indices': [], 'last_updated': None}
            
            # 更新列表
            if remove:
                index_list['indices'] = [idx for idx in index_list['indices'] 
                                       if idx.get('name') != index_name]
            else:
                # 检查是否已存在
                existing_names = [idx.get('name') for idx in index_list['indices']]
                if index_name not in existing_names:
                    index_list['indices'].append({
                        'name': index_name,
                        'created_at': datetime.now().isoformat()
                    })
            
            index_list['last_updated'] = datetime.now().isoformat()
            
            # 保存更新后的列表
            updated_data = json.dumps(index_list, ensure_ascii=False, indent=2)
            self.bucket.put_object(list_key, updated_data.encode('utf-8'))
            
        except Exception as e:
            logger.error(f"更新索引列表失败: {str(e)}")
    
    def get_storage_usage(self) -> Dict:
        """
        获取存储使用情况
        
        Returns:
            Dict: 存储使用统计
        """
        if not self.is_connected:
            return {}
        
        try:
            usage = {
                'total_size': 0,
                'file_count': 0,
                'folders': {}
            }
            
            # 遍历所有邮件相关文件
            for obj in oss2.ObjectIterator(self.bucket, prefix='emails/'):
                usage['total_size'] += obj.size
                usage['file_count'] += 1
                
                # 按文件夹统计
                folder = obj.key.split('/')[1] if '/' in obj.key else 'root'
                if folder not in usage['folders']:
                    usage['folders'][folder] = {'size': 0, 'count': 0}
                
                usage['folders'][folder]['size'] += obj.size
                usage['folders'][folder]['count'] += 1
            
            # 转换为可读格式
            usage['total_size_mb'] = round(usage['total_size'] / (1024 * 1024), 2)
            
            return usage
            
        except Exception as e:
            logger.error(f"获取存储使用情况失败: {str(e)}")
            return {}
    
    def backup_index(self, index_name: str, backup_name: str = None) -> bool:
        """
        备份索引
        
        Args:
            index_name: 要备份的索引名称
            backup_name: 备份名称，默认添加时间戳
            
        Returns:
            bool: 备份是否成功
        """
        if backup_name is None:
            backup_name = f"{index_name}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        try:
            # 复制索引文件
            source_files = [
                (f"{self.paths['indices']}{index_name}.faiss", 
                 f"{self.paths['indices']}{backup_name}.faiss"),
                (f"{self.paths['metadata']}{index_name}.metadata", 
                 f"{self.paths['metadata']}{backup_name}.metadata"),
                (f"{self.paths['config']}{index_name}.config", 
                 f"{self.paths['config']}{backup_name}.config")
            ]
            
            for source_key, dest_key in source_files:
                try:
                    # 检查源文件是否存在（可能是压缩版本）
                    source_key_gz = source_key + '.gz'
                    try:
                        self.bucket.copy_object(self.bucket_name, source_key_gz, dest_key + '.gz')
                    except oss2.exceptions.NoSuchKey:
                        self.bucket.copy_object(self.bucket_name, source_key, dest_key)
                except oss2.exceptions.NoSuchKey:
                    logger.warning(f"源文件不存在: {source_key}")
            
            logger.info(f"索引备份完成: {index_name} -> {backup_name}")
            return True
            
        except Exception as e:
            logger.error(f"备份索引失败: {str(e)}")
            return False
    
    def cleanup_old_backups(self, keep_count: int = 5) -> int:
        """
        清理旧的备份文件
        
        Args:
            keep_count: 保留的备份数量
            
        Returns:
            int: 删除的备份数量
        """
        if not self.is_connected:
            return 0
    
    def upload_emails_index(self, emails_data: List[Dict]) -> bool:
        """
        上传邮件数据到OSS
        
        Args:
            emails_data: 邮件数据列表
            
        Returns:
            bool: 上传是否成功
        """
        if not self.is_connected:
            logger.error("OSS未连接")
            return False
        
        try:
            # 创建临时文件保存邮件数据
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
                json.dump(emails_data, temp_file, ensure_ascii=False, indent=2, default=str)
                temp_file_path = temp_file.name
            
            # 上传到OSS
            oss_key = f"{self.paths['cache']}emails_data.json"
            self._upload_file_with_compression(temp_file_path, oss_key)
            
            # 清理临时文件
            os.unlink(temp_file_path)
            
            logger.info(f"邮件数据已上传到OSS: {len(emails_data)} 封邮件")
            return True
            
        except Exception as e:
            logger.error(f"上传邮件数据失败: {str(e)}")
            return False
    
    def download_emails_index(self) -> Optional[List[Dict]]:
        """
        从OSS下载邮件数据
        
        Returns:
            Optional[List[Dict]]: 邮件数据列表，失败时返回None
        """
        if not self.is_connected:
            logger.error("OSS未连接")
            return None
        
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
                temp_file_path = temp_file.name
            
            # 从OSS下载
            oss_key = f"{self.paths['cache']}emails_data.json"
            if self._download_file_with_decompression(oss_key, temp_file_path):
                # 读取邮件数据
                with open(temp_file_path, 'r', encoding='utf-8') as f:
                    emails_data = json.load(f)
                
                # 清理临时文件
                os.unlink(temp_file_path)
                
                logger.info(f"从OSS下载了 {len(emails_data)} 封邮件")
                return emails_data
            else:
                # 清理临时文件
                os.unlink(temp_file_path)
                return None
                
        except Exception as e:
            logger.error(f"下载邮件数据失败: {str(e)}")
            return None