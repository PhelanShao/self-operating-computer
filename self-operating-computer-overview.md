# Self-Operating Computer 项目结构与功能概述

Self-Operating Computer 是一个框架，使多模态模型能够操作计算机。该框架使用与人类操作员相同的输入和输出，模型查看屏幕并决定一系列鼠标和键盘操作以达成目标。

## 项目目录结构

```
self-operating-computer/
├── .gitignore                  # Git忽略文件
├── CONTRIBUTING.md             # 贡献指南
├── evaluate.py                 # 评估脚本
├── LICENSE                     # 许可证文件
├── README.md                   # 项目说明文档
├── requirements-audio.txt      # 语音功能所需的依赖
├── requirements.txt            # 项目主要依赖
├── setup.py                    # 安装脚本
├── operate/                    # 主要代码目录
│   ├── __init__.py             # 包初始化文件
│   ├── config.py               # 配置管理
│   ├── exceptions.py           # 自定义异常
│   ├── main.py                 # 程序入口点
│   ├── operate.py              # 核心操作逻辑
│   ├── models/                 # 模型相关代码
│   │   ├── __init__.py         # 包初始化文件
│   │   ├── apis.py             # 模型API接口
│   │   ├── prompts.py          # 提示词模板
│   │   └── weights/            # 模型权重
│   │       ├── __init__.py     # 包初始化文件
│   │       └── best.pt         # 最佳模型权重
│   └── utils/                  # 工具函数
│       ├── __init__.py         # 包初始化文件
│       ├── label.py            # 标签处理
│       ├── misc.py             # 杂项工具
│       ├── ocr.py              # 光学字符识别
│       ├── operating_system.py # 操作系统交互
│       ├── screenshot.py       # 屏幕截图
│       └── style.py            # 样式定义
├── readme/                     # 说明文档资源
└── screenshots/                # 截图保存目录
```

## 核心组件功能

### 1. 程序入口与主要流程

#### `operate/main.py`
- 程序的入口点
- 解析命令行参数，包括模型选择、语音模式和详细模式
- 调用`operate.py`中的主函数

#### `operate/operate.py`
- 包含两个主要函数：
  - `main(model, terminal_prompt, voice_mode=False, verbose_mode=False)`: 初始化配置、获取用户目标，进入主循环
  - `operate(operations, model)`: 执行具体操作，如按键、写入文本、鼠标点击等

### 2. 模型与API

#### `operate/models/apis.py`
- 提供与不同AI模型交互的接口
- 支持的模型包括：
  - GPT-4o
  - Claude 3
  - Gemini Pro Vision
  - LLaVa (通过Ollama)
  - Qwen-VL
- 每个模型都有对应的函数来处理截图、OCR识别和操作执行
- 包含错误处理和回退机制

#### `operate/models/prompts.py`
- 定义系统提示和用户提示模板
- 为不同模型提供特定的提示词

### 3. 配置管理

#### `operate/config.py`
- 使用单例模式管理配置
- 处理API密钥的存储和验证
- 初始化各种模型的客户端
- 支持的API包括：
  - OpenAI
  - Google
  - Anthropic
  - Qwen
  - Ollama

### 4. 工具函数

#### `operate/utils/screenshot.py`
- 提供跨平台的屏幕截图功能
- 支持Windows、Linux和macOS
- 包含截图压缩功能

#### `operate/utils/operating_system.py`
- 提供与操作系统交互的功能
- 包含三个主要方法：
  - `write(content)`: 模拟键盘输入文本
  - `press(keys)`: 模拟按下和释放键盘按键
  - `mouse(click_detail)`: 模拟鼠标点击
- 特殊的`click_at_percentage`方法，在点击前会绕着目标位置画一个圆圈

#### `operate/utils/ocr.py`
- 提供光学字符识别功能
- 用于识别屏幕上的文本元素
- 帮助模型定位需要点击的文本

#### `operate/utils/label.py`
- 处理Set-of-Mark (SoM)标签
- 使用YOLOv8模型检测屏幕上的按钮和可交互元素

## 工作流程

1. 用户启动程序并提供目标（通过命令行、直接输入或语音）
2. 系统初始化选定的AI模型
3. 系统捕获屏幕截图
4. 将截图发送给AI模型，并请求下一步操作
5. AI模型分析截图并返回操作指令（点击、输入文本、按键等）
6. 系统执行操作
7. 重复步骤3-6，直到任务完成或达到最大循环次数

## 支持的操作类型

- `press`/`hotkey`: 按下键盘按键
- `write`: 输入文本
- `click`: 点击屏幕上的特定位置
- `done`: 完成任务并提供摘要

## 特殊功能

1. **OCR模式**: 使用光学字符识别来识别屏幕上的文本，使模型能够通过文本内容而不是坐标来指定点击位置
2. **Set-of-Mark (SoM)提示**: 使用YOLOv8模型检测屏幕上的按钮和可交互元素，增强模型的视觉定位能力
3. **语音模式**: 允许用户通过语音输入目标
4. **多模型支持**: 支持多种多模态AI模型，包括商业模型和开源模型

## 使用场景

Self-Operating Computer可以用于多种场景，包括但不限于：

- 自动化日常计算机任务
- 辅助不熟悉计算机操作的用户
- 测试软件界面的可用性
- 创建自动化演示
- 研究AI与计算机交互的能力

通过这个框架，多模态AI模型能够像人类一样操作计算机，打开了人工智能应用的新可能性。