# ARCH-F3: 评估对比模式方案

## 目标

借鉴 prompt-optimizer 的评估+对比模式，新增 prompt 质量评估能力：给定原 prompt 和优化后的 prompt，从多个维度评估改进效果。

## 新模块

```
prompt_engine/evaluator.py
  ├── EvaluationDimension (枚举)
  │   ├── CLARITY       # 清晰度
  │   ├── SPECIFICITY   # 具体度
  │   ├── CREATIVITY    # 创意度
  │   ├── ACTIONABILITY # 可执行性 (LLM 能否理解)
  │   └── PLATFORM_BEST # 平台最佳实践
  ├── EvaluationResult (dataclass)
  └── evaluate(original, optimized, platform) → EvaluationResult
```

## API

```
POST /v1/evaluate
{
  "original": "a cat",
  "optimized": "a fluffy cat sitting on a windowsill, golden hour lighting",
  "platform": "midjourney"
}

Response:
{
  "original": "...",
  "optimized": "...",
  "scores": {
    "clarity": {"before": 3, "after": 8, "improvement": "+5"},
    "specificity": {"before": 2, "after": 9, "improvement": "+7"},
    ...
  },
  "overall_improvement": "+62%"
}
```

## 实现

使用 LLM 评估（调用自身），做零样本评估。
- 构造评估 prompt，让 LLM 对每个维度打分 1-10
- 返回分数和改进幅度

## 测试

- 测试评估 prompt 构造
- 测试 mock LLM 评估结果解析
- 测试边界 (空输入、过长输入)
