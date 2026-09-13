from src.infrastructure.config.settings import parse_notification_link_types
from src.infrastructure.external.notification_clients.base import NotificationClient


class _EchoClient(NotificationClient):
    channel_key = "echo"
    display_name = "Echo"

    async def send(self, product_data, reason):
        return None


def test_parse_notification_link_types_accepts_both_values():
    assert parse_notification_link_types("mobile,desktop") == {"mobile", "desktop"}


def test_parse_notification_link_types_accepts_single_value():
    assert parse_notification_link_types("mobile") == {"mobile"}


def test_parse_notification_link_types_ignores_invalid_tokens():
    assert parse_notification_link_types("mobile, bogus , ") == {"mobile"}


def test_parse_notification_link_types_falls_back_to_desktop_when_empty_or_invalid():
    assert parse_notification_link_types("") == {"desktop"}
    assert parse_notification_link_types(None) == {"desktop"}
    assert parse_notification_link_types("bogus") == {"desktop"}


PRODUCT_DATA = {
    "商品标题": "Sony A7M4",
    "当前售价": "¥9999",
    "商品链接": "https://www.goofish.com/item.htm?id=123",
}


def test_build_message_mobile_only_omits_desktop_line():
    client = _EchoClient(enabled=True, link_types={"mobile"})
    message = client._build_message(PRODUCT_DATA, "价格合适")

    assert message.mobile_link is not None
    assert "手机端链接" in message.content
    assert "电脑端链接" not in message.content


def test_build_message_desktop_only_omits_mobile_line():
    client = _EchoClient(enabled=True, link_types={"desktop"})
    message = client._build_message(PRODUCT_DATA, "价格合适")

    assert message.mobile_link is None
    assert "电脑端链接" in message.content
    assert "手机端链接" not in message.content


def test_build_message_both_link_types_included():
    client = _EchoClient(enabled=True, link_types={"mobile", "desktop"})
    message = client._build_message(PRODUCT_DATA, "价格合适")

    assert "手机端链接" in message.content
    assert "电脑端链接" in message.content


def test_build_message_falls_back_to_generic_link_when_no_types_resolve_content():
    # 极端情况：显式传入空集合（正常业务不会出现，但要确保兜底逻辑不产出无链接的消息）
    client = _EchoClient(enabled=True, link_types=set())
    message = client._build_message(PRODUCT_DATA, "价格合适")

    assert "链接:" in message.content
    assert message.desktop_link in message.content
