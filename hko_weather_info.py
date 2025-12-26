import requests
import logging
from typing import Tuple, List, Optional

# ==========================================
# 1. 配置独立日志 (不使用 basicConfig)
# ==========================================
def setup_custom_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # 检查是否已经添加过 handler，防止重复打印
    if not logger.handlers:
        # 创建控制台处理器
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        
        # 设置独立的格式
        formatter = logging.Formatter("[HKOWeather] %(message)s")
        handler.setFormatter(formatter)
        
        # 添加处理器到 logger
        logger.addHandler(handler)
        
        # 禁止日志向上传播到根 Logger (防止主程序也配置了日志导致重复打印)
        logger.propagate = False 
        
    return logger

# 初始化本模块专用的 logger
logger = setup_custom_logger("HKO_Module")

# ==========================================
# 2. 常量定义
# ==========================================
class HKOWarningCode:
    """
    香港天文台警告信号代码 (HKO Warning Codes)
    """
    FIRE_YELLOW = "WFIREY"
    FIRE_RED    = "WFIRER"
    RAIN_AMBER  = "WRAINY"
    RAIN_RED    = "WRAINR"
    RAIN_BLACK  = "WRAINB"
    TYPHOON_1   = "TC1"
    TYPHOON_3   = "TC3"
    TYPHOON_8NE = "TC8NE"
    TYPHOON_8SE = "TC8SE"
    TYPHOON_8NW = "TC8NW"
    TYPHOON_8SW = "TC8SW"
    TYPHOON_9   = "TC9"
    TYPHOON_10  = "TC10"
    THUNDERSTORM = "WTS"
    FROST        = "WFROST"
    HOT          = "WHOT"
    COLD         = "WCOLD"
    MONSOON      = "WMSGNL"
    LANDSLIP     = "WL"
    TSUNAMI      = "WTMW"

# ==========================================
# 3. 获取数据的函数
# ==========================================
def get_hko_weather() -> Tuple[Optional[float], Optional[int], List[str]]:
    """
    获取香港天气数据
    :return: (温度, 湿度, 警告代码列表)
    """
    base_url = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php"
    
    session = requests.Session()
    session.trust_env = False

    temp_val = None
    humidity_val = None
    warning_codes = []

    try:
        # logger.info("正在请求数据...") 
        
        # --- 1. 获取实时天气 ---
        resp_weather = session.get(base_url, params={"dataType": "rhrread", "lang": "en"}, timeout=5)
        
        if resp_weather.status_code == 200:
            w_data = resp_weather.json()
            
            # 温度
            temps = w_data.get("temperature", {}).get("data", [])
            if temps:
                hko_temp = next((item for item in temps if item["place"] == "Hong Kong Observatory"), temps[0])
                try:
                    temp_val = float(hko_temp["value"])
                except (ValueError, KeyError):
                    logger.warning(f"⚠️ 温度数据解析错误: {hko_temp}")
                    temp_val = None
            
            # 湿度
            hums = w_data.get("humidity", {}).get("data", [])
            if hums:
                try:
                    humidity_val = int(hums[0]["value"])
                except (ValueError, KeyError):
                    logger.warning("⚠️ 湿度数据解析错误")
                    humidity_val = None
        else:
            logger.error(f"❌ 获取实时天气失败 (HTTP {resp_weather.status_code})")

        # --- 2. 获取警告代码 ---
        resp_warn = session.get(base_url, params={"dataType": "warnsum"}, timeout=5)
        
        if resp_warn.status_code == 200:
            warn_data = resp_warn.json()
            if warn_data:
                for key, info in warn_data.items():
                    code = info.get('code')
                    if code:
                        warning_codes.append(code)
                if warning_codes:
                    logger.info(f"⚠️ 检测到生效警告: {warning_codes}")
        else:
            logger.error(f"❌ 获取警告数据失败 (HTTP {resp_warn.status_code})")

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ 网络请求错误: {e}")
    except Exception as e:
        logger.error(f"❌ 未知程序错误: {e}")

    return (temp_val, humidity_val, warning_codes)

# ==========================================
# 4. 使用示例
# ==========================================
if __name__ == "__main__":
    # 测试获取数据
    temp, hum, codes = get_hko_weather()
    
    if temp is not None:
        logger.info(f"当前天气: {temp}°C, 湿度 {hum}%")
    else:
        logger.warning("未能获取天气数据")