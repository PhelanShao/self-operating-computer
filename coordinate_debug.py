import sys
import pyautogui
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QMainWindow
from PyQt5.QtCore import Qt, QRect, QTimer

class RegionTester(QMainWindow):
    """坐标转换测试工具 - 用于验证区域内坐标与全屏坐标的转换"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("区域坐标测试工具")
        self.setGeometry(100, 100, 600, 400)
        
        self.region = QRect(200, 200, 400, 300)  # 默认区域
        self.selected_region = None
        
        self.init_ui()
        
        # 启动定时器每秒显示鼠标位置
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_mouse_pos)
        self.timer.start(100)  # 每100毫秒更新一次
        
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        
        # 区域信息显示
        self.region_label = QLabel(f"测试区域: x={self.region.x()}, y={self.region.y()}, w={self.region.width()}, h={self.region.height()}")
        layout.addWidget(self.region_label)
        
        # 鼠标位置显示
        self.mouse_screen_label = QLabel("全屏鼠标: ")
        layout.addWidget(self.mouse_screen_label)
        
        self.mouse_region_label = QLabel("区域内鼠标: ")
        layout.addWidget(self.mouse_region_label)
        
        self.mouse_percent_label = QLabel("百分比坐标: ")
        layout.addWidget(self.mouse_percent_label)
        
        # 测试按钮
        self.test_center_btn = QPushButton("测试区域中央点击")
        self.test_center_btn.clicked.connect(self.test_center_click)
        layout.addWidget(self.test_center_btn)
        
        self.test_tl_btn = QPushButton("测试区域左上角点击")
        self.test_tl_btn.clicked.connect(self.test_tl_click)
        layout.addWidget(self.test_tl_btn)
        
        self.test_br_btn = QPushButton("测试区域右下角点击")
        self.test_br_btn.clicked.connect(self.test_br_click)
        layout.addWidget(self.test_br_btn)
        
        self.test_custom_btn = QPushButton("测试自定义坐标点击 (0.75, 0.25)")
        self.test_custom_btn.clicked.connect(self.test_custom_click)
        layout.addWidget(self.test_custom_btn)
        
        # 帮助文本
        help_text = QLabel("""
测试说明:
1. 此工具帮助理解和验证区域坐标转换逻辑
2. 移动鼠标观察屏幕、区域和百分比坐标关系
3. 点击按钮测试不同位置的点击行为
        """)
        layout.addWidget(help_text)
    
    def update_mouse_pos(self):
        """更新鼠标位置信息"""
        # 获取鼠标全屏位置
        screen_pos = pyautogui.position()
        self.mouse_screen_label.setText(f"全屏鼠标: x={screen_pos.x}, y={screen_pos.y}")
        
        # 计算鼠标在区域内的位置
        if (self.region.x() <= screen_pos.x <= self.region.x() + self.region.width() and 
            self.region.y() <= screen_pos.y <= self.region.y() + self.region.height()):
            
            region_x = screen_pos.x - self.region.x()
            region_y = screen_pos.y - self.region.y()
            self.mouse_region_label.setText(f"区域内鼠标: x={region_x}, y={region_y}")
            
            # 计算百分比坐标
            percent_x = region_x / self.region.width()
            percent_y = region_y / self.region.height()
            self.mouse_percent_label.setText(f"百分比坐标: x={percent_x:.3f}, y={percent_y:.3f}")
        else:
            self.mouse_region_label.setText("区域内鼠标: 鼠标不在区域内")
            self.mouse_percent_label.setText("百分比坐标: N/A")
    
    def test_center_click(self):
        """测试点击区域中心"""
        # 计算区域中心点
        center_x = self.region.x() + self.region.width() / 2
        center_y = self.region.y() + self.region.height() / 2
        
        print(f"点击区域中心点: 全屏坐标=({center_x}, {center_y}), 百分比=(0.5, 0.5)")
        
        # 执行点击
        pyautogui.moveTo(center_x, center_y, duration=0.5)
        pyautogui.click()
    
    def test_tl_click(self):
        """测试点击区域左上角"""
        tl_x = self.region.x()
        tl_y = self.region.y()
        
        print(f"点击区域左上角: 全屏坐标=({tl_x}, {tl_y}), 百分比=(0, 0)")
        
        # 执行点击
        pyautogui.moveTo(tl_x, tl_y, duration=0.5)
        pyautogui.click()
    
    def test_br_click(self):
        """测试点击区域右下角"""
        br_x = self.region.x() + self.region.width()
        br_y = self.region.y() + self.region.height()
        
        print(f"点击区域右下角: 全屏坐标=({br_x}, {br_y}), 百分比=(1, 1)")
        
        # 执行点击
        pyautogui.moveTo(br_x, br_y, duration=0.5)
        pyautogui.click()
    
    def test_custom_click(self):
        """测试点击自定义位置 (0.75, 0.25)"""
        # 计算相对区域的坐标
        custom_x = self.region.x() + self.region.width() * 0.75
        custom_y = self.region.y() + self.region.height() * 0.25
        
        print(f"点击自定义位置: 全屏坐标=({custom_x}, {custom_y}), 百分比=(0.75, 0.25)")
        
        # 执行点击
        pyautogui.moveTo(custom_x, custom_y, duration=0.5)
        pyautogui.click()

# 主函数
def main():
    app = QApplication(sys.argv)
    window = RegionTester()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()