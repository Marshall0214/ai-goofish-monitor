"""
AI 请求消息构造辅助函数
"""
from typing import Dict, List, Union


TEXT_ONLY_ANALYSIS_NOTE = (
    "补充说明：本次未提供商品图片，请仅根据商品文字字段和卖家信息判断，不要推断图片内容。"
)


def build_analysis_text_prompt(
    product_json: str,
    prompt_text: str,
    *,
    include_images: bool,
) -> str:
    # 注意：这里故意不再附带"结合价格参考给性价比评分"的指令。任务本身的
    # min_price/max_price 已经是闲鱼搜索页自己的价格筛选框（服务端过滤，跟
    # 用户手动在闲鱼上按价格筛选是同一个输入框），能进入 AI 分析这一步的商品
    # 必然已经在预算范围内；之前这段指令会让模型自己再叠加一层"性价比"门槛，
    # 导致价格明明合规的商品也被判定为不推荐（真实评测里 recall 只有 40.9%，
    # 13/14 个误判全部是这个模式）。商品 JSON 里也不再包含"价格参考"/
    # price_insight（见 item_analysis_dispatcher.py），价格判断完全交给闲鱼
    # 自己的搜索筛选，AI 只负责判断硬性条件里能确认的东西（真伪/成色/卖家/
    # 功能/邮寄等）。
    note = "" if include_images else f"\n{TEXT_ONLY_ANALYSIS_NOTE}\n"
    return f"""请基于你的专业知识和我的要求，分析以下完整的商品JSON数据：

```json
{product_json}
```

    {prompt_text}
    {note}"""


def build_user_message_content(
    text_prompt: str,
    image_data_urls: List[str],
) -> Union[str, List[Dict[str, object]]]:
    if not image_data_urls:
        return text_prompt

    user_content: List[Dict[str, object]] = [
        {"type": "image_url", "image_url": {"url": url}}
        for url in image_data_urls
    ]
    user_content.append({"type": "text", "text": text_prompt})
    return user_content
