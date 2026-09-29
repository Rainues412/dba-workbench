"""
清理重复脚本并重新导入
"""
import requests
import os

API_BASE = "http://localhost:8686"

def cleanup_duplicates():
    """删除content_len=0的重复脚本（ID 95-101）"""
    print("=" * 60)
    print("清理重复脚本")
    print("=" * 60)

    # 删除ID 95-101（第一次导入时没有内容的版本）
    for script_id in range(95, 102):
        try:
            response = requests.delete(f"{API_BASE}/api/scripts/{script_id}")
            if response.status_code == 200:
                print(f"[OK] 删除脚本 ID={script_id}")
            else:
                print(f"[SKIP] 脚本 ID={script_id} 不存在或已删除")
        except Exception as e:
            print(f"[FAIL] 删除失败 ID={script_id}: {e}")

    print("=" * 60)
    print("清理完成")
    print("=" * 60)

if __name__ == "__main__":
    cleanup_duplicates()
