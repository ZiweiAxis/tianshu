# Weather Skill - Tool Definition

```json
{
  "name": "weather",
  "description": "查询指定城市的天气信息",
  "parameters": {
    "type": "object",
    "properties": {
      "city": {
        "type": "string",
        "description": "要查询的城市名称"
      }
    },
    "required": ["city"]
  }
}
```

---

# 天气查询 Skill

## 使用方法

当用户询问天气时，使用 `weather` 工具查询。

### 参数

- `city`: 城市名称（必填），如 "北京"、"上海"、"郑州"

### 返回结果

天气信息，包含：
- 天气状况（晴、雨、雪等）
- 温度
- 湿度
- 风速

### 示例

**调用**:
```json
{
  "tool": "weather",
  "args": {"city": "北京"}
}
```

**返回**:
```
北京: ☀️ 晴, 15°C, 湿度 65%
```
