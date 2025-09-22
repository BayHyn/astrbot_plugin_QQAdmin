import re
from typing import Any
from astrbot.api.star import Context
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot import logger
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from data.plugins.astrbot_plugin_qqadmin.utils import get_ats


class LLMHandle:
    def __init__(self, context: Context, config: AstrBotConfig):
        self.context = context
        self.conf = config

    def _build_user_context(
        self, round_messages: list[dict[str, Any]], target_id: str
    ) -> list[dict[str, str]]:
        """
        把指定用户在所有回合里的纯文本消息打包成 openai-style 的 user 上下文。
        """
        contexts: list[dict[str, str]] = []

        for msg in round_messages:
            # 1. 过滤发送者
            if msg["sender"]["user_id"] != int(target_id):
                continue
            # 2. 提取并拼接所有 text 片段
            text_segments = [
                seg["data"]["text"] for seg in msg["message"] if seg["type"] == "text"
            ]
            text = "".join(text_segments).strip()
            # 3. 仅当真正说了话才保留
            if text:
                contexts.append({"role": "user", "content": text})
        return contexts

    async def get_msg_contexts(
        self, event: AiocqhttpMessageEvent, target_id: str, query_rounds: int
    ) -> list[dict]:
        """持续获取群聊历史消息直到达到要求"""
        group_id = event.get_group_id()
        message_seq = 0
        contexts: list[dict] = []
        for _ in range(query_rounds):
            payloads = {
                "group_id": group_id,
                "message_seq": message_seq,
                "count": 200,
                "reverseOrder": True,
            }
            result: dict = await event.bot.api.call_action(
                "get_group_msg_history", **payloads
            )
            round_messages = result["messages"]
            message_seq = round_messages[0]["message_id"]

            contexts.extend(self._build_user_context(round_messages, target_id))
        return contexts

    async def get_llm_respond(
        self, system_prompt: str, contexts: list[dict]
    ) -> str | None:
        """调用llm回复"""
        get_using = self.context.get_using_provider()
        if not get_using:
            return None
        print(contexts)
        try:
            llm_response = await get_using.text_chat(
                system_prompt=system_prompt,
                prompt="这是这位群友的聊天记录",
                contexts=contexts,
            )
            return llm_response.completion_text

        except Exception as e:
            logger.error(f"LLM 调用失败：{e}")
            return None



    async def ai_set_card(self, event: AiocqhttpMessageEvent, at_str: str):
        """让AI设置群友的群名片"""
        at_ids = get_ats(event)
        if not at_ids:
            await event.send(event.plain_result("请@群友"))
            return

        target_id: str = at_ids[0]
        query_rounds = 15
        raw_card = at_str.removeprefix("@").split("(")[0]

        logger.info(f"正在根据 {raw_card} 的聊天记录生成新昵称...")


        contexts = await self.get_msg_contexts(event, target_id, query_rounds)
        if not contexts:
            await event.send(event.plain_result("聊天记录为空"))
            return
        logger.debug(contexts)

        system_prompt = (
            "请根据这位群友的聊天记录，生成一个昵称。\n"
            "注意：昵称要简洁且符合这位群友的人格特征。\n"
            "请只返回一个昵称，并且用 Markdown 加粗格式返回，例如：**小明**。\n"
            "不要附带任何多余的文字、解释或标点。"
        )

        llm_respond = await self.get_llm_respond(
            system_prompt=system_prompt, contexts=contexts
        )
        if not llm_respond:
            await event.send(event.plain_result("LLM响应为空"))
            return

        # 提取 **加粗** 的内容
        match = re.search(r"\*\*(.+?)\*\*", llm_respond)
        if not match:
            await event.send(
                event.plain_result(f"未能从LLM回复中提取到昵称: {llm_respond}")
            )
            return
        # 保留中英文，最多8个字符
        new_card = re.sub(r"[^a-zA-Z\u4e00-\u9fff]", "", match.group(1))[:8]

        await event.bot.set_group_card(
            group_id=int(event.get_group_id()),
            user_id=int(target_id),
            card=new_card,
        )
        await event.send(event.plain_result(f"给{raw_card}取的新昵称：{new_card}"))
        logger.info(f"已为 {target_id} 设置群昵称: {new_card}")
