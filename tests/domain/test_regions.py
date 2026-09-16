"""regions 工具函数：省级行政区划代码校验。"""

from cg_domain.regions import is_province_code


def test_is_province_code():
    assert is_province_code("110000")  # 北京
    assert is_province_code("440000")  # 广东
    assert not is_province_code(None)
    assert not is_province_code("")
    assert not is_province_code("11000")  # 位数不足
    assert not is_province_code("1100000")  # 位数超出
    assert not is_province_code("11o000")  # 非数字
    assert not is_province_code("999999")  # 数字但不在省级列表
