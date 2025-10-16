#!/usr/bin/env python3
"""
PythonAnywhere 部署设置脚本
用于在PythonAnywhere平台上配置和运行邮件搜索应用
"""

import os
import sys

# 添加项目路径到Python路径
project_path = '/home/yourusername/email_research'  # 替换为你的用户名
if project_path not in sys.path:
    sys.path.append(project_path)

# 设置环境变量
os.environ['STREAMLIT_SERVER_HEADLESS'] = 'true'
os.environ['STREAMLIT_BROWSER_GATHER_USAGE_STATS'] = 'false'

# WSGI应用配置
def application(environ, start_response):
    """
    WSGI应用入口点
    PythonAnywhere需要这个函数来运行web应用
    """
    # 导入Streamlit应用
    try:
        from api.index import main
        # 启动Streamlit应用
        import subprocess
        import threading
        
        def run_streamlit():
            subprocess.run([
                sys.executable, '-m', 'streamlit', 'run', 
                'api/index.py', 
                '--server.port', '8000',
                '--server.address', '0.0.0.0'
            ])
        
        # 在后台线程中运行Streamlit
        thread = threading.Thread(target=run_streamlit)
        thread.daemon = True
        thread.start()
        
        # 返回简单的响应
        status = '200 OK'
        headers = [('Content-type', 'text/html')]
        start_response(status, headers)
        return [b'<html><body><h1>Email Research App is starting...</h1><p>Please wait a moment and refresh the page.</p></body></html>']
        
    except Exception as e:
        status = '500 Internal Server Error'
        headers = [('Content-type', 'text/html')]
        start_response(status, headers)
        return [f'<html><body><h1>Error</h1><p>{str(e)}</p></body></html>'.encode()]

if __name__ == '__main__':
    # 本地测试
    print("PythonAnywhere setup script")
    print("Project path:", project_path)
    print("Python path:", sys.path)