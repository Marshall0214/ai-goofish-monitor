from src.ai_message_builder import build_analysis_text_prompt


def test_build_analysis_text_prompt_no_longer_asks_model_to_score_value():
    # 回归测试：这段"结合价格参考给性价比评分"的指令曾经无条件拼进每一次分析
    # prompt，诱导模型把"性价比"和"是否推荐"混为一谈——真实评测里 107 条标注
    # 样本中 14 处判断不一致，13 处都是这个模式（商品本身完全合格，只因为价格
    # 没贴近一个被任务自己的 min_price/max_price 截断过、本身就不准的"市场均价"
    # 就被拒）。任务的价格区间已经由闲鱼搜索页自己的价格筛选框强制保证，AI 不
    # 应该再自己叠加一层价格判断。
    prompt = build_analysis_text_prompt(
        "{}", "示例判断标准", include_images=True
    )

    assert "性价比" not in prompt
    assert "value_score" not in prompt
    assert "价格参考" not in prompt
    assert "price_insight" not in prompt


def test_build_analysis_text_prompt_still_includes_product_json_and_criteria():
    prompt = build_analysis_text_prompt(
        '{"商品ID": "1"}', "示例判断标准", include_images=True
    )

    assert '{"商品ID": "1"}' in prompt
    assert "示例判断标准" in prompt


def test_build_analysis_text_prompt_adds_text_only_note_without_images():
    prompt = build_analysis_text_prompt("{}", "示例判断标准", include_images=False)

    assert "本次未提供商品图片" in prompt
