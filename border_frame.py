from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QPainter, QPen, QColor

class BorderFrame(QWidget):
    """
    用于在选定区域周围显示红色边框的透明窗口
    """
    def __init__(self, region=None):
        super().__init__()
        # 设置为无边框、始终在顶层的窗口
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        # 设置透明背景
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # 存储区域信息
        self.region = region
        
        # 如果有区域信息，立即设置窗口位置和大小
        if region:
            self.setGeometry(region)
        
    def set_region(self, region):
        """设置边框区域并更新窗口"""
        self.region = region
        self.setGeometry(region)
        self.update()
        
    def paintEvent(self, event):
        """绘制边框"""
        if not self.region:
            return
            
        painter = QPainter(self)
        # 消除锯齿
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 创建红色画笔，宽度为3像素
        pen = QPen(QColor(255, 0, 0))
        pen.setWidth(3)
        painter.setPen(pen)
        
        # 绘制矩形边框
        # 注意：坐标是相对于窗口的，所以从(0,0)开始
        painter.drawRect(0, 0, self.width()-1, self.height()-1)