#!/usr/bin/env python3
"""Extract JOTY nominations with context from iMessage database."""

import sqlite3
from datetime import datetime
from pathlib import Path
import json

DB_PATH = Path.home() / "Library/Messages/chat.db"
OUTPUT_PATH = Path(__file__).parent / "joty_contexts.json"

def apple_time_to_datetime(apple_time):
    """Convert Apple's timestamp to datetime."""
    unix_timestamp = apple_time / 1_000_000_000 + 978307200
    return datetime.fromtimestamp(unix_timestamp)

def get_joty_messages(conn):
    """Get all JOTY nomination messages from 2025."""
    cursor = conn.cursor()

    # Get JOTY messages that are actual nominations (just "JOTY" or "JOTY [name]")
    cursor.execute("""
        SELECT
            m.ROWID,
            m.date,
            m.text,
            m.is_from_me,
            m.handle_id,
            m.cache_roomnames
        FROM message m
        WHERE LOWER(m.text) LIKE '%joty%'
        AND datetime(m.date/1000000000 + 978307200, 'unixepoch', 'localtime') >= '2025-01-01'
        AND m.text NOT LIKE 'Loved %'
        AND m.text NOT LIKE 'Liked %'
        AND m.text NOT LIKE 'Emphasized %'
        AND m.text NOT LIKE 'Laughed at %'
        AND m.text NOT LIKE 'Disliked %'
        AND LENGTH(TRIM(m.text)) <= 30  -- Short messages are likely nominations
        ORDER BY m.date
    """)

    return cursor.fetchall()

def get_context_messages(conn, joty_rowid, joty_date, cache_roomnames, num_before=15):
    """Get messages before the JOTY nomination in the same chat."""
    cursor = conn.cursor()

    # Find the chat this message belongs to
    cursor.execute("""
        SELECT chat_id FROM chat_message_join WHERE message_id = ?
    """, (joty_rowid,))

    result = cursor.fetchone()
    if not result:
        return []

    chat_id = result[0]

    # Get preceding messages in the same chat
    cursor.execute("""
        SELECT
            m.ROWID,
            m.date,
            m.text,
            m.is_from_me,
            h.id as sender,
            m.cache_has_attachments
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

    messages = cursor.fetchall()
    return list(reversed(messages))  # Chronological order

def get_handle_name(conn, handle_id):
    """Get the phone/email for a handle."""
    if not handle_id:
        return "Me"
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM handle WHERE ROWID = ?", (handle_id,))
    result = cursor.fetchone()
    return result[0] if result else "Unknown"

def main():
    conn = sqlite3.connect(DB_PATH)

    joty_messages = get_joty_messages(conn)
    print(f"Found {len(joty_messages)} JOTY nominations in 2025")

    all_contexts = []

    for joty in joty_messages:
        rowid, date, text, is_from_me, handle_id, cache_roomnames = joty

        joty_time = apple_time_to_datetime(date)
        joty_sender = "Me" if is_from_me else get_handle_name(conn, handle_id)

        context_msgs = get_context_messages(conn, rowid, date, cache_roomnames)

        context_list = []
        for msg in context_msgs:
            msg_rowid, msg_date, msg_text, msg_is_from_me, sender, has_attachments = msg
            context_list.append({
                "time": apple_time_to_datetime(msg_date).strftime("%Y-%m-%d %H:%M"),
                "sender": "Me" if msg_is_from_me else (sender or "Unknown"),
                "text": msg_text,
                "has_image": bool(has_attachments)
            })

        all_contexts.append({
            "joty_id": rowid,
            "joty_time": joty_time.strftime("%Y-%m-%d %H:%M"),
            "joty_text": text,
            "joty_sender": joty_sender,
            "context": context_list
        })

    # Save to JSON
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(all_contexts, f, indent=2)

    print(f"Saved to {OUTPUT_PATH}")

    # Also print a readable summary
    print("\n" + "="*80)
    for i, ctx in enumerate(all_contexts, 1):
        print(f"\n### JOTY #{i} - {ctx['joty_time']} (by {ctx['joty_sender']})")
        print(f"### JOTY text: {ctx['joty_text']}")
        print("-" * 40)
        for msg in ctx['context']:
            img_marker = " [📷 IMAGE]" if msg['has_image'] else ""
            print(f"  {msg['time']} | {msg['sender']}: {msg['text']}{img_marker}")
        print("="*80)

    conn.close()

if __name__ == "__main__":
    main()
