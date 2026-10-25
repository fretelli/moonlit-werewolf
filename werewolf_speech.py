"""Public hosting script and strict offline PCM asset loading.

No private assignment, night target or inspection result is spoken. Solo bot
suspicions are explicitly public, unverified opinions, not host role reveals.
"""
from pathlib import Path
from watcherobot.audio import load_pcm_wave

ROOT = Path(__file__).resolve().parent
TEXTS = {
    "solo_ready": "语音狼人杀已准备好。请对我说开始游戏，也可以用自然语言表达开始。",
    "solo_role": "请私下查看机器人屏幕上的身份。W 是狼人，眼睛是预言家，V 是村民。记住后直接说继续。不要把屏幕投到公开画面。",
    "solo_partner": "机器人屏幕正在显示你的狼人队友座位。记住后直接说继续。",
    "solo_next": "准备进入下一夜。继续游戏请直接说继续；终止本局请说结束游戏，再说确认。",
    "solo_night": "进入夜晚。电脑行动自动完成，不展示电脑的秘密目标或查验。轮到你时按语音提示操作。",
    "solo_wolf_action": "请你代表狼人选择目标。不能选择自己或狼人队友。请说目标座位数字并确认。",
    "solo_seer_action": "请查验一位其他存活玩家。请说座位数字并确认。屏幕 W 为狼人，G 为好人。",
    "solo_accuse": "请说公开怀疑的座位数字并确认。说零表示暂不指认。六十秒内未提交也视为暂无意见。这不是正式投票。",
    "solo_suspect": "这位玩家公开怀疑的对象是下面的座位。注意，这只是玩家观点，不是主持人确认身份。",
    "solo_no_opinion": "这位玩家暂时没有指认对象。",
    "solo_spectator": "你已经出局，可以继续观战，不能再发言或投票。下一夜前直接说继续；退出请说结束游戏，再说确认。",
    "dawn": "天亮了。现在公布昨夜出局座位。",
    "vote": "现在逐座位进行语音投票。被叫到时说目标座位数字或弃票，再说确认。全部收齐后统一公布票数。",
    "runoff": "出现最高票平票。现在加投一次，只能投给公布的平票候选人，也可以弃票。再次平票则本轮无人出局。",
    "candidates": "本次加投候选座位为。",
    "tally": "投票已收齐，现在公布票数。",
    "eliminated": "本轮投票出局座位为。",
    "none": "本轮无人出局。",
    "good_win": "所有狼人已经出局，好人阵营获胜。游戏结束。",
    "wolves_win": "存活狼人数量已经不少于好人，狼人阵营获胜。游戏结束。",
    "paused": "游戏暂停。恢复游戏请直接说继续；终止本局请说结束游戏，再说确认。",
    "resume": "游戏继续。",
}
for seat in range(1, 7):
    TEXTS[f"seat_{seat}"] = f"{seat}号。"
    TEXTS[f"speaker_{seat}"] = f"请{seat}号玩家开始发言。"
TEXTS["voter_1"] = "请1号玩家进行私密投票。"
for count in range(7):
    TEXTS[f"votes_{count}"] = f"{count}票。"


def load_clips(root=ROOT):
    """Fail before device ownership if any required audio is absent/invalid."""
    clips = {}
    for key in TEXTS:
        path = root / "assets" / "werewolf_speech" / f"{key}.wav"
        if not path.is_file():
            raise RuntimeError("狼人杀主持音频不完整；请先准备并校验全部配音资源")
        clip = load_pcm_wave(path)
        if not clip.data:
            raise RuntimeError("狼人杀主持音频为空")
        clips[key] = clip
    return clips
