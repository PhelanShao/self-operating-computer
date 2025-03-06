import pyautogui
import platform
import time
import math
import traceback
from PyQt5.QtWidgets import QApplication

# 自定义操作系统工具类 - 包装原OperatingSystem，增加区域限制和调试功能
class RegionLimitedOperatingSystem:
    def __init__(self, original_os, region, logger=None):
        self.original_os = original_os
        self.region = region
        self.logger = logger
        self.debug = True
        
    def mouse(self, click_detail):
        """限制鼠标点击在选定区域内"""
        try:
            if self.debug:
                print(f"[DEBUG] 点击操作开始: {click_detail}")
            
            # 首先检查是否有text字段但没有x/y坐标
            if "text" in click_detail and not ("x" in click_detail and "y" in click_detail):
                text = click_detail.get("text")
                if self.debug:
                    print(f"[DEBUG] 根据文本'{text}'执行点击")
                if self.logger:
                    self.logger.log(f"根据文本'{text}'尝试点击", "ACTION")
                
                # 默认点击区域中心
                x_percent = 0.5  
                y_percent = 0.5
                
                # 创建新的点击详情，使用中心坐标
                # 注意：这里使用的百分比坐标是相对于选定区域的
                click_detail = {
                    "x": str(x_percent),
                    "y": str(y_percent)
                }
                
                if self.debug:
                    print(f"[DEBUG] 文本点击转换为区域中心坐标: x={x_percent}, y={y_percent}")
            
            # 确保x和y坐标存在且为有效值
            if "x" not in click_detail or "y" not in click_detail:
                if self.debug:
                    print(f"[DEBUG] 点击操作缺少坐标信息，使用默认中心点")
                if self.logger:
                    self.logger.log(f"点击操作缺少坐标信息，使用默认中心点", "WARNING")
                
                # 默认使用中心点
                click_detail["x"] = "0.5"
                click_detail["y"] = "0.5"
            
            # 确保x和y是字符串
            if not isinstance(click_detail["x"], str):
                click_detail["x"] = str(click_detail["x"])
            if not isinstance(click_detail["y"], str):
                click_detail["y"] = str(click_detail["y"])
            
            # 处理坐标转换 - 这是关键步骤
            try:
                # 1. 获取区域内百分比坐标
                x_percent = float(click_detail.get("x", "0.5"))
                y_percent = float(click_detail.get("y", "0.5"))
                
                if self.debug:
                    print(f"[DEBUG] 原始百分比坐标: x={x_percent}, y={y_percent}")
                
                # 2. 计算区域内的实际像素坐标
                x_pixel_in_region = int(self.region.width() * x_percent)
                y_pixel_in_region = int(self.region.height() * y_percent)
                
                if self.debug:
                    print(f"[DEBUG] 区域内像素坐标: x={x_pixel_in_region}, y={y_pixel_in_region}")
                
                # 3. 添加区域偏移 - 转换为全屏坐标
                x_pixel_screen = x_pixel_in_region + self.region.x()
                y_pixel_screen = y_pixel_in_region + self.region.y()
                
                if self.debug:
                    print(f"[DEBUG] 全屏像素坐标: x={x_pixel_screen}, y={y_pixel_screen}")
                
                # 4. 获取屏幕尺寸
                screen = QApplication.primaryScreen()
                screen_width = screen.size().width()
                screen_height = screen.size().height()
                
                if self.debug:
                    print(f"[DEBUG] 屏幕尺寸: {screen_width}x{screen_height}")
                
                # 5. 确保坐标在屏幕范围内
                x_pixel_screen = max(0, min(x_pixel_screen, screen_width - 1))
                y_pixel_screen = max(0, min(y_pixel_screen, screen_height - 1))
                
                if self.debug:
                    print(f"[DEBUG] 限制后的全屏像素坐标: x={x_pixel_screen}, y={y_pixel_screen}")
                
                # 6. 直接使用PyAutoGUI按像素坐标点击
                # 不再转换为百分比，而是直接使用像素坐标
                pyautogui.moveTo(x_pixel_screen, y_pixel_screen, duration=0.5)
                time.sleep(0.2)  # 稍等一下，确保移动完成
                pyautogui.click()
                
                if self.debug:
                    print(f"[DEBUG] 执行点击: 位置=({x_pixel_screen}, {y_pixel_screen})")
                
                if self.logger:
                    self.logger.log(f"点击执行: 区域内({x_percent:.2f}, {y_percent:.2f}) -> 全屏({x_pixel_screen}, {y_pixel_screen})", "INFO")
                
                return True
                
            except (ValueError, TypeError) as e:
                error_msg = f"坐标转换错误: {e}"
                print(f"[ERROR] {error_msg}")
                if self.logger:
                    self.logger.log(error_msg, "ERROR")
                traceback.print_exc()
                return False
            
        except Exception as e:
            error_msg = f"鼠标点击操作错误: {e}"
            print(f"[ERROR] {error_msg}")
            if self.logger:
                self.logger.log(error_msg, "ERROR")
            traceback.print_exc()
            return False
    
    def write(self, content):
        """执行键盘输入"""
        try:
            if self.debug:
                print(f"[DEBUG] 写入操作: {content}")
            
            # 处理不同类型的输入
            actual_content = content
            if isinstance(content, dict) and "content" in content:
                actual_content = content["content"]
            
            # 确保内容是字符串
            if not isinstance(actual_content, str):
                actual_content = str(actual_content)
            
            if self.debug:
                print(f"[DEBUG] 实际写入内容: '{actual_content}'")
            
            # 使用pyautogui模拟键盘输入
            pyautogui.write(actual_content)
            
            if self.logger:
                self.logger.log(f"输入文本: '{actual_content}'", "INFO")
            
            return True
            
        except Exception as e:
            error_msg = f"键盘输入错误: {e}"
            print(f"[ERROR] {error_msg}")
            if self.logger:
                self.logger.log(error_msg, "ERROR")
            traceback.print_exc()
            return False
    
    def press(self, keys):
        """执行按键操作"""
        try:
            if self.debug:
                print(f"[DEBUG] 按键操作: {keys}")
            
            # 处理不同类型的按键输入
            actual_keys = keys
            if isinstance(keys, dict) and "keys" in keys:
                actual_keys = keys["keys"]
            
            # 标准化键名
            normalized_keys = []
            if isinstance(actual_keys, list):
                for key in actual_keys:
                    # 处理常见的键名替换
                    if isinstance(key, str):
                        key_lower = key.lower().replace("键", "").strip()
                        if key_lower in ["windows", "win"]:
                            normalized_keys.append("win")
                        elif key_lower in ["enter", "回车", "return"]:
                            normalized_keys.append("enter")
                        elif key_lower in ["ctrl", "control", "控制"]:
                            normalized_keys.append("ctrl")
                        elif key_lower in ["alt", "option", "选项"]:
                            normalized_keys.append("alt")
                        elif key_lower in ["shift", "上档"]:
                            normalized_keys.append("shift")
                        elif key_lower in ["esc", "escape", "退出"]:
                            normalized_keys.append("esc")
                        elif key_lower in ["tab", "制表"]:
                            normalized_keys.append("tab")
                        elif key_lower == "e":
                            normalized_keys.append("e")
                        else:
                            normalized_keys.append(key)
                    else:
                        normalized_keys.append(key)
            elif isinstance(actual_keys, str):
                # 单个键作为字符串传入
                normalized_keys = [actual_keys]
            else:
                if self.logger:
                    self.logger.log(f"无法识别的按键格式: {actual_keys}", "ERROR")
                return False
            
            if self.debug:
                print(f"[DEBUG] 标准化后的按键: {normalized_keys}")
            
            # 使用 pyautogui 按下并释放键
            try:
                if len(normalized_keys) == 1:
                    # 单个按键
                    key = normalized_keys[0]
                    pyautogui.press(key)
                    if self.debug:
                        print(f"[DEBUG] 按下单个按键: {key}")
                else:
                    # 组合键
                    for key in normalized_keys:
                        pyautogui.keyDown(key)
                    
                    time.sleep(0.1)  # 短暂暂停
                    
                    for key in reversed(normalized_keys):
                        pyautogui.keyUp(key)
                    
                    if self.debug:
                        print(f"[DEBUG] 按下组合键: {'+'.join(normalized_keys)}")
            
                if self.logger:
                    self.logger.log(f"按键操作: {normalized_keys}", "INFO")
                
                return True
                
            except Exception as e:
                error_msg = f"按键执行错误: {e}"
                print(f"[ERROR] {error_msg}")
                if self.logger:
                    self.logger.log(error_msg, "ERROR")
                traceback.print_exc()
                return False
                
        except Exception as e:
            error_msg = f"按键操作错误: {e}"
            print(f"[ERROR] {error_msg}")
            if self.logger:
                self.logger.log(error_msg, "ERROR")
            traceback.print_exc()
            return False

# 单元测试
if __name__ == "__main__":
    import sys
    from PyQt5.QtCore import QRect
    
    # 创建QApplication实例，否则QScreen无法使用
    app = QApplication(sys.argv)
    
    # 创建一个模拟的OperatingSystem
    class DummyOS:
        def mouse(self, detail):
            print(f"模拟点击: {detail}")
            return True
        
        def write(self, content):
            print(f"模拟写入: {content}")
            return True
        
        def press(self, keys):
            print(f"模拟按键: {keys}")
            return True
    
    # 创建一个模拟的区域
    region = QRect(100, 100, 400, 300)  # x, y, width, height
    
    # 创建RegionLimitedOperatingSystem实例
    region_os = RegionLimitedOperatingSystem(DummyOS(), region)
    
    # 测试点击操作
    print("\n--- 测试点击操作 ---")
    region_os.mouse({"x": "0.5", "y": "0.5"})
    region_os.mouse({"text": "搜索"})
    
    # 测试写入操作
    print("\n--- 测试写入操作 ---")
    region_os.write("测试文本")
    region_os.write({"content": "字典内容"})
    
    # 测试按键操作
    print("\n--- 测试按键操作 ---")
    region_os.press(["enter"])
    region_os.press(["ctrl", "a"])
    region_os.press({"keys": ["windows键", "e键"]})
    
    print("\n测试完成")