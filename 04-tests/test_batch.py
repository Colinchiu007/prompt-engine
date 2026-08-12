"""批量优化测试"""
from prompt_engine.models import OptimizeRequest, BatchOptimizeRequest, PlatformType


class TestBatchOptimizeRequest:
    def test_min_valid(self):
        req = BatchOptimizeRequest(requests=[
            OptimizeRequest(prompt="cat"),
        ])
        assert len(req.requests) == 1

    def test_mid_size_valid(self):
        # videogen storyboard 上限 12 场景：12 条单批必须合法（2026-08-12 批量上限 10->20）
        reqs = [OptimizeRequest(prompt=f"test {i}") for i in range(12)]
        req = BatchOptimizeRequest(requests=reqs)
        assert len(req.requests) == 12

    def test_max_valid(self):
        reqs = [OptimizeRequest(prompt=f"test {i}") for i in range(20)]
        req = BatchOptimizeRequest(requests=reqs)
        assert len(req.requests) == 20

    def test_exceeds_limit(self):
        import pydantic
        reqs = [OptimizeRequest(prompt=f"test {i}") for i in range(21)]
        try:
            BatchOptimizeRequest(requests=reqs)
            assert False, "应抛出校验异常"
        except pydantic.ValidationError:
            pass

    def test_empty(self):
        import pydantic
        try:
            BatchOptimizeRequest(requests=[])
            assert False, "应抛出校验异常"
        except pydantic.ValidationError:
            pass