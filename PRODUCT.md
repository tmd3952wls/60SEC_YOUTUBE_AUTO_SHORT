# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Static HTML/CSS/JS served by a Python standard-library server (`editor/server.py`). No build step, no Node. Chosen by the user so the editor can later be packaged as an installer.

## Users

- **Primary:** the creator of this project. They make Korean YouTube Shorts that recap overseas TV pitches (Shark Tank). They watch a rendered short, spot wrong or awkward subtitles and narration, fix them, and re-render.
- **Later:** non-developer Shorts creators who receive the editor as an installed program. They are not expected to edit JSON or use a terminal.

## Product Purpose

A local editor for the shorts pipeline's EDL (edit decision list). The renderer (`shorts/edl.py`) turns an EDL plus the source video into a finished 1080x1920 short: TTS narration, original dialogue with Korean subtitles, a two-line top title, SFX, red circles, and KRW conversions.

The editor lets a creator change the EDL on screen and re-render, instead of editing JSON by hand. Success means a creator can fix subtitles and narration, check the result, and get a new version without touching a file.

## Positioning

The editor does not cut video by hand. It edits the decisions the automatic renderer uses: beats, narration text, subtitle chunks, shots, and SFX categories. TTS re-synthesis, word-timed subtitles, lip-synced dialogue cuts, and SFX levelling all stay automatic.

## Operating Context

- **Workflow:** open a job, pick an EDL version, watch the rendered video beat by beat, edit a beat, preview only that beat (fast), save as a new version, then render the full short. Old EDLs and videos are never overwritten.
- **Structure:** a short has about 19 beats, each either a narration item or an original-dialogue clip item.
- **Hardware and render time:** runs on the creator's own Windows PC. A full render takes minutes.

## Capabilities and Constraints

- **Most frequent task:** fixing subtitle and narration text, line breaks, and colour highlights, then re-rendering.
- **Subtitle markup:**
  - `[yellow:word]` colours a word.
  - `|` forces a line break.
  - `solo: true` makes an interjection (와우!) its own subtitle.
- **SFX:** a category (whoosh, pop, ding, impact, surprise, question, success, caption, tension), or a pinned file written as `category/name`.
- **API keys:** each user enters their own (Typecast TTS, optional Anthropic/OpenAI). Keys are never bundled with the program.
- **SFX library:** the user's own folder, not redistributable.
- **Style presets:** in `editor/presets/`. Each one carries render overrides and lint rules, such as banned words and solo interjections.
- **Undecided:** installer packaging, and creating a new job from a source URL inside the editor.

## Brand Commitments

The Korean wording rules in the shorts themselves are binding:

- Investors are "투자자", never "샤크".
- Interjections get their own subtitle.
- Narration advances the story rather than describing shots.
- A short ends with the business's current status.

## Evidence on Hand

- Real job data is in `jobs/`. For example, `jobs/vulcan_rattrap` holds the v1–v5 EDLs and rendered videos.
- The reference beat sheet for the target style is in memory notes. It is not bundled.
- There are no testimonials, users or metrics yet, and none should be invented.

## Product Principles

1. Never lose work. Every save is a new version, and renders never overwrite a finished video.
2. Fast loop over full control: preview one beat in seconds before rendering everything.
3. Plain language for non-developers. Show the original English line next to its Korean subtitle, and explain errors in Korean.
4. The automation stays the source of truth; the editor exposes its decisions, not a timeline NLE.
