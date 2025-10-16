"""
基于OpenAI API的轻量级语义搜索引擎
使用OpenAI的embedding API，避免本地模型加载
专为Vercel部署优化，零内存占用
"""

import numpy as np
import re
import jieba
from typing import List, Dict, Tuple, Optional
from collections import Counter, defaultdict
import os
import logging
from datetime import datetime
import json
import math
from dataclasses import dataclass
import requests
import time

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class SearchResult:
    """搜索结果数据类"""
    email_id: str
    score: float
    subject: str
    sender: str
    date: datetime
    preview: str
    folder: str
    attachments: List[str]

class OpenAISemanticSearch:
    """基于OpenAI API的语义搜索引擎"""
    
    def __init__(self, api_key: str = None):
        """
        初始化OpenAI搜索引擎
        
        Args:
            api_key: OpenAI API密钥
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.email_metadata = []
        self.email_embeddings = []
        self.max_documents = 500  # 限制文档数量以控制API成本
        self.embedding_model = "text-embedding-3-small"  # 使用更便宜的模型
        self.max_tokens_per_request = 8000  # 限制每次请求的token数
        
        # API配置
        self.api_base_url = "https://api.openai.com/v1"
        self.max_retries = 3
        self.retry_delay = 1
        
        # 技能关键词映射（用于关键词搜索降级）
        self.skill_keywords = {
            'java': ['Java', 'java', 'JAVA', 'ジャバ', 'ジャヴァ'],
            'vue': ['Vue', 'vue', 'Vue.js', 'vue.js', 'Vue3', 'vue3', 'ビュー'],
            'springboot': ['SpringBoot', 'springboot', 'Spring Boot', 'spring boot', 'スプリングブート'],
            'mybatis': ['MyBatis', 'mybatis', 'Mybatis', 'マイバティス'],
            'react': ['React', 'react', 'React.js', 'react.js', 'リアクト'],
            'angular': ['Angular', 'angular', 'アンギュラー'],
            'nodejs': ['Node.js', 'nodejs', 'node.js', 'Node', 'ノード'],
            'python': ['Python', 'python', 'パイソン'],
            'javascript': ['JavaScript', 'javascript', 'JS', 'js', 'ジャバスクリプト'],
            'typescript': ['TypeScript', 'typescript', 'TS', 'ts', 'タイプスクリプト'],
            'mysql': ['MySQL', 'mysql', 'マイエスキューエル'],
            'postgresql': ['PostgreSQL', 'postgresql', 'postgres', 'ポストグレ'],
            'redis': ['Redis', 'redis', 'レディス'],
            'docker': ['Docker', 'docker', 'ドッカー'],
            'kubernetes': ['Kubernetes', 'kubernetes', 'k8s', 'K8s', 'クーベルネテス'],
            'aws': ['AWS', 'aws', 'Amazon Web Services', 'アマゾンウェブサービス'],
            'azure': ['Azure', 'azure', 'Microsoft Azure', 'アジュール'],
            'gcp': ['GCP', 'gcp', 'Google Cloud', 'グーグルクラウド']
        }
        
        logger.info("OpenAI语义搜索引擎初始化完成")
    
    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """
        获取文本的embedding向量
        
        Args:
            text: 输入文本
            
        Returns:
            List[float]: embedding向量，失败时返回None
        """
        if not self.api_key:
            logger.error("OpenAI API密钥未设置")
            return None
            
        # 限制文本长度以控制成本
        if len(text) > self.max_tokens_per_request:
            text = text[:self.max_tokens_per_request]
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "input": text,
            "model": self.embedding_model
        }
        
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    f"{self.api_base_url}/embeddings",
                    headers=headers,
                    json=data,
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result['data'][0]['embedding']
                elif response.status_code == 429:  # Rate limit
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.warning(f"API速率限制，等待 {wait_time} 秒后重试")
                    time.sleep(wait_time)
                else:
                    logger.error(f"API请求失败: {response.status_code} - {response.text}")
                    return None
                    
            except Exception as e:
                logger.error(f"API请求异常 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    
        return None
    
    def _prepare_email_text(self, email) -> str:
        """
        准备邮件文本用于embedding
        
        Args:
            email: 邮件对象或字典
            
        Returns:
            str: 处理后的文本
        """
        if hasattr(email, 'subject'):
            # EmailMessage对象
            subject = email.subject or ""
            sender = email.sender or ""
            body_text = email.body_text or ""
            body_html = email.body_html or ""
        else:
            # 字典格式
            subject = email.get('subject', '')
            sender = email.get('sender', '')
            body_text = email.get('body_text', '')
            body_html = email.get('body_html', '')
        
        # 清理HTML
        if body_html:
            body_html = re.sub(r'<[^>]+>', ' ', body_html)
        
        # 组合文本，限制长度以控制API成本
        text_parts = []
        if subject:
            text_parts.append(f"主题: {subject[:200]}")
        if sender:
            text_parts.append(f"发件人: {sender[:100]}")
        if body_text:
            text_parts.append(f"正文: {body_text[:800]}")
        elif body_html:
            text_parts.append(f"内容: {body_html[:800]}")
        
        combined_text = ' '.join(text_parts)
        
        # 进一步限制长度
        if len(combined_text) > 1500:
            combined_text = combined_text[:1500] + "..."
            
        return combined_text
    
    def build_index(self, emails: List) -> bool:
        """
        构建搜索索引
        
        Args:
            emails: 邮件列表
            
        Returns:
            bool: 是否成功
        """
        if not self.api_key:
            logger.error("OpenAI API密钥未设置，无法构建索引")
            return False
            
        logger.info(f"开始构建OpenAI搜索索引，邮件数量: {len(emails)}")
        
        # 限制邮件数量以控制API成本
        if len(emails) > self.max_documents:
            emails = emails[:self.max_documents]
            logger.warning(f"邮件数量超过限制，只处理前 {self.max_documents} 封")
        
        self.email_metadata = []
        self.email_embeddings = []
        
        success_count = 0
        
        for i, email in enumerate(emails):
            try:
                # 转换EmailMessage对象为字典格式
                if hasattr(email, 'uid'):
                    email_dict = {
                        'uid': email.uid,
                        'subject': email.subject,
                        'sender': email.sender,
                        'date': email.date,
                        'folder': email.folder,
                        'attachments': email.attachments,
                        'body_text': email.body_text[:500] if email.body_text else "",
                        'body_html': email.body_html[:500] if email.body_html else ""
                    }
                else:
                    email_dict = email
                
                # 准备文本
                text = self._prepare_email_text(email_dict)
                
                # 获取embedding
                embedding = self._get_embedding(text)
                
                if embedding is not None:
                    self.email_metadata.append(email_dict)
                    self.email_embeddings.append(embedding)
                    success_count += 1
                    
                    if (i + 1) % 10 == 0:
                        logger.info(f"已处理 {i + 1}/{len(emails)} 封邮件")
                        
                    # 添加延迟以避免API速率限制
                    time.sleep(0.1)
                else:
                    logger.warning(f"邮件 {i} 的embedding获取失败")
                    
            except Exception as e:
                logger.error(f"处理邮件 {i} 时出错: {e}")
                continue
        
        logger.info(f"索引构建完成，成功处理 {success_count}/{len(emails)} 封邮件")
        return success_count > 0
    
    def search(self, query: str, top_k: int = 20, filters: Dict = None) -> List[SearchResult]:
        """
        执行语义搜索
        
        Args:
            query: 搜索查询
            top_k: 返回结果数量
            filters: 搜索过滤器
            
        Returns:
            List[SearchResult]: 搜索结果列表
        """
        if not self.email_embeddings:
            logger.warning("索引为空，使用关键词搜索降级")
            return self._keyword_search_fallback(query, top_k)
        
        # 获取查询的embedding
        query_embedding = self._get_embedding(query)
        
        if query_embedding is None:
            logger.warning("查询embedding获取失败，使用关键词搜索降级")
            return self._keyword_search_fallback(query, top_k)
        
        # 计算相似度
        similarities = []
        query_vec = np.array(query_embedding)
        
        for i, doc_embedding in enumerate(self.email_embeddings):
            doc_vec = np.array(doc_embedding)
            
            # 计算余弦相似度
            similarity = np.dot(query_vec, doc_vec) / (
                np.linalg.norm(query_vec) * np.linalg.norm(doc_vec)
            )
            
            similarities.append((i, similarity))
        
        # 排序并获取top_k结果
        similarities.sort(key=lambda x: x[1], reverse=True)
        top_results = similarities[:top_k]
        
        # 构建搜索结果
        results = []
        for doc_idx, score in top_results:
            if score < 0.3:  # 过滤低相似度结果
                continue
                
            email = self.email_metadata[doc_idx]
            
            # 生成预览
            preview = self._generate_preview(email, query)
            
            result = SearchResult(
                email_id=email.get('uid', str(doc_idx)),
                score=float(score),
                subject=email.get('subject', ''),
                sender=email.get('sender', ''),
                date=email.get('date', datetime.now()),
                preview=preview,
                folder=email.get('folder', ''),
                attachments=email.get('attachments', [])
            )
            
            results.append(result)
        
        logger.info(f"OpenAI搜索返回 {len(results)} 个结果")
        return results
    
    def _keyword_search_fallback(self, query: str, top_k: int) -> List[SearchResult]:
        """
        关键词搜索降级方案
        
        Args:
            query: 搜索查询
            top_k: 返回结果数量
            
        Returns:
            List[SearchResult]: 搜索结果列表
        """
        if not self.email_metadata:
            return []
        
        query_lower = query.lower()
        results = []
        
        for i, email in enumerate(self.email_metadata):
            score = 0.0
            
            # 检查主题
            subject = email.get('subject', '').lower()
            if query_lower in subject:
                score += 0.8
            
            # 检查发件人
            sender = email.get('sender', '').lower()
            if query_lower in sender:
                score += 0.6
            
            # 检查正文
            body_text = email.get('body_text', '').lower()
            if query_lower in body_text:
                score += 0.4
            
            # 检查技能关键词
            for skill, keywords in self.skill_keywords.items():
                for keyword in keywords:
                    if keyword.lower() in query_lower:
                        if keyword.lower() in subject or keyword.lower() in body_text:
                            score += 0.5
                            break
            
            if score > 0:
                preview = self._generate_preview(email, query)
                
                result = SearchResult(
                    email_id=email.get('uid', str(i)),
                    score=score,
                    subject=email.get('subject', ''),
                    sender=email.get('sender', ''),
                    date=email.get('date', datetime.now()),
                    preview=preview,
                    folder=email.get('folder', ''),
                    attachments=email.get('attachments', [])
                )
                
                results.append(result)
        
        # 按分数排序
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    def _generate_preview(self, email: Dict, query: str) -> str:
        """
        生成搜索结果预览
        
        Args:
            email: 邮件字典
            query: 搜索查询
            
        Returns:
            str: 预览文本
        """
        body_text = email.get('body_text', '')
        
        if not body_text:
            body_html = email.get('body_html', '')
            if body_html:
                body_text = re.sub(r'<[^>]+>', ' ', body_html)
        
        if not body_text:
            return email.get('subject', '')[:150]
        
        # 查找包含查询词的句子
        sentences = re.split(r'[。！？\n]', body_text)
        query_lower = query.lower()
        
        best_sentence = ""
        for sentence in sentences:
            if query_lower in sentence.lower() and len(sentence.strip()) > 10:
                best_sentence = sentence.strip()
                break
        
        # 如果没有找到相关句子，使用开头部分
        if not best_sentence:
            best_sentence = body_text[:150]
        
        # 限制预览长度
        if len(best_sentence) > 200:
            best_sentence = best_sentence[:200] + "..."
        
        return best_sentence