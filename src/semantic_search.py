"""
语义搜索引擎模块
基于Sentence Transformers和FAISS实现智能邮件搜索
"""

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Tuple, Optional
import pickle
import os
import re
from datetime import datetime, timedelta
import logging
from dataclasses import dataclass
import json
import jieba
from collections import Counter

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
    body_text: str = ""  # 添加完整正文字段

class SemanticSearchEngine:
    """语义搜索引擎类"""
    
    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        """
        初始化语义搜索引擎
        
        Args:
            model_name: Sentence Transformers模型名称
        """
        self.model_name = model_name
        self.model = None
        self.index = None
        self.email_metadata = []
        self.is_initialized = False
        
        # 搜索配置
        self.max_preview_length = 200
        self.default_top_k = 20
        
        # 技能关键词映射（中日文）
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
        
    def initialize(self):
        """初始化模型和索引"""
        try:
            logger.info(f"正在加载模型: {self.model_name}")
            
            # 尝试多种方式加载模型以解决兼容性问题
            try:
                # 方法1: 直接加载
                self.model = SentenceTransformer(self.model_name)
            except Exception as e1:
                logger.warning(f"直接加载失败: {str(e1)}, 尝试其他方法...")
                try:
                    # 方法2: 使用device参数
                    import torch
                    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
                    self.model = SentenceTransformer(self.model_name, device=device)
                except Exception as e2:
                    logger.warning(f"指定设备加载失败: {str(e2)}, 尝试CPU模式...")
                    # 方法3: 强制使用CPU
                    self.model = SentenceTransformer(self.model_name, device='cpu')
            
            # 测试模型是否正常工作
            test_text = "测试文本"
            test_embedding = self.model.encode([test_text])
            if test_embedding is not None and len(test_embedding) > 0:
                self.is_initialized = True
                logger.info("语义搜索引擎初始化成功")
            else:
                raise Exception("模型测试失败")
                
        except Exception as e:
            logger.error(f"初始化失败: {str(e)}")
            self.is_initialized = False
            # 提供降级方案
            logger.info("将使用关键词搜索作为降级方案")
    
    def _parse_skill_query(self, query: str) -> Dict:
        """
        解析技能描述查询，支持双向匹配
        
        Args:
            query: 用户输入的查询文本
            
        Returns:
            Dict: 解析结果，包含技能列表、经验年限、查询类型等
        """
        result = {
            'skills': [],
            'experience_years': None,
            'query_type': 'general',  # general, person_to_project, project_to_person
            'enhanced_query': query,
            'keywords': [],
            'input_type': 'unknown',  # person, project, mixed
            'search_direction': 'bidirectional'  # person_to_project, project_to_person, bidirectional
        }
        
        # 智能识别输入类型
        input_analysis = self._analyze_input_type(query)
        result.update(input_analysis)
        
        # 提取经验年限
        year_patterns = [
            r'(\d+)\s*年',
            r'(\d+)\s*年間',
            r'(\d+)\s*年经验',
            r'(\d+)\s*年の経験',
            r'(\d+)\s*年以上',
            r'(\d+)\s*年以上の経験'
        ]
        
        for pattern in year_patterns:
            match = re.search(pattern, query)
            if match:
                result['experience_years'] = int(match.group(1))
                break
        
        # 提取技能关键词
        detected_skills = []
        query_lower = query.lower()
        
        for skill_name, keywords in self.skill_keywords.items():
            for keyword in keywords:
                if keyword.lower() in query_lower or keyword in query:
                    detected_skills.append(skill_name)
                    result['keywords'].append(keyword)
                    break
        
        result['skills'] = list(set(detected_skills))
        
        # 根据输入类型和搜索方向生成增强查询
        result['enhanced_query'] = self._generate_enhanced_query(query, result)
        
        return result
    
    def _analyze_input_type(self, query: str) -> Dict:
        """
        分析输入类型：人员信息、项目信息或混合
        
        Args:
            query: 用户输入的查询文本
            
        Returns:
            Dict: 分析结果
        """
        analysis = {
            'input_type': 'unknown',
            'query_type': 'general',
            'search_direction': 'bidirectional'
        }
        
        # 人员相关指示词
        person_indicators = [
            '程序员', 'プログラマー', '开发者', '開発者', '工程师', 'エンジニア',
            '技术', '技術', '经验', '経験', '年', '年間', '熟悉', '精通',
            '会', '能', '掌握', 'できる', '得意', '専門', '専攻',
            # 日文人员相关词汇
            '要員', '社員', 'プロパー', '人材', '人員', '従業員', 'スタッフ',
            'メンバー', '担当者', '技術者', '開発メンバー', 'チームメンバー',
            '経歴', 'キャリア', 'スキル', '実績', '業務経験', '開発経験'
        ]
        
        # 项目/案件相关指示词
        project_indicators = [
            '项目', 'プロジェクト', '案件', '開発案件', '求人', '募集', '招聘',
            '要求', '必要', '需要', 'スキル要求', '条件', '資格', '応募',
            '職種', '仕事', 'ポジション', '採用', '人材', '人員',
            # 日文项目需求相关词汇
            '募集中', '急募', '即戦力', '経験者', '未経験', '新卒', '中途',
            '正社員', '契約社員', 'アルバイト', 'パート', 'フリーランス',
            '業務委託', '派遣', '常駐', 'リモート', '在宅', 'テレワーク',
            '開発チーム', 'プロジェクトメンバー', '技術要件', '必須スキル',
            '歓迎スキル', '優遇', '給与', '年収', '時給', '単価', '報酬'
        ]
        
        # 计算指示词匹配度
        person_score = sum(1 for indicator in person_indicators if indicator in query)
        project_score = sum(1 for indicator in project_indicators if indicator in query)
        
        # 特殊模式检测
        if any(pattern in query for pattern in ['我是', '私は', '本人', '自己']):
            person_score += 2
        
        if any(pattern in query for pattern in ['招聘', '求人', '募集中', '応募', '採用']):
            project_score += 2
        
        # 判断输入类型
        logger.info(f"输入类型分析 - 查询: '{query[:50]}...', 人员分数: {person_score}, 项目分数: {project_score}")
        
        if person_score > project_score and person_score > 0:
            analysis['input_type'] = 'person'
            analysis['query_type'] = 'person_to_project'
            analysis['search_direction'] = 'person_to_project'
            logger.info(f"识别为人员搜索 -> 项目")
        elif project_score > person_score and project_score > 0:
            analysis['input_type'] = 'project'
            analysis['query_type'] = 'project_to_person'
            analysis['search_direction'] = 'project_to_person'
            logger.info(f"识别为项目搜索 -> 人员")
        elif person_score > 0 or project_score > 0:
            analysis['input_type'] = 'mixed'
            analysis['query_type'] = 'skill_match'
            analysis['search_direction'] = 'bidirectional'
            logger.info(f"识别为混合/技能匹配搜索")
        
        return analysis
    
    def _generate_enhanced_query(self, original_query: str, query_info: Dict) -> str:
        """
        根据查询类型生成增强查询
        
        Args:
            original_query: 原始查询
            query_info: 查询分析信息
            
        Returns:
            str: 增强查询
        """
        enhanced_parts = []
        
        if query_info['search_direction'] == 'person_to_project':
            # 人员→项目：搜索项目需求
            project_terms = [
                'プロジェクト', '案件', '開発', '求人', '募集', '要求', '必要', 
                'スキル', '条件', '資格', '採用', '人材', '職種'
            ]
            enhanced_parts.extend(project_terms)
            
        elif query_info['search_direction'] == 'project_to_person':
            # 项目→人员：搜索人员简历
            person_terms = [
                '程序员', 'プログラマー', '开发者', '開発者', '工程师', 'エンジニア',
                '经验', '経験', '技术', '技術', '熟悉', '精通', '専門', '得意'
            ]
            enhanced_parts.extend(person_terms)
            
        else:
            # 双向搜索：包含两种类型的词汇
            all_terms = [
                'プロジェクト', '案件', '開発', '求人', '募集', '要求', '必要', 'スキル',
                '程序员', 'プログラマー', '开发者', '開発者', '工程师', 'エンジニア',
                '经验', '経験', '技术', '技術'
            ]
            enhanced_parts.extend(all_terms)
        
        # 添加检测到的技能
        if query_info['skills']:
            for skill in query_info['skills']:
                enhanced_parts.extend(self.skill_keywords[skill])
        
        # 添加经验相关词汇
        if query_info['experience_years']:
            exp_terms = [
                f"{query_info['experience_years']}年", 
                f"{query_info['experience_years']}年間", 
                f"{query_info['experience_years']}年以上",
                '経験'
            ]
            enhanced_parts.extend(exp_terms)
        
        # 组合增强查询
        enhanced_query = ' '.join(enhanced_parts) + ' ' + original_query
        return enhanced_query
    
    def _normalize_text(self, text: str) -> str:
        """
        标准化文本，处理中日文混合
        
        Args:
            text: 输入文本
            
        Returns:
            str: 标准化后的文本
        """
        # 统一全角半角
        text = text.replace('（', '(').replace('）', ')')
        text = text.replace('，', ',').replace('。', '.')
        
        # 移除多余空格
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def build_index(self, emails: List) -> bool:
        """
        构建邮件向量索引
        
        Args:
            emails: 邮件数据列表 (EmailMessage对象)
            
        Returns:
            bool: 构建是否成功
        """
        try:
            logger.info(f"开始构建索引，邮件数量: {len(emails)}")
            
            # 准备文本数据和元数据
            texts = []
            metadata = []
            
            for i, email in enumerate(emails):
                # 组合邮件文本用于向量化
                combined_text = self._prepare_email_text(email)
                texts.append(combined_text)
                
                # 调试日志 - 检查前几封邮件的数据
                if i < 3:
                    logger.info(f"构建索引 - 邮件 {i}: {email.uid}")
                    logger.info(f"  - subject: {email.subject[:50]}...")
                    logger.info(f"  - body_text长度: {len(email.body_text)}")
                    logger.info(f"  - body_html长度: {len(email.body_html)}")
                    if len(email.body_text) == 0 and len(email.body_html) > 0:
                        logger.info(f"  - 发现body_text为空但body_html有内容的邮件")
                
                # 保存元数据
                metadata.append({
                    'uid': email.uid,
                    'subject': email.subject,
                    'sender': email.sender,
                    'date': email.date,
                    'folder': email.folder,
                    'attachments': email.attachments,
                    'body_text': email.body_text,
                    'body_html': email.body_html
                })
            
            # 无论语义搜索引擎是否初始化成功，都保存元数据以支持关键词搜索
            self.email_metadata = metadata
            logger.info(f"邮件元数据加载完成，包含 {len(metadata)} 封邮件")
            
            # 尝试初始化语义搜索引擎
            if not self.is_initialized:
                self.initialize()
            
            # 如果语义搜索引擎初始化成功，构建向量索引
            if self.is_initialized:
                try:
                    # 生成向量
                    logger.info("正在生成文本向量...")
                    embeddings = self.model.encode(texts, show_progress_bar=True)
                    
                    # 构建FAISS索引
                    dimension = embeddings.shape[1]
                    self.index = faiss.IndexFlatIP(dimension)  # 使用内积相似度
                    
                    # 标准化向量（用于余弦相似度）
                    faiss.normalize_L2(embeddings)
                    
                    # 添加向量到索引
                    self.index.add(embeddings.astype('float32'))
                    
                    logger.info(f"语义索引构建完成，包含 {self.index.ntotal} 个向量")
                    return True
                    
                except Exception as e:
                    logger.error(f"语义索引构建失败: {str(e)}")
                    logger.info("将仅使用关键词搜索功能")
                    return True  # 元数据已加载，关键词搜索可用
            else:
                logger.info("语义搜索引擎未初始化，将仅使用关键词搜索功能")
                return True  # 元数据已加载，关键词搜索可用
            
        except Exception as e:
            logger.error(f"构建索引失败: {str(e)}")
            return False
    
    def _prepare_email_text(self, email) -> str:
        """
        准备邮件文本用于向量化，增强项目需求信息提取
        
        Args:
            email: 邮件数据对象
            
        Returns:
            str: 组合后的文本
        """
        # 提取关键信息
        subject = email.subject
        sender = email.sender
        body_text = email.body_text
        body_html = email.body_html
        
        # 清理HTML标签
        if body_html and not body_text:
            body_text = self._clean_html(body_html)
        
        # 提取项目需求信息
        enhanced_content = self._extract_project_requirements(body_text)
        
        # 限制正文长度，但保留重要的项目信息
        if len(enhanced_content) > 1500:
            # 优先保留项目需求相关内容
            important_parts = self._extract_important_sections(enhanced_content)
            if important_parts:
                enhanced_content = important_parts[:1500] + "..."
            else:
                enhanced_content = enhanced_content[:1500] + "..."
        
        # 组合文本，增加项目标识
        combined_text = f"主题: {subject}\n发件人: {sender}\n项目内容: {enhanced_content}"
        
        return combined_text
    
    def _extract_project_requirements(self, text: str) -> str:
        """
        提取项目需求信息
        
        Args:
            text: 原始邮件文本
            
        Returns:
            str: 增强后的文本
        """
        if not text:
            return ""
        
        # 项目需求关键词
        requirement_keywords = {
            'skills': ['スキル', '技術', '技能', '経験', '要求', '必要', '求める', '希望'],
            'project': ['プロジェクト', '案件', '開発', '構築', 'システム', 'アプリ'],
            'experience': ['年', '年間', '経験', '実務', 'キャリア'],
            'technologies': list(set([keyword for keywords in self.skill_keywords.values() for keyword in keywords]))
        }
        
        enhanced_text = text
        
        # 标记技术栈
        for tech in requirement_keywords['technologies']:
            if tech in text:
                enhanced_text = enhanced_text.replace(tech, f"【技術】{tech}")
        
        # 标记项目相关词汇
        for keyword in requirement_keywords['project']:
            if keyword in text:
                enhanced_text = enhanced_text.replace(keyword, f"【プロジェクト】{keyword}")
        
        # 标记技能要求
        for keyword in requirement_keywords['skills']:
            if keyword in text:
                enhanced_text = enhanced_text.replace(keyword, f"【要求】{keyword}")
        
        # 标记经验要求
        exp_pattern = r'(\d+年[間以上]*)'
        enhanced_text = re.sub(exp_pattern, r'【経験】\1', enhanced_text)
        
        return enhanced_text
    
    def _extract_important_sections(self, text: str) -> str:
        """
        提取重要的项目信息段落
        
        Args:
            text: 文本内容
            
        Returns:
            str: 重要段落
        """
        # 按句子分割
        sentences = re.split(r'[。．\n]', text)
        important_sentences = []
        
        # 重要性评分
        for sentence in sentences:
            score = 0
            
            # 包含技术关键词
            if any(f"【技術】" in sentence for tech in sentence):
                score += 3
            
            # 包含项目关键词
            if "【プロジェクト】" in sentence:
                score += 2
            
            # 包含要求关键词
            if "【要求】" in sentence:
                score += 2
            
            # 包含经验关键词
            if "【経験】" in sentence:
                score += 2
            
            # 句子长度合理
            if 10 <= len(sentence) <= 100:
                score += 1
            
            if score >= 2:
                important_sentences.append((sentence, score))
        
        # 按重要性排序
        important_sentences.sort(key=lambda x: x[1], reverse=True)
        
        # 返回最重要的句子
        result = "。".join([sent[0] for sent in important_sentences[:10]])
        return result if result else text
    
    def _clean_html(self, html_text: str) -> str:
        """
        清理HTML标签
        
        Args:
            html_text: HTML文本
            
        Returns:
            str: 清理后的纯文本
        """
        # 简单的HTML标签清理
        clean_text = re.sub(r'<[^>]+>', '', html_text)
        clean_text = re.sub(r'\s+', ' ', clean_text)
        return clean_text.strip()
    
    def search(self, query: str, top_k: int = None, 
               filters: Dict = None) -> List[SearchResult]:
        """
        执行智能语义搜索
        
        Args:
            query: 搜索查询
            top_k: 返回结果数量
            filters: 搜索过滤条件
            
        Returns:
            List[SearchResult]: 搜索结果列表
        """
        if not self.is_initialized or self.index is None:
            logger.warning("语义搜索引擎未初始化，使用关键词搜索作为降级方案")
            return self.keyword_search(query, top_k)
        
        if top_k is None:
            top_k = self.default_top_k
        
        try:
            # 智能查询解析
            query_info = self._parse_skill_query(query)
            search_query = query_info['enhanced_query']
            
            logger.info(f"原始查询: {query}")
            logger.info(f"查询类型: {query_info['query_type']}")
            logger.info(f"检测到的技能: {query_info['skills']}")
            logger.info(f"增强查询: {search_query}")
            
            # 标准化查询文本
            search_query = self._normalize_text(search_query)
            
            # 生成查询向量
            query_embedding = self.model.encode([search_query])
            faiss.normalize_L2(query_embedding)
            
            # 执行搜索
            scores, indices = self.index.search(query_embedding.astype('float32'), top_k)
            
            # 处理结果
            results = []
            for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
                if idx == -1:  # FAISS返回-1表示无效结果
                    continue
                
                metadata = self.email_metadata[idx]
                
                # 应用过滤器
                if filters and not self._apply_filters(metadata, filters):
                    continue
                
                # 生成预览
                preview = self._generate_preview(metadata, query)
                
                # 获取完整正文内容 - 优先使用body_text，如果为空则从body_html转换
                original_body_text = metadata.get('body_text', '')
                body_html = metadata.get('body_html', '')
                
                logger.info(f"SearchResult创建 - 邮件ID: {metadata.get('uid', 'unknown')}")
                logger.info(f"  - 原始body_text长度: {len(original_body_text)}")
                logger.info(f"  - body_html长度: {len(body_html)}")
                
                full_body_text = original_body_text
                if not full_body_text.strip() and body_html:
                    # 如果body_text为空但有body_html，则清理HTML标签
                    full_body_text = self._clean_html(body_html)
                    logger.info(f"  - 从body_html转换后长度: {len(full_body_text)}")
                else:
                    logger.info(f"  - 使用原始body_text，长度: {len(full_body_text)}")
                
                result = SearchResult(
                    email_id=metadata['uid'],
                    score=float(score),
                    subject=metadata['subject'],
                    sender=metadata['sender'],
                    date=metadata['date'],
                    preview=preview,
                    folder=metadata['folder'],
                    attachments=metadata['attachments'],
                    body_text=full_body_text
                )
                
                results.append(result)
            
            # 按相关度排序
            results.sort(key=lambda x: x.score, reverse=True)
            
            logger.info(f"搜索完成，返回 {len(results)} 个结果")
            return results
            
        except Exception as e:
            logger.error(f"搜索失败: {str(e)}")
            return []
    
    def _apply_filters(self, metadata: Dict, filters: Dict) -> bool:
        """
        应用搜索过滤器
        
        Args:
            metadata: 邮件元数据
            filters: 过滤条件
            
        Returns:
            bool: 是否通过过滤
        """
        try:
            # 发件人过滤
            if 'sender' in filters and filters['sender']:
                if filters['sender'].lower() not in metadata['sender'].lower():
                    return False
            
            # 主题过滤
            if 'subject' in filters and filters['subject']:
                if filters['subject'].lower() not in metadata['subject'].lower():
                    return False
            
            # 时间范围过滤
            if 'start_date' in filters and filters['start_date']:
                if metadata['date'] < filters['start_date']:
                    return False
            
            if 'end_date' in filters and filters['end_date']:
                if metadata['date'] > filters['end_date']:
                    return False
            
            # 附件过滤
            if 'has_attachment' in filters and filters['has_attachment']:
                if not metadata['attachments']:
                    return False
            
            # 文件夹过滤
            if 'folder' in filters and filters['folder']:
                if metadata['folder'] != filters['folder']:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"应用过滤器失败: {str(e)}")
            return True
    
    def _generate_preview(self, metadata: Dict, query: str) -> str:
        """
        生成邮件预览
        
        Args:
            metadata: 邮件元数据
            query: 搜索查询
            
        Returns:
            str: 邮件预览文本
        """
        body_text = metadata.get('body_text', '')
        
        if not body_text:
            return metadata.get('subject', '无内容预览')
        
        # 尝试找到与查询相关的片段
        query_words = query.lower().split()
        best_snippet = ""
        best_score = 0
        
        # 将正文分成句子
        sentences = re.split(r'[.!?。！？]', body_text)
        
        for sentence in sentences:
            if len(sentence.strip()) < 10:
                continue
            
            # 计算句子与查询的相关性
            sentence_lower = sentence.lower()
            score = sum(1 for word in query_words if word in sentence_lower)
            
            if score > best_score:
                best_score = score
                best_snippet = sentence.strip()
        
        # 如果没有找到相关片段，使用开头部分
        if not best_snippet:
            best_snippet = body_text[:self.max_preview_length]
        
        # 限制预览长度
        if len(best_snippet) > self.max_preview_length:
            best_snippet = best_snippet[:self.max_preview_length] + "..."
        
        return best_snippet
    
    def intelligent_skill_search(self, query: str, top_k: int = None) -> Tuple[List[SearchResult], Dict]:
        """
        智能技能匹配搜索 - 支持双向匹配
        
        Args:
            query: 搜索查询（技能描述或项目需求）
            top_k: 返回结果数量
            
        Returns:
            Tuple[List[SearchResult], Dict]: 搜索结果和解析信息
        """
        if not self.is_initialized or self.index is None:
            logger.warning("语义搜索引擎未初始化，使用关键词搜索作为降级方案")
            keyword_results = self.keyword_search(query, top_k)
            # 返回关键词搜索结果和空的解析信息
            return keyword_results, {"query_type": "keyword_fallback", "skills": [], "experience_years": 0}
        
        if top_k is None:
            top_k = self.default_top_k
        
        try:
            # 解析技能查询
            query_info = self._parse_skill_query(query)
            
            # 如果不是技能相关查询，使用普通搜索
            if query_info['query_type'] == 'general':
                results = self.search(query, top_k)
                return results, query_info
            
            # 根据搜索方向执行双向匹配
            search_results = self._execute_bidirectional_search(query, query_info, top_k)
            
            # 去重并重新评分
            unique_results = {}
            for result in search_results:
                if result.email_id not in unique_results:
                    unique_results[result.email_id] = result
                else:
                    # 保留评分更高的结果
                    if result.score > unique_results[result.email_id].score:
                        unique_results[result.email_id] = result
            
            # 智能评分调整
            final_results = list(unique_results.values())
            for result in final_results:
                # 根据技能匹配度和搜索方向调整评分
                skill_bonus = self._calculate_bidirectional_bonus(result, query_info)
                result.score += skill_bonus
            
            # 根据搜索方向过滤结果
            filtered_results = self._filter_results_by_direction(final_results, query_info)
            
            # 重新排序并限制结果数量
            filtered_results.sort(key=lambda x: x.score, reverse=True)
            filtered_results = filtered_results[:top_k]
            
            logger.info(f"双向技能搜索完成，搜索方向: {query_info['search_direction']}，返回 {len(filtered_results)} 个结果")
            return filtered_results, query_info
            
        except Exception as e:
            logger.error(f"智能技能搜索失败: {str(e)}")
            return [], {}
    
    def _execute_bidirectional_search(self, query: str, query_info: Dict, top_k: int) -> List[SearchResult]:
        """
        执行双向搜索策略
        
        Args:
            query: 原始查询
            query_info: 查询分析信息
            top_k: 结果数量
            
        Returns:
            List[SearchResult]: 搜索结果
        """
        search_results = []
        
        # 1. 根据搜索方向执行专门搜索（主要搜索策略）
        if query_info['search_direction'] == 'person_to_project':
            # 人员→项目：只搜索项目需求和招聘信息
            search_results.extend(self._search_project_requirements(query_info, top_k))
            
        elif query_info['search_direction'] == 'project_to_person':
            # 项目→人员：只搜索人员简历和技能信息
            search_results.extend(self._search_person_profiles(query_info, top_k))
            
        else:
            # 双向搜索：同时搜索项目需求和人员信息
            search_results.extend(self._search_project_requirements(query_info, top_k // 2))
            search_results.extend(self._search_person_profiles(query_info, top_k // 2))
        
        # 2. 针对每个技能进行专门搜索（辅助搜索策略）
        for skill in query_info['skills']:
            skill_keywords = self.skill_keywords[skill]
            for keyword in skill_keywords[:2]:  # 取前2个关键词
                if query_info['search_direction'] == 'person_to_project':
                    # 人员信息输入时，只搜索项目相关内容
                    skill_query = f"プロジェクト 開発 {keyword} 募集 要求 案件 求人 採用"
                elif query_info['search_direction'] == 'project_to_person':
                    # 项目需求输入时，只搜索人员相关内容
                    skill_query = f"プログラマー エンジニア {keyword} 経験 技術 専門 人材"
                else:
                    skill_query = f"{keyword} 開発 プロジェクト エンジニア"
                
                skill_results = self.search(skill_query, top_k // 4)
                search_results.extend(skill_results)
        
        # 3. 使用过滤后的增强查询进行语义搜索
        filtered_enhanced_query = self._create_filtered_enhanced_query(query_info)
        enhanced_results = self.search(filtered_enhanced_query, top_k)
        search_results.extend(enhanced_results)
        
        return search_results
    
    def _create_filtered_enhanced_query(self, query_info: Dict) -> str:
        """
        创建过滤后的增强查询，确保搜索方向的准确性
        
        Args:
            query_info: 查询分析信息
            
        Returns:
            str: 过滤后的增强查询
        """
        base_skills = " ".join(query_info['skills'][:3])  # 限制技能数量
        
        if query_info['search_direction'] == 'person_to_project':
            # 人员→项目：强调项目需求相关词汇
            project_terms = [
                "プロジェクト", "開発案件", "募集", "求人", "採用", 
                "必要", "要求", "条件", "資格", "スキル要求"
            ]
            enhanced_query = f"{base_skills} " + " ".join(project_terms[:4])
            
            if query_info['experience_years']:
                enhanced_query += f" {query_info['experience_years']}年以上"
                
        elif query_info['search_direction'] == 'project_to_person':
            # 项目→人员：强调人员技能相关词汇
            person_terms = [
                "エンジニア", "プログラマー", "開発者", "技術者", 
                "経験", "実績", "スキル", "専門", "人材"
            ]
            enhanced_query = f"{base_skills} " + " ".join(person_terms[:4])
            
        else:
            # 双向搜索：平衡的查询
            enhanced_query = f"{base_skills} 開発 プロジェクト エンジニア"
            
        return enhanced_query
    
    def _filter_results_by_direction(self, results: List[SearchResult], query_info: Dict) -> List[SearchResult]:
        """
        根据搜索方向过滤结果，排除不相关的内容
        
        Args:
            results: 原始搜索结果
            query_info: 查询分析信息
            
        Returns:
            List[SearchResult]: 过滤后的结果
        """
        logger.info(f"过滤逻辑 - 搜索方向: {query_info['search_direction']}, 输入结果数量: {len(results)}")
        
        # 对于所有技能匹配搜索，都需要过滤掉明显的人员信息邮件
        # 特别是标题中包含人员关键词的邮件
        if query_info.get('query_type') == 'general':
            # 只有一般搜索才跳过过滤
            logger.info("一般搜索，跳过人员信息过滤")
            return results
        
        filtered_results = []
        
        # 人员信息相关的关键词（需要排除的）
        person_keywords = [
            # 基本人员信息
            "名前", "年齢", "歳", "性別", "男性", "女性", "国籍", "中国籍", "日本籍",
            "最寄駅", "駅", "稼働", "即日", "所属", "正社員", "単価", "万", "精算",
            "実務経験", "年", "ヶ月", "日本語", "N1", "N2", "N3", "状況", "並行営業",
            "推薦理由", "性格", "明るく", "コミュニケーション", "チーム意識",
            "積極的", "継続的", "学び続ける", "意欲", "挑戦", "理解", "把握",
            
            # 人员类型和身份
            "要員", "社員", "プロパー", "人材", "人員", "メンバー", "スタッフ",
            "弊社", "営業中", "ご紹介", "紹介", "推薦", "候補者", "応募者",
            "フリーランス", "派遣", "契約社員", "業務委託", "外注", "協力会社",
            
            # 人员状态和条件
            "稼働中", "稼働可能", "アサイン", "参画", "常駐", "リモート可",
            "即戦力", "ベテラン", "シニア", "ジュニア", "新人", "若手",
            "経歴", "職歴", "学歴", "資格", "認定", "取得済み",
            
            # 人员评价和特征
            "優秀", "真面目", "責任感", "協調性", "リーダーシップ", "向上心",
            "几帳面", "丁寧", "細かい", "気配り", "サポート力", "対応力"
        ]
        
        # 项目需求相关的关键词（应该保留的）
        project_keywords = [
            "プロジェクト", "開発", "案件", "募集", "求人", "採用", "必要", "要求",
            "条件", "資格", "スキル", "技術", "経験者", "エンジニア", "プログラマー",
            "開発者", "技術者", "業務", "システム", "アプリケーション", "Web",
            "フロントエンド", "バックエンド", "データベース", "インフラ"
        ]
        
        # 标题中的强人员信息指示词（出现在标题中时直接排除）
        title_person_exclusion_keywords = [
            "プロパー", "人材", "要員", "社員", "営業中", "ご紹介", 
            "推薦", "候補者", "応募者", "稼働中", "稼働可能", "アサイン", "参画可能",
            # 人员信息相关
            "要員情報", "人材情報", "人員情報", "社員情報", "メンバー情報",
            "技術者情報", "エンジニア情報", "開発者情報", "プログラマー情報",
            # 新增的人员介绍关键词
            "人財配信", "弊社直個人", "直個人", "個人情報", "履歴書", "経歴書",
            "人財紹介", "人材紹介", "技術者紹介", "エンジニア紹介", "プログラマー紹介",
            "スキルシート", "技術シート", "経験シート", "プロフィール",
            # 人员状态相关
            "即日稼働", "稼働希望", "参画希望", "アサイン希望", "就業希望",
            "転職希望", "求職", "就職活動", "キャリアチェンジ",
            # 人员评价和推荐
            "優秀な", "実力のある", "経験豊富な", "ベテランの", "即戦力の",
            "おすすめの", "推奨の", "イチオシの", "注目の",
            # 自由职业者和直接人员相关
            "フリーランス", "直フリーランス", "フリー", "個人事業主", "業務委託",
            "外部パートナー", "協力会社", "外注先", "委託先"
        ]
        
        # 一般人员信息指示词（用于内容分析）
        general_person_indicators = [
            "弊社", "営業中", "ご紹介", "推薦", "候補者", "応募者", 
            "稼働中", "稼働可能", "アサイン", "参画可能",
            # 新增的人员信息指示词
            "人財配信", "弊社直個人", "直個人", "個人情報", "履歴書", "経歴書",
            "人財紹介", "人材紹介", "技術者紹介", "エンジニア紹介", "プログラマー紹介",
            "スキルシート", "技術シート", "経験シート", "プロフィール",
            "即日稼働", "稼働希望", "参画希望", "アサイン希望", "就業希望",
            "転職希望", "求職", "就職活動", "キャリアチェンジ",
            "優秀な", "実力のある", "経験豊富な", "ベテランの", "即戦力の",
            "おすすめの", "推奨の", "イチオシの", "注目の",
            # 人员配信相关
            "配信", "配属", "派遣", "出向", "常駐", "客先常駐",
            # 自由职业者相关
            "フリーランス", "直フリーランス", "フリー", "個人事業主", "業務委託",
            "外部パートナー", "協力会社", "外注先", "委託先",
            # 人员寻找项目的典型表达
            "見合う案件", "案件ございましたら", "ご紹介いただけます", "案件をお探し",
            "プロジェクトをお探し", "お仕事をお探し", "参画できる案件", "マッチする案件",
            "適した案件", "条件に合う案件", "希望に合う案件"
        ]
        
        for result in results:
            # 检查邮件内容（主题和预览）
            content_text = f"{result.subject} {result.preview}".lower()
            subject_text = result.subject.lower()
            
            # 检查标题中是否包含强人员信息指示词（直接排除）
            has_title_person_keyword = any(
                keyword.lower() in subject_text for keyword in title_person_exclusion_keywords
            )
            
            # 如果标题中包含强人员信息指示词，直接排除
            if has_title_person_keyword:
                logger.info(f"过滤掉标题包含人员关键词的邮件: {result.subject[:50]}...")
                continue
            
            # 检查内容中是否包含一般人员信息指示词
            has_general_person_indicator = any(
                keyword.lower() in content_text for keyword in general_person_indicators
            )
            
            # 计算人员信息关键词出现次数
            person_count = sum(1 for keyword in person_keywords if keyword.lower() in content_text)
            
            # 计算项目需求关键词出现次数
            project_count = sum(1 for keyword in project_keywords if keyword.lower() in content_text)
            
            # 调整后的过滤条件：更加平衡
            should_exclude = False
            
            # 1. 如果内容中包含一般人员信息指示词，且人员关键词明显多于项目关键词
            if has_general_person_indicator and person_count > project_count + 2:
                should_exclude = True
                logger.info(f"过滤掉内容包含人员指示词且人员信息过多的邮件: {result.subject[:50]}...")
            
            # 2. 如果人员关键词数量远超项目关键词（比例过高）
            elif person_count > 0 and project_count == 0 and person_count >= 3:
                should_exclude = True
                logger.info(f"过滤掉纯人员信息邮件: {result.subject[:50]}...")
            
            # 3. 如果人员关键词数量是项目关键词的3倍以上
            elif person_count > 0 and project_count > 0 and person_count >= project_count * 3:
                should_exclude = True
                logger.info(f"过滤掉人员信息占主导的邮件: {result.subject[:50]}...")
            
            if not should_exclude:
                filtered_results.append(result)
        
        logger.info(f"结果过滤完成: {len(results)} -> {len(filtered_results)}")
        return filtered_results
    
    def _search_project_requirements(self, query_info: Dict, top_k: int) -> List[SearchResult]:
        """
        搜索项目需求和招聘信息
        
        Args:
            query_info: 查询分析信息
            top_k: 结果数量
            
        Returns:
            List[SearchResult]: 搜索结果
        """
        project_queries = [
            "プロジェクト 募集 開発 案件 求人",
            "採用 人材 エンジニア 募集 条件",
            "開発者 必要 スキル 要求 資格"
        ]
        
        results = []
        for project_query in project_queries:
            # 添加技能关键词
            if query_info['skills']:
                skill_terms = []
                for skill in query_info['skills'][:2]:  # 限制技能数量
                    skill_terms.extend(self.skill_keywords[skill][:2])
                project_query += " " + " ".join(skill_terms)
            
            # 添加经验要求
            if query_info['experience_years']:
                project_query += f" {query_info['experience_years']}年 経験"
            
            query_results = self.search(project_query, top_k // len(project_queries))
            results.extend(query_results)
        
        return results
    
    def _search_person_profiles(self, query_info: Dict, top_k: int) -> List[SearchResult]:
        """
        搜索人员简历和技能信息
        
        Args:
            query_info: 查询分析信息
            top_k: 结果数量
            
        Returns:
            List[SearchResult]: 搜索结果
        """
        person_queries = [
            "プログラマー エンジニア 経験 技術 専門",
            "開発者 スキル 得意 できる 熟練",
            "技術者 専攻 習得 精通 能力"
        ]
        
        results = []
        for person_query in person_queries:
            # 添加技能关键词
            if query_info['skills']:
                skill_terms = []
                for skill in query_info['skills'][:2]:  # 限制技能数量
                    skill_terms.extend(self.skill_keywords[skill][:2])
                person_query += " " + " ".join(skill_terms)
            
            # 添加经验要求
            if query_info['experience_years']:
                person_query += f" {query_info['experience_years']}年 経験"
            
            query_results = self.search(person_query, top_k // len(person_queries))
            results.extend(query_results)
        
        return results
    
    def _calculate_bidirectional_bonus(self, result: SearchResult, query_info: Dict) -> float:
        """
        计算双向匹配的评分加成
        
        Args:
            result: 搜索结果
            query_info: 查询分析信息
            
        Returns:
            float: 评分加成
        """
        bonus = 0.0
        
        # 基础技能匹配加成
        bonus += self._calculate_skill_bonus(result, query_info)
        
        # 搜索方向匹配加成
        text_content = (result.subject + " " + result.preview).lower()
        
        if query_info['search_direction'] == 'person_to_project':
            # 人员→项目：优先匹配项目需求
            project_indicators = ['プロジェクト', '案件', '募集', '求人', '採用', '開発', '要求', '必要']
            project_matches = sum(1 for indicator in project_indicators if indicator in text_content)
            bonus += project_matches * 0.15
            
        elif query_info['search_direction'] == 'project_to_person':
            # 项目→人员：优先匹配人员信息
            person_indicators = ['プログラマー', 'エンジニア', '開発者', '経験', '技術', '専門', '得意', 'スキル']
            person_matches = sum(1 for indicator in person_indicators if indicator in text_content)
            bonus += person_matches * 0.15
        
        # 输入类型匹配加成
        if query_info['input_type'] == 'person':
            # 输入人员信息时，优先匹配项目需求
            if any(term in text_content for term in ['プロジェクト', '案件', '募集', '求人']):
                bonus += 0.2
        elif query_info['input_type'] == 'project':
            # 输入项目信息时，优先匹配人员简历
            if any(term in text_content for term in ['プログラマー', 'エンジニア', '開発者', '経験']):
                bonus += 0.2
        
        return bonus
    
    def _calculate_skill_bonus(self, result: SearchResult, query_info: Dict) -> float:
        """
        计算技能匹配奖励分数
        
        Args:
            result: 搜索结果
            query_info: 查询解析信息
            
        Returns:
            float: 奖励分数
        """
        bonus = 0.0
        text_content = f"{result.subject} {result.preview}".lower()
        
        # 技能匹配奖励
        for skill in query_info['skills']:
            skill_keywords = self.skill_keywords[skill]
            for keyword in skill_keywords:
                if keyword.lower() in text_content:
                    bonus += 0.1
                    break
        
        # 经验年限匹配奖励
        if query_info['experience_years']:
            exp_patterns = [
                f"{query_info['experience_years']}年",
                f"{query_info['experience_years']}年間",
                f"{query_info['experience_years']}年以上"
            ]
            for pattern in exp_patterns:
                if pattern in text_content:
                    bonus += 0.15
                    break
        
        # 项目相关词汇奖励
        project_keywords = ['プロジェクト', '案件', '開発', '求人', '募集']
        for keyword in project_keywords:
            if keyword in text_content:
                bonus += 0.05
        
        return min(bonus, 0.5)  # 最大奖励0.5分
    
    def keyword_search(self, query: str, top_k: int = None) -> List[SearchResult]:
        """
        关键词搜索（传统搜索方式）
        
        Args:
            query: 搜索查询
            top_k: 返回结果数量
            
        Returns:
            List[SearchResult]: 搜索结果列表
        """
        if not self.email_metadata:
            return []
        
        if top_k is None:
            top_k = self.default_top_k
        
        query_words = query.lower().split()
        results = []
        
        for i, metadata in enumerate(self.email_metadata):
            score = 0
            
            # 在主题中搜索
            subject = metadata.get('subject', '').lower()
            score += sum(2 for word in query_words if word in subject)
            
            # 在发件人中搜索
            sender = metadata.get('sender', '').lower()
            score += sum(1.5 for word in query_words if word in sender)
            
            # 在正文中搜索
            body = metadata.get('body_text', '').lower()
            score += sum(1 for word in query_words if word in body)
            
            if score > 0:
                preview = self._generate_preview(metadata, query)
                
                # 获取完整正文内容 - 优先使用body_text，如果为空则从body_html转换
                original_body_text = metadata.get('body_text', '')
                body_html = metadata.get('body_html', '')
                
                logger.info(f"关键词搜索SearchResult创建 - 邮件ID: {metadata.get('uid', 'unknown')}")
                logger.info(f"  - 原始body_text长度: {len(original_body_text)}")
                logger.info(f"  - body_html长度: {len(body_html)}")
                
                full_body_text = original_body_text
                if not full_body_text.strip() and body_html:
                    # 如果body_text为空但有body_html，则清理HTML标签
                    full_body_text = self._clean_html(body_html)
                    logger.info(f"  - 从body_html转换后长度: {len(full_body_text)}")
                else:
                    logger.info(f"  - 使用原始body_text，长度: {len(full_body_text)}")
                
                result = SearchResult(
                    email_id=metadata['uid'],
                    score=score,
                    subject=metadata['subject'],
                    sender=metadata['sender'],
                    date=metadata['date'],
                    preview=preview,
                    folder=metadata['folder'],
                    attachments=metadata['attachments'],
                    body_text=full_body_text
                )
                
                results.append(result)
        
        # 按分数排序
        results.sort(key=lambda x: x.score, reverse=True)
        
        return results[:top_k]
    
    def save_index(self, filepath: str) -> bool:
        """
        保存索引到文件
        
        Args:
            filepath: 保存路径
            
        Returns:
            bool: 保存是否成功
        """
        try:
            if self.index is None:
                logger.error("没有可保存的索引")
                return False
            
            # 创建保存目录
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            # 保存FAISS索引
            faiss.write_index(self.index, f"{filepath}.faiss")
            
            # 保存元数据
            with open(f"{filepath}.metadata", 'wb') as f:
                pickle.dump(self.email_metadata, f)
            
            # 保存配置信息
            config = {
                'model_name': self.model_name,
                'email_count': len(self.email_metadata),
                'created_at': datetime.now().isoformat()
            }
            
            with open(f"{filepath}.config", 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            logger.info(f"索引已保存到: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"保存索引失败: {str(e)}")
            return False
    
    def load_index(self, filepath: str) -> bool:
        """
        从文件加载索引
        
        Args:
            filepath: 索引文件路径
            
        Returns:
            bool: 加载是否成功
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(f"{filepath}.faiss"):
                logger.error(f"索引文件不存在: {filepath}.faiss")
                return False
            
            # 初始化模型
            if not self.is_initialized:
                self.initialize()
            
            if not self.is_initialized:
                return False
            
            # 加载FAISS索引
            self.index = faiss.read_index(f"{filepath}.faiss")
            
            # 加载元数据
            with open(f"{filepath}.metadata", 'rb') as f:
                self.email_metadata = pickle.load(f)
            
            # 加载配置信息
            if os.path.exists(f"{filepath}.config"):
                with open(f"{filepath}.config", 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    logger.info(f"加载索引配置: {config}")
            
            logger.info(f"索引加载成功，包含 {len(self.email_metadata)} 封邮件")
            return True
            
        except Exception as e:
            logger.error(f"加载索引失败: {str(e)}")
            return False
    
    def get_statistics(self) -> Dict:
        """
        获取搜索引擎统计信息
        
        Returns:
            Dict: 统计信息
        """
        stats = {
            'is_initialized': self.is_initialized,
            'model_name': self.model_name,
            'email_count': len(self.email_metadata) if self.email_metadata else 0,
            'index_size': self.index.ntotal if self.index else 0
        }
        
        if self.email_metadata:
            # 统计邮件分布
            folders = {}
            senders = {}
            
            for metadata in self.email_metadata:
                folder = metadata.get('folder', 'Unknown')
                sender = metadata.get('sender', 'Unknown')
                
                folders[folder] = folders.get(folder, 0) + 1
                senders[sender] = senders.get(sender, 0) + 1
            
            stats['folder_distribution'] = folders
            stats['top_senders'] = dict(sorted(senders.items(), 
                                             key=lambda x: x[1], 
                                             reverse=True)[:10])
        
        return stats