"""
Video Script Agent — Telegram bot that ghost-writes short-film / reel scripts
in the user's personal voice, powered by Claude.

The agent loads a style guide + verbatim sample scripts from disk on startup
and uses them as a reference so every output reads like the same human wrote it.
"""

import os
import asyncio
import logging
from pathlib import Path

from anthropic import Anthropic
from telegram import Update, constants
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ─── CONFIG (env vars) ──────────────────────────────────────

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TG_TOKEN          = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")  # optional — restrict to one chat

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
MAX_TOKENS   = int(os.getenv("MAX_TOKENS", "8000"))
TEMPERATURE  = float(os.getenv("TEMPERATURE", "0.9"))

SAMPLES_DIR = Path(os.getenv("SAMPLES_DIR", "samples"))
STYLE_GUIDE = Path(os.getenv("STYLE_GUIDE", "style_guide.md"))

TG_MAX = 3900  # safely under Telegram's 4096 hard limit per message

# ─── SETUP ──────────────────────────────────────────────────

if not ANTHROPIC_API_KEY:
    raise SystemExit("Missing ANTHROPIC_API_KEY env var.")
if not TG_TOKEN:
    raise SystemExit("Missing TELEGRAM_BOT_TOKEN env var.")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("script-agent")

client = Anthropic(api_key=ANTHROPIC_API_KEY)

# ─── STYLE LOADING ──────────────────────────────────────────

def load_style_block() -> str:
    """Concatenate the style guide and all sample scripts into a single reference block."""
    parts: list[str] = []
    if STYLE_GUIDE.exists():
        parts.append("=== STYLE GUIDE ===\n" + STYLE_GUIDE.read_text())
    if SAMPLES_DIR.exists():
        sample_files = sorted(
            list(SAMPLES_DIR.glob("*.md")) + list(SAMPLES_DIR.glob("*.txt"))
        )
        for i, f in enumerate(sample_files, 1):
            parts.append(f"=== SAMPLE {i}: {f.stem} ===\n{f.read_text()}")
    return "\n\n".join(parts)


def build_system_prompt(style_block: str) -> str:
    return f"""You are a screenwriter ghost-writing for ONE specific writer.
Your only job: produce a script that reads exactly as if THIS writer typed it at 2 AM —
not polished, not committee-approved, not "AI-generated". You are not a generic
screenwriting assistant. You are this person's voice.

# The writer's voice

Read the style guide and samples below carefully. They are the writer's actual work.
Absorb:
- sentence rhythm (how short/long do their lines run?)
- dialogue register (how do their characters actually talk?)
- how they break tone (heroic V.O. → "I need sleep")
- signature details (specific times like 2:47 AM, dim yellow/blue hue, solo-actor framing)
- how they open and close scenes
- how they format (SCENE/SHOT shooting-script OR INT./EXT. screenplay — both are theirs)

{style_block}

# Human-writing rules (non-negotiable)

A reader should not be able to tell an AI wrote this. That means:

1. NO generic screenwriting filler. Never write "the camera slowly reveals", "we see",
   "in a poignant moment", "the tension is palpable". Those are AI tells.
2. NO stacked adjectives. "A quiet, dimly-lit, melancholy room" is AI.
   "Dim yellow light. 2:47 AM." is human.
3. Varied sentence length. Some fragments. Some runs. No metronome.
4. Specific concrete nouns > vague mood words. "half-drunk coffee", "chili, egg, basil",
   "spatula like a sword" — that's what the writer does.
5. Dialogue must sound said out loud. Read every line aloud in your head. Cut anything
   that sounds written.
6. Don't explain feelings. Show a gesture, a beat of silence, an object.
7. Leave small imperfections. Real writers don't tie every thread. An unresolved rattle.
   A half-smile. A "CUT TO BLACK" that doesn't spell out the meaning.
8. No "In conclusion", no AI-style themes summary — UNLESS the user asks for a themes
   block like in "A Day in My Life" (that's part of their style for slice-of-life).
9. When in doubt, shorter. The writer prefers tight.

# Format decision

Pick ONE format based on the request:
- **Shooting script** (SCENE / SHOT / timecode blocks, SFX + MUSIC CUE markers) — for
  tight reels, action-comedy, anything ≤ 3 min. Triggers: "reel", "TikTok", "short",
  "action", "comedy", request for shot-by-shot coverage.
- **Screenplay** (INT./EXT. slugs, V.O. blocks) — for longer slice-of-life, drama,
  introspection. Triggers: "film", "drama", "slice of life", "story", "7 min", "10 min".
- **Hybrid** (screenplay body with SFX/MUSIC markers inline) — for 3-min comedy that
  needs both a narrative feel and shoot-ready cues.

# Required header

Every script starts with:

```
Title: ...
Genre: ...
Runtime: ...
Actor(s): ...
Setting: ...
```

# Required ending

End with a specific final image or line — never "and everyone felt better". Leave a
hook, a rattle, a pause. The writer's endings linger.

# Language

Burmese (မြန်မာ), English, or natural code-switch — match the user's brief. If the user
writes in Burmese, it's fine to keep some lines in Burmese (especially character dialogue
and slang) and some in English (camera / SFX directions, slug lines). Don't force
translation either direction.

# Output contract

Deliver ONLY the script. No preamble ("Here's your script..."), no post-script notes
("Hope this helps!"). Start from the header, end at THE END / FADE OUT / CUT TO BLACK.

# Self-check before sending

Before you finalize, silently scan your draft for:
- stacked adjectives → collapse to one sensory hit
- "we see" / "camera pans to reveal" / "tension is palpable" → delete
- dialogue that sounds written, not spoken → rewrite
- symmetry / metronome rhythm → break it
- explained feelings → replace with a gesture or an object

If any appear, rewrite before sending.
"""


STYLE_BLOCK = load_style_block()
SYSTEM_PROMPT = build_system_prompt(STYLE_BLOCK)
log.info(f"Loaded {len(STYLE_BLOCK):,} chars of style reference.")

# ─── CLAUDE CALL ────────────────────────────────────────────

def generate_script(user_brief: str) -> str:
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_brief}],
    )
    return "".join(getattr(block, "text", "") for block in resp.content).strip()

# ─── TELEGRAM HELPERS ───────────────────────────────────────

WELCOME = (
    "🎬 Script agent ready.\n\n"
    "Describe the scene you want and I'll write it in your voice.\n\n"
    "Examples:\n"
    "• a 30s reel about an awkward elevator moment\n"
    "• 3min action-comedy, guy finds a wallet in the rain\n"
    "• 7min slice-of-life, two strangers at a bus stop at dawn\n\n"
    "Commands:\n"
    "/reel <idea>  — 30–60s vertical reel (shooting script)\n"
    "/short <idea> — 2–3min short (shooting script + timecodes)\n"
    "/film <idea>  — 5–10min screenplay (INT./EXT., V.O.)\n"
    "/style        — show loaded style reference\n"
    "/reload       — reload style guide + samples from disk\n"
    "\n"
    "Or just send plain text and I'll pick the format."
)

def is_allowed(update: Update) -> bool:
    if not ALLOWED_CHAT_ID:
        return True
    return str(update.effective_chat.id) == ALLOWED_CHAT_ID

def split_for_telegram(text: str) -> list[str]:
    """Split long messages on line boundaries, staying under Telegram's per-message cap."""
    if len(text) <= TG_MAX:
        return [text]
    chunks: list[str] = []
    buf = ""
    for line in text.splitlines(keepends=True):
        if len(line) > TG_MAX:
            if buf:
                chunks.append(buf)
                buf = ""
            while len(line) > TG_MAX:
                chunks.append(line[:TG_MAX])
                line = line[TG_MAX:]
        if len(buf) + len(line) > TG_MAX and buf:
            chunks.append(buf)
            buf = ""
        buf += line
    if buf:
        chunks.append(buf)
    return chunks

async def send_long(update: Update, text: str):
    for chunk in split_for_telegram(text):
        await update.message.reply_text(chunk)

# ─── HANDLERS ───────────────────────────────────────────────

async def start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    await update.message.reply_text(WELCOME)

async def show_style(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    samples = sorted(p.name for p in SAMPLES_DIR.glob("*")) if SAMPLES_DIR.exists() else []
    names = "\n".join(f"• {s}" for s in samples) or "(no samples loaded)"
    guide_ok = "✅" if STYLE_GUIDE.exists() else "❌"
    await update.message.reply_text(
        f"Style guide: {guide_ok} {STYLE_GUIDE}\n"
        f"Samples ({len(samples)}):\n{names}\n\n"
        f"Total reference size: {len(STYLE_BLOCK):,} chars"
    )

async def reload_style(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    global STYLE_BLOCK, SYSTEM_PROMPT
    STYLE_BLOCK = load_style_block()
    SYSTEM_PROMPT = build_system_prompt(STYLE_BLOCK)
    await update.message.reply_text(
        f"🔁 Reloaded. {len(STYLE_BLOCK):,} chars of style reference."
    )

def _brief_from_cmd(text: str, framing: str) -> str:
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        return ""
    return f"{framing}\n\nIdea: {parts[1].strip()}"

async def reel_cmd(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    brief = _brief_from_cmd(
        update.message.text,
        "Write a 30–60 second vertical reel. Shooting-script format with SCENE/SHOT "
        "blocks and timecodes. Solo actor. Punchy, shoot-ready.",
    )
    if not brief:
        await update.message.reply_text("Usage: /reel <idea>")
        return
    await _run(update, brief)

async def short_cmd(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    brief = _brief_from_cmd(
        update.message.text,
        "Write a 2–3 minute short. Shooting-script format with SCENE/SHOT blocks, "
        "timecodes, SFX + MUSIC CUE markers. Solo actor. End with a hook image.",
    )
    if not brief:
        await update.message.reply_text("Usage: /short <idea>")
        return
    await _run(update, brief)

async def film_cmd(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    brief = _brief_from_cmd(
        update.message.text,
        "Write a 5–10 minute short film. Screenplay format (INT./EXT. slug lines, "
        "V.O. blocks, action blocks). Meditative pacing. End with FADE OUT + a short "
        "themes block.",
    )
    if not brief:
        await update.message.reply_text("Usage: /film <idea>")
        return
    await _run(update, brief)

async def freeform(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    await _run(update, update.message.text)

async def _run(update: Update, brief: str):
    await update.message.chat.send_action(constants.ChatAction.TYPING)
    try:
        loop = asyncio.get_running_loop()
        script = await loop.run_in_executor(None, generate_script, brief)
        if not script:
            await update.message.reply_text("⚠️ Empty response from model.")
            return
        await send_long(update, script)
    except Exception as e:
        log.exception("generation failed")
        await update.message.reply_text(f"⚠️ Error: {e}")

# ─── MAIN ───────────────────────────────────────────────────

def main():
    app = Application.builder().token(TG_TOKEN).build()
    app.add_handler(CommandHandler(["start", "help"], start))
    app.add_handler(CommandHandler("style", show_style))
    app.add_handler(CommandHandler("reload", reload_style))
    app.add_handler(CommandHandler("reel", reel_cmd))
    app.add_handler(CommandHandler("short", short_cmd))
    app.add_handler(CommandHandler("film", film_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, freeform))

    log.info(f"Script agent starting. model={CLAUDE_MODEL} temp={TEMPERATURE}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
