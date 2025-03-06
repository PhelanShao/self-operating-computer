import os
import platform
import subprocess
import pyautogui
from PIL import Image, ImageDraw
import io
import time
import datetime  # 添加datetime模块

# 尝试导入 Xlib（Linux平台使用）
try:
    import Xlib.display
    import Xlib.X
    import Xlib.Xutil
    XLIB_AVAILABLE = True
except ImportError:
    XLIB_AVAILABLE = False

# 尝试导入 ImageGrab（PIL的一部分）
try:
    from PIL import ImageGrab
    IMAGEGRAB_AVAILABLE = True
except ImportError:
    IMAGEGRAB_AVAILABLE = False

def generate_screenshot_name(prefix="screenshot", dir="screenshots"):
    """
    生成带有时间戳的唯一截图文件名
    """
    # 使用datetime模块而不是time来获取带微秒的时间戳
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    return os.path.join(dir, f"{prefix}_{timestamp}.png")

def capture_region(region, file_path=None, step_number=None, verbose=False):
    """
    捕获指定区域的屏幕截图
    
    Args:
        region (QRect 或 tuple): 截图区域 (x, y, width, height)
        file_path (str, optional): 截图保存路径，若为None则自动生成
        step_number (int, optional): 操作步骤编号
        verbose (bool, optional): 是否打印详细信息
    
    Returns:
        str: 保存的截图文件路径
    """
    try:
        # 如果file_path为None，生成唯一文件名
        if file_path is None:
            prefix = f"step{step_number}_" if step_number is not None else ""
            file_path = generate_screenshot_name(prefix=prefix)
        
        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # 如果是 QRect 对象，转换为元组
        if hasattr(region, 'x') and hasattr(region, 'y') and hasattr(region, 'width') and hasattr(region, 'height'):
            x, y, width, height = region.x(), region.y(), region.width(), region.height()
        else:
            # 假设是元组 (x, y, width, height)
            x, y, width, height = region
            
        if verbose:
            print(f"捕获区域: x={x}, y={y}, width={width}, height={height}")
            
        user_platform = platform.system()
        
        if user_platform == "Windows":
            # Windows平台使用PyAutoGUI
            screenshot = pyautogui.screenshot(region=(x, y, width, height))
            screenshot.save(file_path)
            
        elif user_platform == "Linux":
            if XLIB_AVAILABLE and IMAGEGRAB_AVAILABLE:
                # Linux平台使用PIL的ImageGrab
                screenshot = ImageGrab.grab(bbox=(x, y, x+width, y+height))
                screenshot.save(file_path)
            else:
                # 如果没有Xlib和ImageGrab，尝试使用PyAutoGUI
                screenshot = pyautogui.screenshot(region=(x, y, width, height))
                screenshot.save(file_path)
                
        elif user_platform == "Darwin":  # Mac OS
            # 使用screencapture工具捕获区域
            subprocess.run(["screencapture", "-R", f"{x},{y},{width},{height}", file_path])
            
        else:
            print(f"您使用的平台 ({user_platform}) 目前不受支持")
            return None
            
        if verbose:
            print(f"区域截图已保存到: {file_path}")
        return file_path
        
    except Exception as e:
        print(f"区域截图时发生错误: {e}")
        # 如果出错，回退到全屏截图然后裁剪
        try:
            screenshot = pyautogui.screenshot()
            cropped = screenshot.crop((x, y, x+width, y+height))
            cropped.save(file_path)
            print(f"回退方法: 已裁剪全屏截图并保存到 {file_path}")
            return file_path
        except Exception as e2:
            print(f"回退方法也失败: {e2}")
            return None

def capture_full_screen(file_path=None):
    """
    捕获全屏截图
    
    Args:
        file_path (str, optional): 截图保存路径，若为None则自动生成
        
    Returns:
        str: 保存的截图文件路径
    """
    if file_path is None:
        file_path = generate_screenshot_name(prefix="fullscreen")
        
    # 确保目录存在
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    user_platform = platform.system()
    
    try:
        if user_platform == "Windows":
            screenshot = pyautogui.screenshot()
            screenshot.save(file_path)
        elif user_platform == "Linux" and XLIB_AVAILABLE and IMAGEGRAB_AVAILABLE:
            # 使用xlib避免Linux上的scrot依赖
            screen = Xlib.display.Display().screen()
            size = screen.width_in_pixels, screen.height_in_pixels
            screenshot = ImageGrab.grab(bbox=(0, 0, size[0], size[1]))
            screenshot.save(file_path)
        elif user_platform == "Darwin":  # Mac OS
            # 使用screencapture工具捕获带光标的屏幕
            subprocess.run(["screencapture", "-C", file_path])
        else:
            # 通用回退方法
            screenshot = pyautogui.screenshot()
            screenshot.save(file_path)
            
        return file_path
    except Exception as e:
        print(f"全屏截图失败: {e}")
        return None

def compress_screenshot(raw_screenshot_filename, compressed_filename=None, quality=85):
    """
    压缩截图图像以减小大小
    """
    if compressed_filename is None:
        compressed_filename = raw_screenshot_filename.rsplit(".", 1)[0] + "_compressed.jpg"
        
    try:
        with Image.open(raw_screenshot_filename) as img:
            # 检查图像是否具有alpha通道（透明度）
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                # 创建白色背景图像
                background = Image.new('RGB', img.size, (255, 255, 255))
                # 使用alpha通道作为蒙版将图像粘贴到背景上
                background.paste(img, mask=img.split()[3])  # 3是alpha通道
                # 将结果保存为JPEG
                background.save(compressed_filename, 'JPEG', quality=quality)
            else:
                # 如果没有alpha通道，只需转换并保存
                img.convert('RGB').save(compressed_filename, 'JPEG', quality=quality)
                
        return compressed_filename
    except Exception as e:
        print(f"压缩截图失败: {e}")
        return None

# 在截图上标记选定区域
def mark_selected_region(screenshot_path, region, color="red", width=2):
    """
    在截图上标记选定的操作区域
    
    Args:
        screenshot_path (str): 截图文件路径
        region (tuple): 区域 (x, y, width, height)
        color (str): 边框颜色
        width (int): 边框宽度
    """
    try:
        with Image.open(screenshot_path) as img:
            draw = ImageDraw.Draw(img)
            x, y, width, height = region
            draw.rectangle([(x, y), (x + width, y + height)], outline=color, width=width)
            img.save(screenshot_path)
            return True
    except Exception as e:
        print(f"标记区域失败: {e}")
        return False

# 简单截图函数，用于不需要太多选项的场景
def simple_region_screenshot(region, filename=None):
    """
    简单区域截图函数，用于快速调用
    """
    if filename is None:
        filename = f"screenshot_{int(time.time())}.png"
    
    # 确保目录存在
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    # 如果是 QRect 对象，转换为元组
    if hasattr(region, 'x') and hasattr(region, 'y') and hasattr(region, 'width') and hasattr(region, 'height'):
        x, y, width, height = region.x(), region.y(), region.width(), region.height()
    else:
        # 假设是元组 (x, y, width, height)
        x, y, width, height = region
        
    # 截图
    screenshot = pyautogui.screenshot(region=(x, y, width, height))
    screenshot.save(filename)
    print(f"区域截图已保存到: {filename}")
    return filename

# 自测函数
if __name__ == "__main__":
    # 测试区域截图
    import os
    if not os.path.exists("test"):
        os.makedirs("test")
    test_region = (100, 100, 400, 300)  # x, y, width, height
    
    # 测试自动命名
    result1 = capture_region(test_region, verbose=True)
    print(f"自动命名截图路径: {result1}")
    
    # 测试指定步骤编号
    result2 = capture_region(test_region, step_number=1, verbose=True)
    print(f"带步骤编号的截图路径: {result2}")
    
    # 测试标记
    if result2:
        mark_selected_region(result2, test_region)
        print(f"已标记区域在截图中: {result2}")