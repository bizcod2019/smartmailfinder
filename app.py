"""智能邮件搜索工具 - Streamlit Cloud 入口文件
基于Streamlit + 阿里云OSS的邮件语义搜索系统
"""

import streamlit as st
import os
import sys

# 添加项目根目录到Python路径
project_root = os.path.dirname(__file__)
sys.path.insert(0, project_root)

# 导入主应用模块
try:
    # 从api/index.py导入所有内容
    from api.index import *
except ImportError as e:
    st.error(f"模块导入失败: {str(e)}")
    st.error("请确保所有依赖都已正确安装")
    st.stop()

# 主应用已经在api/index.py中定义，这里只需要导入即可
if __name__ == "__main__":
    # 应用已经通过导入api.index自动运行
    pass