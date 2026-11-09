"""User-initiated exports with no credentials or email/OTP content."""


def conversation_markdown(conversation: dict) -> str:
    lines = [
        f"# {conversation['title']}",
        "",
        f"- Conversation ID: `{conversation['id']}`",
        f"- Created: {conversation['created_at']}",
        f"- Updated: {conversation['updated_at']}",
        "",
    ]
    for message in conversation["messages"]:
        speaker = "You" if message["role"] == "user" else f"Assistant ({message.get('provider') or 'unknown'})"
        lines.extend([f"## {speaker}", "", message["content"], ""])
    if not conversation["messages"]:
        lines.append("No messages in this conversation.")
    return "\n".join(lines).rstrip() + "\n"
