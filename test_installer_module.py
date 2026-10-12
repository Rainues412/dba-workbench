"""
安装包模块测试脚本
用于诊断三级导航无数据问题
"""
import requests
import json

API = 'http://localhost:8686'

def test_api_response():
    """测试 1: API 返回数据结构"""
    print("=" * 60)
    print("测试 1: API 返回数据结构")
    print("=" * 60)

    r = requests.get(f'{API}/api/resources/?page_size=5')
    assert r.status_code == 200, f"API 请求失败: {r.status_code}"

    data = r.json()
    print("[OK] API 响应成功，总数: {}".format(data['total']))

    if data['items']:
        item = data['items'][0]
        print(f"\n第一个资源字段检查:")
        print(f"  id: {item.get('id', 'MISSING')}")
        print(f"  name: {item.get('name', 'MISSING')[:30]}")
        print(f"  wb_db: {item.get('wb_db', 'MISSING')}")
        print(f"  category: {item.get('category', 'MISSING')}")
        print(f"  path: {item.get('path', 'MISSING')[:40]}")
        print(f"  version: {item.get('version', 'MISSING')}")
        print(f"  size_mb: {item.get('size_mb', 'MISSING')}")

        # 检查必要字段
        required = ['id', 'name', 'wb_db', 'category', 'path']
        missing = [f for f in required if f not in item]
        if missing:
            print("\n[X] 缺少字段: {}".format(missing))
            return False
        print("\n[OK] 所有必要字段存在")

    return True

def test_wb_db_distribution():
    """测试 2: wb_db 字段分布"""
    print("\n" + "=" * 60)
    print("测试 2: wb_db 字段分布")
    print("=" * 60)

    r = requests.get(f'{API}/api/resources/?page_size=500')
    data = r.json()

    by_db = {}
    for item in data['items']:
        db = item.get('wb_db', 'unknown')
        if db not in by_db:
            by_db[db] = []
        by_db[db].append(item)

    print(f"总资源数: {len(data['items'])}")
    print(f"\n按 wb_db 分组:")
    for db in sorted(by_db.keys()):
        count = len(by_db[db])
        print(f"  {db}: {count} 个")

    # 检查是否有"通用"以外的分类
    non_generic = [db for db in by_db.keys() if db != '通用']
    if non_generic:
        print("\n[OK] 存在具体数据库类型: {}".format(non_generic))
        return True
    else:
        print("\n[X] 所有资源都是'通用'，需要数据迁移")
        return False

def test_fromapi_mapping():
    """测试 3: 模拟前端 fromApi 映射"""
    print("\n" + "=" * 60)
    print("测试 3: 模拟前端 fromApi 映射")
    print("=" * 60)

    r = requests.get(f'{API}/api/resources/?page_size=3')
    data = r.json()

    print("模拟 workbench.js 的 fromApi 映射:")
    for item in data['items'][:3]:
        # 模拟 fromApi 函数
        mapped = {
            'id': item.get('id'),
            'name': item.get('name', ''),
            'version': item.get('version', ''),
            'type': item.get('kind', ''),
            'path': item.get('path', ''),
            'size': item.get('notes', '') or (f"{item.get('size_mb', 0)} MB" if item.get('size_mb') else ''),
            'db': item.get('wb_db', '通用'),
            'createdAt': item.get('created_at', '')
        }

        print(f"\n  原始 API 数据:")
        print(f"    wb_db: {item.get('wb_db', 'MISSING')}")
        print(f"  映射后前端数据:")
        print(f"    db: {mapped['db']}")
        print(f"    name: {mapped['name'][:30]}")

        if mapped['db'] and mapped['db'] != '通用':
            print("    [OK] db 字段正确映射")
        else:
            print("    [X] db 字段映射异常")
            return False

    return True

def test_filter_by_wb_db():
    """测试 4: 按 wb_db 筛选"""
    print("\n" + "=" * 60)
    print("测试 4: 按 wb_db 筛选")
    print("=" * 60)

    # 测试 MySQL 筛选
    r = requests.get(f'{API}/api/resources/?wb_db=MySQL&page_size=500')
    data = r.json()

    print(f"筛选 wb_db=MySQL:")
    print(f"  总数: {data['total']}")

    if data['total'] > 0:
        print("  [OK] 筛选成功，找到 {} 个 MySQL 资源".format(data['total']))
        if data['items']:
            print("  示例: {}".format(data['items'][0]['name'][:40]))
        return True
    else:
        print("  [X] 未找到 MySQL 资源")
        return False

def test_frontend_render_logic():
    """测试 5: 模拟前端渲染逻辑"""
    print("\n" + "=" * 60)
    print("测试 5: 模拟前端渲染逻辑")
    print("=" * 60)

    r = requests.get(f'{API}/api/resources/?page_size=500')
    data = r.json()

    # 模拟 gd('installers')
    installers = []
    for item in data['items']:
        mapped = {
            'id': item.get('id'),
            'name': item.get('name', ''),
            'version': item.get('version', ''),
            'type': item.get('kind', ''),
            'path': item.get('path', ''),
            'size': item.get('notes', '') or (f"{item.get('size_mb', 0)} MB" if item.get('size_mb') else ''),
            'db': item.get('wb_db', '通用'),
            'createdAt': item.get('created_at', '')
        }
        installers.append(mapped)

    print(f"gd('installers') 返回: {len(installers)} 条")

    # 模拟 renderInstDBGrid 的统计逻辑
    _scriptDBMeta = [
        {'name': 'Oracle'}, {'name': 'MySQL'}, {'name': 'PostgreSQL'},
        {'name': 'SQL Server'}, {'name': 'Linux'}, {'name': 'Redis'}, {'name': '其他'}
    ]

    counts = {d['name']: 0 for d in _scriptDBMeta}
    for inst in installers:
        db = inst.get('db', '其他')
        if db in counts:
            counts[db] += 1
        else:
            counts['其他'] += 1

    print(f"\n数据库类型统计:")
    for db, count in counts.items():
        print(f"  {db}: {count}")

    # 检查是否有数据
    has_data = any(count > 0 for count in counts.values())
    if has_data:
        print("\n[OK] 三级导航有数据")
        return True
    else:
        print("\n[X] 三级导航无数据")
        return False

def main():
    print("\n" + "=" * 60)
    print("安装包模块诊断测试")
    print("=" * 60)

    tests = [
        ("API 返回数据结构", test_api_response),
        ("wb_db 字段分布", test_wb_db_distribution),
        ("fromApi 映射", test_fromapi_mapping),
        ("按 wb_db 筛选", test_filter_by_wb_db),
        ("前端渲染逻辑", test_frontend_render_logic),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print("\n[X] 测试失败: {}".format(e))
            results.append((name, False))

    # 汇总
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    for name, result in results:
        status = "[OK] PASS" if result else "[X] FAIL"
        print("{} - {}".format(status, name))

    passed = sum(1 for _, r in results if r)
    total = len(results)
    print(f"\n通过: {passed}/{total}")

    if passed == total:
        print("\n[OK] 所有测试通过，安装包模块工作正常")
        print("\n建议操作:")
        print("1. 刷新浏览器页面 (Ctrl+F5)")
        print("2. 打开开发者工具 Console，检查是否有 JavaScript 错误")
        print("3. 在 Console 执行: gd('installers') 查看返回数据")
        print("4. 点击安装包模块，检查是否正常显示")
    else:
        print("\n[X] 部分测试失败，需要修复")
        for name, result in results:
            if not result:
                print("  - {}".format(name))

if __name__ == '__main__':
    main()
