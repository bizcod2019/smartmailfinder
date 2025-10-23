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
    # 从api/index.py导入主函数
    from api.index import main
except ImportError as e:
    st.error(f"模块导入失败: {str(e)}")
    st.error("请确保所有依赖都已正确安装")
    st.stop()

# 调用主函数
if __name__ == "__main__":
    main()
else:
    # 当作为模块导入时也运行主函数
    main()