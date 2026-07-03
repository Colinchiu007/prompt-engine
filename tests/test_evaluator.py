"""评估对比模式测试 — F3"""
import pytest
from unittest.mock import patch


class TestEvaluationDimensions:
    """评估维度枚举测试."""

    def test_import_evaluation_dimension(self):
        from prompt_engine.evaluator import EvaluationDimension
        assert EvaluationDimension.CLARITY is not None
        assert EvaluationDimension.SPECIFICITY is not None

    def test_dimension_names(self):
        from prompt_engine.evaluator import EvaluationDimension
        names = [d.value for d in EvaluationDimension]
        assert "clarity" in names
        assert "specificity" in names
        assert "creativity" in names
        assert "actionability" in names


class TestEvaluationResult:
    """评估结果模型测试."""

    def test_import_evaluation_result(self):
        from prompt_engine.evaluator import EvaluationResult, DimensionScore
        score = DimensionScore(before=3, after=8)
        assert score.before == 3
        assert score.after == 8
        assert score.improvement == "+5"

    def test_evaluation_result_creation(self):
        from prompt_engine.evaluator import EvaluationResult, DimensionScore
        result = EvaluationResult(
            original="a cat",
            optimized="a fluffy cat with golden light",
            scores={
                "clarity": DimensionScore(before=3, after=8),
                "specificity": DimensionScore(before=2, after=9),
            },
            overall_improvement=62.5,
        )
        assert result.original == "a cat"
        assert result.overall_improvement == 62.5
        assert len(result.scores) == 2

    def test_evaluation_result_empty_scores(self):
        from prompt_engine.evaluator import EvaluationResult
        result = EvaluationResult(original="", optimized="", scores={}, overall_improvement=0.0)
        assert result.overall_improvement == 0.0


class TestEvaluateFunction:
    """评估函数测试."""

    def test_import_evaluate(self):
        from prompt_engine.evaluator import evaluate
        assert callable(evaluate)

    @patch("prompt_engine.evaluator._call_llm_for_evaluation")
    def test_evaluate_returns_result(self, mock_llm):
        from prompt_engine.evaluator import evaluate, EvaluationResult
        mock_llm.return_value = {
            "clarity": {"before": 3, "after": 8},
            "specificity": {"before": 2, "after": 9},
        }
        result = evaluate("a cat", "a fluffy cat with golden hour lighting")
        assert isinstance(result, EvaluationResult)
        assert result.original == "a cat"
        assert result.scores["clarity"].before == 3
        assert result.scores["specificity"].after == 9

    @patch("prompt_engine.evaluator._call_llm_for_evaluation")
    def test_evaluate_empty_original(self, mock_llm):
        from prompt_engine.evaluator import evaluate
        result = evaluate("", "optimized prompt")
        # 空原词应返回低分
        assert result is not None
