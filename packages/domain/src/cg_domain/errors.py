"""领域异常。连接器与 API 层据此映射为任务失败或 HTTP 错误。"""


class DomainError(Exception):
    """领域层错误基类。"""


class ValidationError(DomainError):
    """输入不满足领域不变量（比例越界、时间区间倒置等）。"""


class RatioError(ValidationError):
    """比例值非法：负数、超过 100%、单位缺失且无法判定。"""


class TemporalError(ValidationError):
    """时间区间非法：valid_from > valid_to 等。"""
