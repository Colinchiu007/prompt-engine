# prompt-engine — 开发流程规范

> 提示词优化引擎的开发流程与编码约定。AI 工具启动时自动读取。

---

## 核心原则

1. **TDD**：测试先于代码，全部 mock 隔离，不依赖真实 API Key
2. **三级流水线顺序不可更改**：keyword_match → vector_rag → llm_classify
3. **惰性加载**：`__init__.py` 用 `__getattr__` 惰性导入，避免启动时 LLM 连接
4. **向后兼容**：25 个 StyleCategory 枚举在 models.py，不新增不删除
5. **先文档再代码**：没有 PRD 不动手，没有架构设计不动手

## AI 角色分工

| 角色 | 阶段 | 产出物 |
|------|------|--------|
| **PM** | 需求分析 | PRD、功能规格、用户故事 |
| **架构师** | 技术设计 | LLM 策略设计、流水线设计、缓存策略 |
| **开发工程师** | 编码实现 | 策略、服务、API + 测试（TDD） |
| **QA** | 质量验证 | 分类准确率测试、LLM 输出测试 |
| **CTO** | 代码评审 | LLM 调用安全审查、流水线完整性 |

## 7 阶段开发流程

### 阶段 1：想法澄清
确认：优化策略类型、LLM 供应商、缓存需求、MVP 范围

### 阶段 2：PRD（PM）
产出：PRD，包含 P0/P1/P2 功能、分类/优化策略、验收标准
**批准后才能进入下一阶段。**

### 阶段 3：技术设计（架构师）
产出：方案对比 + 推荐方案
- 新增策略：在 `strategies/` 或 `services/` 下创建
- 流水线位置：是否在三级流水线前/后插入
- 缓存策略：是否需要新的缓存级别

### 阶段 4：开发计划（PM）
MVP 拆成 ≤4h 的任务。

### 阶段 5：编码实现（开发 + TDD）
- 先写测试（mock LLM，不依赖真实 API）
- 测试全部通过后才能提交
- 25 个 StyleCategory 枚举不能新增不能删除

### 阶段 6：代码评审（CTO）
必检项：
- 🔴 测试是否 mock 隔离（避免 CI 依赖真实 API Key）
- 🔴 三级分类流水线顺序是否被修改
- 🟠 惰性加载是否被破坏（启动时 LLM 连接）
- 🟠 StyleCategory 枚举是否有变更
- 🟢 新增策略是否注册到流水线

### 阶段 7：发布
- 更新 CHANGELOG.md
- pytest 全部通过
- git 提交并 tag

## 质量门禁

**PRD 阶段**：策略类型明确 / 流水线位置明确 / 验收标准可验证
**设计阶段**：最简单方案 / 缓存策略明确
**开发阶段**：测试全通过（mock 隔离） / 手动验证核心功能
**Review 阶段**：CRITICAL 问题已修复 / 流水线完整性

## TDD 流程

```
RED   → 在 prompt_engine/ 下写失败测试（mock LLM）
GREEN → 最小实现让测试通过
REFACTOR → 重构，保持测试通过
```

### 测试规范

```python
# 测试必须 mock LLM 调用，不依赖真实 API Key
def test_classify_returns_style(mock_llm):
    mock_llm.classify.return_value = "轻松易懂"
    result = classifier.classify("测试文本")
    assert result == "轻松易懂"

def test_keyword_match_evaluates_score(keyword_classifier):
    result = keyword_classifier.evaluate("测试文本")
    assert 0 <= result["score"] <= 1
```

## 提交规范

```
feat(rag): 添加 vector_rag 阶段 seed 种子注入
fix(cache): 修复缓存命中率统计
docs: 更新 PRD 分类策略章节
refactor: 统一 LLM 调用超时处理
```

## 文档清单

| 文件 | 路径 | 说明 |
|------|------|------|
| AGENTS.md | `./AGENTS.md` | 本文件，开发流程规范 |
| CLAUDE.md | `./CLAUDE.md` | 项目上下文和开发命令 |
| .clinerules | `./.clinerules` | 硬约束规则 |
| PRD.md | `./docs/PRD.md` | 产品需求文档 |
| ARCHITECTURE.md | `./docs/ARCHITECTURE.md` | 架构设计文档 |
| INTEGRATION.md | `./docs/INTEGRATION.md` | 集成说明 |
| MANUAL.md | `./docs/MANUAL.md` | 用户手册 |
| CHANGELOG.md | `./CHANGELOG.md` | 变更日志 |

## 硬约束（来自 .clinerules）

- `__init__.py` 使用 `__getattr__` 惰性导入 Optimizer/Classifier，避免启动时 LLM 连接
- 三级分类流水线顺序不可更改：keyword_match → vector_rag → llm_classify
- 测试必须全部 mock 隔离，不依赖真实 API Key
- 25 个 StyleCategory 枚举在 models.py，不新增不删除
- 权重系统使用 keyword_weights.json 持久化，_get_weights() 惰性加载

## 常用命令

```bash
# 测试
pytest prompt_engine/ -v

# 运行测试覆盖
pytest prompt_engine/ --cov=prompt_engine
```

## 版本

**v0.9.x** — 提示词优化引擎持续迭代中。
