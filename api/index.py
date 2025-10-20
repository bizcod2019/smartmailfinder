"""智能邮件搜索工具 - 主应用文件
基于Streamlit + Vercel + 阿里云OSS的邮件语义搜索系统
"""

import streamlit as st
import os
import sys
import requests
from datetime import datetime, timedelta
import traceback
from typing import Dict, List, Optional
import logging
import time
from functools import wraps
import pandas as pd

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, project_root)

# 导入自定义模块
try:
    from src.email_connector import EmailConnector
    from src.semantic_search import SemanticSearchEngine
    from src.oss_storage import OSSStorage
    from src.utils import (
        validate_email_config, format_email_preview, export_emails_to_csv,
        export_emails_to_excel, load_config_from_env, save_search_history,
        load_search_history, create_cache_dir, cleanup_temp_files,
        validate_search_query, highlight_search_terms, save_email_config,
        load_email_config, list_saved_configs, delete_email_config,
        save_emails_to_cache, load_emails_from_cache, get_cache_info,
        clean_html_tags, get_historical_cache_files, load_emails_from_specific_cache,
        search_emails_in_cache
    )
except ImportError as e:
    st.error(f"模块导入失败: {str(e)}")
    logger.error(f"Module import failed: {str(e)}")
    st.stop()

# 页面配置
st.set_page_config(
    page_title="智能邮件搜索工具",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 隐藏页面底部默认的“Made with Streamlit”文案
st.markdown("""
<style>
footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# 错误通知（webhook）
def notify_error(context: str, error: Exception, config: Dict):
    try:
        webhook = config.get('app', {}).get('error_webhook_url')
        if not webhook:
            return
        payload = {
            'context': context,
            'error': str(error),
            'timestamp': datetime.now().isoformat()
        }
        # 兼容常见 webhook（如自建、Slack等）
        headers = {'Content-Type': 'application/json'}
        requests.post(webhook, json=payload, headers=headers, timeout=5)
    except Exception as _:
        # 告警失败不影响主流程
        logger.warning("Error notification failed")

# 性能监控装饰器
def performance_monitor(func):
    """性能监控装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            if execution_time > 1.0:  # 记录超过1秒的操作
                logger.warning(f"Slow operation: {func.__name__} took {execution_time:.2f}s")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Error in {func.__name__} after {execution_time:.2f}s: {str(e)}")
            raise
    return wrapper

# 错误处理装饰器
def error_handler(func):
    """错误处理装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            # 发送错误告警
            try:
                notify_error(func.__name__, e, config)
            except Exception:
                pass
            st.error(f"操作失败: {str(e)}")
            if st.session_state.get('debug_mode', False):
                st.code(traceback.format_exc())
            return None
    return wrapper

# 初始化session state
def init_session_state():
    """初始化session state"""
    defaults = {
        'email_connector': None,
        'search_engine': None,
        'oss_storage': None,
        'emails_data': [],
        'search_results': [],
        'connection_status': False,
        'last_sync_time': None,
        'search_history': [],
        'debug_mode': False,
        'performance_stats': {},
        'error_count': 0
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

# 初始化
init_session_state()

# 自动加载缓存的邮件数据
if not st.session_state.emails_data:
    cached_emails = load_emails_from_cache()
    if cached_emails:
        st.session_state.emails_data = cached_emails
        logger.info(f"自动加载了 {len(cached_emails)} 封缓存邮件")

# 加载配置
@st.cache_data(ttl=300)  # 5分钟缓存
def load_app_config():
    """加载应用配置"""
    try:
        return load_config_from_env()
    except Exception as e:
        logger.error(f"Failed to load config: {str(e)}")
        return {
            'app': {'cache_dir': './cache', 'debug': False},
            'oss': {},
            'ai': {'model_name': 'all-MiniLM-L6-v2'}
        }

config = load_app_config()

# 创建缓存目录
try:
    cache_dir = create_cache_dir(config['app']['cache_dir'])
except Exception as e:
    logger.error(f"Failed to create cache directory: {str(e)}")
    cache_dir = './cache'

# 健康检查处理（/?health=1 或 /?health=TOKEN）
def handle_healthcheck() -> bool:
    try:
        params = st.experimental_get_query_params()
        if 'health' not in params:
            return False
        token = params.get('health', [''])[0]
        expected = config['app'].get('healthcheck_token')
        if expected and token != expected:
            st.error('健康检查令牌无效')
            return True
        # 轻量状态输出，避免重载主界面
        emails_count = len(st.session_state.get('emails_data', []))
        indexed = len(st.session_state.search_engine.email_metadata) if st.session_state.get('search_engine') else 0
        st.write({
            'status': 'ok',
            'emails_synced': emails_count,
            'emails_indexed': indexed,
            'connected': bool(st.session_state.get('connection_status', False)),
            'last_sync': st.session_state.get('last_sync_time').isoformat() if st.session_state.get('last_sync_time') else None,
            'errors': int(st.session_state.get('error_count', 0)),
        })
        return True
    except Exception as e:
        logger.error(f"Healthcheck failed: {str(e)}")
        st.write({'status': 'error', 'message': str(e)})
        return True

@error_handler
@performance_monitor
def configure_email_settings() -> Dict:
    """配置邮箱设置"""
    email_config = {}
    
    # 配置管理部分
    st.markdown("#### 📁 配置管理")
    
    # 获取已保存的配置列表
    saved_configs = list_saved_configs()
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # 加载已保存的配置
        if saved_configs:
            selected_config = st.selectbox(
                "选择已保存的配置",
                ["新建配置"] + saved_configs,
                help="选择一个已保存的配置快速加载设置"
            )
            
            if selected_config != "新建配置":
                if st.button("🔄 加载配置", key="load_config"):
                    loaded_config = load_email_config(selected_config)
                    if loaded_config:
                        # 将加载的配置保存到session state
                        for key, value in loaded_config.items():
                            if key != 'saved_at':  # 排除时间戳
                                st.session_state[f"config_{key}"] = value
                        st.success(f"✅ 配置 '{selected_config}' 已加载")
                        st.rerun()
                    else:
                        st.error("❌ 加载配置失败")
        else:
            st.info("暂无已保存的配置")
    
    with col2:
        # 删除配置
        if saved_configs:
            config_to_delete = st.selectbox(
                "删除配置",
                ["选择要删除的配置"] + saved_configs,
                key="delete_config_select"
            )
            
            if config_to_delete != "选择要删除的配置":
                if st.button("🗑️ 删除", key="delete_config", type="secondary"):
                    if delete_email_config(config_to_delete):
                        st.success(f"✅ 配置 '{config_to_delete}' 已删除")
                        st.rerun()
                    else:
                        st.error("❌ 删除配置失败")
    
    st.markdown("---")
    st.markdown("#### ⚙️ 邮箱设置")
    
    # 邮箱类型选择
    email_provider = st.selectbox(
        "邮箱服务商",
        ["Gmail", "Outlook", "QQ邮箱", "163邮箱", "自定义IMAP"],
        index=0 if "config_provider" not in st.session_state else 
              ["Gmail", "Outlook", "QQ邮箱", "163邮箱", "自定义IMAP"].index(st.session_state.get("config_provider", "Gmail"))
    )
    
    # 根据服务商预设IMAP配置
    imap_configs = {
        "Gmail": {"server": "imap.gmail.com", "port": 993},
        "Outlook": {"server": "outlook.office365.com", "port": 993},
        "QQ邮箱": {"server": "imap.qq.com", "port": 993},
        "163邮箱": {"server": "imap.163.com", "port": 993},
        "自定义IMAP": {"server": "", "port": 993}
    }
    
    email_config['provider'] = email_provider
    email_config['server'] = imap_configs[email_provider]['server']
    email_config['port'] = imap_configs[email_provider]['port']
    
    # 如果是自定义IMAP，允许用户输入服务器信息
    if email_provider == "自定义IMAP":
        email_config['server'] = st.text_input(
            "IMAP服务器", 
            value=st.session_state.get("config_server", "")
        )
        email_config['port'] = st.number_input(
            "端口", 
            value=st.session_state.get("config_port", 993), 
            min_value=1, 
            max_value=65535
        )
    else:
        st.info(f"服务器: {email_config['server']}:{email_config['port']}")
    
    # 用户凭据
    email_config['email'] = st.text_input(
        "邮箱地址", 
        placeholder="your.email@example.com",
        value=st.session_state.get("config_email", "")
    )
    email_config['password'] = st.text_input("密码/应用专用密码", type="password")
    email_config['use_ssl'] = True
    
    # SSL配置选项
    with st.expander("🔒 高级SSL设置"):
        email_config['disable_ssl_verify'] = st.checkbox(
            "禁用SSL证书验证", 
            value=st.session_state.get("config_disable_ssl_verify", False),
            help="⚠️ 仅在遇到SSL证书问题时启用。这会降低安全性，请谨慎使用。"
        )
        if email_config['disable_ssl_verify']:
            st.warning("⚠️ SSL证书验证已禁用，连接安全性降低")
    
    # 配置保存部分
    st.markdown("---")
    st.markdown("#### 💾 保存配置")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        config_name = st.text_input(
            "配置名称", 
            value="default",
            placeholder="输入配置名称",
            help="为当前配置指定一个名称，方便以后快速加载"
        )
    
    with col2:
        if st.button("💾 保存配置", key="save_config"):
            if config_name and email_config.get('email'):
                # 保存当前配置（不包含密码）
                if save_email_config(email_config, config_name):
                    st.success(f"✅ 配置 '{config_name}' 已保存")
                else:
                    st.error("❌ 保存配置失败")
            else:
                st.error("❌ 请填写配置名称和邮箱地址")
    
    # 连接测试按钮
    if st.button("🔗 测试连接"):
        if validate_email_config(email_config):
            with st.spinner("正在测试邮箱连接..."):
                try:
                    connector = EmailConnector(email_config)
                    if connector.test_connection():
                        st.session_state.email_connector = connector
                        st.session_state.connection_status = True
                        st.success("✅ 邮箱连接成功！")
                        email_config['configured'] = True
                        logger.info(f"Email connection successful for {email_config['email']}")
                        
                        # 询问用户是否立即开始同步
                        st.info("🚀 邮箱配置完成！您现在可以：")
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("🔄 立即同步邮件", type="primary", use_container_width=True):
                                st.session_state.auto_sync_requested = True
                                st.rerun()
                        with col2:
                            if st.button("🔍 直接开始搜索", type="secondary", use_container_width=True):
                                st.session_state.direct_search_mode = True
                                st.info("💡 您选择了直接搜索模式。搜索时将实时查询邮件服务器，可能会稍慢但无需等待同步。")
                        
                        # 如果用户选择了自动同步
                        if st.session_state.get('auto_sync_requested', False):
                            st.info("🔄 正在自动同步邮件，请稍候...")
                            # 使用默认配置进行同步
                            sync_emails(limit=-1, days_back=365, include_sent=True)
                            st.session_state.auto_sync_requested = False
                            st.success("🎉 邮件同步完成！您现在可以切换到搜索页面开始使用了。")
                            st.balloons()
                    else:
                        st.error("❌ 邮箱连接失败，请检查配置")
                        email_config['configured'] = False
                        st.session_state.error_count += 1
                except Exception as e:
                    st.error(f"❌ 连接错误: {str(e)}")
                    email_config['configured'] = False
                    st.session_state.error_count += 1
                    logger.error(f"Email connection failed: {str(e)}")
        else:
            st.error("❌ 请填写完整的邮箱配置信息")
            email_config['configured'] = False
    
    return email_config

@error_handler
def configure_search_settings() -> Dict:
    """配置搜索设置"""
    search_config = {}
    
    # 搜索模式
    search_config['search_mode'] = st.radio(
        "搜索模式",
        ["智能搜索", "关键词搜索", "混合搜索"],
        help="智能搜索使用AI理解语义，关键词搜索精确匹配，混合搜索结合两者优势"
    )
    
    # 时间范围
    search_config['time_range'] = st.selectbox(
        "时间范围",
        ["全部", "最近一周", "最近一个月", "最近三个月", "最近一年", "自定义"]
    )
    
    if search_config['time_range'] == "自定义":
        col1, col2 = st.columns(2)
        with col1:
            search_config['start_date'] = st.date_input("开始日期")
        with col2:
            search_config['end_date'] = st.date_input("结束日期")
    
    # 邮件文件夹筛选
    search_config['folder_filter'] = st.multiselect(
        "邮件文件夹",
        ["收件箱", "已发送", "草稿箱", "垃圾邮件", "其他"],
        default=["收件箱"]
    )
    
    # 结果数量限制
    search_config['max_results'] = st.slider("最大结果数", 10, 100, 20)
    
    return search_config

def display_system_status():
    """显示系统状态"""
    emails_count = len(st.session_state.emails_data)
    st.metric("已索引邮件", f"{emails_count:,}")
    
    if st.session_state.connection_status:
        st.success("🟢 邮箱已连接")
    else:
        st.error("🔴 邮箱未连接")
    
    if st.session_state.search_engine:
        st.success("🟢 搜索引擎已就绪")
    else:
        st.warning("🟡 搜索引擎未初始化")
    
    # 显示最后同步时间
    if st.session_state.last_sync_time:
        st.info(f"最后同步: {st.session_state.last_sync_time.strftime('%Y-%m-%d %H:%M')}")
    
    # 错误计数
    if st.session_state.error_count > 0:
        st.warning(f"⚠️ 错误次数: {st.session_state.error_count}")
    
    # 调试模式开关
    st.session_state.debug_mode = st.checkbox("调试模式", value=st.session_state.debug_mode)

@error_handler
@performance_monitor
def search_interface(search_config: Dict):
    """搜索界面"""
    # 添加醒目的标题和状态指示
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("🔍 智能邮件搜索")
    with col2:
        # 显示搜索引擎状态
        if st.session_state.search_engine:
            st.success("✅ 搜索就绪")
        else:
            st.error("❌ 未就绪")
    
    # 显示邮件统计信息
    emails_count = len(st.session_state.emails_data)
    indexed_count = len(st.session_state.search_engine.email_metadata) if st.session_state.search_engine else 0
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📧 已同步邮件", f"{emails_count:,}")
    with col2:
        st.metric("🔍 已索引邮件", f"{indexed_count:,}")
    with col3:
        if emails_count > 0:
            coverage = (indexed_count / emails_count * 100) if emails_count > 0 else 0
            st.metric("📊 索引覆盖率", f"{coverage:.1f}%")
    
    st.divider()
    
    # 检查搜索引擎状态
    if not st.session_state.search_engine:
        # 如果有邮件数据但没有搜索引擎，自动重建索引
        if st.session_state.emails_data:
            st.info("🔄 检测到邮件数据，正在自动初始化搜索引擎...")
            rebuild_search_index()
            st.rerun()
        else:
            st.error("⚠️ 搜索引擎未初始化，请先同步邮件！")
        
        # 突出显示的引导信息
        st.markdown("""
        <div style="background-color: #e3f2fd; padding: 20px; border-radius: 8px; border: 2px solid #2196f3; margin-bottom: 20px;">
        <h3 style="color: #1976d2; margin: 0 0 15px 0;">🚀 快速开始指南</h3>
        
        <div style="display: flex; align-items: center; margin-bottom: 15px;">
        <div style="background-color: #2196f3; color: white; border-radius: 50%; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; margin-right: 15px; font-weight: bold;">1</div>
        <div>
        <h4 style="color: #333; margin: 0 0 5px 0;">配置邮箱连接</h4>
        <p style="color: #666; margin: 0; font-size: 16px;">
        📧 前往"邮件配置"标签页，输入邮箱信息并测试连接
        </p>
        </div>
        </div>
        
        <div style="display: flex; align-items: center; margin-bottom: 15px;">
        <div style="background-color: #4caf50; color: white; border-radius: 50%; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; margin-right: 15px; font-weight: bold;">2</div>
        <div>
        <h4 style="color: #333; margin: 0 0 5px 0;">选择搜索方式</h4>
        <p style="color: #666; margin: 0; font-size: 16px;">
        🔍 <strong>实时搜索</strong>：配置完成即可使用，无需等待<br>
        🧠 <strong>智能搜索</strong>：需要先同步邮件，但搜索更智能
        </p>
        </div>
        </div>
        
        <div style="display: flex; align-items: center;">
        <div style="background-color: #ff9800; color: white; border-radius: 50%; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; margin-right: 15px; font-weight: bold;">3</div>
        <div>
        <h4 style="color: #333; margin: 0 0 5px 0;">开始搜索</h4>
        <p style="color: #666; margin: 0; font-size: 16px;">
        ✨ 配置完成后即可开始搜索，或选择同步邮件以获得更好的搜索体验
        </p>
        </div>
        </div>
        </div>
        """, unsafe_allow_html=True)
        
        # 显示操作指南
        st.markdown("""
        <div style="background-color: #e8f4fd; padding: 20px; border-radius: 10px; border: 2px solid #1f77b4; margin: 20px 0;">
        <h3 style="color: #1f77b4; margin: 0 0 15px 0;">📋 操作步骤</h3>
        <div style="background-color: white; padding: 15px; border-radius: 8px; margin-bottom: 15px;">
        <h4 style="color: #333; margin: 0 0 10px 0;">第一步：切换到邮件管理</h4>
        <p style="color: #666; margin: 0; font-size: 16px;">
        👆 点击页面顶部的 <strong style="background-color: #f0f0f0; padding: 2px 6px; border-radius: 4px;">📧 邮件管理</strong> 标签页
        </p>
        </div>
        <div style="background-color: white; padding: 15px; border-radius: 8px; margin-bottom: 15px;">
        <h4 style="color: #333; margin: 0 0 10px 0;">第二步：配置同步选项</h4>
        <p style="color: #666; margin: 0; font-size: 16px;">
        ⚙️ 选择同步数量（建议选择"无限制"）和时间范围
        </p>
        </div>
        <div style="background-color: white; padding: 15px; border-radius: 8px;">
        <h4 style="color: #333; margin: 0 0 10px 0;">第三步：开始同步</h4>
        <p style="color: #666; margin: 0; font-size: 16px;">
        🔄 点击"同步邮件"按钮，等待同步完成
        </p>
        </div>
        </div>
        """, unsafe_allow_html=True)
        
        # 简化的操作按钮
        col1, col2 = st.columns(2)
        with col1:
            if st.button("💡 显示详细指导", type="primary", use_container_width=True):
                st.session_state.show_detailed_guide = True
                st.rerun()
        with col2:
            if emails_count > 0:
                if st.button("🔨 重建搜索索引", type="secondary", use_container_width=True):
                    if config['app'].get('index_async'):
                        rebuild_search_index_async()
                    else:
                        rebuild_search_index()
                    st.rerun()
        
        # 显示详细指导
        if st.session_state.get('show_detailed_guide', False):
            st.markdown("""
            <div style="background-color: #fff3cd; padding: 20px; border-radius: 8px; border: 2px solid #ffc107; margin-top: 15px;">
            <h4 style="color: #856404; margin: 0 0 15px 0;">🎯 详细操作指导</h4>
            
            <div style="margin-bottom: 20px;">
            <h5 style="color: #856404; margin: 0 0 10px 0;">📧 邮箱配置步骤：</h5>
            <ol style="color: #856404; margin: 0; padding-left: 20px;">
            <li style="margin-bottom: 5px;">点击页面顶部的"📧 邮件配置"标签</li>
            <li style="margin-bottom: 5px;">填写邮箱服务器信息（IMAP地址、端口、用户名、密码）</li>
            <li style="margin-bottom: 5px;">点击"🔗 测试连接"验证配置</li>
            <li style="margin-bottom: 5px;">连接成功后选择"立即同步邮件"或"直接开始搜索"</li>
            </ol>
            </div>
            
            <div style="margin-bottom: 20px;">
            <h5 style="color: #856404; margin: 0 0 10px 0;">🔍 搜索模式选择：</h5>
            <ul style="color: #856404; margin: 0; padding-left: 20px;">
            <li style="margin-bottom: 5px;"><strong>实时搜索：</strong>配置完邮箱即可使用，直接查询邮件服务器</li>
            <li style="margin-bottom: 5px;"><strong>智能搜索：</strong>需要先同步邮件，支持AI语义理解和自然语言查询</li>
            </ul>
            </div>
            
            <div>
            <h5 style="color: #856404; margin: 0 0 10px 0;">⚡ 快速开始建议：</h5>
            <p style="color: #856404; margin: 0;">
            如果您想立即开始搜索，建议先使用<strong>实时搜索</strong>模式。
            如果您有时间等待同步，<strong>智能搜索</strong>将提供更好的搜索体验。
            </p>
            </div>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("✅ 关闭指导", type="secondary"):
                st.session_state.show_detailed_guide = False
                st.rerun()
    else:
        # 搜索引擎已就绪，显示搜索提示
        st.success("🎉 搜索引擎已就绪！您可以开始搜索邮件了")
    
    # 搜索模式选择
    st.subheader("🔎 搜索您的邮件")
    
    # 搜索模式选择
    col1, col2 = st.columns([3, 1])
    with col1:
        search_mode = st.radio(
            "选择搜索模式：",
            options=["智能搜索", "技能匹配搜索", "实时搜索"],
            index=0 if st.session_state.search_engine else 2,
            horizontal=True,
            help="智能搜索：基于AI语义理解；技能匹配搜索：双向匹配程序员技能和项目需求；实时搜索：直接查询邮件服务器"
        )
    with col2:
        if search_mode in ["智能搜索", "技能匹配搜索"]:
            if st.session_state.search_engine:
                st.success("✅ 可用")
            else:
                st.error("❌ 需同步")
        else:
            if st.session_state.email_connector:
                st.success("✅ 可用")
            else:
                st.error("❌ 需配置")
    
    # 初始化缓存文件选择变量
    selected_cache_file = None
    if search_mode in ["智能搜索", "技能匹配搜索"]:
        # 获取历史缓存文件列表
        historical_files = get_historical_cache_files()
        
        if historical_files:
            # 创建缓存选项列表，最新缓存显示为"最新"，历史缓存显示时间信息
            cache_options = ["最新"]
            for file in historical_files:
                # 从文件名中提取日期编号（去掉前缀和后缀）
                filename = file['filename']
                if filename.startswith('emails_cache_') and filename.endswith('.json'):
                    date_part = filename[13:-5]  # 去掉 'emails_cache_' 和 '.json'
                    readable_time = file.get('readable_time', date_part)
                    # 显示格式：日期编号 (时间)
                    display_text = f"{date_part} ({readable_time})"
                    cache_options.append(display_text)
            
            selected_cache_file = st.selectbox(
                "📂 数据源",
                options=cache_options,
                help="选择要搜索的数据源：最新缓存或历史缓存文件"
            )
    else:
        # 对于实时搜索模式，确保变量有定义
        selected_cache_file = None
    
    # 根据搜索模式显示不同的提示
    if search_mode == "智能搜索":
        search_disabled = not st.session_state.search_engine
        if search_disabled:
            st.warning("⚠️ 智能搜索需要先同步邮件。您可以切换到实时搜索模式或先同步邮件。")
        else:
            cache_info = "最新缓存" if selected_cache_file is None or selected_cache_file == "最新" else f"历史缓存 ({selected_cache_file})"
            st.info(f"💡 智能搜索支持自然语言查询，当前数据源：{cache_info}\n例如：'昨天的会议邮件'、'包含附件的重要邮件'、'来自客户的报价单'等")
    elif search_mode == "技能匹配搜索":
        search_disabled = not st.session_state.search_engine
        if search_disabled:
            st.warning("⚠️ 技能匹配搜索需要先同步邮件。您可以切换到实时搜索模式或先同步邮件。")
        else:
            cache_info = "最新缓存" if selected_cache_file is None or selected_cache_file == "最新" else f"历史缓存 ({selected_cache_file})"
            st.info(f"🎯 技能匹配搜索支持双向匹配，当前数据源：{cache_info}\n• 输入人员技能 → 匹配项目需求\n• 输入项目需求 → 匹配相关人员\n例如：'4年Java程序员，会Vue3、SpringBoot、MyBatis' 或 '招聘Python开发工程师，要求3年以上经验'")
    else:
        search_disabled = not st.session_state.email_connector
        if search_disabled:
            st.warning("⚠️ 实时搜索需要先配置邮箱连接。")
        else:
            st.info("💡 实时搜索直接查询邮件服务器，支持关键词搜索，例如：'会议'、'合同'、'报价'等")
    
    # 根据搜索模式设置不同的提示信息
    if search_mode == "技能匹配搜索":
        placeholder_text = "双向匹配示例：\n\n【人员技能 → 项目需求】\n• 4年Java程序员，会Vue3、SpringBoot、MyBatis\n• 3年前端开发，熟悉React、TypeScript、Node.js\n• 5年全栈工程师，Python、Django、PostgreSQL\n\n【项目需求 → 相关人员】\n• 招聘Python开发工程师，要求3年以上经验\n• 寻找熟悉React的前端开发者\n• 需要有SpringBoot经验的后端程序员\n\n系统会智能识别输入类型并进行双向匹配..."
        help_text = "🎯 支持双向智能匹配：输入人员技能匹配项目需求，输入项目需求匹配相关人员。系统会自动识别输入类型并优化搜索策略。"
    else:
        placeholder_text = "例如：\n• 上周客户A的报价邮件\n• 关于项目进度的讨论\n• 包含'合同'的重要邮件\n• 昨天收到的所有邮件\n\n支持详细描述，搜索结果会更精准..."
        help_text = "💡 支持自然语言描述和关键词搜索。您可以描述邮件的内容、发件人、时间等任何特征。"
    
    query = st.text_area(
        "输入搜索内容",
        placeholder=placeholder_text,
        help=help_text,
        height=150,
        disabled=search_disabled
    )
    
    # 搜索按钮
    if search_mode == "智能搜索":
        button_text = "🔍 智能搜索" if not search_disabled else "🔍 智能搜索（请先同步邮件）"
    elif search_mode == "技能匹配搜索":
        button_text = "🔍 技能匹配搜索" if not search_disabled else "🔍 技能匹配搜索（请先同步邮件）"
    else:
        button_text = "🔍 实时搜索" if not search_disabled else "🔍 实时搜索（请先配置邮箱）"
    
    search_button = st.button(
        button_text, 
        type="primary", 
        use_container_width=True,
        disabled=search_disabled or not query.strip()
    )
    
    # 高级筛选选项
    with st.expander("🔧 高级筛选"):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            sender_filter = st.text_input("发件人筛选", placeholder="example@domain.com")
        
        with col2:
            subject_filter = st.text_input("主题包含", placeholder="关键词")
        
        with col3:
            has_attachment = st.checkbox("包含附件")
    
    # 执行搜索
    if search_button and query:
        if not validate_search_query(query):
            st.error("❌ 请输入有效的搜索内容")
        elif search_mode in ["智能搜索", "技能匹配搜索"] and not st.session_state.search_engine:
            st.error("❌ 请先同步邮件建立搜索索引")
        elif search_mode == "实时搜索" and not st.session_state.email_connector:
            st.error("❌ 请先配置邮箱连接")
        else:
            if search_mode == "智能搜索":
                cache_info = "最新缓存" if selected_cache_file is None or selected_cache_file == "最新" else f"历史缓存 ({selected_cache_file})"
                spinner_text = f"正在智能搜索邮件（{cache_info}）..."
            elif search_mode == "技能匹配搜索":
                cache_info = "最新缓存" if selected_cache_file is None or selected_cache_file == "最新" else f"历史缓存 ({selected_cache_file})"
                spinner_text = f"正在匹配技能和项目需求（{cache_info}）..."
            else:
                spinner_text = "正在实时搜索邮件..."
                
            with st.spinner(spinner_text):
                try:
                    start_time = time.time()
                    
                    if search_mode == "智能搜索":
                        # 如果选择了历史缓存文件，先加载该文件的邮件
                        if selected_cache_file and selected_cache_file != "最新":
                            # 从显示文本中提取实际的日期编号（格式：日期编号 (时间)）
                            if " (" in selected_cache_file:
                                date_part = selected_cache_file.split(" (")[0]
                            else:
                                date_part = selected_cache_file
                            # 构造完整的文件名
                            cache_filename = f"emails_cache_{date_part}.json"
                            emails = load_emails_from_specific_cache(cache_filename)
                            if emails:
                                # 创建临时的语义搜索引擎实例用于历史缓存
                                from src.semantic_search import SemanticSearchEngine
                                temp_search_engine = SemanticSearchEngine()
                                
                                # 使用历史缓存数据构建临时索引
                                if temp_search_engine.build_index(emails):
                                    # 使用智能语义搜索
                                    search_results = temp_search_engine.search(query, search_config.get('max_results', 20))
                                    
                                    # 转换为统一格式并应用筛选器
                                    results = []
                                    for result in search_results:
                                        # 应用筛选器
                                        if sender_filter and sender_filter.lower() not in result.sender.lower():
                                            continue
                                        if subject_filter and subject_filter.lower() not in result.subject.lower():
                                            continue
                                        if has_attachment and not result.attachments:
                                            continue
                                        
                                        # 转换为统一格式
                                        results.append({
                                            'uid': result.email_id,
                                            'subject': result.subject,
                                            'sender': result.sender,
                                            'date': result.date,
                                            'folder': result.folder,
                                            'attachments': result.attachments,
                                            'body_text': result.body_text,
                                            'score': result.score
                                        })
                                else:
                                    # 如果语义搜索失败，降级到关键词搜索
                                    results = search_emails_in_cache(emails, query)
                                    # 应用筛选器
                                    filtered_results = []
                                    for result in results:
                                        if sender_filter and sender_filter.lower() not in result.get('sender', '').lower():
                                            continue
                                        if subject_filter and subject_filter.lower() not in result.get('subject', '').lower():
                                            continue
                                        if has_attachment and not result.get('attachments'):
                                            continue
                                        filtered_results.append(result)
                                    results = filtered_results
                                    st.warning("⚠️ 智能搜索引擎初始化失败，已降级到关键词搜索")
                            else:
                                results = []
                        else:
                            # 使用现有的智能搜索（最新缓存）
                            results = perform_search(query, search_config, sender_filter, subject_filter, has_attachment)
                    elif search_mode == "技能匹配搜索":
                        # 如果选择了历史缓存文件，先加载该文件的邮件
                        if selected_cache_file and selected_cache_file != "最新":
                            # 从显示文本中提取实际的日期编号（格式：日期编号 (时间)）
                            if " (" in selected_cache_file:
                                date_part = selected_cache_file.split(" (")[0]
                            else:
                                date_part = selected_cache_file
                            # 构造完整的文件名
                            cache_filename = f"emails_cache_{date_part}.json"
                            emails = load_emails_from_specific_cache(cache_filename)
                            if emails:
                                # 创建临时的语义搜索引擎实例用于历史缓存
                                from src.semantic_search import SemanticSearchEngine
                                temp_search_engine = SemanticSearchEngine()
                                
                                # 初始化query_info变量
                                query_info = None
                                
                                # 使用历史缓存数据构建临时索引
                                if temp_search_engine.build_index(emails):
                                    # 使用智能技能匹配搜索
                                    search_results, query_info = temp_search_engine.intelligent_skill_search(query, search_config.get('max_results', 20))
                                    
                                    # 转换为统一格式并应用筛选器
                                    results = []
                                    for result in search_results:
                                        # 应用筛选器
                                        if sender_filter and sender_filter.lower() not in result.sender.lower():
                                            continue
                                        if subject_filter and subject_filter.lower() not in result.subject.lower():
                                            continue
                                        if has_attachment and not result.attachments:
                                            continue
                                        
                                        # 转换为统一格式
                                        results.append({
                                            'uid': result.email_id,
                                            'subject': result.subject,
                                            'sender': result.sender,
                                            'date': result.date,
                                            'folder': result.folder,
                                            'attachments': result.attachments,
                                            'body_text': result.body_text,
                                            'score': result.score
                                        })
                                    
                                    # 显示双向匹配信息
                                    if query_info:
                                        input_type = query_info.get('input_type', 'unknown')
                                        search_direction = query_info.get('search_direction', 'bidirectional')
                                        detected_skills = query_info.get('skills', [])
                                        
                                        if input_type != 'unknown':
                                            st.info(f"🎯 **双向匹配结果** | 输入类型: {input_type} | 搜索方向: {search_direction}")
                                            if detected_skills:
                                                st.info(f"🔧 **检测到的技能**: {', '.join(detected_skills)}")
                                else:
                                    # 如果语义搜索失败，降级到关键词搜索
                                    results = search_emails_in_cache(emails, query)
                                    # 应用筛选器
                                    filtered_results = []
                                    for result in results:
                                        if sender_filter and sender_filter.lower() not in result.get('sender', '').lower():
                                            continue
                                        if subject_filter and subject_filter.lower() not in result.get('subject', '').lower():
                                            continue
                                        if has_attachment and not result.get('attachments'):
                                            continue
                                        filtered_results.append(result)
                                    results = filtered_results
                                    st.warning("⚠️ 智能搜索引擎初始化失败，已降级到关键词搜索")
                            else:
                                results = []
                        else:
                            # 使用技能匹配搜索（最新缓存）
                            search_results, query_info = st.session_state.search_engine.intelligent_skill_search(query, search_config.get('max_results', 20))
                            
                            # 转换为统一格式并应用筛选器
                            results = []
                            for result in search_results:
                                # 应用筛选器
                                if sender_filter and sender_filter.lower() not in result.sender.lower():
                                    continue
                                if subject_filter and subject_filter.lower() not in result.subject.lower():
                                    continue
                                if has_attachment and not result.attachments:
                                    continue
                                
                                results.append({
                                    'uid': result.email_id,
                                    'subject': result.subject,
                                    'sender': result.sender,
                                    'date': result.date,
                                    'preview': result.preview,
                                    'folder': result.folder,
                                    'attachments': result.attachments,
                                    'score': result.score,
                                    'body_text': result.body_text  # 添加完整正文字段
                                })
                            
                            # 显示双向匹配信息
                            if isinstance(query_info, dict) and query_info.get('query_type') != 'general':
                                # 显示输入类型和搜索方向
                                input_type_map = {
                                    'person': '👤 人员信息',
                                    'project': '📋 项目需求',
                                    'mixed': '🔄 混合信息',
                                    'unknown': '❓ 未知类型'
                                }
                                
                                direction_map = {
                                    'person_to_project': '👤 → 📋 人员匹配项目',
                                    'project_to_person': '📋 → 👤 项目匹配人员',
                                    'bidirectional': '🔄 双向匹配'
                                }
                                
                                input_type = query_info.get('input_type', 'unknown')
                                search_direction = query_info.get('search_direction', 'bidirectional')
                                
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.info(f"📝 输入类型：{input_type_map.get(input_type, input_type)}")
                                with col2:
                                    st.info(f"🎯 搜索方向：{direction_map.get(search_direction, search_direction)}")
                                
                                # 显示检测到的技能
                                if query_info.get('skills'):
                                    st.success(f"💡 检测到技能：{', '.join(query_info.get('skills', []))}")
                                
                                # 显示经验年限
                                if query_info.get('experience_years'):
                                    st.success(f"📅 经验年限：{query_info['experience_years']}年")
                    else:
                        # 使用实时搜索
                        results = st.session_state.email_connector.search_emails_realtime(query)
                        # 应用筛选器
                        if sender_filter:
                            results = [r for r in results if sender_filter.lower() in r.sender.lower()]
                        if subject_filter:
                            results = [r for r in results if subject_filter.lower() in r.subject.lower()]
                        if has_attachment:
                            results = [r for r in results if r.has_attachment]
                    
                    search_time = time.time() - start_time
                    
                    # 保存搜索结果到session_state，以便导出时使用
                    st.session_state.last_search_results = results
                    st.session_state.last_search_query = query
                    st.session_state.last_search_time = search_time
                    
                    display_search_results(results, query, search_time)
                    
                    # 保存搜索历史
                    save_search_history(query, len(results))
                    st.session_state.search_history.append({
                        'query': query,
                        'results_count': len(results),
                        'timestamp': datetime.now(),
                        'search_mode': search_mode,
                        'search_time': search_time
                    })
                    
                except Exception as e:
                    st.error(f"❌ 搜索失败: {str(e)}")
                    st.session_state.error_count += 1
                    logger.error(f"Search failed: {str(e)}")
                    if st.session_state.debug_mode:
                        st.code(traceback.format_exc())

    # 页面重新运行（例如点击导出按钮）时，若未点击搜索按钮但已有上次搜索结果，则保持显示
    if not search_button:
        _prev_results = st.session_state.get('last_search_results', [])
        if _prev_results:
            display_search_results(
                _prev_results,
                st.session_state.get('last_search_query', ''),
                st.session_state.get('last_search_time', 0.0)
            )




@performance_monitor
def perform_search(query: str, search_config: Dict, sender_filter: str = "", subject_filter: str = "", has_attachment: bool = False) -> List:
    """执行搜索"""
    search_mode = search_config.get('search_mode', '智能搜索')
    max_results = search_config.get('max_results', 20)
    time_range = search_config.get('time_range', '全部')
    folder_filter = search_config.get('folder_filter', ['收件箱'])
    
    # 执行搜索
    if search_mode == "智能搜索":
        results = st.session_state.search_engine.search(
            query=query,
            top_k=max_results
        )
    elif search_mode == "关键词搜索":
        results = st.session_state.search_engine.keyword_search(
            query=query,
            top_k=max_results
        )
    else:  # 混合搜索
        semantic_results = st.session_state.search_engine.search(
            query=query,
            top_k=max_results//2
        )
        keyword_results = st.session_state.search_engine.keyword_search(
            query=query,
            top_k=max_results//2
        )
        # 合并结果并去重
        seen_ids = set()
        results = []
        for result in semantic_results + keyword_results:
            email_id = result.email_id
            if email_id not in seen_ids:
                seen_ids.add(email_id)
                results.append(result)
    
    # 应用额外筛选
    if sender_filter:
        results = [r for r in results if sender_filter.lower() in r.sender.lower()]
    
    if subject_filter:
        results = [r for r in results if subject_filter.lower() in r.subject.lower()]
    
    if has_attachment:
        results = [r for r in results if len(r.attachments) > 0]
    
    return results

def display_search_results(results: List, query: str, search_time: float = 0):
    """显示搜索结果"""
    # 优先使用session_state中保存的结果，确保页面重新运行时结果不丢失
    display_results = st.session_state.get('last_search_results', results)
    
    if not display_results:
        st.info("🔍 未找到匹配的邮件")
        return
    
    st.success(f"🎯 找到 {len(display_results)} 封相关邮件 (用时 {search_time:.2f}秒)")
    
    # 导出选项 - 使用session_state中保存的结果
    export_results = display_results
    col1, col2 = st.columns([1, 3])
    with col1:
        try:
            excel_data = export_emails_to_excel(export_results)
            st.download_button(
                label="📋 导出Excel",
                data=excel_data,
                file_name=f"search_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        except Exception as e:
            logger.error(f"Excel导出失败: {str(e)}")
            st.error("Excel导出失败")
    
    # 显示结果
    for i, result in enumerate(display_results):
        try:
            with st.container():
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    # 兼容处理：支持SearchResult对象和字典格式
                    if hasattr(result, 'subject'):
                        # SearchResult对象格式
                        subject = result.subject
                        sender = result.sender
                        date = result.date
                        preview = result.preview
                        attachments = result.attachments
                        score = result.score
                    else:
                        # 字典格式
                        if not isinstance(result, dict):
                            logger.error(f"结果 {i} 不是字典类型: {type(result)}, 值: {repr(result)[:200]}")
                            continue
                        subject = result.get('subject', '无主题')
                        sender = result.get('sender', '未知发件人')
                        date = result.get('date', '未知日期')
                        preview = result.get('preview', '无预览')
                        attachments = result.get('attachments', [])
                        score = result.get('score', 0)
                
                # 先清理主题中的HTML标签，避免原始HTML造成删除线
                if isinstance(subject, str):
                    # 统一进行清理，移除HTML/实体/Unicode删除线
                    subject = clean_html_tags(subject)
                # 高亮搜索词（使用HTML <mark>）
                highlighted_subject = highlight_search_terms(subject, query, highlight_tag="<mark>")
                st.markdown(f"**{highlighted_subject}**", unsafe_allow_html=True)
                
                st.text(f"📧 {sender} | 📅 {date}")
                
                # 邮件预览
                if isinstance(preview, str):
                    # 统一进行清理，移除HTML/实体/Unicode删除线
                    preview = clean_html_tags(preview)
                    preview_formatted = preview[:200] + "..." if len(preview) > 200 else preview
                else:
                    # 如果preview是字典，使用format_email_preview函数
                    preview_formatted = format_email_preview(preview, max_length=200)
                highlighted_preview = highlight_search_terms(preview_formatted, query, highlight_tag="<mark>")
                st.markdown(highlighted_preview, unsafe_allow_html=True)
                
                # 附件信息
                if len(attachments) > 0:
                    st.text("📎 包含附件")
            
            with col2:
                # 相关度分数
                st.metric("相关度", f"{score:.0%}")
            
            # 替换分隔线为留白，避免视觉上的“删除线”误解
            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        except Exception as e:
            logger.error(f"显示搜索结果 {i} 时出错: {str(e)}")
            st.error(f"显示结果时出错: {str(e)}")



@error_handler
def email_management_interface():
    """邮件管理界面"""
    st.header("📧 邮件管理")
    
    # 显示缓存信息
    cache_info = get_cache_info()
    if cache_info:
        st.info(f"📁 本地缓存: {cache_info['email_count']} 封邮件 | "
                f"同步时间: {cache_info['sync_time'][:19]} | "
                f"文件大小: {cache_info['file_size'] / 1024 / 1024:.1f} MB")
    else:
        st.warning("📁 暂无本地缓存数据")
    
    # 历史缓存文件管理
    st.markdown("### 📂 历史缓存文件")
    
    # 获取历史缓存文件列表
    historical_files = get_historical_cache_files()
    
    if historical_files:
        col1, col2 = st.columns([3, 1])
        
        with col1:
            # 选择历史缓存文件
            selected_cache_file = st.selectbox(
                "选择历史缓存文件",
                options=["当前缓存 (latest_emails_cache.json)"] + [f"{file['filename']} ({file['readable_time']})" for file in historical_files],
                help="选择要加载的历史缓存文件"
            )
        
        with col2:
            # 加载历史缓存文件
            if st.button("🔄 加载历史缓存", help="加载选定的历史缓存文件"):
                if selected_cache_file.startswith("当前缓存"):
                    # 重新加载当前缓存
                    try:
                        emails_data = load_emails_from_cache()
                        if emails_data:
                            st.session_state.emails_data = emails_data
                            st.session_state.current_cache_source = "latest_emails_cache.json"
                            st.success("✅ 当前缓存已重新加载")
                        else:
                            st.error("❌ 当前缓存文件为空或不存在")
                    except Exception as e:
                        st.error(f"❌ 加载当前缓存失败: {str(e)}")
                else:
                    # 加载历史缓存文件
                    try:
                        # 从选择的文件名中提取实际文件名
                        filename = selected_cache_file.split(" (")[0]
                        emails_data = load_emails_from_specific_cache(filename)
                        if emails_data:
                            st.session_state.emails_data = emails_data
                            st.session_state.current_cache_source = filename
                            st.success(f"✅ 历史缓存文件 '{filename}' 已加载，包含 {len(emails_data)} 封邮件")
                            
                            # 重建搜索索引
                            rebuild_search_index()
                        else:
                            st.error(f"❌ 历史缓存文件 '{filename}' 为空或不存在")
                    except Exception as e:
                        st.error(f"❌ 加载历史缓存文件失败: {str(e)}")
        
        # 显示当前加载的缓存源
        current_source = getattr(st.session_state, 'current_cache_source', 'latest_emails_cache.json')
        st.info(f"📋 当前数据源: {current_source}")
        
        # 显示历史缓存文件列表
        with st.expander("📋 查看所有历史缓存文件"):
            for file_info in historical_files:
                file_size_mb = file_info['file_size'] / (1024 * 1024)  # 转换为MB
                st.text(f"📄 {file_info['filename']} - {file_info['readable_time']} ({file_size_mb:.1f} MB)")
    else:
        st.info("📂 暂无历史缓存文件")
    
    # 同步配置选项
    st.markdown("### ⚙️ 同步配置")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        sync_limit = st.selectbox(
            "每个文件夹邮件数量限制",
            options=[1000, 5000, 10000, 50000, 100000, -1],
            format_func=lambda x: "无限制" if x == -1 else f"{x:,} 封",
            index=5,  # 默认选择无限制
            help="设置每个文件夹最多同步多少封邮件，-1表示无限制"
        )
    
    with col2:
        days_back = st.selectbox(
            "时间范围",
            options=[30, 90, 180, 365, 730, -1],
            format_func=lambda x: "全部邮件" if x == -1 else f"最近 {x} 天",
            index=5,  # 默认选择全部邮件
            help="设置同步多长时间内的邮件，-1表示同步全部邮件"
        )
    
    with col3:
        include_sent = st.checkbox(
            "包含已发送邮件",
            value=True,
            help="是否同步已发送邮件文件夹"
        )
    
    # 操作按钮
    st.markdown("### 🔧 操作")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔄 同步邮件", help="从邮箱服务器同步最新邮件"):
            sync_emails(limit=sync_limit, days_back=days_back, include_sent=include_sent)
    
    with col2:
        if st.button("🔨 重建索引", help="重新构建搜索索引"):
            rebuild_search_index()
    
    with col3:
        if st.button("🧹 清理缓存", help="清理临时文件和缓存"):
            cleanup_cache()
    
    # 邮件统计
    st.markdown("### 📊 邮件统计")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_emails = len(st.session_state.emails_data)
        st.metric("总邮件数", f"{total_emails:,}")
    
    with col2:
        indexed_emails = len(st.session_state.emails_data) if st.session_state.search_engine else 0
        st.metric("已索引", f"{indexed_emails:,}")
    
    with col3:
        # 计算今日新增邮件
        today_emails = 0
        if st.session_state.emails_data:
            today = datetime.now().date()
            today_emails = sum(1 for email in st.session_state.emails_data 
                             if email.date and 
                             isinstance(email.date, datetime) and 
                             email.date.date() == today)
        st.metric("今日新增", f"{today_emails:,}")
    
    with col4:
        # 计算存储使用量（估算）
        storage_usage = 0
        if st.session_state.search_engine and hasattr(st.session_state.search_engine, 'index'):
            # 估算索引大小（每个向量约4KB）
            if st.session_state.search_engine.index:
                vector_count = st.session_state.search_engine.index.ntotal
                storage_usage = round(vector_count * 4 / 1024, 1)  # 转换为MB
        st.metric("存储使用", f"{storage_usage} MB")

@error_handler
@performance_monitor
def sync_emails(limit=10000, days_back=365, include_sent=True):
    """同步邮件"""
    if not st.session_state.email_connector:
        st.error("❌ 请先配置并连接邮箱")
        return
    
    with st.spinner("正在同步邮件..."):
        try:
            # 获取邮件文件夹
            folders = st.session_state.email_connector.get_folders()
            
            # 过滤文件夹（可选择是否包含已发送邮件）
            if not include_sent:
                # 过滤掉常见的已发送邮件文件夹
                sent_folders = ['Sent', 'Sent Items', '已发送', 'Sent Messages', 'Drafts', '草稿箱']
                folders = [f for f in folders if not any(sent in f for sent in sent_folders)]
            
            all_emails = []
            progress_bar = st.progress(0)
            
            st.info(f"📋 同步配置: 每文件夹限制 {'无限制' if limit == -1 else f'{limit:,} 封'}, "
                   f"时间范围 {'全部邮件' if days_back == -1 else f'最近 {days_back} 天'}, "
                   f"文件夹数量 {len(folders)} 个")
            
            for i, folder in enumerate(folders):
                st.text(f"正在同步文件夹: {folder}")
                
                # 设置实际的限制参数
                actual_limit = None if limit == -1 else limit
                actual_days_back = None if days_back == -1 else days_back
                
                emails = st.session_state.email_connector.get_emails(
                    folder=folder,
                    limit=actual_limit,
                    days_back=actual_days_back
                )
                all_emails.extend(emails)
                progress_bar.progress((i + 1) / len(folders))
                
                # 显示当前文件夹的邮件数量
                st.text(f"  └─ 获取到 {len(emails)} 封邮件")
            
            st.session_state.emails_data = all_emails
            st.session_state.last_sync_time = datetime.now()
            
            # 保存邮件数据到本地
            try:
                save_emails_to_cache(all_emails)
                st.info(f"📁 邮件数据已保存到本地缓存")
            except Exception as e:
                logger.warning(f"保存邮件数据到缓存失败: {str(e)}")
            
            st.success(f"✅ 成功同步 {len(all_emails)} 封邮件")
            logger.info(f"Synced {len(all_emails)} emails")
            
            # 自动重建搜索索引
            rebuild_search_index()
            
        except Exception as e:
            st.error(f"❌ 同步失败: {str(e)}")
            st.session_state.error_count += 1
            logger.error(f"Email sync failed: {str(e)}")

@error_handler
@performance_monitor
def rebuild_search_index():
    """重建搜索索引"""
    if not st.session_state.emails_data:
        st.error("❌ 没有邮件数据，请先同步邮件")
        return
    
    with st.spinner("正在重建搜索索引..."):
        try:
            # 初始化搜索引擎
            model_name = config['ai'].get('model_name', 'all-MiniLM-L6-v2')
            search_engine = SemanticSearchEngine(model_name=model_name)
            
            # 构建索引
            search_engine.build_index(st.session_state.emails_data)
            st.session_state.search_engine = search_engine
            
            st.success(f"✅ 搜索索引重建完成，包含 {len(st.session_state.emails_data)} 封邮件")
            logger.info(f"Search index rebuilt with {len(st.session_state.emails_data)} emails")
            
        except Exception as e:
            st.error(f"❌ 索引重建失败: {str(e)}")
            st.session_state.error_count += 1
            logger.error(f"Index rebuild failed: {str(e)}")

@error_handler
@performance_monitor
def rebuild_search_index_async():
    """可选的异步索引：分批构建，基于会话进度控制"""
    if not st.session_state.emails_data:
        st.error("❌ 没有邮件数据，请先同步邮件")
        return

    batch_size = int(config['app'].get('index_batch_size', 500))
    time_budget = int(config['app'].get('index_time_slice_sec', 20))
    start_time = time.time()

    # 初始化或继续进度
    progress = st.session_state.get('index_progress', 0)
    total = len(st.session_state.emails_data)

    if not st.session_state.get('search_engine') or progress == 0:
        model_name = config['ai'].get('model_name', 'all-MiniLM-L6-v2')
        st.session_state.search_engine = SemanticSearchEngine(model_name=model_name)
        # 预加载元数据，保证关键词搜索可用
        try:
            st.session_state.search_engine.build_index([])  # 初始化模型
        except Exception:
            pass
        # 手动准备元数据
        metadata = []
        for email in st.session_state.emails_data:
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
        st.session_state.search_engine.email_metadata = metadata
        st.session_state.index_progress = 0

    engine = st.session_state.search_engine

    # 分批处理直到耗尽时间预算
    processed = progress
    with st.spinner("分批构建索引中..."):
        while processed < total:
            if time.time() - start_time >= time_budget:
                break
            batch_end = min(processed + batch_size, total)
            # 准备文本
            texts = []
            for email in st.session_state.emails_data[processed:batch_end]:
                combined_text = engine._prepare_email_text(email)
                texts.append(combined_text)
            if not texts:
                break
            # 生成向量并添加到索引
            embeddings = engine.model.encode(texts, show_progress_bar=False)
            import faiss
            faiss.normalize_L2(embeddings)
            if engine.index is None:
                dimension = embeddings.shape[1]
                engine.index = faiss.IndexFlatIP(dimension)
            engine.index.add(embeddings.astype('float32'))
            processed = batch_end
            st.session_state.index_progress = processed

    # 完成与提示
    if processed >= total:
        st.success(f"✅ 索引构建完成，共 {total} 封邮件")
    else:
        remaining = total - processed
        percent = processed / total * 100 if total else 0
        st.info(f"⏳ 已处理 {processed}/{total} ({percent:.1f}%)，剩余 {remaining}。再次点击即可继续加速构建。")

def cleanup_cache():
    """清理缓存"""
    try:
        cleanup_temp_files(cache_dir)
        st.success("✅ 缓存清理完成")
        logger.info("Cache cleanup completed")
    except Exception as e:
        st.error(f"❌ 缓存清理失败: {str(e)}")
        logger.error(f"Cache cleanup failed: {str(e)}")

def statistics_interface():
    """统计分析界面"""
    st.header("📊 统计分析")
    
    # 搜索历史
    st.markdown("### 🔍 搜索历史")
    if st.session_state.search_history:
        history_df = pd.DataFrame(st.session_state.search_history)
        st.dataframe(history_df, use_container_width=True)
        
        # 搜索统计
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("总搜索次数", len(st.session_state.search_history))
        with col2:
            avg_results = history_df['results_count'].mean() if not history_df.empty else 0
            st.metric("平均结果数", f"{avg_results:.1f}")
        with col3:
            avg_time = history_df['search_time'].mean() if not history_df.empty else 0
            st.metric("平均搜索时间", f"{avg_time:.2f}s")
    else:
        st.info("暂无搜索历史")
    
    # 性能统计
    st.markdown("### ⚡ 性能统计")
    if st.session_state.performance_stats:
        st.json(st.session_state.performance_stats)
    else:
        st.info("暂无性能数据")
    
    # 使用提示
    st.markdown("### 💡 使用提示")
    st.markdown("""
    **智能搜索技巧：**
    - 使用自然语言描述：如"上周的会议邮件"
    - 结合时间和人员：如"张三昨天发的报告"
    - 指定内容类型：如"包含附件的邮件"
    - 使用具体关键词：如"报价单"、"合同"、"发票"
    
    **性能优化建议：**
    - 定期清理缓存以释放存储空间
    - 限制搜索时间范围以提高搜索速度
    - 使用精确的搜索词以获得更好的结果
    
    **系统限制：**
    - 最大支持30,000封邮件
    - 搜索结果最多显示100条
    - 支持常见邮箱服务商
    - 单次同步限制1000封邮件/文件夹
    """)

def display_welcome_page():
    """显示欢迎页面"""
    st.markdown("""
    ## 👋 欢迎使用智能邮件搜索工具
    
    这是一个基于AI的邮件语义搜索系统，帮助您快速找到需要的邮件。
    
    ### 🚀 开始使用
    1. **配置邮箱**: 在左侧边栏配置您的邮箱信息
    2. **测试连接**: 确保邮箱连接正常
    3. **同步邮件**: 从邮箱服务器同步邮件数据
    4. **开始搜索**: 使用自然语言描述搜索邮件
    
    ### ✨ 主要功能
    - 🧠 **智能语义搜索**: 理解自然语言查询
    - 📱 **关键词搜索**: 精确匹配搜索
    - 🎯 **混合搜索**: 结合语义和关键词搜索
    - 📊 **高级筛选**: 按时间、发件人、附件等筛选
    - 📤 **结果导出**: 支持CSV和Excel格式导出
    - ☁️ **云端存储**: 基于阿里云OSS的数据持久化
    
    ### 🔒 隐私安全
    - 邮件数据仅在本地处理
    - 支持SSL/TLS加密连接
    - 不存储邮箱密码
    """)

def main():
    """主应用函数"""
    # 调试：检查session_state状态
    logger.info(f"主函数开始执行，show_email_details: {st.session_state.get('show_email_details', False)}")
    logger.info(f"主函数开始执行，selected_email存在: {st.session_state.get('selected_email') is not None}")
    
    st.title("📧 智能邮件搜索工具")
    st.markdown("基于AI的语义搜索，快速找到您需要的邮件")
    
    # 侧边栏配置
    with st.sidebar:
        st.header("⚙️ 配置")
        
        # 邮箱配置部分
        st.subheader("📮 邮箱设置")
        email_config = configure_email_settings()
        
        # 搜索配置部分
        st.subheader("🔍 搜索设置")
        search_config = configure_search_settings()
        
        # 系统状态
        st.subheader("📊 系统状态")
        display_system_status()
    
    # 显示导航提示（如果需要）
    if st.session_state.get('show_detailed_guide', False):
        st.markdown("""
        <div style="background-color: #d1ecf1; padding: 15px; border-radius: 8px; border: 2px solid #17a2b8; margin-bottom: 15px; text-align: center; animation: pulse 2s infinite;">
        <h3 style="color: #0c5460; margin: 0 0 10px 0;">👇 请点击下方的 "📧 邮件管理" 标签页 👇</h3>
        <p style="color: #0c5460; margin: 0; font-size: 16px; font-weight: bold;">在那里您可以配置同步选项并开始同步邮件</p>
        </div>
        <style>
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.02); }
            100% { transform: scale(1); }
        }
        </style>
        """, unsafe_allow_html=True)
    

    
    # 主内容区域 - 使用标签页
    tab1, tab2, tab3 = st.tabs(["🔍 邮件搜索", "📧 邮件管理", "📊 统计分析"])
    
    with tab1:
        search_interface(search_config)
    
    with tab2:
        # 如果用户进入邮件管理页面，自动清除导航提示
        if st.session_state.get('show_detailed_guide', False):
            st.session_state.show_detailed_guide = False
        email_management_interface()
    
    with tab3:
        statistics_interface()
    

    
    # 页脚（移除对第三方平台的显式文案）
    # 保留分隔线以视觉收尾
    st.markdown("---")

if __name__ == "__main__":
    main()