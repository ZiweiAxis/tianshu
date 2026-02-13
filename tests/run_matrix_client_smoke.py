#!/usr/bin/env python3
# 单测/烟雾验证：不依赖真实 Matrix 与 pytest，仅验证 MatrixClient 可导入、实例化及具备约定接口。
# 使用方式：python3 tests/run_matrix_client_smoke.py 或 PYTHONPATH=src python3 tests/run_matrix_client_smoke.py

import sys

def main():
    errors = []
    # 1) 导入
    try:
        from src.matrix.client import MatrixClient
    except ImportError as e:
        print("SKIP: 无法导入 MatrixClient（需安装 matrix-nio 等依赖）:", e)
        return 0 if "nio" in str(e).lower() else 1

    # 2) 实例化（不连真实 MHS）
    try:
        client = MatrixClient()
    except Exception as e:
        errors.append(f"MatrixClient() 实例化失败: {e}")
        return 1

    # 3) 接口存在性
    for method in ("connect", "disconnect", "create_room", "join_room", "leave_room", "send_text", "start_sync_loop", "get_rooms"):
        if not hasattr(client, method):
            errors.append(f"缺少方法: {method}")
    if not hasattr(client, "is_connected"):
        errors.append("缺少属性: is_connected")

    if errors:
        for e in errors:
            print("FAIL:", e)
        return 1
    print("OK: MatrixClient 导入、实例化及约定接口检查通过（单侧验证通过）")
    return 0

if __name__ == "__main__":
    sys.exit(main())
