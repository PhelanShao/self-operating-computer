import os
import json
import base64
import time
from openai import OpenAI

# 自定义的Qwen API工具类
class QwenAPI:
    def __init__(self, api_key, verbose=False):
        self.api_key = api_key
        self.verbose = verbose
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.prev_operations = []  # 记录之前的操作，用于提供上下文
        
    def analyze_image(self, image_path, prompt):
        """
        使用Qwen-VL模型分析图像并回答问题
        
        Args:
            image_path (str): 图像文件路径
            prompt (str): 提示词/问题
            
        Returns:
            dict: 模型回复
        """
        try:
            # 将图像转换为Base64
            with open(image_path, "rb") as img_file:
                img_base64 = base64.b64encode(img_file.read()).decode("utf-8")
                
            if self.verbose:
                print(f"[QwenAPI] 分析图像: {image_path}")
                print(f"[QwenAPI] 提示词: {prompt}")
                
            # 调用API
            completion = self.client.chat.completions.create(
                model="qwen-vl-plus",  # 或 "qwen-vl-max" 等其他可用模型
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
                    ]
                }]
            )
            
            # 解析回复
            response = completion.choices[0].message.content
            
            if self.verbose:
                print(f"[QwenAPI] 原始回复: {response}")
                
            return response
        
        except Exception as e:
            print(f"[QwenAPI] 错误: {e}")
            return f"分析图像时出错: {str(e)}"
            
    def analyze_for_next_action(self, image_path, objective):
        """
        分析屏幕截图并确定下一步操作
        
        Args:
            image_path (str): 截图文件路径
            objective (str): 目标任务
            
        Returns:
            list: 操作指令列表
        """
        # 构建提示词，强调当前任务和图像内容
        system_prompt = f"""
You are performing a SPECIFIC TASK on a computer. Your role is to analyze the current screenshot and determine the next action to take.

CONTEXT:
- You are looking at a SCREENSHOT of a specific region of the screen, not the whole computer screen
- Your objective is: {objective}
- You can only act on what you see in this screenshot

AVAILABLE ACTIONS:
1. click - Move mouse and click at specific coordinates:
```
[{{ "thought": "I need to click the search box", "operation": "click", "x": "0.5", "y": "0.5" }}]
```

2. write - Type text:
```
[{{ "thought": "I need to type the search query", "operation": "write", "content": "天气" }}]
```

3. press - Press specific keys:
```
[{{ "thought": "I need to press Enter to search", "operation": "press", "keys": ["enter"] }}]
```

4. done - Task completed:
```
[{{ "thought": "I have finished the task", "operation": "done", "summary": "Successfully searched for weather" }}]
```

IMPORTANT NOTES:
- For click operations, x and y must be decimal values between 0 and 1, representing the position relative to the CURRENT SCREENSHOT, not the whole screen
- All coordinates are relative to the screenshot you're seeing, NOT the entire screen
- For keyboard operations, use specific key names like "enter", "tab", "ctrl", "win" (not "windows键" or "e键")
- If you can already see the Baidu search interface, focus on interacting with it directly
- Look carefully at the screenshot before deciding what to do

YOUR TASK PROGRESS:
"""
        
        # 添加之前的操作记录
        progress_info = ""
        if self.prev_operations:
            progress_info = "Previous actions:\n"
            for i, op in enumerate(self.prev_operations):
                progress_info += f"{i+1}. {op.get('operation')}: {self._describe_operation(op)}\n"
        
        # 构建完整提示词
        prompt = f"""
{system_prompt}
{progress_info}

Based on the current screenshot, what is the next step to achieve the objective: {objective}?

Provide your answer as a JSON array with a SINGLE action to take right now. Ensure your JSON is properly formatted without code blocks.
"""
        
        # 增加重试机制
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 调用API
                response = self.analyze_image(image_path, prompt)
                
                # 尝试解析JSON
                if "```json" in response:
                    json_str = response.split("```json")[1].split("```")[0].strip()
                elif "```" in response:
                    json_str = response.split("```")[1].strip()
                else:
                    json_str = response.strip()
                    
                # 解析JSON
                operations = json.loads(json_str)
                
                # 确保是列表
                if not isinstance(operations, list):
                    operations = [operations]
                    
                # 处理可能的格式不匹配
                normalized_operations = []
                for op in operations:
                    normalized_op = {
                        "thought": op.get("thought", "执行操作"),
                        "operation": op.get("operation", "").lower()
                    }
                    
                    # 处理点击操作
                    if normalized_op["operation"] == "click":
                        # 检查各种可能的字段
                        if "x" in op and "y" in op:
                            # 转换为字符串
                            normalized_op["x"] = str(op.get("x"))
                            normalized_op["y"] = str(op.get("y"))
                        elif "target" in op:
                            # 将target转换为text
                            target_text = op.get("target", "")
                            if target_text and isinstance(target_text, str):
                                normalized_op["text"] = target_text
                            else:
                                # 默认中心点
                                normalized_op["x"] = "0.5"  
                                normalized_op["y"] = "0.5"
                        elif "text" in op:
                            normalized_op["text"] = op.get("text")
                        else:
                            # 没有找到任何坐标信息，使用默认值
                            normalized_op["x"] = "0.5"
                            normalized_op["y"] = "0.5"
                            
                    # 处理写入操作
                    elif normalized_op["operation"] == "write":
                        normalized_op["content"] = op.get("content", "")
                        
                    # 处理按键操作
                    elif normalized_op["operation"] == "press":
                        # 确保keys是列表并标准化键名
                        keys = op.get("keys", [])
                        if isinstance(keys, str):
                            keys = [keys]
                            
                        # 标准化键名
                        normalized_keys = []
                        for key in keys:
                            # 将中文键名转换为标准键名
                            if isinstance(key, str):
                                key = key.lower().replace("键", "").strip()
                                if key == "windows" or key == "windows键":
                                    key = "win"
                                elif key == "enter" or key == "return" or key == "回车":
                                    key = "enter"
                                elif key == "control" or key == "ctrl" or key == "控制":
                                    key = "ctrl"
                                elif key == "shift" or key == "上档":
                                    key = "shift"
                                elif key == "alt" or key == "备选":
                                    key = "alt"
                                elif key == "tab" or key == "制表":
                                    key = "tab"
                                elif key == "escape" or key == "退出":
                                    key = "esc"
                                # 单字母键保持不变
                            normalized_keys.append(key)
                            
                        normalized_op["keys"] = normalized_keys
                        
                    # 处理完成操作
                    elif normalized_op["operation"] == "done":
                        normalized_op["summary"] = op.get("summary", "操作完成")
                    
                    normalized_operations.append(normalized_op)
                
                if self.verbose:
                    print(f"[QwenAPI] 解析的操作: {normalized_operations}")
                    
                # 记录这次操作
                self.prev_operations.extend(normalized_operations)
                
                # 如果需要保留最近的N个操作，可以这样做
                if len(self.prev_operations) > 5:
                    self.prev_operations = self.prev_operations[-5:]
                    
                return normalized_operations
                
            except Exception as e:
                print(f"[QwenAPI] 尝试 {attempt+1}/{max_retries} 解析失败: {e}")
                if attempt < max_retries - 1:
                    print(f"[QwenAPI] 等待1秒后重试...")
                    time.sleep(1)
                else:
                    print(f"[QwenAPI] 达到最大重试次数，返回默认操作")
                    print(f"[QwenAPI] 原始回复: {response}")
            
        # 如果所有尝试都失败，返回一个基本操作
        return [{
            "operation": "click", 
            "thought": "尝试点击屏幕中间区域", 
            "x": "0.5", 
            "y": "0.5"
        }]
    
    def _describe_operation(self, op):
        """将操作转换为人类可读的描述"""
        op_type = op.get("operation", "").lower()
        
        if op_type == "click":
            if "text" in op:
                return f"点击文本 '{op.get('text')}'"
            elif "x" in op and "y" in op:
                return f"点击坐标 ({op.get('x')}, {op.get('y')})"
            else:
                return "点击未知位置"
                
        elif op_type == "write":
            return f"输入文本 '{op.get('content', '')}'"
            
        elif op_type == "press":
            keys = op.get("keys", [])
            if isinstance(keys, list):
                return f"按键 {'+'.join(map(str, keys))}"
            else:
                return f"按键 {keys}"
                
        elif op_type == "done":
            return f"完成: {op.get('summary', '操作完成')}"
            
        return "未知操作"

# 测试代码
if __name__ == "__main__":
    # 获取API密钥
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        api_key = input("请输入DASHSCOPE_API_KEY: ")
        
    qwen = QwenAPI(api_key, verbose=True)
    
    # 测试图像分析
    test_image = "screenshots/screenshot_1234567890.png"  # 替换为实际截图
    if os.path.exists(test_image):
        objective = "在百度搜索框中输入'天气'"
        result = qwen.analyze_for_next_action(test_image, objective)
        print("\n最终结果:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"测试图像 {test_image} 不存在")