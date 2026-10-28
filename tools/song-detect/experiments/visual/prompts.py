"""제로샷 프롬프트 세트 (영어; CLIP/SigLIP 영어 텍스트 타워). N = 라이브 아님 개념, L = 라이브 개념. 세트마다 N/L 목록."""
SETS = {
    "A_basic": dict(
        N=["a screenshot of a web browser page", "a 3D video game scene", "a rhythm game with falling notes", "a concert video playing on screen",
           "a static waiting screen with text", "a YouTube video player", "a split screen showing another streamer's broadcast"],
        L=["an anime virtual avatar singing into a microphone", "a close-up of a virtual youtuber avatar"]),
    "B_desc": dict(
        N=["a desktop screenshot with a web page and a small virtual avatar at the corner", "a first person video game with a small avatar overlay in the corner",
           "a karaoke room inside a 3D open world game", "a music video or concert footage shown in a window", "a rhythm game screen with note lanes and a score",
           "a still image with a be right back message", "a video of another streamer playing in a window next to the avatar", "a music player showing album art and a song title"],
        L=["a large anime avatar face filling the screen with a chat overlay", "a vtuber avatar standing on a stage with a microphone and lyrics",
           "a virtual singer performing a live song on stream"]),
    "C_game": dict(
        N=["video game", "game user interface with a minimap", "gameplay footage", "web browser", "website", "video player controls", "music game", "concert"],
        L=["anime girl avatar", "virtual streamer", "character illustration", "singing"]),
    "D_only_N": dict(
        N=["a screenshot of a web browser page", "a 3D video game scene", "a rhythm game with falling notes", "a concert video playing on screen", "a YouTube video player",
           "a split screen showing another streamer's broadcast", "a static waiting screen with text"],
        L=["a photo"]),
    "E_layout": dict(
        N=["a screen with a large video window and a small avatar in the corner", "a screen with two video windows side by side", "a dark game screen with a heads-up display",
           "a screen with a webpage and text columns"],
        L=["a screen mostly filled by a single large anime character", "a colorful stage background behind an anime character"]),
}

# 개념 탐지기용 (run_det.py): 이름 -> 텍스트. 방향: 'N' 개념은 점수가 높을수록 N, 'L' 개념은 낮을수록 N (두 방향 모두 후보로 시험).
# 주의: 프롬프트는 유형 목록(HANDOFF 25절 N 유형)을 보고 썼고 개별 곡 점수를 보고 고치지 않았다. E_layout 세트만 접촉 시트를 본 뒤 작성.
CONCEPTS = {
    "gta_small_avatar": "a 3D video game scene with a small avatar in the corner",
    "gta_crowd": "a crowd of video game characters in a room",
    "gta_mic": "a video game character holding a microphone",
    "web_page": "a screenshot of a web browser page",
    "web_text": "a website with text columns",
    "web_video": "a web page with an embedded video player",
    "split_other": "a split screen showing another streamer's broadcast",
    "two_windows": "two video windows side by side",
    "stream_window": "a live stream window inside a screen",
    "concert": "a concert stage with singers",
    "music_video": "a music video",
    "real_people": "a video of real people performing",
    "rhythm": "a rhythm game with falling notes",
    "score_combo": "a game screen with a score and combo counter",
    "idle_text": "a static image with text",
    "waiting": "a waiting screen with a be right back message",
    "menu": "a video game menu screen",
    "music_player": "a music player user interface",
    "cutscene": "a video game cutscene",
    "hud_minimap": "game user interface with a minimap",
    "L_big_face": "a large anime avatar face filling the screen",
    "L_sing_mic": "an anime girl singing with a microphone",
    "L_vtuber": "a virtual youtuber",
    "L_stage": "a colorful stage background behind an anime character",
    "L_chat": "a stream overlay with a chat window and an anime avatar",
}
