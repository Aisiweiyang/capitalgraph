"""规范化与 USCC 校验测试。"""

from cg_domain.normalization import is_valid_uscc, normalize_company_name, normalize_name


def test_normalize_name_unifies_width_and_case():
    assert normalize_name("Ｔｅｓｔ 公司") == "test公司"
    assert normalize_name("华为（深圳）有限公司") == "华为(深圳)有限公司"
    assert normalize_name("ABC　Corp") == "abccorp"


def test_normalize_company_name_strips_suffix():
    assert normalize_company_name("华康科技（北京）有限公司").endswith("华康科技(北京)")
    assert normalize_company_name("华康科技股份有限公司") == "华康科技"
    # 无后缀的短名不被剥空
    assert normalize_company_name("张三") == "张三"


def test_uscc_check_digit_valid_and_invalid():
    # 由合成连接器使用的算法生成一个确定合法的代码（基数 17 位 + 校验位）
    base = "91110000ABCDEF01X"  # 17 位
    assert len(base) == 17
    charset = "0123456789ABCDEFGHJKLMNPQRTUWXY"
    weights = (1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28)
    total = sum(charset.index(ch) * w for ch, w in zip(base, weights, strict=True))
    code = base + charset[(31 - total % 31) % 31]
    assert len(code) == 18
    assert is_valid_uscc(code)
    # 篡改校验位后必须失败
    bad = code[:17] + charset[(charset.index(code[17]) + 1) % 31]
    assert not is_valid_uscc(bad)
    # 长度/字符集非法
    assert not is_valid_uscc("1234")
    assert not is_valid_uscc("91110000IO SVA0000X")  # 含非法字符 I/O/S/V 与空格


def test_synthetic_uscc_is_valid():
    import random

    from cg_connectors.synthetic import _fake_uscc

    rng = random.Random(7)
    for _ in range(20):
        assert is_valid_uscc(_fake_uscc(rng))
