#!/usr/bin/env python3
"""
Vercel部署验证脚本
检查生产环境兼容性和配置正确性
"""

import os
import sys
import json
import importlib
from pathlib import Path

def check_python_version():
    """检查Python版本"""
    print("🐍 检查Python版本...")
    version = sys.version_info
    print(f"   当前版本: {version.major}.{version.minor}.{version.micro}")
    
    if version.major == 3 and version.minor >= 8:
        print("   ✅ Python版本兼容")
        return True
    else:
        print("   ❌ Python版本不兼容，需要Python 3.8+")
        return False

def check_dependencies():
    """检查依赖包"""
    print("\n📦 检查依赖包...")
    
    required_packages = [
        'streamlit',
        'sentence_transformers',
        'faiss-cpu',
        'oss2',
        'pandas',
        'numpy',
        'openpyxl',
        'python-dotenv',
        'tqdm',
        'requests'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            # 特殊处理一些包名映射
            import_name = package
            if package == 'faiss-cpu':
                import_name = 'faiss'
            elif package == 'python-dotenv':
                import_name = 'dotenv'
            
            importlib.import_module(import_name)
            print(f"   ✅ {package}")
        except ImportError:
            print(f"   ❌ {package} - 未安装")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\n❌ 缺少依赖包: {', '.join(missing_packages)}")
        return False
    else:
        print("\n✅ 所有依赖包已安装")
        return True

def check_vercel_config():
    """检查Vercel配置"""
    print("\n⚙️ 检查Vercel配置...")
    
    vercel_config_path = Path("vercel.json")
    if not vercel_config_path.exists():
        print("   ❌ vercel.json 文件不存在")
        return False
    
    try:
        with open(vercel_config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 检查必要的配置项
        required_keys = ['version', 'builds', 'routes']
        for key in required_keys:
            if key not in config:
                print(f"   ❌ 缺少配置项: {key}")
                return False
        
        # 检查构建配置
        builds = config.get('builds', [])
        if not builds:
            print("   ❌ 没有构建配置")
            return False
        
        python_build = None
        for build in builds:
            if build.get('use') == '@vercel/python':
                python_build = build
                break
        
        if not python_build:
            print("   ❌ 没有Python构建配置")
            return False
        
        print("   ✅ Vercel配置正确")
        return True
        
    except json.JSONDecodeError:
        print("   ❌ vercel.json 格式错误")
        return False
    except Exception as e:
        print(f"   ❌ 读取配置文件失败: {str(e)}")
        return False

def check_environment_variables():
    """检查环境变量配置"""
    print("\n🔧 检查环境变量配置...")
    
    env_example_path = Path(".env.example")
    if not env_example_path.exists():
        print("   ❌ .env.example 文件不存在")
        return False
    
    try:
        with open(env_example_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查必要的环境变量
        required_vars = [
            'OSS_ACCESS_KEY_ID',
            'OSS_ACCESS_KEY_SECRET',
            'OSS_BUCKET_NAME',
            'OSS_ENDPOINT',
            'AI_MODEL_NAME',
            'APP_CACHE_DIR'
        ]
        
        missing_vars = []
        for var in required_vars:
            if var not in content:
                missing_vars.append(var)
        
        if missing_vars:
            print(f"   ❌ 缺少环境变量配置: {', '.join(missing_vars)}")
            return False
        else:
            print("   ✅ 环境变量配置完整")
            return True
            
    except Exception as e:
        print(f"   ❌ 读取环境变量配置失败: {str(e)}")
        return False

def check_project_structure():
    """检查项目结构"""
    print("\n📁 检查项目结构...")
    
    required_files = [
        'app.py',
        'requirements.txt',
        'vercel.json',
        '.env.example',
        'README.md'
    ]
    
    required_dirs = [
        'src',
        'src/email_connector.py',
        'src/semantic_search.py',
        'src/oss_storage.py',
        'src/utils.py'
    ]
    
    missing_items = []
    
    # 检查文件
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_items.append(f"文件: {file_path}")
        else:
            print(f"   ✅ {file_path}")
    
    # 检查目录和模块
    for item in required_dirs:
        if not Path(item).exists():
            missing_items.append(f"模块: {item}")
        else:
            print(f"   ✅ {item}")
    
    if missing_items:
        print(f"\n❌ 缺少项目文件/目录:")
        for item in missing_items:
            print(f"   - {item}")
        return False
    else:
        print("\n✅ 项目结构完整")
        return True

def check_app_imports():
    """检查应用导入"""
    print("\n🔍 检查应用导入...")
    
    try:
        # 添加src目录到路径
        sys.path.insert(0, str(Path('src').absolute()))
        
        # 尝试导入主要模块
        modules_to_check = [
            'src.email_connector',
            'src.semantic_search',
            'src.oss_storage',
            'src.utils'
        ]
        
        for module_name in modules_to_check:
            try:
                importlib.import_module(module_name)
                print(f"   ✅ {module_name}")
            except ImportError as e:
                print(f"   ❌ {module_name} - 导入失败: {str(e)}")
                return False
        
        print("\n✅ 所有模块导入成功")
        return True
        
    except Exception as e:
        print(f"\n❌ 模块导入检查失败: {str(e)}")
        return False

def check_streamlit_compatibility():
    """检查Streamlit兼容性"""
    print("\n🌊 检查Streamlit兼容性...")
    
    try:
        import streamlit as st
        print(f"   Streamlit版本: {st.__version__}")
        
        # 检查关键功能
        required_features = [
            'set_page_config',
            'sidebar',
            'tabs',
            'columns',
            'spinner',
            'progress',
            'cache_data'
        ]
        
        for feature in required_features:
            if hasattr(st, feature):
                print(f"   ✅ {feature}")
            else:
                print(f"   ❌ {feature} - 功能不可用")
                return False
        
        print("\n✅ Streamlit兼容性检查通过")
        return True
        
    except Exception as e:
        print(f"\n❌ Streamlit兼容性检查失败: {str(e)}")
        return False

def main():
    """主检查函数"""
    print("🚀 开始Vercel部署验证检查...\n")
    
    checks = [
        ("Python版本", check_python_version),
        ("依赖包", check_dependencies),
        ("Vercel配置", check_vercel_config),
        ("环境变量", check_environment_variables),
        ("项目结构", check_project_structure),
        ("应用导入", check_app_imports),
        ("Streamlit兼容性", check_streamlit_compatibility)
    ]
    
    results = []
    
    for check_name, check_func in checks:
        try:
            result = check_func()
            results.append((check_name, result))
        except Exception as e:
            print(f"\n❌ {check_name}检查失败: {str(e)}")
            results.append((check_name, False))
    
    # 汇总结果
    print("\n" + "="*50)
    print("📊 检查结果汇总:")
    print("="*50)
    
    passed = 0
    total = len(results)
    
    for check_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{check_name:20} {status}")
        if result:
            passed += 1
    
    print(f"\n总计: {passed}/{total} 项检查通过")
    
    if passed == total:
        print("\n🎉 所有检查通过！项目已准备好部署到Vercel")
        return True
    else:
        print(f"\n⚠️ 有 {total - passed} 项检查失败，请修复后重新检查")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)