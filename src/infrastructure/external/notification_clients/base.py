"""
通知客户端基类
定义通知客户端的统一接口
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Iterable

from src.utils import convert_goofish_link


@dataclass(frozen=True)
class NotificationMessage:
    title: str
    price: str
    reason: str
    desktop_link: str
    mobile_link: str | None
    notification_title: str
    content: str
    image_url: str | None


_DEFAULT_LINK_TYPES = frozenset({"mobile", "desktop"})


class NotificationClient(ABC):
    """通知客户端抽象基类"""

    channel_key = "unknown"
    display_name = "未知渠道"

    def __init__(
        self,
        enabled: bool = False,
        link_types: Iterable[str] | None = None,
    ):
        self._enabled = enabled
        self._link_types = frozenset(link_types) if link_types is not None else _DEFAULT_LINK_TYPES

    def is_enabled(self) -> bool:
        """检查客户端是否启用"""
        return self._enabled

    @abstractmethod
    async def send(self, product_data: Dict, reason: str) -> bool:
        """
        发送通知

        Args:
            product_data: 商品数据
            reason: 推荐原因

        Returns:
            是否发送成功
        """
        raise NotImplementedError

    def _build_message(self, product_data: Dict, reason: str) -> NotificationMessage:
        """格式化消息内容"""
        title = product_data.get('商品标题', 'N/A')
        price = product_data.get('当前售价', 'N/A')
        desktop_link = product_data.get('商品链接', '#')
        show_mobile = "mobile" in self._link_types
        show_desktop = "desktop" in self._link_types

        mobile_link = None
        if show_mobile and desktop_link and desktop_link != "#":
            mobile_link = convert_goofish_link(desktop_link)

        content_lines = [
            f"价格: {price}",
            f"原因: {reason}",
        ]
        link_lines = []
        if mobile_link:
            link_lines.append(f"手机端链接: {mobile_link}")
        if show_desktop:
            link_lines.append(f"电脑端链接: {desktop_link}")
        if not link_lines:
            # 兜底：不管配置如何，通知里至少要有一个可用链接
            link_lines.append(f"链接: {desktop_link}")
        content_lines.extend(link_lines)

        short_title = title[:30]
        suffix = "..." if len(title) > 30 else ""
        notification_title = f"🚨 新推荐! {short_title}{suffix}"

        main_image = product_data.get('商品主图链接')
        if not main_image:
            image_list = product_data.get('商品图片列表', [])
            if image_list:
                main_image = image_list[0]

        return NotificationMessage(
            title=title,
            price=price,
            reason=reason,
            desktop_link=desktop_link,
            mobile_link=mobile_link,
            notification_title=notification_title,
            content="\n".join(content_lines),
            image_url=main_image,
        )
