# -*- coding: utf-8 -*-
"""Factory for creating chat models and formatters."""

import logging
import os
from typing import TYPE_CHECKING, Optional, Sequence, Tuple, Type

from agentscope.formatter import FormatterBase, OpenAIChatFormatter
from agentscope.model import ChatModelBase, OpenAIChatModel

from .utils.tool_message_utils import _sanitize_tool_messages
from ..local_models import create_local_chat_model
from ..providers import (
    get_active_llm_config,
    get_chat_model_class,
    get_provider_chat_model,
    load_providers_json,
)

if TYPE_CHECKING:
    from ..providers import ResolvedModelConfig

logger = logging.getLogger(__name__)

_CHAT_MODEL_FORMATTER_MAP: dict[Type[ChatModelBase], Type[FormatterBase]] = {
    OpenAIChatModel: OpenAIChatFormatter,
}


def _get_formatter_for_chat_model(
    chat_model_class: Type[ChatModelBase],
) -> Type[FormatterBase]:
    return _CHAT_MODEL_FORMATTER_MAP.get(chat_model_class, OpenAIChatFormatter)


def _create_file_block_support_formatter(
    base_formatter_class: Type[FormatterBase],
) -> Type[FormatterBase]:

    class FileBlockSupportFormatter(base_formatter_class):
        async def _format(self, msgs):
            msgs = _sanitize_tool_messages(msgs)
            return await super()._format(msgs)

        @staticmethod
        def convert_tool_result_to_string(
            output: str | list[dict],
        ) -> tuple[str, Sequence[Tuple[str, dict]]]:
            if isinstance(output, str):
                return output, []
            try:
                return base_formatter_class.convert_tool_result_to_string(output)
            except ValueError as e:
                if "Unsupported block type: file" not in str(e):
                    raise
                textual_output = []
                multimodal_data = []
                for block in output:
                    if not isinstance(block, dict) or "type" not in block:
                        raise ValueError(f"Invalid block: {block}") from e
                    if block["type"] == "file":
                        file_path = block.get("path", "") or block.get("url", "")
                        file_name = block.get("name", file_path)
                        textual_output.append(
                            f"The returned file '{file_name}' can be found at: {file_path}"
                        )
                        multimodal_data.append((file_path, block))
                    else:
                        text, data = base_formatter_class.convert_tool_result_to_string([block])
                        textual_output.append(text)
                        multimodal_data.extend(data)
                if len(textual_output) == 0:
                    return "", multimodal_data
                elif len(textual_output) == 1:
                    return textual_output[0], multimodal_data
                else:
                    return "\n".join("- " + _ for _ in textual_output), multimodal_data

    FileBlockSupportFormatter.__name__ = f"FileBlockSupport{base_formatter_class.__name__}"
    return FileBlockSupportFormatter


def create_model_and_formatter(
    llm_cfg: Optional["ResolvedModelConfig"] = None,
) -> Tuple[ChatModelBase, FormatterBase]:
    if llm_cfg is None:
        llm_cfg = get_active_llm_config()
    model, chat_model_class = _create_model_instance(llm_cfg)
    formatter = _create_formatter_instance(chat_model_class)
    return model, formatter


def _create_model_instance(
    llm_cfg: Optional["ResolvedModelConfig"],
) -> Tuple[ChatModelBase, Type[ChatModelBase]]:
    if llm_cfg and llm_cfg.is_local:
        model = create_local_chat_model(
            model_id=llm_cfg.model,
            stream=True,
            generate_kwargs={"max_tokens": None},
        )
        return model, OpenAIChatModel

    chat_model_class = _get_chat_model_class_from_provider()
    model = _create_remote_model_instance(chat_model_class)
    return model, chat_model_class


def _get_chat_model_class_from_provider() -> Type[ChatModelBase]:
    chat_model_class = OpenAIChatModel
    try:
        providers_data = load_providers_json()
        provider_id = providers_data.active_llm.provider_id
        if provider_id:
            chat_model_name = get_provider_chat_model(provider_id, providers_data)
            chat_model_class = get_chat_model_class(chat_model_name)
    except Exception as e:
        logger.debug("Failed to determine chat model from provider: %s", e)
    return chat_model_class


def _create_remote_model_instance(
    chat_model_class: Type[ChatModelBase],
) -> ChatModelBase:
    """Create remote model - KIMI ONLY via Baseten.
    
    ALWAYS uses environment variables, ignores any saved config.
    """
    # ALWAYS use environment variables - ignore llm_cfg completely
    api_key = os.getenv("BASETEN_API_KEY", "")
    model_name = os.getenv("BASETEN_MODEL", "moonshotai/Kimi-K2.5")
    base_url = "https://inference.baseten.co/v1"
    
    if not api_key:
        raise ValueError(
            "BASETEN_API_KEY environment variable is required. "
            "Set it to your Baseten API key."
        )

    logger.info(f"Using Kimi model: {model_name} via Baseten")

    model = chat_model_class(
        model_name,
        api_key=api_key,
        stream=True,
        client_kwargs={"base_url": base_url},
    )

    return model


def _create_formatter_instance(chat_model_class: Type[ChatModelBase]) -> FormatterBase:
    base_formatter_class = _get_formatter_for_chat_model(chat_model_class)
    formatter_class = _create_file_block_support_formatter(base_formatter_class)
    return formatter_class()


__all__ = ["create_model_and_formatter"]
