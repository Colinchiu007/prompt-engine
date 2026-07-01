"""REST API 输入验证"""

_MIN_CHINESE_LEN = 3
_MIN_ENGLISH_WORDS = 2


def _is_chinese(text: str) -> bool:
    """是否主要是中文"""
    cn = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return cn / max(len(text), 1) > 0.3


def _validate_prompt(prompt: str):
    """验证输入，过短则抛出 400"""
    if not prompt or not prompt.strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="描述不能为空")
    text = prompt.strip()
    if _is_chinese(text):
        if len(text) < _MIN_CHINESE_LEN:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail=f"描述太简短了（{len(text)} 字），建议更详细描述画面"
            )
    else:
        words = text.split()
        if len(words) < _MIN_ENGLISH_WORDS:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail=f"Too short ({len(words)} words). Try a more detailed description"
            )
