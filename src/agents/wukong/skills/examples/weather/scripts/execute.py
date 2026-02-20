"""
Weather Skill 执行脚本

简单的天气查询示例
"""

import sys
import json


def get_weather(city: str) -> str:
    """
    获取天气信息（模拟实现）
    
    实际项目中可以调用天气 API
    """
    # 模拟天气数据
    weather_data = {
        "北京": "☀️ 晴，15°C - 28°C",
        "上海": "🌤️ 多云，18°C - 26°C",
        "广州": "🌧️ 小雨，22°C - 30°C",
        "深圳": "⛅ 阴，23°C - 29°C",
        "杭州": "🌤️ 多云，17°C - 27°C",
    }
    
    return weather_data.get(city, f"抱歉，未找到城市 {city} 的天气信息")


def main():
    """主函数"""
    # 从命令行参数获取城市
    if len(sys.argv) < 2:
        result = {"success": False, "message": "请提供城市名称"}
    else:
        city = sys.argv[1]
        weather = get_weather(city)
        result = {
            "success": True,
            "message": f"{city}的天气: {weather}"
        }
    
    # 输出 JSON 格式结果
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
