from datetime import datetime
import os

from aiohttp import ClientSession
from astrbot.core.message.components import At, BaseMessageComponent, Image, Reply
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot import logger

BAN_ME_QUOTES: list[str] = [
    "还真有人有这种奇怪的要求",
    "满足你",
    "静一会也挺好的",
    "是你自己要求的哈！",
    "行，你去静静",
    "好好好，禁了",
    "主人你没事吧？",
]


ADMIN_HELP = (
    "#【群管帮助】(指令前缀以bot配置为准)\n\n"
    "## NormalHandle 群管理\n"
    "- 禁言 <秒数> @人：禁言指定成员\n"
    "- 禁我 <秒数>：禁言自己\n"
    "- 解禁 @人：解除禁言\n"
    "- 开启全员禁言 / 关闭全员禁言：控制全群发言权限\n"
    "- 改名 <新昵称> @人 / 改我 <新昵称>：修改群名片\n"
    "- 头衔 <头衔> @人 / 申请头衔 <头衔>：设置群头衔（需群主）\n"
    "- 踢了 @人：移出群聊\n"
    "- 拉黑 @人：踢出并拉黑\n"
    "- 上管 @人 / 下管 @人：设置或取消管理员（需群主）\n"
    "- 撤回 (引用消息) / 撤回 @人 数量：撤回消息，默认10条\n"
    "- 设置群头像 (引用图片)：修改群头像\n"
    "- 设置群名 <新群名>：修改群名称\n"
    "- 设精 (引用消息) / 移精 (引用消息)：管理精华消息\n"
    "- 查看精华：查看精华列表\n\n"
    "## NoticeHandle 公告管理\n"
    "- 发布群公告 <内容> (可引用图片)：发布群公告\n"
    "- 查看群公告：查看群公告\n\n"
    "## EnhanceHandle 增强功能\n"
    "- 投票禁言 <秒数> @人：发起禁言投票\n"
    "- 赞同禁言 / 反对禁言：投票同意或反对\n"
    "（自动）违禁词检测：检测违禁词自动撤回并禁言\n"
    "（自动）刷屏检测：检测刷屏并自动处理\n\n"
    "## CurfewHandle 宵禁功能\n"
    "- 开启宵禁 HH:MM HH:MM：设置宵禁时间段\n"
    "- 关闭宵禁：关闭宵禁任务\n\n"
    "## JoinHandle 入群管理\n"
    "- 添加进群关键词 <关键词...> / 删除进群关键词 <关键词...>：管理自动同意关键词\n"
    "- 查看进群关键词：查看当前关键词\n"
    "- 添加进群黑名单 <QQ号...> / 删除进群黑名单 <QQ号...>：管理入群黑名单\n"
    "- 查看进群黑名单：查看当前群聊的进群黑名单\n"
    "- 批准 / 驳回 <理由>：审批入群申请\n"
    "（自动）监听进群退群事件：记录群员变动\n\n"
    "## MemberHandle 群成员工具\n"
    "- 群友信息：查看群成员活跃情况\n"
    "- 清理群友 <未发言天数> <群等级>：移除不活跃或低等级成员\n\n"
    "## FileHandle 群文件管理\n"
    "- 上传群文件 <文件夹名/文件名>：引用文件并上传\n"
    "- 删除群文件 <文件夹名或序号> <文件名或序号>：删除群文件或文件夹\n"
    "- 查看群文件 <文件夹名或序号> <文件名或序号>：查看文件夹或文件详情\n\n"
)


def print_logo():
    """打印欢迎 Logo"""
    logo = r"""
 ________  __                  __            __
|        \|  \                |  \          |  \
 \$$$$$$$$| $$____    ______  | $$  _______ | $$  ______    ______
    /  $$ | $$    \  |      \ | $$ /       \| $$ |      \  /      \
   /  $$  | $$$$$$$\  \$$$$$$\| $$|  $$$$$$$| $$  \$$$$$$\|  $$$$$$\
  /  $$   | $$  | $$ /      $$| $$ \$$    \ | $$ /      $$| $$   \$$
 /  $$___ | $$  | $$|  $$$$$$$| $$ _\$$$$$$\| $$|  $$$$$$$| $$
|  $$    \| $$  | $$ \$$    $$| $$|       $$| $$ \$$    $$| $$
 \$$$$$$$$ \$$   \$$  \$$$$$$$ \$$ \$$$$$$$  \$$  \$$$$$$$ \$$

        """
    print("\033[92m" + logo + "\033[0m")  # 绿色文字
    print("\033[94m欢迎使用群管插件！\033[0m")  # 蓝色文字


async def get_nickname(event: AiocqhttpMessageEvent, user_id) -> str:
    """获取指定群友的群昵称或Q名"""
    client = event.bot
    group_id = event.get_group_id()
    all_info = await client.get_group_member_info(
        group_id=int(group_id), user_id=int(user_id)
    )
    return all_info.get("card") or all_info.get("nickname")


def get_ats(event: AiocqhttpMessageEvent) -> list[str]:
    """获取被at者们的id列表"""
    return [
        str(seg.qq)
        for seg in event.get_messages()
        if (isinstance(seg, At) and str(seg.qq) != event.get_self_id())
    ]


def get_replyer_id(event: AiocqhttpMessageEvent) -> str | None:
    """获取被引用消息者的id"""
    for seg in event.get_messages():
        if isinstance(seg, Reply):
            return str(seg.sender_id)


def get_reply_message_str(event: AiocqhttpMessageEvent) -> str | None:
    """
    获取被引用的消息解析后的纯文本消息字符串。
    """
    return next(
        (
            seg.message_str
            for seg in event.message_obj.message
            if isinstance(seg, Reply)
        ),
        "",
    )


def format_time(timestamp):
    """格式化时间戳"""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")


async def download_file(url: str, save_path: str) -> str | None:
    """下载文件并保存到本地"""
    url = url.replace("https://", "http://")
    try:
        async with ClientSession() as client:
            response = await client.get(url)
            file = await response.read()

            os.makedirs(os.path.dirname(save_path), exist_ok=True)

            with open(save_path, "wb") as img_file:
                img_file.write(file)

            logger.info(f"文件已保存: {save_path}")
            return save_path
    except Exception as e:
        logger.error(f"文件下载并保存失败: {e}")
        return None


def extract_image_url(chain: list[BaseMessageComponent]) -> str | None:
    """从消息链中提取图片URL"""
    for seg in chain:
        if isinstance(seg, Image):
            return seg.url
        elif isinstance(seg, Reply) and seg.chain:
            for reply_seg in seg.chain:
                if isinstance(reply_seg, Image):
                    return reply_seg.url
    return None



