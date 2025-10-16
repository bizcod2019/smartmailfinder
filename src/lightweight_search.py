"""
轻量级语义搜索引擎
使用TF-IDF和预训练词向量，避免大型transformer模型
专为Vercel部署优化，内存占用极低
"""

import numpy as np
import re
import jieba
from typing import List, Dict, Tuple, Optional
from collections import Counter, defaultdict
import pickle
import os
import logging
from datetime import datetime
import json
import math
from dataclasses import dataclass

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

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LightweightSemanticSearch:
    """轻量级语义搜索引擎"""
    
    def __init__(self):
        """初始化轻量级搜索引擎"""
        self.is_initialized = False
        self.vocabulary = {}  # 词汇表
        self.idf_scores = {}  # IDF分数
        self.document_vectors = []  # 文档向量
        self.email_metadata = []  # 邮件元数据
        self.word_embeddings = {}  # 简单词向量
        
        # 搜索配置
        self.max_vocab_size = 5000  # 限制词汇表大小
        self.max_documents = 500    # 限制文档数量 - 更严格的限制
        self.vector_dim = 100       # 向量维度
        
        # 预定义的技能词汇和权重
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
        
        # 初始化简单词向量
        self._init_word_embeddings()
        
    def _init_word_embeddings(self):
        """初始化简单的词向量"""
        # 为技能关键词创建简单的词向量
        np.random.seed(42)  # 确保可重现性
        
        for skill, keywords in self.skill_keywords.items():
            # 为每个技能创建一个基础向量
            base_vector = np.random.normal(0, 0.1, self.vector_dim)
            
            for keyword in keywords:
                # 为每个关键词添加一些随机噪声
                noise = np.random.normal(0, 0.05, self.vector_dim)
                self.word_embeddings[keyword.lower()] = base_vector + noise
                
        logger.info(f"初始化了 {len(self.word_embeddings)} 个词向量")
        
    def _tokenize_text(self, text: str) -> List[str]:
        """文本分词"""
        if not text:
            return []
            
        # 清理文本
        text = re.sub(r'[^\w\s\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip().lower()
        
        # 分词（中文使用jieba，其他使用空格分割）
        tokens = []
        
        # 英文和数字
        english_tokens = re.findall(r'[a-zA-Z0-9]+', text)
        tokens.extend(english_tokens)
        
        # 中文和日文
        chinese_japanese_text = re.sub(r'[a-zA-Z0-9\s]', '', text)
        if chinese_japanese_text:
            chinese_tokens = list(jieba.cut(chinese_japanese_text))
            tokens.extend([t for t in chinese_tokens if len(t.strip()) > 0])
            
        return [token.lower() for token in tokens if len(token) > 1]
        
    def _compute_tf_idf(self, documents: List[List[str]]) -> Tuple[np.ndarray, Dict[str, int]]:
        """计算TF-IDF向量"""
        # 构建词汇表
        word_freq = Counter()
        for doc in documents:
            word_freq.update(set(doc))  # 只计算文档频率，不计算词频
            
        # 选择最频繁的词汇，限制词汇表大小
        most_common_words = word_freq.most_common(self.max_vocab_size)
        vocabulary = {word: idx for idx, (word, _) in enumerate(most_common_words)}
        
        # 计算IDF
        num_docs = len(documents)
        idf_scores = {}
        for word, idx in vocabulary.items():
            df = word_freq[word]  # 文档频率
            idf_scores[word] = math.log(num_docs / (df + 1))
            
        # 计算TF-IDF矩阵
        tfidf_matrix = np.zeros((num_docs, len(vocabulary)))
        
        for doc_idx, doc in enumerate(documents):
            # 计算词频
            tf_counter = Counter(doc)
            doc_length = len(doc)
            
            for word in doc:
                if word in vocabulary:
                    word_idx = vocabulary[word]
                    tf = tf_counter[word] / doc_length  # 归一化词频
                    idf = idf_scores[word]
                    tfidf_matrix[doc_idx, word_idx] = tf * idf
                    
        return tfidf_matrix, vocabulary
        
    def _get_word_vector(self, word: str) -> np.ndarray:
        """获取词向量"""
        word_lower = word.lower()
        if word_lower in self.word_embeddings:
            return self.word_embeddings[word_lower]
        else:
            # 为未知词创建随机向量
            np.random.seed(hash(word_lower) % 2**32)
            return np.random.normal(0, 0.1, self.vector_dim)
            
    def _compute_semantic_similarity(self, query_tokens: List[str], doc_tokens: List[str]) -> float:
        """计算语义相似度"""
        if not query_tokens or not doc_tokens:
            return 0.0
            
        # 获取查询和文档的词向量
        query_vectors = [self._get_word_vector(token) for token in query_tokens]
        doc_vectors = [self._get_word_vector(token) for token in doc_tokens]
        
        if not query_vectors or not doc_vectors:
            return 0.0
            
        # 计算平均向量
        query_avg = np.mean(query_vectors, axis=0)
        doc_avg = np.mean(doc_vectors, axis=0)
        
        # 计算余弦相似度
        query_norm = np.linalg.norm(query_avg)
        doc_norm = np.linalg.norm(doc_avg)
        
        if query_norm == 0 or doc_norm == 0:
            return 0.0
            
        similarity = np.dot(query_avg, doc_avg) / (query_norm * doc_norm)
        return max(0, similarity)  # 确保非负
        
    def build_index(self, email_data) -> bool:
        """构建搜索索引"""
        try:
            logger.info("开始构建轻量级搜索索引...")
            
            # 限制邮件数量
            if len(email_data) > self.max_documents:
                email_data = email_data[:self.max_documents]
                logger.info(f"限制邮件数量为 {self.max_documents}")
            
            # 转换EmailMessage对象为字典格式
            processed_emails = []
            for email in email_data:
                if hasattr(email, 'uid'):  # EmailMessage对象
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
                else:  # 已经是字典格式
                    email_dict = email
                processed_emails.append(email_dict)
                
            self.email_metadata = processed_emails
            
            # 准备文档文本
            documents = []
            for email in processed_emails:
                # 组合邮件文本
                text_parts = []
                
                # 主题
                if email.get('subject'):
                    text_parts.append(email['subject'])
                    
                # 正文（限制长度）
                body_text = email.get('body_text', '')
                if body_text:
                    text_parts.append(body_text[:500])  # 限制正文长度 - 更严格的限制
                    
                # HTML内容（限制长度）
                body_html = email.get('body_html', '')
                if body_html:
                    # 简单清理HTML
                    clean_html = re.sub(r'<[^>]+>', ' ', body_html)
                    text_parts.append(clean_html[:300])  # 限制HTML长度 - 更严格的限制
                    
                combined_text = ' '.join(text_parts)
                tokens = self._tokenize_text(combined_text)
                documents.append(tokens)
                
            # 计算TF-IDF
            self.document_vectors, self.vocabulary = self._compute_tf_idf(documents)
            self.idf_scores = {word: math.log(len(documents) / (Counter([token for doc in documents for token in doc])[word] + 1)) 
                              for word in self.vocabulary}
            
            self.is_initialized = True
            logger.info(f"轻量级搜索索引构建完成，包含 {len(documents)} 个文档，词汇表大小 {len(self.vocabulary)}")
            return True
            
        except Exception as e:
            logger.error(f"构建索引失败: {str(e)}")
            return False
            
    def search(self, query: str, top_k: int = 20, filters: Dict = None) -> List[SearchResult]:
        """执行搜索"""
        if not self.is_initialized:
            logger.warning("搜索引擎未初始化")
            return []
            
        try:
            # 分词查询
            query_tokens = self._tokenize_text(query)
            if not query_tokens:
                return []
                
            # 计算查询的TF-IDF向量
            query_vector = np.zeros(len(self.vocabulary))
            query_tf = Counter(query_tokens)
            query_length = len(query_tokens)
            
            for token in query_tokens:
                if token in self.vocabulary:
                    word_idx = self.vocabulary[token]
                    tf = query_tf[token] / query_length
                    idf = self.idf_scores.get(token, 0)
                    query_vector[word_idx] = tf * idf
                    
            # 计算与所有文档的相似度
            scores = []
            for doc_idx, doc_vector in enumerate(self.document_vectors):
                # TF-IDF相似度
                tfidf_sim = np.dot(query_vector, doc_vector) / (np.linalg.norm(query_vector) * np.linalg.norm(doc_vector) + 1e-8)
                
                # 语义相似度
                doc_tokens = self._tokenize_text(
                    f"{self.email_metadata[doc_idx].get('subject', '')} {self.email_metadata[doc_idx].get('body_text', '')[:300]}"
                )
                semantic_sim = self._compute_semantic_similarity(query_tokens, doc_tokens)
                
                # 技能匹配加权
                skill_bonus = self._compute_skill_bonus(query, self.email_metadata[doc_idx])
                
                # 综合评分
                final_score = 0.4 * tfidf_sim + 0.3 * semantic_sim + 0.3 * skill_bonus
                scores.append((doc_idx, final_score))
                
            # 排序并返回结果
            scores.sort(key=lambda x: x[1], reverse=True)
            
            results = []
            for doc_idx, score in scores[:top_k]:
                if score > 0.01:  # 过滤低分结果
                    email = self.email_metadata[doc_idx]
                    result = SearchResult(
                        email_id=email.get('uid', f'email_{doc_idx}'),
                        score=float(score),
                        subject=email.get('subject', ''),
                        sender=email.get('sender', ''),
                        date=email.get('date', datetime.now()),
                        preview=self._generate_preview(email, query),
                        folder=email.get('folder', ''),
                        attachments=email.get('attachments', [])
                    )
                    results.append(result)
                    
            logger.info(f"搜索完成，返回 {len(results)} 个结果")
            return results
            
        except Exception as e:
            logger.error(f"搜索失败: {str(e)}")
            return []
            
    def _compute_skill_bonus(self, query: str, email: Dict) -> float:
        """计算技能匹配加权"""
        query_lower = query.lower()
        email_text = f"{email.get('subject', '')} {email.get('body_text', '')}".lower()
        
        bonus = 0.0
        for skill, keywords in self.skill_keywords.items():
            query_has_skill = any(keyword.lower() in query_lower for keyword in keywords)
            email_has_skill = any(keyword.lower() in email_text for keyword in keywords)
            
            if query_has_skill and email_has_skill:
                bonus += 0.2  # 技能匹配加分
                
        return min(bonus, 1.0)  # 限制最大加分
        
    def _generate_preview(self, email: Dict, query: str) -> str:
        """生成邮件预览"""
        body_text = email.get('body_text', '')
        if not body_text:
            return email.get('subject', '无内容预览')
            
        # 尝试找到与查询相关的片段
        query_words = self._tokenize_text(query)
        sentences = re.split(r'[.!?。！？]', body_text)
        
        best_sentence = ""
        best_score = 0
        
        for sentence in sentences:
            if len(sentence.strip()) < 10:
                continue
                
            sentence_tokens = self._tokenize_text(sentence)
            score = len(set(query_words) & set(sentence_tokens))
            
            if score > best_score:
                best_score = score
                best_sentence = sentence.strip()
                
        # 如果没有找到相关片段，使用开头部分
        if not best_sentence:
            best_sentence = body_text[:150]
            
        # 限制预览长度
        if len(best_sentence) > 200:
            best_sentence = best_sentence[:200] + "..."
            
        return best_sentence