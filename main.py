#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LinkedIn营销自动化系统 - 主程序入口
LinkedIn Marketing Automation System - Main Entry Point

使用方法:
1. 直接运行: python main.py
2. 快速启动: python main.py --quick-start
3. 指定项目目录: python main.py --project-root /path/to/project

Usage:
1. Direct run: python main.py
2. Quick start: python main.py --quick-start
3. Specify project root: python main.py --project-root /path/to/project
"""

import os
import sys
import argparse
from pathlib import Path

# 确保项目根目录在Python路径中
project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))

# 加载 .env 文件中的环境变量（API keys 等）
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    pass

try:
    from src.cli import LinkedInMarketingCLI, main as cli_main
    from src.main_controller import quick_start
except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    print("💡 请确保所有依赖已正确安装")
    print("💡 运行: pip install -r requirements.txt")
    sys.exit(1)

def print_welcome():
    """打印欢迎信息"""
    welcome_text = f"""
🎯 LinkedIn营销自动化系统
📁 项目目录: {project_root}

🚀 系统功能:
  • 🔍 多关键词智能搜索
  • 📊 联系人数据管理
  • 🎯 AI智能筛选
  • 📤 自动化营销
  • 📧 邮件批量发送

💡 使用提示:
  1. 确保Chrome浏览器已启动调试模式
  2. 请先登录LinkedIn账户
  3. 遵守LinkedIn使用条款

⚡ 快速开始:
  输入 'help' 查看所有命令
  输入 'init' 初始化系统
  输入 'start' 启动浏览器会话
    """
    print(welcome_text)

def check_dependencies():
    """检查依赖"""
    required_modules = [
        'selenium',
        'sqlite3',
        'requests'
    ]
    
    missing_modules = []
    
    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            missing_modules.append(module)
    
    if missing_modules:
        print(f"❌ 缺少依赖模块: {', '.join(missing_modules)}")
        print("💡 请运行: pip install -r requirements.txt")
        return False
    
    return True

def check_project_structure():
    """检查项目结构"""
    required_dirs = [
        'config',
        'data',
        'data/raw',
        'data/processed',
        'data/exports',
        'src'
    ]
    
    missing_dirs = []
    
    for dir_path in required_dirs:
        full_path = project_root / dir_path
        if not full_path.exists():
            missing_dirs.append(dir_path)
    
    if missing_dirs:
        print(f"⚠️ 缺少目录: {', '.join(missing_dirs)}")
        print("🔧 正在创建缺失目录...")
        
        for dir_path in missing_dirs:
            full_path = project_root / dir_path
            full_path.mkdir(parents=True, exist_ok=True)
            print(f"✅ 创建目录: {dir_path}")
    
    return True

def check_config_files():
    """检查配置文件"""
    config_dir = project_root / 'config'
    required_configs = [
        'settings.json',
        'keywords.json',
        'email_templates.json'
    ]
    
    missing_configs = []
    
    for config_file in required_configs:
        config_path = config_dir / config_file
        if not config_path.exists():
            missing_configs.append(config_file)
    
    if missing_configs:
        print(f"⚠️ 缺少配置文件: {', '.join(missing_configs)}")
        print("💡 请检查config目录中的配置文件")
        return False
    
    return True

def run_system_check():
    """运行系统检查"""
    print("🔍 正在进行系统检查...")
    
    checks = [
        ("依赖模块", check_dependencies),
        ("项目结构", check_project_structure),
        ("配置文件", check_config_files)
    ]
    
    all_passed = True
    
    for check_name, check_func in checks:
        print(f"\n📋 检查{check_name}...")
        if check_func():
            print(f"✅ {check_name}检查通过")
        else:
            print(f"❌ {check_name}检查失败")
            all_passed = False
    
    if all_passed:
        print("\n🎉 系统检查全部通过，可以开始使用!")
    else:
        print("\n⚠️ 系统检查发现问题，请先解决后再使用")
    
    return all_passed

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='LinkedIn营销自动化系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python main.py                    # 标准启动
  python main.py --quick-start      # 快速启动
  python main.py --check-only       # 仅进行系统检查
  python main.py --no-check         # 跳过系统检查
        """
    )
    
    parser.add_argument(
        '--quick-start', 
        action='store_true', 
        help='快速启动系统（自动初始化并启动浏览器）'
    )
    
    parser.add_argument(
        '--project-root', 
        type=str, 
        help='指定项目根目录'
    )
    
    parser.add_argument(
        '--check-only', 
        action='store_true', 
        help='仅进行系统检查，不启动系统'
    )
    
    parser.add_argument(
        '--no-check', 
        action='store_true', 
        help='跳过系统检查，直接启动'
    )
    
    args = parser.parse_args()
    
    # 设置项目根目录
    if args.project_root:
        global project_root
        project_root = Path(args.project_root).absolute()
        sys.path.insert(0, str(project_root))
    
    # 打印欢迎信息
    print_welcome()
    
    # 系统检查
    if not args.no_check:
        if not run_system_check():
            if not args.check_only:
                print("\n❓ 是否继续启动系统? (y/N): ", end="")
                if input().strip().lower() != 'y':
                    print("👋 系统启动已取消")
                    return
    
    # 如果只是检查，则退出
    if args.check_only:
        return
    
    try:
        # 启动CLI
        if args.quick_start:
            print("\n🚀 快速启动模式...")
            # 设置快速启动参数
            sys.argv = ['main.py', '--quick-start']
        
        # 运行CLI主程序
        cli_main()
        
    except KeyboardInterrupt:
        print("\n\n👋 检测到中断信号，正在退出...")
    except Exception as e:
        print(f"\n❌ 系统运行出错: {e}")
        print("💡 请检查错误信息并重试")
    finally:
        print("\n👋 感谢使用LinkedIn营销自动化系统!")

if __name__ == '__main__':
    main()