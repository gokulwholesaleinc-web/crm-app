"""Multi-iteration tool-use agent loop for the AI assistant."""

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.action_safety import ActionRisk, classify_action, get_confirmation_description, requires_confirmation
from src.ai.models import AIActionLog
from src.ai.learning_service import AILearningService

logger = logging.getLogger(__name__)

MAX_AGENT_ITERATIONS = 10


def _summarize_result(data: Dict[str, Any]) -> str:
    if "error" in data:
        return f"Error: {data['error']}"
    if "message" in data:
        return data["message"]
    if "count" in data:
        return f"Found {data['count']} results"
    if "report_type" in data:
        return f"{data['report_type']} report generated"
    return "Completed"


class AIToolExecutor:
    def __init__(self, db: AsyncSession, openai_client, tools: List[Dict], system_prompt: str):
        self.db = db
        self.client = openai_client
        self.tools = tools
        self.system_prompt = system_prompt

    async def run(
        self,
        query: str,
        user_id: int,
        session_id: str,
        history: List[Dict],
        execute_fn,
        save_conversation_fn,
    ) -> Dict[str, Any]:
        learning_service = AILearningService(self.db)

        await save_conversation_fn(user_id, session_id, "user", query)

        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": query})

        actions_taken = []

        try:
            for _iteration in range(MAX_AGENT_ITERATIONS):
                response = await self.client.chat.completions.create(
                    model="gpt-4",
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto",
                )

                message = response.choices[0].message

                if not message.tool_calls:
                    response_text = message.content or ""

                    await save_conversation_fn(user_id, session_id, "assistant", response_text)

                    tool_log = [a for a in actions_taken] if actions_taken else None
                    await learning_service.log_interaction(
                        user_id=user_id,
                        query=query,
                        tool_calls=tool_log,
                    )

                    return {
                        "response": response_text,
                        "data": None,
                        "actions_taken": actions_taken,
                        "session_id": session_id,
                    }

                messages.append(message)

                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}

                    if requires_confirmation(func_name):
                        description = get_confirmation_description(func_name, func_args)
                        await self._log_action(
                            user_id=user_id,
                            session_id=session_id,
                            function_name=func_name,
                            arguments=func_args,
                            result={"status": "pending_confirmation"},
                            risk_level=classify_action(func_name).value,
                            was_confirmed=False,
                        )
                        return {
                            "response": f"This action requires confirmation: {description}",
                            "data": None,
                            "confirmation_required": True,
                            "pending_action": {
                                "function_name": func_name,
                                "arguments": func_args,
                                "description": description,
                                "session_id": session_id,
                            },
                            "actions_taken": actions_taken,
                            "session_id": session_id,
                        }

                    data = await execute_fn(func_name, func_args, user_id)

                    risk = classify_action(func_name)
                    await self._log_action(
                        user_id=user_id,
                        session_id=session_id,
                        function_name=func_name,
                        arguments=func_args,
                        result=data,
                        risk_level=risk.value,
                        was_confirmed=(risk == ActionRisk.READ),
                    )

                    actions_taken.append({
                        "function": func_name,
                        "arguments": func_args,
                        "result_summary": _summarize_result(data),
                    })

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(data),
                    })

            final_response = await self.client.chat.completions.create(
                model="gpt-4",
                messages=messages + [
                    {"role": "user", "content": "Please summarize what was accomplished."}
                ],
            )

            response_text = final_response.choices[0].message.content or ""

            await save_conversation_fn(user_id, session_id, "assistant", response_text)

            return {
                "response": response_text,
                "data": None,
                "actions_taken": actions_taken,
                "session_id": session_id,
            }

        except Exception as e:
            return {
                "response": f"I encountered an error processing your request: {str(e)}",
                "data": None,
                "error": str(e),
                "actions_taken": actions_taken,
                "session_id": session_id,
            }

    async def _log_action(
        self,
        user_id: int,
        session_id: str,
        function_name: str,
        arguments: Dict[str, Any],
        result: Dict[str, Any],
        risk_level: str,
        was_confirmed: bool,
        model_used: str = "gpt-4",
        tokens_used: int = None,
    ) -> None:
        result_to_store = result
        result_str = json.dumps(result)
        if len(result_str) > 5000:
            result_to_store = {"truncated": True, "summary": _summarize_result(result)}

        log_entry = AIActionLog(
            user_id=user_id,
            session_id=session_id,
            function_name=function_name,
            arguments=arguments,
            result=result_to_store,
            risk_level=risk_level,
            was_confirmed=was_confirmed,
            model_used=model_used,
            tokens_used=tokens_used,
        )
        self.db.add(log_entry)
        await self.db.flush()
