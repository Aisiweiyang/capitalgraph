"""名称与标识符规范化。

设计约束（提示词 §5）：禁止仅用名称做主键；名称相似度只产生候选。
规范化目的是让"同一主体的不同写法"在检索与匹配候选阶段可汇聚，
最终确认仍需标识符（USCC/LEI/代码/来源内部 ID）或人工复核。
"""

from __future__ import annotations

import re
import unicodedata

# GB 32100-2015 统一社会信用代码字符集（不含 I/O/S/V/Z）
_USCC_CHARSET = "0123456789ABCDEFGHJKLMNPQRTUWXY"
_USCC_WEIGHTS = (1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28)

# 尾部公司后缀，按长度降序剥离。只剥结尾，避免误伤含“集团”的正式全名。
_COMPANY_SUFFIXES = (
    "股份有限公司",
    "有限责任公司",
    "集团有限公司",
    "有限公司",
    "股份公司",
    "集团公司",
    "合伙企业（有限合伙）",
    "合伙企业（普通合伙）",
    "（有限合伙）",
    "（普通合伙）",
    "有限合伙",
    "普通合伙",
    "事务所",
    "总公司",
    "公司",
)

_BRACKETS = {"（": "(", "）": ")", "【": "[", "】": "]", "［": "[", "］": "]"}


def normalize_name(name: str) -> str:
    """全半角统一、括号统一、去空白、小写化。用于一切名称比较的基线。"""
    if not name:
        return ""
    text = unicodedata.normalize("NFKC", name).casefold()
    for full, half in _BRACKETS.items():
        text = text.replace(full, half)
    # 去除全部空白（中文企业名称中空白无语义）
    return re.sub(r"\s+", "", text)


def normalize_company_name(name: str) -> str:
    """在 normalize_name 基础上剥离尾部公司后缀，得到匹配用短名。

    保留原名的规范化形式供展示；剥离结果仅用于相似候选生成。
    """
    text = normalize_name(name)
    changed = True
    while changed:
        changed = False
        for suffix in _COMPANY_SUFFIXES:
            normalized_suffix = normalize_name(suffix)
            if text.endswith(normalized_suffix) and len(text) > len(normalized_suffix):
                text = text[: -len(normalized_suffix)]
                changed = True
                break
    return text


def is_valid_uscc(code: str) -> bool:
    """按 GB 32100-2015 校验统一社会信用代码（18 位含校验位）。"""
    if not isinstance(code, str) or len(code) != 18:
        return False
    upper = code.upper()
    try:
        total = sum(
            _USCC_CHARSET.index(ch) * weight
            for ch, weight in zip(upper[:17], _USCC_WEIGHTS, strict=True)
        )
    except ValueError:
        return False
    expected = _USCC_CHARSET[(31 - total % 31) % 31]
    return upper[17] == expected
