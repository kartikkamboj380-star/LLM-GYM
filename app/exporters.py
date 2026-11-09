"""User-initiated exports with no credentials or email/OTP content."""


def _assistant_metadata(message: dict) -> str:
    details = []
    if message.get("model"):
        details.append(f"Model: `{message['model']}`")
    input_tokens = message.get("input_tokens")
    output_tokens = message.get("output_tokens")
    if input_tokens is not None or output_tokens is not None:
        details.append(f"Tokens: {input_tokens if input_tokens is not None else '—'} in / {output_tokens if output_tokens is not None else '—'} out")
    else:
        details.append("Tokens: not reported")
    if message.get("finish_reason"):
        details.append(f"Finish: {message['finish_reason']}")
    if message.get("truncated"):
        details.append("Output truncated")
    if message.get("context_messages") is not None:
        count = message["context_messages"]
        details.append(f"Context: {count} message{'' if count == 1 else 's'}")
    if message.get("context_truncated"):
        details.append("Earlier history omitted")
    if message.get("retrieved_memory_count") is not None:
        details.append(f"Memories: {message['retrieved_memory_count']}")
    return " · ".join(details)


def conversation_markdown(conversation: dict) -> str:
    lines = [
        f"# {conversation['title']}",
        "",
        f"- Conversation ID: `{conversation['id']}`",
        f"- Provider: {conversation.get('provider', 'unknown')}",
        f"- Configured model: {conversation.get('model', 'unknown')}",
        f"- Created: {conversation['created_at']}",
        f"- Updated: {conversation['updated_at']}",
        "",
    ]
    for message in conversation["messages"]:
        speaker = "You" if message["role"] == "user" else f"Assistant ({message.get('provider') or 'unknown'})"
        lines.extend([f"## {speaker}", ""])
        if message["role"] == "assistant":
            lines.extend([f"*{_assistant_metadata(message)}*", ""])
        lines.extend([message["content"], ""])
    if not conversation["messages"]:
        lines.append("No messages in this conversation.")
    return "\n".join(lines).rstrip() + "\n"
