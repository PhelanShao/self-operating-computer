import sys
import os
import threading
import time
import asyncio
import json
import traceback
import base64
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QComboBox, QLineEdit, QPushButton, QFrame, QGroupBox,
                             QRadioButton, QButtonGroup, QCheckBox, QFileDialog, QMessageBox,
                             QDesktopWidget, QTabWidget, QTextEdit, QSplitter, QScrollArea)
from PyQt5.QtCore import Qt, QRect, QPoint, pyqtSignal, QThread, QTimer, QSize
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QScreen, QTextCursor, QFont

# 如果可用，导入原框架组件
try:
    from operate.config import Config
    from operate.utils.operating_system import OperatingSystem
    from operate.models.apis import get_next_action
    from operate.models.prompts import get_system_prompt
    # 添加特定模型的导入
    import easyocr
    HAS_OPERATE = True
except ImportError:
    print("警告: 无法导入 operate 模块，将使用简化版功能")
    HAS_OPERATE = False

# 导入我们的区域截图功能
from region_screenshot import capture_region, generate_screenshot_name

# 导入边框显示窗口类
from border_frame import BorderFrame

# 导入Qwen API工具类
from qwen_api import QwenAPI

# 全局变量 - 存储边框窗口实例
border_frame = None

# 区域选择器类 (保持不变)
class RegionSelector(QWidget):
    regionSelected = pyqtSignal(QRect)
    selectionCanceled = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # 设置为无边框、始终在顶层的窗口
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        # 设置全屏
        self.showFullScreen()
        # 设置透明背景
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # 初始化选择状态
        self.begin = QPoint()
        self.end = QPoint()
        self.selecting = False
        
        # 添加提示标签
        self.hint_label = QLabel("请拖动鼠标选择区域 (ESC取消)", self)
        self.hint_label.setStyleSheet("background-color: rgba(0, 0, 0, 150); color: white; padding: 10px; border-radius: 5px;")
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setGeometry(0, 0, 300, 40)
        # 将提示标签放在屏幕中央上方
        desktop = QDesktopWidget().screenGeometry()
        self.hint_label.move(desktop.width() // 2 - 150, 50)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 半透明背景
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
        
        if not self.selecting:
            return
            
        # 选择框
        rect = QRect(self.begin, self.end).normalized()
        painter.setPen(QPen(Qt.red, 2))
        painter.drawRect(rect)
        
        # 清除选择区域的半透明背景
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.fillRect(rect, Qt.transparent)
        
        # 显示当前区域尺寸
        size_text = f"{rect.width()}x{rect.height()}"
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        
        # 设置白色文本带黑色轮廓效果
        text_x = min(self.begin.x(), self.end.x()) + 5
        text_y = min(self.begin.y(), self.end.y()) - 10
        if text_y < 15:  # 防止文字超出屏幕上方
            text_y = min(self.begin.y(), self.end.y()) + 20
            
        painter.setPen(QPen(Qt.black, 2))
        painter.drawText(text_x, text_y, size_text)
        painter.setPen(QPen(Qt.white, 1))
        painter.drawText(text_x, text_y, size_text)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.begin = event.pos()
            self.end = event.pos()
            self.selecting = True
            self.update()
            
    def mouseMoveEvent(self, event):
        if self.selecting:
            self.end = event.pos()
            self.update()
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.selecting:
            self.selecting = False
            rect = QRect(self.begin, self.end).normalized()
            
            # 检查选择的区域是否太小
            if rect.width() < 50 or rect.height() < 50:
                QMessageBox.warning(None, "警告", "选择的区域太小，请重新选择更大的区域")
                return
            
            # 发送选择完成信号
            self.regionSelected.emit(rect)
            self.hide()  # 隐藏而不是关闭
            
    def keyPressEvent(self, event):
        # 按ESC取消选择并发出信号
        if event.key() == Qt.Key_Escape:
            self.selectionCanceled.emit()
            self.hide()

# 配置类模拟（如果无法导入）
class DummyConfig:
    def __init__(self):
        self.verbose = False

# 操作系统工具类模拟（如果无法导入）
class DummyOperatingSystem:
    def mouse(self, click_detail):
        print(f"模拟点击: {click_detail}")
        return True
    
    def write(self, content):
        print(f"模拟输入: {content}")
        return True
    
    def press(self, keys):
        print(f"模拟按键: {keys}")
        return True

# 自定义操作系统工具类 - 包装原OperatingSystem，增加区域限制
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
                import pyautogui
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
            import pyautogui
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
                import pyautogui
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

# 预览窗口类 (保持不变)
class PreviewWindow(QMainWindow):
    def __init__(self, region, parent=None):
        super().__init__(parent)
        self.setWindowTitle("区域预览")
        self.region = region
        
        # 创建预览图像
        screenshots_dir = "screenshots"
        if not os.path.exists(screenshots_dir):
            os.makedirs(screenshots_dir)
            
        self.preview_path = os.path.join(screenshots_dir, "preview.png")
        capture_region(self.region, self.preview_path)
        
        # 显示预览
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        layout = QVBoxLayout(self.central_widget)
        
        self.preview_label = QLabel()
        pixmap = QPixmap(self.preview_path)
        self.preview_label.setPixmap(pixmap)
        
        layout.addWidget(self.preview_label)
        
        # 添加按钮
        btn_layout = QHBoxLayout()
        
        self.ok_btn = QPushButton("确认")
        self.ok_btn.clicked.connect(self.accept)
        
        self.cancel_btn = QPushButton("重新选择")
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.ok_btn)
        
        layout.addLayout(btn_layout)
        
        # 调整窗口大小
        self.resize(min(pixmap.width() + 40, 800), min(pixmap.height() + 80, 600))
        
    def accept(self):
        self.close()
        
    def reject(self):
        self.close()
        if self.parent():
            self.parent().select_region()

# 日志记录器类 - 用于传递LLM对话和操作日志
class Logger:
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.log_buffer = []
        
    def log(self, message, category="INFO"):
        """添加日志条目"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{category}] {message}"
        
        # 添加到缓冲区
        self.log_buffer.append(log_entry)
        
        # 更新文本控件
        if self.text_widget:
            self.text_widget.append(log_entry)
            # 滚动到底部
            cursor = self.text_widget.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.text_widget.setTextCursor(cursor)
            
    def log_llm_message(self, role, content):
        """记录LLM对话消息"""
        if role == "system":
            category = "SYSTEM"
        elif role == "user":
            category = "USER"
        elif role == "assistant":
            category = "LLM"
        else:
            category = "DIALOG"
            
        # 如果内容太长，进行截断
        if isinstance(content, str) and len(content) > 500:
            display_content = content[:500] + "... [内容过长已截断]"
        else:
            display_content = str(content)
            
        self.log(f"{role}: {display_content}", category)
        
    def log_operation(self, operation):
        """记录操作详情"""
        op_type = operation.get("operation", "unknown")
        
        if op_type == "click":
            x = operation.get("x", "?")
            y = operation.get("y", "?")
            text = operation.get("text", "")
            details = f"点击坐标: ({x}, {y})" + (f", 文本: '{text}'" if text else "")
        elif op_type == "write":
            content = operation.get("content", "")
            details = f"输入内容: '{content[:50]}'" + ("..." if len(content) > 50 else "")
        elif op_type == "press":
            keys = operation.get("keys", [])
            details = f"按键: {keys}"
        elif op_type == "done":
            summary = operation.get("summary", "")
            details = f"完成, 摘要: {summary}"
        else:
            details = f"未知操作: {operation}"
            
        thought = operation.get("thought", "")
        if thought:
            self.log(f"思考: {thought}", "THOUGHT")
            
        self.log(f"操作: {op_type} - {details}", "ACTION")
        
    def clear(self):
        """清空日志"""
        self.log_buffer = []
        if self.text_widget:
            self.text_widget.clear()

# OpenAI OCR 操作线程
class OpenAIOperateThread(QThread):
    update_status = pyqtSignal(str)
    log_message = pyqtSignal(str, str)  # 消息, 类别
    operation_completed = pyqtSignal()
    
    def __init__(self, objective, region, api_key, logger=None):
        super().__init__()
        self.objective = objective
        self.region = region
        self.api_key = api_key
        self.running = True
        self.paused = False
        self.logger = logger
        self.steps_count = 0  # 步骤计数器
        
        # 检查是否可以使用原框架
        if HAS_OPERATE:
            from operate.config import Config
            from operate.utils.operating_system import OperatingSystem
            self.config = Config()
            self.config.verbose = True
            
            # 设置 API 密钥
            os.environ["OPENAI_API_KEY"] = api_key
            self.config.openai_api_key = api_key
            
            # 初始化 OperatingSystem
            original_os = OperatingSystem()
            # 包装原OperatingSystem，增加区域限制
            self.operating_system = RegionLimitedOperatingSystem(original_os, region, logger)
        else:
            self.operating_system = DummyOperatingSystem()
    
    def run(self):
        if self.logger:
            self.logger.log(f"开始使用OpenAI-OCR模型执行任务: {self.objective}", "INFO")
            
        self.update_status.emit("已启动 OpenAI-OCR 模型")
        
        loop_count = 0
        max_loops = 10
        max_retries = 3
        
        # 初始化消息列表
        from operate.models.prompts import get_system_prompt
        system_prompt = get_system_prompt("gpt-4-with-ocr", self.objective)
        messages = [{"role": "system", "content": system_prompt}]
        
        while self.running and loop_count < max_loops:
            # 检查是否暂停
            while self.paused and self.running:
                time.sleep(0.5)
                
            if not self.running:
                break
                
            try:
                self.steps_count += 1
                status_msg = f"正在分析屏幕 (周期 {loop_count+1}/{max_loops}, 步骤 {self.steps_count})"
                self.update_status.emit(status_msg)
                self.log_message.emit(status_msg, "INFO")
                
                # 创建截图目录
                screenshots_dir = "screenshots"
                os.makedirs(screenshots_dir, exist_ok=True)
                
                # 为该步骤创建唯一文件名
                screenshot_filename = os.path.join(
                    screenshots_dir, 
                    f"step{self.steps_count}_{int(time.time())}.png"
                )
                
                # 捕获选定区域的截图
                capture_region(self.region, screenshot_filename)
                self.log_message.emit(f"已捕获区域截图: {screenshot_filename}", "INFO")
                
                # 使用OpenAI分析截图
                retry_count = 0
                operations = None
                
                while retry_count < max_retries and operations is None:
                    try:
                        self.log_message.emit(f"使用OpenAI-OCR分析截图 (尝试 {retry_count+1}/{max_retries})", "INFO")
                        
                        # 这里调用operate框架的接口
                        from operate.models.apis import call_gpt_4o_with_ocr
                        
                        # 创建临时的用户消息，因为我们只需要模型的分析
                        from operate.models.prompts import get_user_prompt, get_user_first_message_prompt
                        if len(messages) == 1:
                            user_prompt = get_user_first_message_prompt()
                        else:
                            user_prompt = get_user_prompt()
                            
                        # 将截图添加到消息中
                        with open(screenshot_filename, "rb") as img_file:
                            img_base64 = base64.b64encode(img_file.read()).decode("utf-8")
                            
                        vision_message = {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": user_prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"},
                                },
                            ],
                        }
                        
                        # 添加到消息列表
                        temp_messages = messages.copy()
                        temp_messages.append(vision_message)
                        
                        # 直接调用 operate 框架的 API 函数
                        # 创建事件循环来运行异步函数
                        import asyncio
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        operations_result = loop.run_until_complete(call_gpt_4o_with_ocr(temp_messages, self.objective, "gpt-4-with-ocr"))
                        operations = operations_result  # 获取操作列表
                        
                        if not operations or not isinstance(operations, list):
                            raise Exception("OpenAI返回的操作格式不正确")
                            
                    except Exception as e:
                        retry_count += 1
                        error_msg = f"尝试 {retry_count}/{max_retries} 获取操作失败: {str(e)}"
                        self.log_message.emit(error_msg, "ERROR")
                        
                        if retry_count < max_retries:
                            self.log_message.emit("等待3秒后重试...", "INFO")
                            time.sleep(3)
                        else:
                            raise Exception(f"达到最大重试次数({max_retries})，无法获取下一步操作")
                
                # 如果多次尝试后仍未获取到操作，使用备用策略
                if operations is None:
                    operations = [{"operation": "done", "thought": "无法确定下一步操作", "summary": "无法分析屏幕内容，已终止程序"}]
                    self.log_message.emit("无法获取有效操作，使用默认结束操作", "WARNING")
                
                # 记录操作
                self.log_message.emit(f"OpenAI返回的操作: {json.dumps(operations, ensure_ascii=False)}", "INFO")
                
                # 执行操作
                for operation in operations:
                    if not self.running:
                        break
                        
                    while self.paused and self.running:
                        time.sleep(0.5)
                        
                    operate_type = operation.get("operation", "").lower()
                    self.update_status.emit(f"步骤 {self.steps_count}: 执行操作: {operate_type}")
                    
                    # 记录操作详情
                    if self.logger:
                        self.logger.log_operation(operation)
                    
                    # 执行操作
                    if operate_type == "click":
                        # 执行点击操作
                        # 如果text字段存在，但是x和y不存在，则需要使用OCR
                        if "text" in operation and not ("x" in operation and "y" in operation):
                            text_to_click = operation.get("text")
                            self.log_message.emit(f"使用OCR查找文本: {text_to_click}", "INFO")
                            
                            try:
                                # 初始化 EasyOCR Reader
                                reader = easyocr.Reader(["en"])
                                # 读取截图
                                result = reader.readtext(screenshot_filename)
                                
                                # 查找匹配的文本
                                from operate.utils.ocr import get_text_element, get_text_coordinates
                                text_element_index = get_text_element(
                                    result, text_to_click, screenshot_filename
                                )
                                coordinates = get_text_coordinates(
                                    result, text_element_index, screenshot_filename
                                )
                                
                                # 更新坐标
                                operation["x"] = coordinates["x"]
                                operation["y"] = coordinates["y"]
                                
                                self.log_message.emit(f"OCR找到的坐标: x={coordinates['x']}, y={coordinates['y']}", "INFO")
                            except Exception as e:
                                self.log_message.emit(f"OCR查找文本失败: {str(e)}", "ERROR")
                                # 默认使用中心点
                                operation["x"] = "0.5"
                                operation["y"] = "0.5"
                        
                        self.operating_system.mouse(operation)
                        
                        # 操作后等待并截图
                        time.sleep(1.5)
                        after_action_screenshot = os.path.join(
                            screenshots_dir, 
                            f"step{self.steps_count}_after_click_{int(time.time())}.png"
                        )
                        capture_region(self.region, after_action_screenshot)
                        self.log_message.emit(f"点击后截图: {after_action_screenshot}", "INFO")
                        
                    elif operate_type == "write":
                        content = operation.get("content", "")
                        self.operating_system.write(content)
                        
                        # 输入后等待并截图
                        time.sleep(1)
                        after_action_screenshot = os.path.join(
                            screenshots_dir, 
                            f"step{self.steps_count}_after_write_{int(time.time())}.png"
                        )
                        capture_region(self.region, after_action_screenshot)
                        self.log_message.emit(f"输入后截图: {after_action_screenshot}", "INFO")
                        
                    elif operate_type == "press":
                        keys = operation.get("keys", [])
                        self.operating_system.press(keys)
                        
                        # 按键后等待并截图
                        time.sleep(1.5)  # 按键后等待时间稍长，以便页面加载
                        after_action_screenshot = os.path.join(
                            screenshots_dir, 
                            f"step{self.steps_count}_after_press_{int(time.time())}.png"
                        )
                        capture_region(self.region, after_action_screenshot)
                        self.log_message.emit(f"按键后截图: {after_action_screenshot}", "INFO")
                        
                    elif operate_type == "done":
                        complete_msg = f"任务完成: {operation.get('summary')}"
                        self.update_status.emit(complete_msg)
                        self.log_message.emit(complete_msg, "SUCCESS")
                        self.running = False
                        break
                    else:
                        self.log_message.emit(f"未知操作类型: {operate_type}", "WARNING")
                        
                    time.sleep(1)
                    
                loop_count += 1
                
            except Exception as e:
                error_msg = f"步骤 {self.steps_count} 发生错误: {str(e)}"
                self.update_status.emit(error_msg)
                self.log_message.emit(error_msg, "ERROR")
                
                # 记录完整的错误堆栈
                trace_msg = traceback.format_exc()
                self.log_message.emit(trace_msg, "TRACE")
                
                # 捕获错误后的截图
                error_screenshot = os.path.join(
                    "screenshots", 
                    f"step{self.steps_count}_error_{int(time.time())}.png"
                )
                capture_region(self.region, error_screenshot)
                self.log_message.emit(f"错误时的截图: {error_screenshot}", "INFO")
                
                # 打印堆栈到控制台
                traceback.print_exc()
                
                # 暂停3秒后尝试继续
                self.log_message.emit("暂停3秒后继续尝试...", "INFO")
                time.sleep(3)
                
        self.operation_completed.emit()
                
    def pause(self):
        self.paused = True
        self.log_message.emit("操作已暂停", "INFO")
        
    def resume(self):
        self.paused = False
        self.log_message.emit("操作已继续", "INFO")
        
    def stop(self):
        self.running = False
        self.log_message.emit("操作已停止", "INFO")

# Gemini 操作线程
class GeminiOperateThread(QThread):
    update_status = pyqtSignal(str)
    log_message = pyqtSignal(str, str)  # 消息, 类别
    operation_completed = pyqtSignal()
    
    def __init__(self, objective, region, api_key, logger=None):
        super().__init__()
        self.objective = objective
        self.region = region
        self.api_key = api_key
        self.running = True
        self.paused = False
        self.logger = logger
        self.steps_count = 0  # 步骤计数器
        
        # 检查是否可以使用原框架
        if HAS_OPERATE:
            from operate.config import Config
            from operate.utils.operating_system import OperatingSystem
            self.config = Config()
            self.config.verbose = True
            
            # 设置 API 密钥
            os.environ["GOOGLE_API_KEY"] = api_key
            self.config.google_api_key = api_key
            
            # 初始化 OperatingSystem
            original_os = OperatingSystem()
            # 包装原OperatingSystem，增加区域限制
            self.operating_system = RegionLimitedOperatingSystem(original_os, region, logger)
        else:
            self.operating_system = DummyOperatingSystem()
    
    def run(self):
        if self.logger:
            self.logger.log(f"开始使用Gemini模型执行任务: {self.objective}", "INFO")
            
        self.update_status.emit("已启动 Gemini 模型")
        
        loop_count = 0
        max_loops = 10
        max_retries = 3
        
        # 导入Google Gemini
        try:
            import google.generativeai as genai
            # 配置API密钥
            genai.configure(api_key=self.api_key, transport="rest")
        except Exception as e:
            self.log_message.emit(f"初始化Gemini API失败: {str(e)}", "ERROR")
            self.operation_completed.emit()
            return
        
        while self.running and loop_count < max_loops:
            # 检查是否暂停
            while self.paused and self.running:
                time.sleep(0.5)
                
            if not self.running:
                break
                
            try:
                self.steps_count += 1
                status_msg = f"正在分析屏幕 (周期 {loop_count+1}/{max_loops}, 步骤 {self.steps_count})"
                self.update_status.emit(status_msg)
                self.log_message.emit(status_msg, "INFO")
                
                # 创建截图目录
                screenshots_dir = "screenshots"
                os.makedirs(screenshots_dir, exist_ok=True)
                
                # 为该步骤创建唯一文件名
                screenshot_filename = os.path.join(
                    screenshots_dir, 
                    f"step{self.steps_count}_{int(time.time())}.png"
                )
                
                # 捕获选定区域的截图
                capture_region(self.region, screenshot_filename)
                self.log_message.emit(f"已捕获区域截图: {screenshot_filename}", "INFO")
                
                # 使用Gemini分析截图
                retry_count = 0
                operations = None
                
                while retry_count < max_retries and operations is None:
                    try:
                        self.log_message.emit(f"使用Gemini分析截图 (尝试 {retry_count+1}/{max_retries})", "INFO")
                        
                        # 构建系统提示词
                        from operate.models.prompts import get_system_prompt
                        system_prompt = get_system_prompt("gemini-pro-vision", self.objective)
                        
                        # 创建Gemini模型
                        model = genai.GenerativeModel("gemini-pro-vision")
                        
                        # 调用Gemini API分析截图
                        from PIL import Image
                        response = model.generate_content([system_prompt, Image.open(screenshot_filename)])
                        content = response.text
                        
                        # 解析JSON
                        if "```json" in content:
                            json_str = content.split("```json")[1].split("```")[0].strip()
                        elif "```" in content:
                            json_str = content.split("```")[1].strip()
                        else:
                            json_str = content.strip()
                            
                        operations = json.loads(json_str)
                        
                        if not operations or not isinstance(operations, list):
                            raise Exception("Gemini返回的操作格式不正确")
                            
                    except Exception as e:
                        retry_count += 1
                        error_msg = f"尝试 {retry_count}/{max_retries} 获取操作失败: {str(e)}"
                        self.log_message.emit(error_msg, "ERROR")
                        
                        if retry_count < max_retries:
                            self.log_message.emit("等待3秒后重试...", "INFO")
                            time.sleep(3)
                        else:
                            raise Exception(f"达到最大重试次数({max_retries})，无法获取下一步操作")
                
                # 如果多次尝试后仍未获取到操作，使用备用策略
                if operations is None:
                    operations = [{"operation": "done", "thought": "无法确定下一步操作", "summary": "无法分析屏幕内容，已终止程序"}]
                    self.log_message.emit("无法获取有效操作，使用默认结束操作", "WARNING")
                
                # 记录操作
                self.log_message.emit(f"Gemini返回的操作: {json.dumps(operations, ensure_ascii=False)}", "INFO")
                
                # 执行操作
                for operation in operations:
                    if not self.running:
                        break
                        
                    while self.paused and self.running:
                        time.sleep(0.5)
                        
                    operate_type = operation.get("operation", "").lower()
                    self.update_status.emit(f"步骤 {self.steps_count}: 执行操作: {operate_type}")
                    
                    # 记录操作详情
                    if self.logger:
                        self.logger.log_operation(operation)
                    
                    # 执行操作
                    if operate_type == "click":
                        self.operating_system.mouse(operation)
                        
                        # 操作后等待并截图
                        time.sleep(1.5)
                        after_action_screenshot = os.path.join(
                            screenshots_dir, 
                            f"step{self.steps_count}_after_click_{int(time.time())}.png"
                        )
                        capture_region(self.region, after_action_screenshot)
                        self.log_message.emit(f"点击后截图: {after_action_screenshot}", "INFO")
                        
                    elif operate_type == "write":
                        content = operation.get("content", "")
                        self.operating_system.write(content)
                        
                        # 输入后等待并截图
                        time.sleep(1)
                        after_action_screenshot = os.path.join(
                            screenshots_dir, 
                            f"step{self.steps_count}_after_write_{int(time.time())}.png"
                        )
                        capture_region(self.region, after_action_screenshot)
                        self.log_message.emit(f"输入后截图: {after_action_screenshot}", "INFO")
                        
                    elif operate_type == "press":
                        keys = operation.get("keys", [])
                        self.operating_system.press(keys)
                        
                        # 按键后等待并截图
                        time.sleep(1.5)  # 按键后等待时间稍长，以便页面加载
                        after_action_screenshot = os.path.join(
                            screenshots_dir, 
                            f"step{self.steps_count}_after_press_{int(time.time())}.png"
                        )
                        capture_region(self.region, after_action_screenshot)
                        self.log_message.emit(f"按键后截图: {after_action_screenshot}", "INFO")
                        
                    elif operate_type == "done":
                        complete_msg = f"任务完成: {operation.get('summary')}"
                        self.update_status.emit(complete_msg)
                        self.log_message.emit(complete_msg, "SUCCESS")
                        self.running = False
                        break
                    else:
                        self.log_message.emit(f"未知操作类型: {operate_type}", "WARNING")
                        
                    time.sleep(1)
                    
                loop_count += 1
                
            except Exception as e:
                error_msg = f"步骤 {self.steps_count} 发生错误: {str(e)}"
                self.update_status.emit(error_msg)
                self.log_message.emit(error_msg, "ERROR")
                
                # 记录完整的错误堆栈
                trace_msg = traceback.format_exc()
                self.log_message.emit(trace_msg, "TRACE")
                
                # 捕获错误后的截图
                error_screenshot = os.path.join(
                    "screenshots", 
                    f"step{self.steps_count}_error_{int(time.time())}.png"
                )
                capture_region(self.region, error_screenshot)
                self.log_message.emit(f"错误时的截图: {error_screenshot}", "INFO")
                
                # 打印堆栈到控制台
                traceback.print_exc()
                
                # 暂停3秒后尝试继续
                self.log_message.emit("暂停3秒后继续尝试...", "INFO")
                time.sleep(3)
                
        self.operation_completed.emit()
                
    def pause(self):
        self.paused = True
        self.log_message.emit("操作已暂停", "INFO")
        
    def resume(self):
        self.paused = False
        self.log_message.emit("操作已继续", "INFO")
        
    def stop(self):
        self.running = False
        self.log_message.emit("操作已停止", "INFO")

# Claude 操作线程
class ClaudeOperateThread(QThread):
    update_status = pyqtSignal(str)
    log_message = pyqtSignal(str, str)  # 消息, 类别
    operation_completed = pyqtSignal()
    
    def __init__(self, objective, region, api_key, logger=None):
        super().__init__()
        self.objective = objective
        self.region = region
        self.api_key = api_key
        self.running = True
        self.paused = False
        self.logger = logger
        self.steps_count = 0  # 步骤计数器
        
        # 检查是否可以使用原框架
        if HAS_OPERATE:
            from operate.config import Config
            from operate.utils.operating_system import OperatingSystem
            self.config = Config()
            self.config.verbose = True
            
            # 设置 API 密钥
            os.environ["ANTHROPIC_API_KEY"] = api_key
            self.config.anthropic_api_key = api_key
            
            # 初始化 OperatingSystem
            original_os = OperatingSystem()
            # 包装原OperatingSystem，增加区域限制
            self.operating_system = RegionLimitedOperatingSystem(original_os, region, logger)
        else:
            self.operating_system = DummyOperatingSystem()
    
    def run(self):
        if self.logger:
            self.logger.log(f"开始使用Claude-3模型执行任务: {self.objective}", "INFO")
            
        self.update_status.emit("已启动 Claude-3 模型")
        
        loop_count = 0
        max_loops = 10
        max_retries = 3
        
        # 导入Anthropic包
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
        except Exception as e:
            self.log_message.emit(f"初始化Claude API失败: {str(e)}", "ERROR")
            self.operation_completed.emit()
            return
        
        # 初始化消息列表
        from operate.models.prompts import get_system_prompt
        system_prompt = get_system_prompt("claude-3", self.objective)
        messages = [{"role": "system", "content": system_prompt}]
        
        while self.running and loop_count < max_loops:
            # 检查是否暂停
            while self.paused and self.running:
                time.sleep(0.5)
                
            if not self.running:
                break
                
            try:
                self.steps_count += 1
                status_msg = f"正在分析屏幕 (周期 {loop_count+1}/{max_loops}, 步骤 {self.steps_count})"
                self.update_status.emit(status_msg)
                self.log_message.emit(status_msg, "INFO")
                
                # 创建截图目录
                screenshots_dir = "screenshots"
                os.makedirs(screenshots_dir, exist_ok=True)
                
                # 为该步骤创建唯一文件名
                screenshot_filename = os.path.join(
                    screenshots_dir, 
                    f"step{self.steps_count}_{int(time.time())}.png"
                )
                
                # 捕获选定区域的截图
                capture_region(self.region, screenshot_filename)
                self.log_message.emit(f"已捕获区域截图: {screenshot_filename}", "INFO")
                
                # 使用Claude分析截图
                retry_count = 0
                operations = None
                
                while retry_count < max_retries and operations is None:
                    try:
                        self.log_message.emit(f"使用Claude-3分析截图 (尝试 {retry_count+1}/{max_retries})", "INFO")
                        
                        # 创建临时的用户消息，因为我们只需要模型的分析
                        from operate.models.prompts import get_user_prompt, get_user_first_message_prompt
                        if len(messages) == 1:
                            user_prompt = get_user_first_message_prompt()
                        else:
                            user_prompt = get_user_prompt()
                            
                        # 将截图处理成较小的尺寸，因为Claude有5MB限制
                        from PIL import Image
                        with Image.open(screenshot_filename) as img:
                            # 转换RGBA到RGB
                            if img.mode == "RGBA":
                                img = img.convert("RGB")
                                
                            # 保持宽高比例缩小图片
                            width, height = img.size
                            max_dim = 1280
                            if width > max_dim or height > max_dim:
                                if width > height:
                                    new_width = max_dim
                                    new_height = int(height * (max_dim / width))
                                else:
                                    new_height = max_dim
                                    new_width = int(width * (max_dim / height))
                                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                                
                            # 转换到内存缓存
                            buffer = io.BytesIO()
                            img.save(buffer, format="JPEG", quality=80)
                            buffer.seek(0)
                            image_bytes = buffer.getvalue()
                            img_base64 = base64.b64encode(image_bytes).decode("utf-8")
                            
                        # 构建消息，添加提示词和强制JSON输出的要求
                        system_message = messages[0]["content"]
                        user_message = {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/jpeg",
                                        "data": img_base64,
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": user_prompt + "**REMEMBER** Only output json format, do not append any other text.",
                                },
                            ],
                        }
                        
                        # 调用Claude API
                        response = client.messages.create(
                            model="claude-3-opus-20240229",
                            max_tokens=3000,
                            system=system_message,
                            messages=[user_message],
                        )
                        
                        content = response.content[0].text
                        
                        # 清理JSON
                        if "```json" in content:
                            json_str = content.split("```json")[1].split("```")[0].strip()
                        elif "```" in content:
                            json_str = content.split("```")[1].strip()
                        else:
                            json_str = content.strip()
                            
                        operations = json.loads(json_str)
                        
                        if not operations or not isinstance(operations, list):
                            raise Exception("Claude返回的操作格式不正确")
                            
                        # 添加到消息历史
                        messages.append(user_message)
                        messages.append({"role": "assistant", "content": content})
                            
                    except Exception as e:
                        retry_count += 1
                        error_msg = f"尝试 {retry_count}/{max_retries} 获取操作失败: {str(e)}"
                        self.log_message.emit(error_msg, "ERROR")
                        
                        if retry_count < max_retries:
                            self.log_message.emit("等待3秒后重试...", "INFO")
                            time.sleep(3)
                        else:
                            raise Exception(f"达到最大重试次数({max_retries})，无法获取下一步操作")
                
                # 如果多次尝试后仍未获取到操作，使用备用策略
                if operations is None:
                    operations = [{"operation": "done", "thought": "无法确定下一步操作", "summary": "无法分析屏幕内容，已终止程序"}]
                    self.log_message.emit("无法获取有效操作，使用默认结束操作", "WARNING")
                
                # 记录操作
                self.log_message.emit(f"Claude返回的操作: {json.dumps(operations, ensure_ascii=False)}", "INFO")
                
                # 执行操作
                for operation in operations:
                    if not self.running:
                        break
                        
                    while self.paused and self.running:
                        time.sleep(0.5)
                        
                    operate_type = operation.get("operation", "").lower()
                    self.update_status.emit(f"步骤 {self.steps_count}: 执行操作: {operate_type}")
                    
                    # 记录操作详情
                    if self.logger:
                        self.logger.log_operation(operation)
                    
                    # 执行操作
                    if operate_type == "click":
                        # 如果text字段存在，但是x和y不存在，则需要使用OCR
                        if "text" in operation and not ("x" in operation and "y" in operation):
                            text_to_click = operation.get("text")
                            self.log_message.emit(f"使用OCR查找文本: {text_to_click}", "INFO")
                            
                            try:
                                # 初始化 EasyOCR Reader
                                reader = easyocr.Reader(["en"])
                                # 读取截图
                                result = reader.readtext(screenshot_filename)
                                
                                # 查找匹配的文本
                                from operate.utils.ocr import get_text_element, get_text_coordinates
                                text_element_index = get_text_element(
                                    result, text_to_click[:3], screenshot_filename  # Claude的OCR只使用前3个字符
                                )
                                coordinates = get_text_coordinates(
                                    result, text_element_index, screenshot_filename
                                )
                                
                                # 更新坐标
                                operation["x"] = coordinates["x"]
                                operation["y"] = coordinates["y"]
                                
                                self.log_message.emit(f"OCR找到的坐标: x={coordinates['x']}, y={coordinates['y']}", "INFO")
                            except Exception as e:
                                self.log_message.emit(f"OCR查找文本失败: {str(e)}", "ERROR")
                                # 默认使用中心点
                                operation["x"] = "0.5"
                                operation["y"] = "0.5"
                        
                        self.operating_system.mouse(operation)
                        
                        # 操作后等待并截图
                        time.sleep(1.5)
                        after_action_screenshot = os.path.join(
                            screenshots_dir, 
                            f"step{self.steps_count}_after_click_{int(time.time())}.png"
                        )
                        capture_region(self.region, after_action_screenshot)
                        self.log_message.emit(f"点击后截图: {after_action_screenshot}", "INFO")
                        
                    elif operate_type == "write":
                        content = operation.get("content", "")
                        self.operating_system.write(content)
                        
                        # 输入后等待并截图
                        time.sleep(1)
                        after_action_screenshot = os.path.join(
                            screenshots_dir, 
                            f"step{self.steps_count}_after_write_{int(time.time())}.png"
                        )
                        capture_region(self.region, after_action_screenshot)
                        self.log_message.emit(f"输入后截图: {after_action_screenshot}", "INFO")
                        
                    elif operate_type == "press":
                        keys = operation.get("keys", [])
                        self.operating_system.press(keys)
                        
                        # 按键后等待并截图
                        time.sleep(1.5)  # 按键后等待时间稍长，以便页面加载
                        after_action_screenshot = os.path.join(
                            screenshots_dir, 
                            f"step{self.steps_count}_after_press_{int(time.time())}.png"
                        )
                        capture_region(self.region, after_action_screenshot)
                        self.log_message.emit(f"按键后截图: {after_action_screenshot}", "INFO")
                        
                    elif operate_type == "done":
                        complete_msg = f"任务完成: {operation.get('summary')}"
                        self.update_status.emit(complete_msg)
                        self.log_message.emit(complete_msg, "SUCCESS")
                        self.running = False
                        break
                    else:
                        self.log_message.emit(f"未知操作类型: {operate_type}", "WARNING")
                        
                    time.sleep(1)
                    
                loop_count += 1
                
            except Exception as e:
                error_msg = f"步骤 {self.steps_count} 发生错误: {str(e)}"
                self.update_status.emit(error_msg)
                self.log_message.emit(error_msg, "ERROR")
                
                # 记录完整的错误堆栈
                trace_msg = traceback.format_exc()
                self.log_message.emit(trace_msg, "TRACE")
                
                # 捕获错误后的截图
                error_screenshot = os.path.join(
                    "screenshots", 
                    f"step{self.steps_count}_error_{int(time.time())}.png"
                )
                capture_region(self.region, error_screenshot)
                self.log_message.emit(f"错误时的截图: {error_screenshot}", "INFO")
                
                # 打印堆栈到控制台
                traceback.print_exc()
                
                # 暂停3秒后尝试继续
                self.log_message.emit("暂停3秒后继续尝试...", "INFO")
                time.sleep(3)
                
        self.operation_completed.emit()
                
    def pause(self):
        self.paused = True
        self.log_message.emit("操作已暂停", "INFO")
        
    def resume(self):
        self.paused = False
        self.log_message.emit("操作已继续", "INFO")
        
    def stop(self):
        self.running = False
        self.log_message.emit("操作已停止", "INFO")

# Qwen操作线程类
class QwenOperateThread(QThread):
    update_status = pyqtSignal(str)
    log_message = pyqtSignal(str, str)  # 消息, 类别
    operation_completed = pyqtSignal()
    
    def __init__(self, objective, region, api_key, logger=None):
        super().__init__()
        self.objective = objective
        self.region = region
        self.api_key = api_key
        self.running = True
        self.paused = False
        self.logger = logger
        self.steps_count = 0  # 步骤计数器
        
        # 初始化Qwen API
        self.qwen_api = QwenAPI(api_key, verbose=True)
        
        # 检查是否可以使用原框架
        if HAS_OPERATE:
            original_os = OperatingSystem()
            # 包装原OperatingSystem，增加区域限制
            self.operating_system = RegionLimitedOperatingSystem(original_os, region, logger)
        else:
            self.operating_system = DummyOperatingSystem()
        
    def run(self):
        if self.logger:
            self.logger.log(f"开始使用Qwen-VL模型执行任务: {self.objective}", "INFO")
            
        self.update_status.emit("已启动 Qwen-VL 模型")
        
        loop_count = 0
        max_loops = 10
        max_retries = 3
        
        while self.running and loop_count < max_loops:
            # 检查是否暂停
            while self.paused and self.running:
                time.sleep(0.5)
                
            if not self.running:
                break
                
            try:
                self.steps_count += 1
                status_msg = f"正在分析屏幕 (周期 {loop_count+1}/{max_loops}, 步骤 {self.steps_count})"
                self.update_status.emit(status_msg)
                self.log_message.emit(status_msg, "INFO")
                
                # 创建截图目录
                screenshots_dir = "screenshots"
                os.makedirs(screenshots_dir, exist_ok=True)
                
                # 为该步骤创建唯一文件名
                screenshot_filename = os.path.join(
                    screenshots_dir, 
                    f"step{self.steps_count}_{int(time.time())}.png"
                )
                
                # 捕获选定区域的截图
                capture_region(self.region, screenshot_filename)
                self.log_message.emit(f"已捕获区域截图: {screenshot_filename}", "INFO")
                
                # 使用Qwen分析截图
                retry_count = 0
                operations = None
                
                while retry_count < max_retries and operations is None:
                    try:
                        self.log_message.emit(f"使用Qwen-VL分析截图 (尝试 {retry_count+1}/{max_retries})", "INFO")
                        operations = self.qwen_api.analyze_for_next_action(
                            screenshot_filename, 
                            self.objective
                        )
                        
                        if not operations or not isinstance(operations, list):
                            raise Exception("Qwen返回的操作格式不正确")
                            
                    except Exception as e:
                        retry_count += 1
                        error_msg = f"尝试 {retry_count}/{max_retries} 获取操作失败: {str(e)}"
                        self.log_message.emit(error_msg, "ERROR")
                        
                        if retry_count < max_retries:
                            self.log_message.emit("等待3秒后重试...", "INFO")
                            time.sleep(3)
                        else:
                            raise Exception(f"达到最大重试次数({max_retries})，无法获取下一步操作")
                
                # 如果多次尝试后仍未获取到操作，使用备用策略
                if operations is None:
                    operations = [{"operation": "done", "thought": "无法确定下一步操作", "summary": "无法分析屏幕内容，已终止程序"}]
                    self.log_message.emit("无法获取有效操作，使用默认结束操作", "WARNING")
                
                # 记录操作
                self.log_message.emit(f"Qwen返回的操作: {json.dumps(operations, ensure_ascii=False)}", "INFO")
                
                # 执行操作
                for operation in operations:
                    if not self.running:
                        break
                        
                    while self.paused and self.running:
                        time.sleep(0.5)
                        
                    operate_type = operation.get("operation", "").lower()
                    self.update_status.emit(f"步骤 {self.steps_count}: 执行操作: {operate_type}")
                    
                    # 记录操作详情
                    if self.logger:
                        self.logger.log_operation(operation)
                    
                    # 执行操作
                    if operate_type == "click":
                        # 执行点击操作
                        self.operating_system.mouse(operation)
                        
                        # 操作后等待并截图
                        time.sleep(1.5)
                        after_action_screenshot = os.path.join(
                            screenshots_dir, 
                            f"step{self.steps_count}_after_click_{int(time.time())}.png"
                        )
                        capture_region(self.region, after_action_screenshot)
                        self.log_message.emit(f"点击后截图: {after_action_screenshot}", "INFO")
                        
                    elif operate_type == "write":
                        content = operation.get("content", "")
                        self.operating_system.write(content)
                        
                        # 输入后等待并截图
                        time.sleep(1)
                        after_action_screenshot = os.path.join(
                            screenshots_dir, 
                            f"step{self.steps_count}_after_write_{int(time.time())}.png"
                        )
                        capture_region(self.region, after_action_screenshot)
                        self.log_message.emit(f"输入后截图: {after_action_screenshot}", "INFO")
                        
                    elif operate_type == "press":
                        keys = operation.get("keys", [])
                        self.operating_system.press(keys)
                        
                        # 按键后等待并截图
                        time.sleep(1.5)  # 按键后等待时间稍长，以便页面加载
                        after_action_screenshot = os.path.join(
                            screenshots_dir, 
                            f"step{self.steps_count}_after_press_{int(time.time())}.png"
                        )
                        capture_region(self.region, after_action_screenshot)
                        self.log_message.emit(f"按键后截图: {after_action_screenshot}", "INFO")
                        
                    elif operate_type == "done":
                        complete_msg = f"任务完成: {operation.get('summary')}"
                        self.update_status.emit(complete_msg)
                        self.log_message.emit(complete_msg, "SUCCESS")
                        self.running = False
                        break
                    else:
                        self.log_message.emit(f"未知操作类型: {operate_type}", "WARNING")
                        
                    time.sleep(1)
                    
                loop_count += 1
                
            except Exception as e:
                error_msg = f"步骤 {self.steps_count} 发生错误: {str(e)}"
                self.update_status.emit(error_msg)
                self.log_message.emit(error_msg, "ERROR")
                
                # 记录完整的错误堆栈
                trace_msg = traceback.format_exc()
                self.log_message.emit(trace_msg, "TRACE")
                
                # 捕获错误后的截图
                error_screenshot = os.path.join(
                    "screenshots", 
                    f"step{self.steps_count}_error_{int(time.time())}.png"
                )
                capture_region(self.region, error_screenshot)
                self.log_message.emit(f"错误时的截图: {error_screenshot}", "INFO")
                
                # 打印堆栈到控制台
                traceback.print_exc()
                
                # 暂停3秒后尝试继续
                self.log_message.emit("暂停3秒后继续尝试...", "INFO")
                time.sleep(3)
                
        self.operation_completed.emit()
                
    def pause(self):
        self.paused = True
        self.log_message.emit("操作已暂停", "INFO")
        
    def resume(self):
        self.paused = False
        self.log_message.emit("操作已继续", "INFO")
        
    def stop(self):
        self.running = False
        self.log_message.emit("操作已停止", "INFO")

# 主应用类
class RegionOperateApp(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("区域选择自动化操作")
        self.setGeometry(100, 100, 900, 700)
        
        self.selected_region = None
        self.operate_thread = None
        self.selector = None
        self.preview_window = None
        self.border_frame = None
        self.logger = None
        
        self.init_ui()
        
    def init_ui(self):
        # 创建中央部件和主布局
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        main_layout = QVBoxLayout(self.central_widget)
        
        # 创建选项卡控件
        self.tabs = QTabWidget()
        
        # 创建"设置"选项卡
        self.settings_tab = QWidget()
        self.init_settings_tab()
        
        # 创建"日志"选项卡
        self.logs_tab = QWidget()
        self.init_logs_tab()
        
        # 添加选项卡
        self.tabs.addTab(self.settings_tab, "设置")
        self.tabs.addTab(self.logs_tab, "日志")
        
        # 状态栏
        status_layout = QHBoxLayout()
        self.status_label = QLabel("就绪")
        status_layout.addWidget(QLabel("状态:"))
        status_layout.addWidget(self.status_label, 1)  # 1表示伸展因子
        
        # 将选项卡和状态栏添加到主布局
        main_layout.addWidget(self.tabs, 1)  # 1表示伸展因子
        main_layout.addLayout(status_layout)
        
        # 检查框架可用性
        if not HAS_OPERATE:
            self.status_label.setText("警告: operate模块未导入，部分功能可能受限")
            self.status_label.setStyleSheet("color: orange")
            
        # 初始化日志记录器
        self.logger = Logger(self.log_text)
        
    def init_settings_tab(self):
        layout = QVBoxLayout(self.settings_tab)
        
        # 区域选择框
        region_group = QGroupBox("区域选择")
        region_layout = QHBoxLayout(region_group)
        
        self.region_label = QLabel("未选择区域")
        self.select_btn = QPushButton("选择区域")
        self.select_btn.clicked.connect(self.select_region)
        
        self.preview_btn = QPushButton("预览区域")
        self.preview_btn.clicked.connect(self.preview_region)
        self.preview_btn.setEnabled(False)
        
        self.toggle_border_btn = QPushButton("显示/隐藏边框")
        self.toggle_border_btn.clicked.connect(self.toggle_border)
        self.toggle_border_btn.setEnabled(False)
        
        region_layout.addWidget(self.region_label)
        region_layout.addWidget(self.select_btn)
        region_layout.addWidget(self.preview_btn)
        region_layout.addWidget(self.toggle_border_btn)
        
        # 模型选择框
        model_select_group = QGroupBox("模型选择")
        model_select_layout = QVBoxLayout(model_select_group)
        
        self.model_radios = QButtonGroup(self)
        
        self.qwen_radio = QRadioButton("Qwen-VL (阿里云)")
        self.qwen_radio.setChecked(True)  # 默认选中
        self.model_radios.addButton(self.qwen_radio, 1)
        
        self.openai_radio = QRadioButton("OpenAI-OCR (GPT-4o)")
        self.model_radios.addButton(self.openai_radio, 2)
        
        self.gemini_radio = QRadioButton("Gemini (谷歌)")
        self.model_radios.addButton(self.gemini_radio, 3)
        
        self.claude_radio = QRadioButton("Claude-3 (Anthropic)")
        self.model_radios.addButton(self.claude_radio, 4)
        
        model_select_layout.addWidget(self.qwen_radio)
        model_select_layout.addWidget(self.openai_radio)
        model_select_layout.addWidget(self.gemini_radio)
        model_select_layout.addWidget(self.claude_radio)
        
        # 连接模型选择信号
        self.model_radios.buttonClicked.connect(self.on_model_selected)
        
        # API密钥配置框
        api_group = QGroupBox("API密钥配置")
        api_layout = QVBoxLayout(api_group)
        
        # 阿里云API密钥
        qwen_api_layout = QHBoxLayout()
        qwen_api_layout.addWidget(QLabel("阿里云API密钥:"))
        self.qwen_api_key_input = QLineEdit()
        self.qwen_api_key_input.setEchoMode(QLineEdit.Password)
        # 尝试从环境变量获取
        env_qwen_api_key = os.getenv("DASHSCOPE_API_KEY")
        if env_qwen_api_key:
            self.qwen_api_key_input.setText(env_qwen_api_key)
        qwen_api_layout.addWidget(self.qwen_api_key_input)
        api_layout.addLayout(qwen_api_layout)
        
        # OpenAI API密钥
        openai_api_layout = QHBoxLayout()
        openai_api_layout.addWidget(QLabel("OpenAI API密钥:"))
        self.openai_api_key_input = QLineEdit()
        self.openai_api_key_input.setEchoMode(QLineEdit.Password)
        # 尝试从环境变量获取
        env_openai_api_key = os.getenv("OPENAI_API_KEY")
        if env_openai_api_key:
            self.openai_api_key_input.setText(env_openai_api_key)
        openai_api_layout.addWidget(self.openai_api_key_input)
        api_layout.addLayout(openai_api_layout)
        
        # Google API密钥
        google_api_layout = QHBoxLayout()
        google_api_layout.addWidget(QLabel("Google API密钥:"))
        self.google_api_key_input = QLineEdit()
        self.google_api_key_input.setEchoMode(QLineEdit.Password)
        # 尝试从环境变量获取
        env_google_api_key = os.getenv("GOOGLE_API_KEY")
        if env_google_api_key:
            self.google_api_key_input.setText(env_google_api_key)
        google_api_layout.addWidget(self.google_api_key_input)
        api_layout.addLayout(google_api_layout)
        
        # Anthropic API密钥
        anthropic_api_layout = QHBoxLayout()
        anthropic_api_layout.addWidget(QLabel("Anthropic API密钥:"))
        self.anthropic_api_key_input = QLineEdit()
        self.anthropic_api_key_input.setEchoMode(QLineEdit.Password)
        # 尝试从环境变量获取
        env_anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        if env_anthropic_api_key:
            self.anthropic_api_key_input.setText(env_anthropic_api_key)
        anthropic_api_layout.addWidget(self.anthropic_api_key_input)
        api_layout.addLayout(anthropic_api_layout)
        
        # 任务输入框
        task_group = QGroupBox("任务")
        task_layout = QVBoxLayout(task_group)
        
        task_layout.addWidget(QLabel("输入任务目标:"))
        self.task_input = QLineEdit()
        self.task_input.setPlaceholderText("例如: 在百度搜索框中输入'天气'并点击搜索")
        task_layout.addWidget(self.task_input)
        
        # 控制按钮
        btn_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("开始")
        self.start_btn.clicked.connect(self.start_operation)
        
        self.pause_btn = QPushButton("暂停")
        self.pause_btn.clicked.connect(self.pause_operation)
        self.pause_btn.setEnabled(False)
        
        self.resume_btn = QPushButton("继续")
        self.resume_btn.clicked.connect(self.resume_operation)
        self.resume_btn.setEnabled(False)
        
        self.stop_btn = QPushButton("停止")
        self.stop_btn.clicked.connect(self.stop_operation)
        self.stop_btn.setEnabled(False)
        
        self.clear_btn = QPushButton("清空日志")
        self.clear_btn.clicked.connect(self.clear_logs)
        
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.pause_btn)
        btn_layout.addWidget(self.resume_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addWidget(self.clear_btn)
        
        # 将所有组件添加到布局
        layout.addWidget(region_group)
        layout.addWidget(model_select_group)
        layout.addWidget(api_group)
        layout.addWidget(task_group)
        layout.addLayout(btn_layout)
        layout.addStretch(1)  # 添加弹性空间
        
        # 默认显示Qwen API密钥输入
        self.on_model_selected()
        
    def on_model_selected(self):
        """处理模型选择变更"""
        selected_id = self.model_radios.checkedId()
        
        # 根据选择的模型显示/隐藏相应的API密钥输入
        self.qwen_api_key_input.setEnabled(selected_id == 1)
        self.openai_api_key_input.setEnabled(selected_id == 2)
        self.google_api_key_input.setEnabled(selected_id == 3)
        self.anthropic_api_key_input.setEnabled(selected_id == 4)
        
    def init_logs_tab(self):
        layout = QVBoxLayout(self.logs_tab)
        
        # 创建日志文本区域
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QTextEdit.WidgetWidth)
        
        # 设置等宽字体
        font = QFont("Courier New", 10)
        self.log_text.setFont(font)
        
        # 初始日志内容
        self.log_text.append("=== 应用启动 ===")
        self.log_text.append(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.log_text.append("使用多模型视觉语言自动化操作")
        
        layout.addWidget(self.log_text)
        
    def select_region(self):
        """打开区域选择器"""
        # 如果已有边框，先隐藏它
        if self.border_frame and self.border_frame.isVisible():
            self.border_frame.hide()
            
        self.hide()  # 隐藏主窗口
        QTimer.singleShot(500, self._show_selector)  # 使用定时器确保主窗口完全隐藏
        
    def _show_selector(self):
        """显示区域选择器"""
        self.selector = RegionSelector()
        self.selector.regionSelected.connect(self.on_region_selected)
        self.selector.selectionCanceled.connect(self.on_selection_canceled)
        self.selector.show()
        
    def on_region_selected(self, region):
        """区域选择完成的回调"""
        self.selected_region = region
        region_info = f"已选择区域: {region.width()}x{region.height()} (位置: {region.x()},{region.y()})"
        self.region_label.setText(region_info)
        
        if self.logger:
            self.logger.log(f"选择区域: {region_info}", "INFO")
        
        self.preview_btn.setEnabled(True)
        self.toggle_border_btn.setEnabled(True)
        
        # 创建并显示边框
        if self.border_frame:
            self.border_frame.close()
        self.border_frame = BorderFrame(region)
        self.border_frame.show()
        
        # 显示预览窗口
        self.preview_window = PreviewWindow(region, self)
        self.preview_window.show()
        
        # 主窗口在用户关闭预览窗口后显示
        QTimer.singleShot(200, self.show)
        
    def on_selection_canceled(self):
        """区域选择取消的回调"""
        QTimer.singleShot(200, self.show)  # 确保主窗口重新显示
        
    def preview_region(self):
        """预览选定区域"""
        if self.selected_region:
            self.preview_window = PreviewWindow(self.selected_region, self)
            self.preview_window.show()
    
    def toggle_border(self):
        """切换边框显示状态"""
        global border_frame
        
        if not self.selected_region:
            return
            
        if self.border_frame and self.border_frame.isVisible():
            self.border_frame.hide()
            if self.logger:
                self.logger.log("边框已隐藏", "INFO")
        else:
            if not self.border_frame:
                self.border_frame = BorderFrame(self.selected_region)
            else:
                self.border_frame.set_region(self.selected_region)
            self.border_frame.show()
            if self.logger:
                self.logger.log("边框已显示", "INFO")
        
    def start_operation(self):
        """开始自动化操作"""
        if not self.selected_region:
            QMessageBox.warning(self, "警告", "请先选择操作区域")
            return
            
        if not self.task_input.text():
            QMessageBox.warning(self, "警告", "请输入任务目标")
            return
        
        # 根据选择的模型检查对应的API密钥
        selected_id = self.model_radios.checkedId()
        
        if selected_id == 1:  # Qwen-VL
            if not self.qwen_api_key_input.text():
                QMessageBox.warning(self, "警告", "请输入阿里云API密钥")
                return
            api_key = self.qwen_api_key_input.text()
            model_name = "Qwen-VL"
        elif selected_id == 2:  # OpenAI-OCR
            if not self.openai_api_key_input.text():
                QMessageBox.warning(self, "警告", "请输入OpenAI API密钥")
                return
            api_key = self.openai_api_key_input.text()
            model_name = "OpenAI-OCR"
        elif selected_id == 3:  # Gemini
            if not self.google_api_key_input.text():
                QMessageBox.warning(self, "警告", "请输入Google API密钥")
                return
            api_key = self.google_api_key_input.text()
            model_name = "Gemini"
        elif selected_id == 4:  # Claude-3
            if not self.anthropic_api_key_input.text():
                QMessageBox.warning(self, "警告", "请输入Anthropic API密钥")
                return
            api_key = self.anthropic_api_key_input.text()
            model_name = "Claude-3"
        
        # 切换到日志选项卡
        self.tabs.setCurrentIndex(1)  # 索引1是日志选项卡
            
        # 根据选择的模型创建并启动相应的操作线程
        if selected_id == 1:  # Qwen-VL
            self.operate_thread = QwenOperateThread(
                objective=self.task_input.text(),
                region=self.selected_region,
                api_key=api_key,
                logger=self.logger
            )
        elif selected_id == 2:  # OpenAI-OCR
            self.operate_thread = OpenAIOperateThread(
                objective=self.task_input.text(),
                region=self.selected_region,
                api_key=api_key,
                logger=self.logger
            )
        elif selected_id == 3:  # Gemini
            self.operate_thread = GeminiOperateThread(
                objective=self.task_input.text(),
                region=self.selected_region,
                api_key=api_key,
                logger=self.logger
            )
        elif selected_id == 4:  # Claude-3
            self.operate_thread = ClaudeOperateThread(
                objective=self.task_input.text(),
                region=self.selected_region,
                api_key=api_key,
                logger=self.logger
            )
        
        self.operate_thread.update_status.connect(self.update_status)
        self.operate_thread.log_message.connect(self.add_log)
        self.operate_thread.operation_completed.connect(self.on_operation_completed)
        self.operate_thread.start()
        
        # 更新按钮状态
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.resume_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        
        if self.logger:
            self.logger.log(f"开始操作 - 模型: {model_name}, 任务: {self.task_input.text()}", "INFO")
        
        
    def pause_operation(self):
        """暂停操作"""
        if self.operate_thread and self.operate_thread.isRunning():
            self.operate_thread.pause()
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(True)
            self.update_status("已暂停")
            
    def resume_operation(self):
        """继续操作"""
        if self.operate_thread and self.operate_thread.isRunning():
            self.operate_thread.resume()
            self.pause_btn.setEnabled(True)
            self.resume_btn.setEnabled(False)
            self.update_status("继续执行...")
            
    def stop_operation(self):
        """停止操作"""
        if self.operate_thread and self.operate_thread.isRunning():
            self.operate_thread.stop()
            self.update_status("正在停止...")
            
    def on_operation_completed(self):
        """操作完成回调"""
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.update_status("操作已完成")
            
    def update_status(self, message):
        """更新状态标签"""
        self.status_label.setText(message)
        
    def add_log(self, message, category="INFO"):
        """添加日志条目"""
        if self.logger:
            self.logger.log(message, category)
            
    def clear_logs(self):
        """清空日志"""
        reply = QMessageBox.question(
            self, '确认清空', 
            "确定要清空所有日志吗？",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if self.logger:
                self.logger.clear()
                self.logger.log("日志已清空", "INFO")
        
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 关闭边框
        if self.border_frame:
            self.border_frame.close()
            
        # 停止线程
        if self.operate_thread and self.operate_thread.isRunning():
            reply = QMessageBox.question(
                self, '确认退出', 
                "操作正在进行中，确定要退出吗？",
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.operate_thread.stop()
                self.operate_thread.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

# 主函数
def main():
    app = QApplication(sys.argv)
    window = RegionOperateApp()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
