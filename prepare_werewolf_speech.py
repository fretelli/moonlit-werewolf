"""Explicit audio preparation. Default only exports a local recording script."""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
import wave

from werewolf_speech import ROOT, TEXTS, load_clips


async def synthesize(output, only=None):
    import edge_tts
    from watcherobot.audio import load_audio_file
    for key, text in TEXTS.items():
        if only and key not in only:
            continue
        target = output / f"{key}.wav"
        with tempfile.TemporaryDirectory(dir=output) as temporary:
            mp3 = Path(temporary) / "speech.mp3"
            wav = Path(temporary) / "speech.wav"
            await asyncio.wait_for(
                edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural", rate="+0%").save(str(mp3)),
                timeout=90,
            )
            clip = load_audio_file(mp3)
            with wave.open(str(wav), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(24000)
                stream.writeframes(clip.data)
            wav.replace(target)
        print("Prepared:", key, flush=True)
    (output / "SOURCE.txt").write_text(
        "Generated with Edge online TTS, zh-CN-XiaoxiaoNeural.\n"
        "Only fixed hosting script was sent; no player information.\n"
        "Redistribution permission has NOT been verified. Do not treat tool licensing\n"
        "as an audio redistribution license. Verify service terms before publication,\n"
        "or replace these clips with recordings you have permission to distribute.\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edge-online", action="store_true",
                        help="Explicitly send public hosting text to Edge TTS; no redistribution license implied")
    parser.add_argument("--check", action="store_true", help="Validate all offline WAV clips")
    parser.add_argument("--only", nargs="+", choices=sorted(TEXTS),
                        help="Regenerate only these explicit script keys")
    args = parser.parse_args()
    output = ROOT / "assets" / "werewolf_speech"
    output.mkdir(parents=True, exist_ok=True)
    (output / "script.json").write_text(json.dumps(TEXTS, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.edge_online:
        asyncio.run(synthesize(output, args.only))
    if args.check or args.edge_online:
        clips = load_clips()
        print(f"Validated {len(clips)} clips. Hardware playback still requires verification on a compatible robot.")
    else:
        print("Exported recording script. No network access or synthesis performed.")
        print("Record each key as 24 kHz / mono / 16-bit PCM WAV in", output)


if __name__ == "__main__":
    main()
