from src.services.result_blacklist_service import match_blacklist_keywords


def _build_record(title: str, **extra_product_fields) -> dict:
    return {
        "商品信息": {
            "商品标题": title,
            **extra_product_fields,
        },
        "卖家信息": {},
    }


def test_regex_blacklist_rule_matches_aliases_case_insensitively():
    keywords = [r"re:\b(pm|pro[\s-]?max)\b"]

    assert match_blacklist_keywords(_build_record("iPhone 15 Pm 256G"), keywords) == keywords
    assert match_blacklist_keywords(_build_record("iPhone 15 Pro Max 256G"), keywords) == keywords
    assert match_blacklist_keywords(_build_record("iPhone 15 promax 256G"), keywords) == keywords
    assert match_blacklist_keywords(_build_record("iPhone 15 pro-max 256G"), keywords) == keywords


def test_regex_blacklist_rule_does_not_hide_plain_pro_models():
    keywords = [r"re:\b(pm|pro[\s-]?max)\b"]

    assert match_blacklist_keywords(_build_record("iPhone 15 Pro 256G"), keywords) == []


def test_blacklist_keyword_matches_title():
    record = _build_record("外壳维修过的手机壳")

    assert match_blacklist_keywords(record, ["维修"]) == ["维修"]


def test_blacklist_keyword_does_not_match_seller_nickname():
    """卖家昵称里带黑名单词，不应该连带屏蔽跟昵称无关的商品（回归：曾经全字段拼接匹配）。"""
    record = _build_record("全新未拆封手机")
    record["卖家信息"] = {"卖家昵称": "小明维修店"}

    assert match_blacklist_keywords(record, ["维修"]) == []


def test_blacklist_keyword_does_not_match_product_tags_or_area():
    """商品标签、发货地区等元数据字段不应该参与黑名单匹配。"""
    record = _build_record(
        "全新未拆封手机",
        商品标签=["验货宝维修保障"],
        发货地区="维修镇",
    )

    assert match_blacklist_keywords(record, ["维修"]) == []


def test_blacklist_keyword_does_not_match_other_product_metadata():
    """商品ID/链接/售价等字段也不应该参与黑名单匹配。"""
    record = _build_record(
        "全新未拆封手机",
        商品ID="维修12345",
        商品链接="https://example.com/维修",
    )

    assert match_blacklist_keywords(record, ["维修"]) == []
