#!/usr/bin/env python3
"""Extract JOTY nominations with context - thread-aware version."""

import sqlite3
from datetime import datetime
from pathlib import Path
import json
import re

DB_PATH = Path.home() / "Library/Messages/chat.db"
OUTPUT_JSON = Path(__file__).parent / "joty_candidates.json"
OUTPUT_MD = Path(__file__).parent / "joty_review.md"

EXCLUDED_CHATS = {
    "Olympians",
    "Trading Cards",
    "shubham.patel23@yahoo.com",
    "brothers in christ ",  # has trailing space
    "Gnar 2.0",
    "Ballard Bois",
    "chat212275003571070051",
}

def apple_time_to_datetime(apple_time):
    unix_timestamp = apple_time / 1_000_000_000 + 978307200
    return datetime.fromtimestamp(unix_timestamp)

def is_actual_nomination(text):
    """Filter to only keep actual JOTY nominations, not meta-commentary."""
    text_lower = text.lower().strip()

    meta_patterns = [
        r'joty.*voting',
        r'joty.*results',
        r'joty.*tabulated',
        r'joty.*contender',
        r'joty.*nom',
        r'joty.*candidate',
        r'personal joty',
        r'doing joty',
        r'give the joty',
        r'joty.*winner',
        r'joty.*refractory',
        r'joty.*hilarity',
        r'strava joty',
        r'joty.*hit',
    ]

    for pattern in meta_patterns:
        if re.search(pattern, text_lower):
            return False

    if len(text.strip()) > 20:
        return False

    return True

def get_joty_messages(conn):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            m.ROWID,
            m.date,
            m.text,
            m.is_from_me,
            m.handle_id,
            m.cache_roomnames,
            m.thread_originator_guid,
            m.guid
        FROM message m
        WHERE LOWER(m.text) LIKE '%joty%'
        AND datetime(m.date/1000000000 + 978307200, 'unixepoch', 'localtime') >= '2025-01-01'
        AND m.text NOT LIKE 'Loved %'
        AND m.text NOT LIKE 'Liked %'
        AND m.text NOT LIKE 'Emphasized %'
        AND m.text NOT LIKE 'Laughed at %'
        AND m.text NOT LIKE 'Disliked %'
        ORDER BY m.date
    """)

    results = cursor.fetchall()
    return [r for r in results if is_actual_nomination(r[2])]

def get_chat_info(conn, joty_rowid):
    """Get chat name for a message."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.ROWID, c.display_name, c.chat_identifier
        FROM chat c
        JOIN chat_message_join cmj ON c.ROWID = cmj.chat_id
        WHERE cmj.message_id = ?
    """, (joty_rowid,))
    result = cursor.fetchone()
    if result:
        chat_id, display_name, chat_identifier = result
        name = display_name if display_name else chat_identifier
        return chat_id, name
    return None, "Unknown Chat"

def get_thread_context(conn, thread_originator_guid, joty_date, joty_rowid, chat_id, num_before_thread=5):
    """Get thread context: messages before thread start + all thread messages up to JOTY."""
    cursor = conn.cursor()

    # First, find the thread originator message
    cursor.execute("""
        SELECT m.ROWID, m.date, m.text, m.is_from_me, h.id as sender, m.cache_has_attachments
        FROM message m
        LEFT JOIN handle h ON m.handle_id = h.ROWID
        WHERE m.guid = ?
    """, (thread_originator_guid,))

    originator = cursor.fetchone()
    if not originator:
        return [], False

    originator_rowid, originator_date, _, _, _, _ = originator

    # Get messages before the thread originator (for context)
    cursor.execute("""
        SELECT m.ROWID, m.date, m.text, m.is_from_me, h.id as sender, m.cache_has_attachments
        FROM message m
        JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
        LEFT JOIN handle h ON m.handle_id = h.ROWID
        WHERE cmj.chat_id = ?
        AND m.date < ?
        AND m.text IS NOT NULL
        AND m.text != ''
        AND m.text NOT LIKE 'Loved %'
        AND m.text NOT LIKE 'Liked %'
        AND m.text NOT LIKE 'Emphasized %'
        AND m.text NOT LIKE 'Laughed at %'
        AND m.thread_originator_guid IS NULL
        ORDER BY m.date DESC
        LIMIT ?
    """, (chat_id, originator_date, num_before_thread))

    pre_thread_msgs = list(reversed(cursor.fetchall()))

    # Add the thread originator
    thread_msgs = [originator]

    # Get all thread replies up to (but not including) JOTY - we add JOTY separately at the end
    cursor.execute("""
        SELECT m.ROWID, m.date, m.text, m.is_from_me, h.id as sender, m.cache_has_attachments
        FROM message m
        LEFT JOIN handle h ON m.handle_id = h.ROWID
        WHERE m.thread_originator_guid = ?
        AND m.date < ?
        AND m.text IS NOT NULL
        AND m.text != ''
        AND m.text NOT LIKE 'Loved %'
        AND m.text NOT LIKE 'Liked %'
        AND m.text NOT LIKE 'Emphasized %'
        AND m.text NOT LIKE 'Laughed at %'
        ORDER BY m.date
    """, (thread_originator_guid, joty_date))

    thread_replies = cursor.fetchall()
    thread_msgs.extend(thread_replies)

    # Mark which messages are part of the thread
    # Return tuple: (messages, is_thread, thread_start_index)
    all_msgs = pre_thread_msgs + thread_msgs
    thread_start_index = len(pre_thread_msgs)  # Index where thread begins
    return all_msgs, True, thread_start_index

def get_regular_context(conn, joty_rowid, joty_date, chat_id, num_before=15):
    """Get regular context for non-threaded JOTY."""
    cursor = conn.cursor()

    cursor.execute("""
        SELECT m.ROWID, m.date, m.text, m.is_from_me, h.id as sender, m.cache_has_attachments
        FROM message m
        JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
        LEFT JOIN handle h ON m.handle_id = h.ROWID
        WHERE cmj.chat_id = ?
        AND m.date < ?
        AND m.text IS NOT NULL
        AND m.text != ''
        AND m.text NOT LIKE 'Loved %'
        AND m.text NOT LIKE 'Liked %'
        AND m.text NOT LIKE 'Emphasized %'
        AND m.text NOT LIKE 'Laughed at %'
        ORDER BY m.date DESC
        LIMIT ?
    """, (chat_id, joty_date, num_before))

    return list(reversed(cursor.fetchall()))

def get_handle_name(conn, handle_id):
    if not handle_id:
        return "Me"
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM handle WHERE ROWID = ?", (handle_id,))
    result = cursor.fetchone()
    return result[0] if result else "Unknown"

def format_sender(sender):
    if sender == "Me":
        return "Jesse"
    if sender and sender.startswith("+1"):
        return f"({sender[-4:]})"
    if sender and "@" in sender:
        return sender.split("@")[0]
    return sender or "Unknown"

def main():
    conn = sqlite3.connect(DB_PATH)

    joty_messages = get_joty_messages(conn)
    print(f"Found {len(joty_messages)} actual JOTY nominations in 2025")

    all_contexts = []
    md_content = "# JOTY 2025 Candidates\n\n"
    md_content += "Review each JOTY and its context. Delete entries that aren't actual nominations.\n\n"
    md_content += "---\n\n"

    idx = 0
    for joty in joty_messages:
        rowid, date, text, is_from_me, handle_id, cache_roomnames, thread_originator_guid, guid = joty

        joty_time = apple_time_to_datetime(date)
        joty_sender = "Jesse" if is_from_me else format_sender(get_handle_name(conn, handle_id))

        chat_id, chat_name = get_chat_info(conn, rowid)

        # Skip excluded chats
        if chat_name in EXCLUDED_CHATS:
            continue

        idx += 1

        # Determine if this is a thread reply or regular message
        is_thread = False
        thread_start_index = 0
        if thread_originator_guid and chat_id:
            context_msgs, is_thread, thread_start_index = get_thread_context(
                conn, thread_originator_guid, date, rowid, chat_id
            )

        if not is_thread and chat_id:
            context_msgs = get_regular_context(conn, rowid, date, chat_id)
        elif not chat_id:
            context_msgs = []

        context_list = []
        for i, msg in enumerate(context_msgs):
            msg_rowid, msg_date, msg_text, msg_is_from_me, sender, has_attachments = msg
            sender_name = "Jesse" if msg_is_from_me else format_sender(sender)

            # Mark if this message is part of the thread (at or after thread_start_index)
            in_thread = is_thread and i >= thread_start_index

            context_list.append({
                "time": apple_time_to_datetime(msg_date).strftime("%H:%M"),
                "sender": sender_name,
                "text": msg_text,
                "has_image": bool(has_attachments),
                "in_thread": in_thread,
            })

        # Add the JOTY message itself at the end (it's part of the thread if this is a thread)
        context_list.append({
            "time": joty_time.strftime("%H:%M"),
            "sender": joty_sender,
            "text": text.strip(),
            "has_image": False,
            "is_joty": True,
            "in_thread": is_thread,
        })

        entry = {
            "id": idx,
            "joty_time": joty_time.strftime("%Y-%m-%d %H:%M"),
            "joty_text": text.strip(),
            "joty_sender": joty_sender,
            "chat_name": chat_name,
            "is_thread": is_thread,
            "context": context_list
        }
        all_contexts.append(entry)

        # Build markdown
        thread_marker = " 🧵" if is_thread else ""
        md_content += f"## JOTY #{idx} — {joty_time.strftime('%b %d, %Y %I:%M %p')}{thread_marker}\n\n"
        md_content += f"**Chat:** {chat_name}  \n"
        md_content += f"**Nominated by:** {joty_sender}\n\n"
        md_content += "**Context:**\n```\n"

        for msg in context_list:
            img = " 📷" if msg.get('has_image') else ""
            if msg.get('is_joty'):
                md_content += f"{msg['time']} {msg['sender']}: ⭐ {msg['text']} ⭐\n"
            else:
                md_content += f"{msg['time']} {msg['sender']}: {msg['text']}{img}\n"

        md_content += "```\n\n"

        # Identify likely joke
        joke_candidates = [m for m in context_list if m['text'] and len(m['text']) > 5 and not m.get('is_joty')]
        if joke_candidates:
            last_msg = joke_candidates[-1]
            md_content += f"**Likely joke:** \"{last_msg['text']}\" — {last_msg['sender']}"
            if last_msg.get('has_image'):
                md_content += f" 📷\n\n*Search on phone:* `{last_msg['text'][:40]}`"
            md_content += "\n\n"

        md_content += "---\n\n"

    # Save JSON
    with open(OUTPUT_JSON, 'w') as f:
        json.dump(all_contexts, f, indent=2)

    # Save markdown
    with open(OUTPUT_MD, 'w') as f:
        f.write(md_content)

    print(f"Saved JSON: {OUTPUT_JSON}")
    print(f"Saved review file: {OUTPUT_MD}")

    # Count threads
    thread_count = sum(1 for ctx in all_contexts if ctx['is_thread'])
    print(f"Thread replies: {thread_count}, Regular messages: {len(all_contexts) - thread_count}")

    conn.close()

if __name__ == "__main__":
    main()
