#!/usr/bin/env python3
"""Regenerate JOTY review with proper names."""

import json
from pathlib import Path

INPUT_JSON = Path(__file__).parent / "joty_candidates.json"
OUTPUT_JSON = Path(__file__).parent / "joty_candidates.json"
OUTPUT_MD = Path(__file__).parent / "joty_review.md"

NAME_MAP = {
    "(3660)": "Will",
    "(7478)": "Connor",
    "(0842)": "Shubs",
    "shubham.patel23": "Shubs",
    "gshellady23": "Geoff",
    "(9141)": "Adi",
    "(4025)": "Steven",
    "(9025)": "Morgan",
    "(8841)": "Geoff",
    "(0387)": "Andrew",
}

def map_name(sender):
    return NAME_MAP.get(sender, sender)

def main():
    with open(INPUT_JSON) as f:
        data = json.load(f)

    # Update names
    for item in data:
        item['joty_sender'] = map_name(item['joty_sender'])
        for msg in item['context']:
            msg['sender'] = map_name(msg['sender'])

    # Save updated JSON
    with open(OUTPUT_JSON, 'w') as f:
        json.dump(data, f, indent=2)

    # Regenerate markdown
    md_content = "# JOTY 2025 Candidates\n\n"
    md_content += "Review each JOTY and its context. Delete entries that aren't actual nominations.\n"
    md_content += "For jokes with images, search the quoted text on your phone to screenshot.\n\n"
    md_content += "---\n\n"

    for item in data:
        chat_name = item.get('chat_name', 'Unknown Chat')
        thread_marker = " 🧵" if item.get('is_thread') else ""
        md_content += f"## JOTY #{item['id']} — {item['joty_time']}{thread_marker}\n\n"
        md_content += f"**Chat:** {chat_name}  \n"
        md_content += f"**Nominated by:** {item['joty_sender']}\n\n"
        md_content += "**Context:**\n```\n"

        for msg in item['context']:
            img = " 📷" if msg.get('has_image') else ""
            indent = "    ↳ " if msg.get('in_thread') else ""
            if msg.get('is_joty'):
                md_content += f"{indent}{msg['time']} {msg['sender']}: ⭐ {msg['text']} ⭐\n"
            else:
                md_content += f"{indent}{msg['time']} {msg['sender']}: {msg['text']}{img}\n"

        md_content += "```\n\n"

        # Identify likely joke (exclude the JOTY message itself)
        joke_candidates = [m for m in item['context'] if m['text'] and len(m['text']) > 5 and not m.get('is_joty')]
        if joke_candidates:
            last_msg = joke_candidates[-1]
            md_content += f"**Likely joke:** \"{last_msg['text']}\" — {last_msg['sender']}"
            if last_msg.get('has_image'):
                md_content += f" 📷\n\n*Search on phone:* `{last_msg['text'][:40]}`"
            md_content += "\n\n"

        md_content += "---\n\n"

    with open(OUTPUT_MD, 'w') as f:
        f.write(md_content)

    print(f"Updated {len(data)} entries")
    print(f"Saved: {OUTPUT_JSON}")
    print(f"Saved: {OUTPUT_MD}")

if __name__ == "__main__":
    main()
