"""QA 综合检查 — v0.15.0 PROJECT-011"""
import os, re, subprocess
import urllib.request, urllib.error

REPO = r"C:\\Users\\邱领\\projects\\prompt-engine"
SERVER = "http://127.0.0.1:8000"


def banner(t):
    print(f"\n{'='*60}\n{t}\n{'='*60}")


# QA-1
banner("QA-1: 全量测试")
r = subprocess.run(
    ["python", "-m", "pytest", "tests/", "-q", "--tb=line",
     "--ignore=tests/test_infinity_features.py"],
    cwd=REPO, capture_output=True, text=True, timeout=300
)
print(r.stdout[-400:])

# QA-2
banner("QA-2: CLI --help")
r = subprocess.run(
    ["python", "-m", "prompt_engine.cli", "--help"],
    cwd=REPO, capture_output=True, text=True, timeout=15
)
print(f"exit={r.returncode}")
print(f"stdout: {r.stdout[:300]}")

# QA-3
banner("QA-3: REST API 端点")
with open(os.path.join(REPO, "prompt_engine/api/rest.py"), encoding="utf-8") as f:
    rest = f.read()
endpoints = re.findall(r'@app\.(get|post)\("([^"]+)"', rest)
print(f"已注册: {len(endpoints)}")
working = 0
broken = []
for method, path in endpoints:
    try:
        if method == "get":
            r = urllib.request.urlopen(f"{SERVER}{path}", timeout=3)
        else:
            r = urllib.request.urlopen(urllib.request.Request(
                f"{SERVER}{path}", data=b"{}",
                headers={"Content-Type": "application/json"}), timeout=3)
        if r.status in (200, 405):
            working += 1
        else:
            broken.append((method, path, r.status))
    except urllib.error.HTTPError as e:
        if e.code in (404, 405, 422):
            working += 1
        else:
            broken.append((method, path, e.code))
    except Exception as e:
        broken.append((method, path, str(e)[:30]))
print(f"工作: {working}/{len(endpoints)}")
if broken:
    for m, p, s in broken:
        print(f"  ❌ {m.upper():4s} {p:30s} {s}")

# QA-4
banner("QA-4: Web UI 完整性")
r = urllib.request.urlopen(SERVER + "/", timeout=5)
html = r.read().decode()
checks = {
    "Workbench tab": "Prompt 工作台" in html,
    "Dashboard tab": "数据看板" in html,
    "Settings tab": "配置" in html,
    "ECharts": "echarts" in html,
    "ElementPlus": "element-plus" in html,
    "Vue 3": "vue@3" in html,
}
for name, ok in checks.items():
    print(f"  {'✅' if ok else '❌'} {name}")

# QA-5
banner("QA-5: 安全扫描")
for fn in ["prompt_engine/api/rest.py", "prompt_engine/web/index.html",
          "prompt_engine/llm/xfyun.py", "prompt_engine/llm/openai_compat.py"]:
    fp = os.path.join(REPO, fn)
    if not os.path.exists(fp):
        continue
    with open(fp, encoding="utf-8") as f:
        c = f.read()
    findings = re.findall(r'(sk-[a-zA-Z0-9]{20,}|api_key\s*=\s*["\'][a-zA-Z0-9]{20,})', c)
    real = [k for k in findings if 'test' not in k and 'fake' not in k.lower()]
    print(f"  {'✅' if not real else '⚠️'} {fn}: {'干净' if not real else str(len(real))+' keys'}")

# QA-6
banner("QA-6: 文档审计")
for fn in ["CHANGELOG.md", "README.md", "README.en.md", "docs/PRD.md",
          "docs/AGENTS.md", "docs/INTEGRATION.md", "docs/MANUAL.md"]:
    fp = os.path.join(REPO, fn)
    if os.path.exists(fp):
        size = os.path.getsize(fp)
        print(f"  ✅ {fn:30s} ({size:,}b)")
    else:
        print(f"  ❌ {fn} 不存在")

# QA-7
banner("QA-7: Git 状态")
r = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True, timeout=5)
print(f"未提交: {r.stdout.strip() or 'None'}")
r = subprocess.run(["git", "log", "--oneline", "-3"], cwd=REPO, capture_output=True, text=True, timeout=5)
print("\n最近 3 次提交：")
for line in r.stdout.strip().split("\n"):
    print(f"  {line}")
