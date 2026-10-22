import os

from openai import AsyncOpenAI
from app.core.config import settings
from typing import AsyncGenerator

class LLMClient:
    def __init__(self,provider:str=None ):
        self.provider = provider or settings.DEFAULT_PROVIDER

        if self.provider=="deepseek":
            self.client=AsyncOpenAI(
                api_key=settings.DEEPSEEK_API_KEY,
                base_url=settings.DEEPSEEK_BASE_URL,
                default_headers={
                    "x-langfuse-public-key":os.getenv("LANGUSE_PUBLIC_KEY"),
                    "x-langfuse-secret-key":os.getenv("LANGUSE_SECRET_KEY"),
                }if os.getenv("LANGUSE_PUBLIC_KEY") else None,

            )
            self.model="deepseek-chat"
        elif self.provider=="ollama":
            self.client=AsyncOpenAI(
                api_key="ollama",
                base_url=f"{settings.OLLAMA_URL}/v1",
            )
            self.model=settings.OLLAMA_MODEL
        else:
            raise ValueError(f"Invalid provider: {self.provider}")

    async def chat_stream(self,prompt:str)->AsyncGenerator[str,None]:
        """流式对话生成"""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                temperature=0.1,
                steam_options={"include_usage": True}
            )
            async for chunk in response:
                content=chunk.choices[0].delta.content
                if content:
                    yield content
        except Exception as e:
            yield f"[错误,调用模型失败:{str(e)}]"


def get_llm_client(provider:str=None)->LLMClient:
    return LLMClient(provider)




