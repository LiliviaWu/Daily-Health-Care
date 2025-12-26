import json
import random
import logging
import threading
import paho.mqtt.client as mqtt

# ==========================================
# 1. 配置日志
# ==========================================
def setup_custom_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # 防止重复添加 Handler
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        
        # 设置独立的格式
        formatter = logging.Formatter("[HealthMonitor] %(message)s")
        handler.setFormatter(formatter)
        
        logger.addHandler(handler)
        
        # 禁止日志向上传播 (防止污染全局或被全局影响)
        logger.propagate = False
        
    return logger

# 初始化本模块专用的 logger
logger = setup_custom_logger("HealthMonitor_Module")

# ==========================================
# 2. 配置参数
# ==========================================
BROKER = "broker.emqx.io"
PORT = 1883
TOPIC = "ierg6200/health/monitor1"
CLIENT_ID = f"python-sub-reader-{random.randint(1000, 9999)}"

# ==========================================
# 3. 核心类：继承 threading.Thread
# ==========================================
class HealthMonitor(threading.Thread):
    def __init__(self):
        # 1. 初始化父类 (Thread)
        super().__init__()
        
        # 2. 设置为守护线程 (Daemon)
        # 意味着主程序结束时，这个线程会被强制关闭，不会卡住程序
        self.daemon = True 
        
        # 3. 初始化数据存储
        self.current_heart_rate = None
        self.current_steps = None
        
        # 4. 初始化 MQTT
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, CLIENT_ID)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def run(self):
        """
        重写 Thread 的 run 方法。
        当调用 self.start() 时，这个方法会在新线程中执行。
        """
        logger.info("正在启动后台线程连接...")
        self.client.connect(BROKER, PORT, 60)
        try:
            # 阻塞式循环，但因为它在独立线程里，所以不会卡住主程序
            self.client.loop_forever()
        except Exception as e:
            logger.error(f"❌ 线程运行出错: {e}")

    def _on_connect(self, client, userdata, flags, rc, properties):
        if rc == 0:
            logger.info(f"✅ 连接成功，监听: {TOPIC}")
            client.subscribe(TOPIC)
        else:
            logger.error(f"❌ 连接失败 code: {rc}")

    def _on_message(self, client, userdata, msg):
        try:
            payload_str = msg.payload.decode('utf-8')
            data = json.loads(payload_str)
            metrics = data.get("metrics", {})
            self.current_heart_rate = metrics.get("heart_rate")
            self.current_steps = metrics.get("steps")
            self.current_sleep = metrics.get("sleep")
            # logger.info(f"收到数据: HR={self.current_heart_rate}")
        except Exception:
            pass

    def get_latest_data(self):
        return (self.current_heart_rate, self.current_steps, self.current_sleep)

# ==========================================
# 4. 模块初始化
# ==========================================
_monitor = HealthMonitor()
_monitor.start() # 这里直接调用 start()，它会自动去跑 run()

def get_user_sensors():
    """
    外部调用接口
    """
    return _monitor.get_latest_data()

# import json
# import paho.mqtt.client as mqtt

# # === 配置信息 ===
# BROKER = "broker.emqx.io"
# PORT = 1883
# TOPIC = "ierg6200/health/monitor1" 
# CLIENT_ID = f"python-sub-reader"

# # ✅ 修改点 1: 增加 properties 参数
# def on_connect(client, userdata, flags, rc, properties):
#     """连接回调函数"""
#     if rc == 0:
#         print(f"✅ 已连接到公共 Broker! 监听 Topic: {TOPIC}")
#         client.subscribe(TOPIC)
#     else:
#         print(f"❌ 连接失败，返回码: {rc}")

# def on_message(client, userdata, msg):
#     """消息接收回调函数"""
#     try:
#         payload_str = msg.payload.decode('utf-8')
#         data = json.loads(payload_str)
        
#         device = data.get("device_id")
#         metrics = data.get("metrics", {})
#         hr = metrics.get("heart_rate")
#         steps = metrics.get("steps")
        
#         print("-" * 30)
#         print(f"📩 收到来自 [{device}] 的数据:")
#         print(f"   ❤️  心率: {hr} bpm")
#         print(f"   🏃 步数: {steps} 步")
        
#     except json.JSONDecodeError:
#         print(f"⚠️ 收到非 JSON 格式消息: {msg.payload}")
#     except Exception as e:
#         print(f"❌ 处理消息时出错: {e}")

# def run_subscriber():
#     # ✅ 修改点 2: 指定 VERSION2
#     client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, CLIENT_ID)
    
#     client.on_connect = on_connect
#     client.on_message = on_message
    
#     print(f"🔌 正在连接...")
#     try:
#         client.connect(BROKER, PORT, 60)
#         client.loop_forever()
#     except KeyboardInterrupt:
#         print("\n⏹️ 停止接收")
#         client.disconnect()
#     except Exception as e:
#         print(f"❌ 错误: {e}")

# if __name__ == "__main__":
#     run_subscriber()