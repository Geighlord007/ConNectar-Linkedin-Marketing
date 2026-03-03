#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LinkedIn营销系统 - 延迟加载工具

实现组件的延迟加载，优化系统启动性能

主要功能:
1. LazyLoader - 延迟加载器
2. ComponentManager - 组件管理器
3. timing_monitor - 性能监控装饰器
4. lazy_import - 延迟导入装饰器
"""

import time
import logging
from typing import Dict, Any, Optional, Callable, List
from functools import wraps
from pathlib import Path

class LazyLoader:
    """延迟加载器 - 实现组件的按需加载"""
    
    def __init__(self, loader_func: Callable, *args, **kwargs):
        """初始化延迟加载器
        
        Args:
            loader_func: 加载函数
            *args: 位置参数
            **kwargs: 关键字参数
        """
        self.loader_func = loader_func
        self.args = args
        self.kwargs = kwargs
        self._instance = None
        self._loaded = False
        self._loading = False
        self.logger = logging.getLogger(__name__)
    
    def __call__(self):
        """调用加载器，返回实例"""
        if self._loaded:
            return self._instance
        
        if self._loading:
            # 防止循环加载
            self.logger.warning("检测到循环加载，返回None")
            return None
        
        self._loading = True
        try:
            start_time = time.time()
            self._instance = self.loader_func(*self.args, **self.kwargs)
            load_time = time.time() - start_time
            
            if load_time > 0.5:  # 记录耗时较长的加载
                self.logger.info(f"组件加载完成，耗时: {load_time:.2f}秒")
            
            self._loaded = True
            return self._instance
            
        except Exception as e:
            self.logger.error(f"组件加载失败: {e}")
            return None
        finally:
            self._loading = False
    
    def is_loaded(self) -> bool:
        """检查是否已加载"""
        return self._loaded
    
    def get_instance(self):
        """获取实例（如果已加载）"""
        return self._instance if self._loaded else None

def lazy_import(module_name: str, class_name: str = None):
    """延迟导入装饰器
    
    Args:
        module_name: 模块名
        class_name: 类名（可选）
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                if class_name:
                    module = __import__(module_name, fromlist=[class_name])
                    cls = getattr(module, class_name)
                    return cls(*args, **kwargs)
                else:
                    module = __import__(module_name)
                    return func(module, *args, **kwargs)
            except ImportError as e:
                logger = logging.getLogger(__name__)
                logger.error(f"延迟导入失败 {module_name}.{class_name}: {e}")
                return None
        return wrapper
    return decorator

def timing_monitor(func_name: str = None):
    """性能监控装饰器
    
    Args:
        func_name: 函数名称（用于日志）
    """
    def decorator(func):
        name = func_name or func.__name__
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            logger = logging.getLogger(__name__)
            
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                if execution_time > 1.0:  # 只记录耗时超过1秒的操作
                    logger.info(f"⏱️ {name} 执行完成，耗时: {execution_time:.2f}秒")
                elif execution_time > 0.1:  # 记录耗时超过0.1秒的操作
                    logger.debug(f"⏱️ {name} 执行完成，耗时: {execution_time:.2f}秒")
                
                return result
                
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(f"❌ {name} 执行失败，耗时: {execution_time:.2f}秒，错误: {e}")
                raise
                
        return wrapper
    return decorator

class ComponentManager:
    """组件管理器 - 管理系统组件的注册和按需加载"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._components = {}  # 组件注册表
        self._instances = {}   # 已加载的实例
        self._loading_order = []  # 加载顺序
        self._performance_stats = {}  # 性能统计
    
    def register_component(self, name: str, loader_func: Callable, 
                         dependencies: List[str] = None, priority: int = 0):
        """注册组件
        
        Args:
            name: 组件名称
            loader_func: 加载函数
            dependencies: 依赖的其他组件
            priority: 优先级（数字越小优先级越高）
        """
        self._components[name] = {
            'loader': loader_func,
            'dependencies': dependencies or [],
            'priority': priority,
            'loaded': False
        }
        
        # 按优先级排序
        self._loading_order = sorted(
            self._components.keys(),
            key=lambda x: self._components[x]['priority']
        )
        
        self.logger.debug(f"📝 注册组件: {name} (优先级: {priority})")
    
    def get_component(self, name: str, loader_func: Callable = None):
        """获取组件实例（延迟加载）
        
        支持两种方式：
        1) 若已注册，按注册表和依赖顺序加载
        2) 若未注册但提供了 loader_func，则直接用该函数实例化并缓存
        
        Args:
            name: 组件名称
            loader_func: 可选的即时加载函数
            
        Returns:
            组件实例或 None
        """
        # 已加载直接返回
        if name in self._instances:
            return self._instances[name]

        # 按注册表加载
        if name in self._components:
            return self.load_component(name)

        # 未注册：若提供了加载函数，则即时加载并缓存
        if loader_func is not None:
            try:
                self.logger.info(f"⚙️ 未注册组件 {name}，使用提供的加载函数即时加载…")
                instance = loader_func()
                if instance is not None:
                    self._instances[name] = instance
                    # 记录性能统计为0（即时加载无法度量耗时）
                    self._performance_stats[name] = self._performance_stats.get(name, 0.0)
                    self.logger.info(f"✅ 组件 {name} 即时加载完成")
                    return instance
                else:
                    self.logger.error(f"❌ 组件 {name} 加载函数返回None")
                    return None
            except Exception as e:
                self.logger.error(f"❌ 组件 {name} 即时加载失败: {e}")
                return None

        # 未注册且无加载函数
        self.logger.error(f"❌ 未注册的组件: {name} 且未提供加载函数")
        return None
    
    def load_component(self, name: str):
        """加载指定组件
        
        Args:
            name: 组件名称
            
        Returns:
            组件实例
        """
        if name in self._instances:
            return self._instances[name]
        
        if name not in self._components:
            self.logger.error(f"❌ 未注册的组件: {name}")
            return None
        
        component_info = self._components[name]
        
        # 先加载依赖
        for dep in component_info['dependencies']:
            if dep not in self._instances:
                self.logger.debug(f"🔗 加载依赖组件: {dep}")
                self.load_component(dep)
        
        # 加载组件
        start_time = time.time()
        try:
            self.logger.info(f"🚀 正在加载组件: {name}")
            instance = component_info['loader']()
            
            if instance is not None:
                self._instances[name] = instance
                component_info['loaded'] = True
                
                # 记录性能统计
                load_time = time.time() - start_time
                self._performance_stats[name] = load_time
                
                self.logger.info(f"✅ 组件 {name} 加载完成 ({load_time:.2f}s)")
                return instance
            else:
                self.logger.error(f"❌ 组件 {name} 加载返回None")
                return None
            
        except Exception as e:
            load_time = time.time() - start_time
            self.logger.error(f"❌ 组件 {name} 加载失败 ({load_time:.2f}s): {e}")
            return None
    
    def preload_essential_components(self):
        """预加载必要组件"""
        essential = ['contact_manager', 'smart_filter_v3']
        self.logger.info("🔄 预加载必要组件...")
        
        for name in essential:
            if name in self._components:
                self.load_component(name)
    
    def preload_all_components(self):
        """预加载所有组件（调试用）"""
        self.logger.info("🔄 预加载所有组件...")
        
        for name in self._loading_order:
            self.load_component(name)
    
    def get_performance_stats(self) -> Dict[str, float]:
        """获取性能统计"""
        return self._performance_stats.copy()
    
    def get_loaded_components(self) -> List[str]:
        """获取已加载的组件列表"""
        return list(self._instances.keys())
    
    def is_component_loaded(self, name: str) -> bool:
        """检查组件是否已加载"""
        return name in self._instances
    
    def cleanup(self):
        """清理资源"""
        self.logger.info("🧹 清理组件管理器资源...")
        
        for name, instance in self._instances.items():
            if hasattr(instance, 'cleanup'):
                try:
                    instance.cleanup()
                    self.logger.debug(f"✅ 组件 {name} 清理完成")
                except Exception as e:
                    self.logger.error(f"❌ 清理组件 {name} 时出错: {e}")
        
        self._instances.clear()
        self._performance_stats.clear()
        self.logger.info("🧹 组件管理器清理完成")
    
    def get_status_report(self) -> Dict[str, Any]:
        """获取状态报告"""
        return {
            'registered_components': len(self._components),
            'loaded_components': len(self._instances),
            'loading_order': self._loading_order,
            'performance_stats': self._performance_stats,
            'loaded_list': list(self._instances.keys())
        }

# 全局实例
component_manager = ComponentManager()

# 便捷函数
def register_component(name: str, loader_func: Callable, 
                      dependencies: List[str] = None, priority: int = 0):
    """注册组件的便捷函数"""
    component_manager.register_component(name, loader_func, dependencies, priority)

def get_component(name: str, loader_func: Callable = None):
    """获取组件的便捷函数（支持可选加载函数）"""
    return component_manager.get_component(name, loader_func)

def cleanup_components():
    """清理组件的便捷函数"""
    component_manager.cleanup()