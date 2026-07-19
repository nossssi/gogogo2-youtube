#!/usr/bin/env python3
"""
CapCut 프로젝트 생성기
파이프라인 결과물 (MP3, SRT, 이미지)을 CapCut 프로젝트로 자동 변환
"""

import json
import uuid
import os
import re
import shutil
from pathlib import Path
from datetime import datetime
import subprocess


def load_settings(config_path):
    """settings.json에서 설정 로드"""
    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def hex_to_rgb(hex_color):
    """#RRGGBB → [r, g, b] (0.0~1.0)"""
    hex_color = hex_color.lstrip("#")
    return [int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4)]


def generate_uuid():
    """CapCut 형식의 UUID 생성"""
    return str(uuid.uuid4()).upper()


def parse_srt_time(time_str):
    """SRT 시간을 마이크로초로 변환"""
    # 00:00:00,000 형식
    match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})', time_str)
    if match:
        h, m, s, ms = map(int, match.groups())
        return (h * 3600 + m * 60 + s) * 1000000 + ms * 1000
    return 0


def parse_srt(srt_path):
    """SRT 파일 파싱"""
    subtitles = []
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()

    blocks = content.strip().split('\n\n')
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            time_line = lines[1]
            text = ' '.join(lines[2:])

            times = time_line.split(' --> ')
            if len(times) == 2:
                start = parse_srt_time(times[0].strip())
                end = parse_srt_time(times[1].strip())
                subtitles.append({
                    'start': start,
                    'duration': end - start,
                    'text': text
                })

    return subtitles


def get_audio_duration_us(audio_path):
    """오디오 파일의 길이를 마이크로초로 반환"""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
             '-of', 'csv=p=0', audio_path],
            capture_output=True, text=True
        )
        duration_sec = float(result.stdout.strip())
        return int(duration_sec * 1000000)
    except:
        return 0


def create_text_material(subtitle, group_id, subtitle_config=None, highlight_range=None, emphasis=False):
    """자막용 텍스트 material 생성

    highlight_range: (start, end) 튜플이면 해당 글자 범위만 빨간색, 나머지 흰색 (카라오케)
    emphasis: True이면 텍스트 색상을 빨간색으로 변경
    """
    material_id = generate_uuid()
    cfg = subtitle_config or {}

    font_size = cfg.get("font_size", 5.0)
    text_color = "#FF0000" if emphasis else cfg.get("text_color", "#FFFFFF")
    border_color = cfg.get("border_color", "#000000")
    border_width = cfg.get("border_width", 0.08)
    background_color = cfg.get("background_color", "#000000")
    background_alpha = cfg.get("background_alpha", 0.7)

    # 스타일 블록 생성 헬퍼
    def make_style(range_start, range_end, color):
        return {
            "fill": {
                "alpha": 1.0,
                "content": {
                    "render_type": "solid",
                    "solid": {"alpha": 1.0, "color": hex_to_rgb(color)}
                }
            },
            "font": {
                "id": "",
                "path": "/Applications/CapCut.app/Contents/Resources/Font/SystemFont/en.ttf"
            },
            "range": [range_start, range_end],
            "size": font_size,
            "strokes": [{
                "width": border_width,
                "mode": 0,
                "content": {
                    "render_type": "solid",
                    "solid": {"color": hex_to_rgb(border_color)}
                }
            }]
        }

    text_len = len(subtitle['text'])
    if highlight_range:
        # 카라오케: 앞(흰) + 강조(빨강) + 뒤(흰)
        hl_start, hl_end = highlight_range
        styles = []
        if hl_start > 0:
            styles.append(make_style(0, hl_start, text_color))
        styles.append(make_style(hl_start, hl_end, "#FF0000"))
        if hl_end < text_len:
            styles.append(make_style(hl_end, text_len, text_color))
    else:
        styles = [make_style(0, text_len, text_color)]

    # content JSON 구조 (획 포함)
    content = {
        "styles": styles,
        "text": subtitle['text']
    }

    return {
        "recognize_task_id": "",
        "id": material_id,
        "name": "",
        "recognize_text": "",
        "recognize_model": "",
        "punc_model": "",
        "type": "subtitle",
        "content": json.dumps(content, ensure_ascii=False),
        "base_content": "",
        "words": {"start_time": [], "end_time": [], "text": []},
        "current_words": {"start_time": [], "end_time": [], "text": []},
        "global_alpha": 1.0,
        "background_color": background_color,
        "background_alpha": background_alpha,
        "background_style": 1,
        "combo_info": {"text_templates": []},
        "caption_template_info": {
            "resource_id": "", "third_resource_id": "", "resource_name": "",
            "category_id": "", "category_name": "", "effect_id": "",
            "request_id": "", "path": "", "is_new": False, "source_platform": 0
        },
        "layer_weight": 1,
        "letter_spacing": 0.0,
        "text_curve": None,
        "text_loop_on_path": False,
        "offset_on_path": 0.0,
        "enable_path_typesetting": False,
        "text_exceeds_path_process_type": 0,
        "text_typesetting_paths": None,
        "text_typesetting_paths_file": "",
        "text_typesetting_path_index": 0,
        "line_spacing": 0.02,
        "has_shadow": False,
        "shadow_color": "",
        "shadow_alpha": 0.9,
        "shadow_smoothing": 0.45,
        "shadow_distance": 5.0,
        "shadow_point": {"x": 0.636, "y": -0.636},
        "shadow_angle": -45.0,
        "border_alpha": 1.0,
        "border_color": border_color,
        "border_width": border_width,
        "border_mode": 0,
        "style_name": "",
        "text_color": text_color,
        "text_alpha": 1.0,
        "font_name": "",
        "font_title": "none",
        "font_size": font_size,
        "font_path": "/Applications/CapCut.app/Contents/Resources/Font/SystemFont/en.ttf",
        "font_id": "",
        "font_resource_id": "",
        "initial_scale": 1.0,
        "font_url": "",
        "typesetting": 0,
        "alignment": 1,
        "line_feed": 1,
        "use_effect_default_color": True,
        "is_rich_text": False,
        "shape_clip_x": False,
        "shape_clip_y": False,
        "ktv_color": "",
        "text_to_audio_ids": [],
        "bold_width": 0.0,
        "italic_degree": 0,
        "underline": False,
        "underline_width": 0.05,
        "underline_offset": 0.22,
        "sub_type": 0,
        "check_flag": 31,
        "text_size": 30,
        "font_category_name": "",
        "font_source_platform": 0,
        "font_third_resource_id": "",
        "font_category_id": "",
        "add_type": 2,
        "operation_type": 0,
        "recognize_type": 0,
        "fonts": [],
        "background_round_radius": 0.0,
        "background_width": 0.0,
        "background_height": 0.0,
        "background_vertical_offset": 0.0,
        "background_horizontal_offset": 0.0,
        "background_fill": "",
        "font_team_id": "",
        "tts_auto_update": False,
        "text_preset_resource_id": "",
        "group_id": group_id,
        "preset_id": "",
        "preset_name": "",
        "preset_category": "",
        "preset_category_id": "",
        "preset_index": 0,
        "preset_has_set_alignment": False,
        "force_apply_line_max_width": False,
        "language": "",
        "relevance_segment": [],
        "original_size": [],
        "fixed_width": -1.0,
        "fixed_height": -1.0,
        "line_max_width": 0.82,
        "oneline_cutoff": False,
        "cutoff_postfix": "",
        "subtitle_template_original_fontsize": 0.0,
        "subtitle_keywords": None,
        "inner_padding": -1.0,
        "multi_language_current": "none",
        "source_from": "",
        "is_lyric_effect": False,
        "lyric_group_id": "",
        "lyrics_template": {
            "resource_id": "", "resource_name": "", "panel": "",
            "effect_id": "", "path": "", "category_id": "",
            "category_name": "", "request_id": ""
        },
        "is_batch_replace": False,
        "is_words_linear": False,
        "ssml_content": "",
        "subtitle_keywords_config": None,
        "sub_template_id": -1,
        "translate_original_text": ""
    }


def create_audio_material(audio_path, duration_us):
    """오디오 material 생성"""
    material_id = generate_uuid()

    return {
        "id": material_id,
        "type": "extract_music",
        "name": os.path.basename(audio_path),
        "duration": duration_us,
        "path": str(Path(audio_path).absolute()),
        "category_name": "local",
        "wave_points": [],
        "music_id": generate_uuid(),
        "app_id": 0,
        "text_id": "",
        "tone_type": "",
        "source_platform": 0,
        "video_id": "",
        "effect_id": "",
        "resource_id": "",
        "third_resource_id": "",
        "category_id": "",
        "intensifies_path": "",
        "formula_id": "",
        "check_flag": 1,
        "team_id": "",
        "local_material_id": generate_uuid(),
        "tone_speaker": "",
        "mock_tone_speaker": "",
        "tone_effect_id": "",
        "tone_effect_name": "",
        "tone_platform": "",
        "cloned_model_type": "",
        "tone_category_id": "",
        "tone_category_name": "",
        "tone_second_category_id": "",
        "tone_second_category_name": "",
        "tone_emotion_name_key": "",
        "tone_emotion_style": "",
        "tone_emotion_role": "",
        "tone_emotion_selection": "",
        "tone_emotion_scale": 0.0,
        "moyin_emotion": "",
        "request_id": "",
        "query": "",
        "search_id": "",
        "sound_separate_type": "",
        "is_text_edit_overdub": False,
        "is_ugc": False,
        "is_ai_clone_tone": False,
        "is_ai_clone_tone_post": False,
        "source_from": "",
        "copyright_limit_type": "none",
        "aigc_history_id": "",
        "aigc_item_id": "",
        "music_source": "",
        "pgc_id": "",
        "pgc_name": "",
        "similiar_music_info": {"original_song_id": "", "original_song_name": ""},
        "ai_music_type": 0,
        "ai_music_enter_from": "",
        "lyric_type": 0,
        "tts_task_id": "",
        "tts_generate_scene": "",
        "ai_music_generate_scene": 0
    }


def create_video_material(image_path, duration_us, is_video=False):
    """이미지/비디오 material 생성"""
    material_id = generate_uuid()
    abs_path = str(Path(image_path).absolute())

    mat_type = "video" if is_video else "photo"
    width = 1280 if is_video else 1024
    height = 720 if is_video else 1024

    return {
        "id": material_id,
        "type": mat_type,
        "name": os.path.basename(image_path),
        "path": abs_path,
        "duration": duration_us,
        "width": width,
        "height": height,
        "category_name": "",
        "category_id": "",
        "check_flag": 63487,
        "crop": {
            "lower_left_x": 0.0, "lower_left_y": 1.0,
            "lower_right_x": 1.0, "lower_right_y": 1.0,
            "upper_left_x": 0.0, "upper_left_y": 0.0,
            "upper_right_x": 1.0, "upper_right_y": 0.0
        },
        "crop_ratio": "free",
        "crop_scale": 1.0,
        "extra_type_option": 0,
        "formula_id": "",
        "freeze": None,
        "has_audio": False,
        "height": height,
        "width": width,
        "intensifies_audio_path": "",
        "intensifies_path": "",
        "is_ai_generate_content": False,
        "is_copyright": False,
        "is_text_edit_overdub": False,
        "is_unified_beauty_mode": False,
        "local_id": "",
        "local_material_id": "",
        "material_id": "",
        "material_name": os.path.basename(image_path),
        "material_url": "",
        "matting": {"flag": 0, "has_use_quick_brush": False, "has_use_quick_eraser": False, "interactiveTime": [], "path": "", "strokes": []},
        "media_path": "",
        "object_locked": None,
        "origin_material_id": "",
        "request_id": "",
        "reverse_intensifies_path": "",
        "reverse_path": "",
        "smart_motion": None,
        "source": 0,
        "source_platform": 0,
        "stable": {"matrix_path": "", "stable_level": 0, "time_range": {"duration": 0, "start": 0}},
        "team_id": "",
        "video_algorithm": {"algorithms": [], "deflicker": None, "motion_blur_config": None, "noise_reduction": None, "path": "", "quality_enhance": None, "time_range": None},
        "aigc_type": "none"
    }


def create_text_segment(subtitle, material_id, render_index, subtitle_config=None, emphasis=False, start_override=None, duration_override=None):
    """텍스트 segment 생성

    emphasis: True면 y_position을 중앙(0.0)으로
    start_override/duration_override: 카라오케 단어별 타이밍 오버라이드 (마이크로초)
    """
    segment_id = generate_uuid()
    animation_id = generate_uuid()
    cfg = subtitle_config or {}
    y_position = 0.0 if emphasis else cfg.get("y_position", -0.8)

    return {
        "id": segment_id,
        "source_timerange": None,
        "target_timerange": {
            "start": start_override if start_override is not None else subtitle['start'],
            "duration": duration_override if duration_override is not None else subtitle['duration']
        },
        "render_timerange": {"start": 0, "duration": 0},
        "desc": "",
        "state": 0,
        "speed": 1.0,
        "is_loop": False,
        "is_tone_modify": False,
        "reverse": False,
        "intensifies_audio": False,
        "cartoon": False,
        "volume": 1.0,
        "last_nonzero_volume": 1.0,
        "clip": {
            "scale": {"x": 1.0, "y": 1.0},
            "rotation": 0.0,
            "transform": {"x": 0.0, "y": y_position},
            "flip": {"vertical": False, "horizontal": False},
            "alpha": 1.0
        },
        "uniform_scale": {"on": True, "value": 1.0},
        "material_id": material_id,
        "extra_material_refs": [animation_id],
        "render_index": render_index,
        "keyframe_refs": [],
        "enable_lut": False,
        "enable_adjust": False,
        "enable_hsl": False,
        "visible": True,
        "group_id": "",
        "enable_color_curves": True,
        "enable_hsl_curves": True,
        "track_render_index": 1,
        "hdr_settings": None,
        "enable_color_wheels": True,
        "track_attribute": 0,
        "is_placeholder": False,
        "template_id": "",
        "enable_smart_color_adjust": False,
        "template_scene": "default",
        "common_keyframes": [],
        "caption_info": None,
        "responsive_layout": {
            "enable": False, "target_follow": "",
            "size_layout": 0, "horizontal_pos_layout": 0, "vertical_pos_layout": 0
        },
        "enable_color_match_adjust": False,
        "enable_color_correct_adjust": False,
        "enable_adjust_mask": False,
        "raw_segment_id": "",
        "lyric_keyframes": None,
        "enable_video_mask": True,
        "digital_human_template_group_id": "",
        "color_correct_alg_result": "",
        "source": "segmentsourcenormal",
        "enable_mask_stroke": False,
        "enable_mask_shadow": False
    }, animation_id


def create_audio_segment(material_id, duration_us):
    """오디오 segment 생성"""
    segment_id = generate_uuid()
    speed_id = generate_uuid()
    mapping_id = generate_uuid()

    return {
        "id": segment_id,
        "source_timerange": {"start": 0, "duration": duration_us},
        "target_timerange": {"start": 0, "duration": duration_us},
        "render_timerange": {"start": 0, "duration": 0},
        "desc": "",
        "state": 0,
        "speed": 1.0,
        "is_loop": False,
        "is_tone_modify": False,
        "reverse": False,
        "intensifies_audio": False,
        "cartoon": False,
        "volume": 1.0,
        "last_nonzero_volume": 1.0,
        "clip": None,
        "uniform_scale": None,
        "material_id": material_id,
        "extra_material_refs": [speed_id, mapping_id],
        "render_index": 0,
        "keyframe_refs": [],
        "enable_lut": False,
        "enable_adjust": False,
        "enable_hsl": False,
        "visible": True,
        "group_id": "",
        "enable_color_curves": True,
        "enable_hsl_curves": True,
        "track_render_index": 2,
        "hdr_settings": None,
        "enable_color_wheels": True,
        "track_attribute": 0,
        "is_placeholder": False,
        "template_id": "",
        "enable_smart_color_adjust": False,
        "template_scene": "default",
        "common_keyframes": [],
        "caption_info": None,
        "responsive_layout": {
            "enable": False, "target_follow": "",
            "size_layout": 0, "horizontal_pos_layout": 0, "vertical_pos_layout": 0
        },
        "enable_color_match_adjust": False,
        "enable_color_correct_adjust": False,
        "enable_adjust_mask": False,
        "raw_segment_id": "",
        "lyric_keyframes": None,
        "enable_video_mask": True,
        "digital_human_template_group_id": "",
        "color_correct_alg_result": "",
        "source": "segmentsourcenormal",
        "enable_mask_stroke": False,
        "enable_mask_shadow": False
    }, speed_id, mapping_id


def create_video_extra_materials():
    """비디오 segment에 필요한 extra materials 생성"""
    speed_id = generate_uuid()
    placeholder_id = generate_uuid()
    canvas_id = generate_uuid()
    channel_id = generate_uuid()
    color_id = generate_uuid()
    vocal_id = generate_uuid()

    materials = {
        "speed": {
            "id": speed_id,
            "type": "speed",
            "mode": 0,
            "speed": 1.0,
            "curve_speed": None
        },
        "placeholder_info": {
            "id": placeholder_id,
            "type": "placeholder_info",
            "meta_type": "none",
            "res_path": "",
            "res_text": "",
            "error_path": "",
            "error_text": ""
        },
        "canvas": {
            "id": canvas_id,
            "type": "canvas_color",
            "color": "",
            "blur": 0.0,
            "image": "",
            "album_image": "",
            "image_id": "",
            "image_name": "",
            "source_platform": 0,
            "team_id": ""
        },
        "sound_channel_mapping": {
            "id": channel_id,
            "type": "",
            "audio_channel_mapping": 0,
            "is_config_open": False
        },
        "material_color": {
            "id": color_id,
            "is_color_clip": False,
            "is_gradient": False,
            "solid_color": "",
            "gradient_colors": [],
            "gradient_percents": [],
            "gradient_angle": 90.0,
            "width": 0.0,
            "height": 0.0
        },
        "vocal_separation": {
            "id": vocal_id,
            "type": "vocal_separation",
            "choice": 0,
            "removed_sounds": [],
            "time_range": None,
            "production_path": "",
            "final_algorithm": "",
            "enter_from": ""
        }
    }

    refs = [speed_id, placeholder_id, canvas_id, channel_id, color_id, vocal_id]
    return materials, refs


def create_ken_burns_keyframes(duration_us, scene_index, ken_burns_config=None):
    """Ken Burns 효과 키프레임 생성 (4방향 순환 + 줌인)"""
    cfg = ken_burns_config or {}
    movement_range = cfg.get("movement_range", 0.03)

    # 4방향 패턴 정의 (시작 → 끝)
    # 좌상→우하, 우상→좌하, 좌하→우상, 우하→좌상
    mr = movement_range
    patterns = [
        {"start_x": -mr, "start_y": -mr, "end_x": mr, "end_y": mr},   # 좌상→우하
        {"start_x": mr, "start_y": -mr, "end_x": -mr, "end_y": mr},   # 우상→좌하
        {"start_x": -mr, "start_y": mr, "end_x": mr, "end_y": -mr},   # 좌하→우상
        {"start_x": mr, "start_y": mr, "end_x": -mr, "end_y": -mr},   # 우하→좌상
    ]

    pattern = patterns[scene_index % 4]

    # zoom_start must be large enough to cover movement_range so edges don't show
    min_start_scale = 1.0 + mr * 2.5
    start_scale = max(cfg.get("zoom_start", 1.05), min_start_scale)
    end_scale = max(cfg.get("zoom_end", 1.15), min_start_scale)

    # 끝 시간 (약간 여유)
    end_time = int(duration_us * 0.99)

    def create_keyframe(time_offset, value):
        return {
            "id": generate_uuid(),
            "curveType": "Line",
            "time_offset": time_offset,
            "left_control": {"x": 0.0, "y": 0.0},
            "right_control": {"x": 0.0, "y": 0.0},
            "values": [value],
            "string_value": "",
            "graphID": ""
        }

    keyframes = [
        {
            "id": generate_uuid(),
            "material_id": "",
            "property_type": "KFTypePositionX",
            "keyframe_list": [
                create_keyframe(0, pattern["start_x"]),
                create_keyframe(end_time, pattern["end_x"])
            ]
        },
        {
            "id": generate_uuid(),
            "material_id": "",
            "property_type": "KFTypePositionY",
            "keyframe_list": [
                create_keyframe(0, pattern["start_y"]),
                create_keyframe(end_time, pattern["end_y"])
            ]
        },
        {
            "id": generate_uuid(),
            "material_id": "",
            "property_type": "KFTypeScaleX",
            "keyframe_list": [
                create_keyframe(0, start_scale),
                create_keyframe(end_time, end_scale)
            ]
        }
    ]

    return keyframes


def create_video_segment(material_id, start_us, duration_us, render_index, extra_refs, scene_index=0, ken_burns_config=None, is_video=False, alpha=1.0):
    """비디오/이미지 segment 생성 (Ken Burns 효과 포함)"""
    segment_id = generate_uuid()
    cfg = ken_burns_config or {}
    movement_range = cfg.get("movement_range", 0.03)

    # Ken Burns 키프레임 생성
    keyframes = create_ken_burns_keyframes(duration_us, scene_index, ken_burns_config)

    # 시작 위치로 clip 설정
    mr = movement_range
    patterns = [
        {"start_x": -mr, "start_y": -mr},
        {"start_x": mr, "start_y": -mr},
        {"start_x": -mr, "start_y": mr},
        {"start_x": mr, "start_y": mr},
    ]
    pattern = patterns[scene_index % 4]

    return {
        "id": segment_id,
        "source_timerange": {"start": 0, "duration": duration_us},
        "target_timerange": {"start": start_us, "duration": duration_us},
        "render_timerange": {"start": 0, "duration": 0},
        "desc": "",
        "state": 0,
        "speed": 1.0,
        "is_loop": is_video,
        "is_tone_modify": False,
        "reverse": False,
        "intensifies_audio": False,
        "cartoon": False,
        "volume": 1.0,
        "last_nonzero_volume": 1.0,
        "clip": {
            "scale": {"x": 1.0, "y": 1.0},
            "rotation": 0.0,
            "transform": {"x": pattern["start_x"], "y": pattern["start_y"]},
            "flip": {"vertical": False, "horizontal": False},
            "alpha": alpha
        },
        "uniform_scale": {"on": True, "value": 1.0},
        "material_id": material_id,
        "extra_material_refs": extra_refs,
        "render_index": render_index,
        "keyframe_refs": [],
        "enable_lut": True,
        "enable_adjust": True,
        "enable_hsl": False,
        "visible": True,
        "group_id": "",
        "enable_color_curves": True,
        "enable_hsl_curves": True,
        "track_render_index": 0,
        "hdr_settings": {"mode": 1, "intensity": 1.0, "nits": 1000},
        "enable_color_wheels": True,
        "track_attribute": 0,
        "is_placeholder": False,
        "template_id": "",
        "enable_smart_color_adjust": False,
        "template_scene": "default",
        "common_keyframes": keyframes,
        "caption_info": None,
        "responsive_layout": {
            "enable": False, "target_follow": "",
            "size_layout": 0, "horizontal_pos_layout": 0, "vertical_pos_layout": 0
        },
        "enable_color_match_adjust": False,
        "enable_color_correct_adjust": False,
        "enable_adjust_mask": False,
        "raw_segment_id": "",
        "lyric_keyframes": None,
        "enable_video_mask": True,
        "digital_human_template_group_id": "",
        "color_correct_alg_result": "",
        "source": "segmentsourcenormal",
        "enable_mask_stroke": False,
        "enable_mask_shadow": False
    }


def create_material_animation(animation_id):
    """텍스트 애니메이션 material 생성"""
    return {
        "id": animation_id,
        "type": "sticker_animation",
        "name": "",
        "animations": [],
        "multi_language_current": "none"
    }


def create_speed_material(speed_id):
    """속도 material 생성"""
    return {
        "id": speed_id,
        "type": "speed",
        "name": "",
        "mode": 0,
        "speed": 1.0,
        "curve_speed": None
    }


def create_sound_channel_mapping(mapping_id):
    """사운드 채널 매핑 생성"""
    return {
        "id": mapping_id,
        "type": "none",
        "audio_channel_mapping": 0
    }


def generate_capcut_project(output_dir, project_name=None, capcut_config=None, compare_srt=None):
    """CapCut 프로젝트 생성

    compare_srt: 두 번째 SRT 경로. 지정하면 별도 텍스트 트랙으로 화면 위쪽에
    노란색으로 얹어 기본 자막과 나란히 비교할 수 있다 (A/B 검수용).
    """
    output_dir = Path(output_dir)
    capcut_config = capcut_config or {}
    subtitle_config = capcut_config.get("subtitle", {})
    ken_burns_config = capcut_config.get("ken_burns", {})

    # 필요한 파일 찾기
    srt_file = output_dir / "subtitle.srt"
    audio_file = output_dir / "audio.mp3"
    images_dir = output_dir / "images"
    storyboard_file = output_dir / "storyboard.json"

    if not srt_file.exists():
        print(f"SRT 파일을 찾을 수 없습니다: {srt_file}")
        return None

    if not audio_file.exists():
        print(f"오디오 파일을 찾을 수 없습니다: {audio_file}")
        return None

    # SRT 파싱
    subtitles = parse_srt(srt_file)
    print(f"자막 {len(subtitles)}개 로드")

    # 오디오 길이
    audio_duration = get_audio_duration_us(str(audio_file))
    print(f"오디오 길이: {audio_duration / 1000000:.2f}초")

    # 스토리보드에서 이미지 정보 로드
    scenes = []
    if storyboard_file.exists():
        with open(storyboard_file, 'r', encoding='utf-8') as f:
            storyboard = json.load(f)
            scenes = storyboard.get('scenes', [])
        print(f"스토리보드 씬 {len(scenes)}개 로드")

    # [story 어댑터] 씬 타이밍 파생: story 파이프라인의 {V}/storyboard.json 은 씬마다
    # subtitle_range[first,last](1-based 자막 큐 범위)만 갖는다(scene_timing.py 산출).
    # youtube 생성기는 start/end SRT 문자열을 기대하므로 subtitle_range → 자막 시간으로 변환해 채운다.
    def _us_to_srt(us):
        us = max(0, int(us)); ms = us // 1000
        h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    for si, scene in enumerate(scenes):
        if scene.get('start') and scene.get('end'):
            continue
        sr = scene.get('subtitle_range')
        if sr and len(sr) == 2 and subtitles:
            f_i = max(0, min(sr[0] - 1, len(subtitles) - 1))
            l_i = max(0, min(sr[1] - 1, len(subtitles) - 1))
            start_us = subtitles[f_i]['start']
            end_us = subtitles[l_i]['start'] + subtitles[l_i]['duration']
            # 다음 씬과 틈/겹침 없이 이어지도록 끝을 다음 씬 시작 자막에 맞춤
            if si + 1 < len(scenes):
                nsr = scenes[si + 1].get('subtitle_range')
                if nsr and len(nsr) == 2:
                    n_i = max(0, min(nsr[0] - 1, len(subtitles) - 1))
                    end_us = max(start_us + 1, subtitles[n_i]['start'])
            scene['start'] = _us_to_srt(start_us)
            scene['end'] = _us_to_srt(end_us)

    # Emphasis 판별: 섹션(파트)당 마지막 climax 1개만 선택
    EMPHASIS_ROLES = {'climax'}
    # 섹션별 climax 씬 수집 (마지막 것만 사용)
    section_last_climax = {}  # section_id → scene_index
    for i, scene in enumerate(scenes):
        if scene.get('narrative_role', '') in EMPHASIS_ROLES:
            sid = scene.get('section_id', '')
            section_last_climax[sid] = i  # 덮어쓰므로 마지막이 남음

    emphasis_subtitle_indices = set()
    emphasis_scene_indices = set()
    for sid, scene_idx in section_last_climax.items():
        scene = scenes[scene_idx]
        emphasis_scene_indices.add(scene_idx)
        sr = scene.get('subtitle_range', [])
        if len(sr) == 2:
            for idx in range(sr[0], sr[1] + 1):
                emphasis_subtitle_indices.add(idx)
    if emphasis_scene_indices:
        print(f"Emphasis 씬 {len(emphasis_scene_indices)}개 선택 (섹션당 1개, 자막 {len(emphasis_subtitle_indices)}개)")

    # 카라오케용 단어 타이밍 로드 (sentences.json)
    # sentences.json의 타이밍은 무음 제거 전(raw) 기준이므로 보정 필요
    word_timings_by_subtitle = {}  # subtitle_index(0-based) → [(word, char_start, char_end, time_start_us, time_end_us)]
    sentences_file = output_dir / "sentences.json"
    raw_srt_file = output_dir / "subtitle_raw.srt"
    if emphasis_subtitle_indices and sentences_file.exists():
        with open(sentences_file, 'r', encoding='utf-8') as f:
            sentences_data = json.load(f)
        sentences_list = sentences_data.get('sentences', [])

        # 무음 제거 전/후 시간 오프셋 계산
        raw_subtitles = parse_srt(raw_srt_file) if raw_srt_file.exists() else None

        # 자막 텍스트 → 문장 매칭 (텍스트 포함 관계)
        for sub_idx_1based in emphasis_subtitle_indices:
            sub_idx = sub_idx_1based - 1
            if sub_idx >= len(subtitles):
                continue
            sub_text = subtitles[sub_idx]['text']

            # 무음 제거 전/후 오프셋 계산 (raw_start - final_start)
            time_offset_us = 0
            if raw_subtitles and sub_idx < len(raw_subtitles):
                raw_start = raw_subtitles[sub_idx]['start']
                final_start = subtitles[sub_idx]['start']
                time_offset_us = raw_start - final_start  # 양수: raw가 더 늦음 → 빼야 함

            # 이 자막 텍스트를 포함하는 문장 찾기
            for sent in sentences_list:
                sent_text = sent.get('text', '')
                sub_pos_in_sent = sent_text.find(sub_text)
                if sub_pos_in_sent == -1:
                    continue

                # 자막 텍스트에 속하는 단어만 추출
                matched_words = []
                char_cursor = 0
                for w in sent.get('words', []):
                    word_pos_in_sent = sent_text.find(w['word'], char_cursor)
                    if word_pos_in_sent == -1:
                        continue
                    char_cursor = word_pos_in_sent + len(w['word'])

                    if word_pos_in_sent >= sub_pos_in_sent and word_pos_in_sent + len(w['word']) <= sub_pos_in_sent + len(sub_text):
                        char_in_sub = word_pos_in_sent - sub_pos_in_sent
                        # 무음 제거 보정 적용
                        matched_words.append((
                            w['word'],
                            char_in_sub,
                            char_in_sub + len(w['word']),
                            int(w['start'] * 1_000_000) - time_offset_us,
                            int(w['end'] * 1_000_000) - time_offset_us,
                        ))

                if matched_words:
                    # 단어 끝 시간 보정: 각 단어의 끝 = 다음 단어의 시작
                    # 마지막 단어의 끝 = 다음 자막의 시작 (또는 현재 자막의 끝)
                    next_sub_start = subtitles[sub_idx + 1]['start'] if sub_idx + 1 < len(subtitles) else subtitles[sub_idx]['start'] + subtitles[sub_idx]['duration']
                    for wi in range(len(matched_words)):
                        word, cs, ce, ts, te = matched_words[wi]
                        if wi + 1 < len(matched_words):
                            te = matched_words[wi + 1][3]  # 다음 단어의 start
                        else:
                            te = next_sub_start  # 마지막 단어 → 다음 자막 시작
                        matched_words[wi] = (word, cs, ce, ts, te)
                    word_timings_by_subtitle[sub_idx] = matched_words
                    break

        if word_timings_by_subtitle:
            print(f"카라오케 단어 타이밍: 자막 {len(word_timings_by_subtitle)}개 매칭")

    # Materials 생성
    text_materials = []
    audio_materials = []
    video_materials = []
    material_animations = []
    speeds = []
    sound_channel_mappings = []

    # 텍스트 segments
    text_segments = []
    group_id = f"import_{int(datetime.now().timestamp() * 1000)}"

    render_idx = 14000
    for i, subtitle in enumerate(subtitles):
        is_emphasis = (i + 1) in emphasis_subtitle_indices
        word_timings = word_timings_by_subtitle.get(i)

        if is_emphasis and word_timings:
            # 카라오케: 단어별로 material + segment 생성
            for word, char_start, char_end, time_start_us, time_end_us in word_timings:
                mat = create_text_material(subtitle, group_id, subtitle_config, highlight_range=(char_start, char_end))
                text_materials.append(mat)

                seg, anim_id = create_text_segment(
                    subtitle, mat['id'], render_idx, subtitle_config,
                    emphasis=True,
                    start_override=time_start_us,
                    duration_override=time_end_us - time_start_us,
                )
                text_segments.append(seg)
                render_idx += 1

                animation = create_material_animation(anim_id)
                material_animations.append(animation)
        else:
            # 일반 자막: 단일 material + segment
            material = create_text_material(subtitle, group_id, subtitle_config)
            text_materials.append(material)

            segment, animation_id = create_text_segment(subtitle, material['id'], render_idx, subtitle_config)
            text_segments.append(segment)
            render_idx += 1

            animation = create_material_animation(animation_id)
            material_animations.append(animation)

    # 비교용 두 번째 자막 트랙 (compare_srt) — 위쪽·노란색으로 구분
    compare_segments = []
    if compare_srt:
        comp_path = Path(compare_srt)
        if comp_path.exists():
            comp_subs = parse_srt(comp_path)
            comp_cfg = dict(subtitle_config)
            comp_cfg["y_position"] = subtitle_config.get("y_position", -0.8) + 0.25
            comp_cfg["text_color"] = "#FFD54A"
            for sub in comp_subs:
                mat = create_text_material(sub, group_id, comp_cfg)
                text_materials.append(mat)
                seg, anim_id = create_text_segment(sub, mat['id'], render_idx, comp_cfg)
                compare_segments.append(seg)
                render_idx += 1
                material_animations.append(create_material_animation(anim_id))
            print(f"비교 자막 트랙: {comp_path.name} {len(comp_subs)}개 (노란색, 위쪽)")
        else:
            print(f"⚠️ 비교 SRT 없음: {comp_path}")

    # 오디오 material과 segment
    audio_material = create_audio_material(str(audio_file), audio_duration)
    audio_materials.append(audio_material)

    audio_segment, speed_id, mapping_id = create_audio_segment(audio_material['id'], audio_duration)

    speed = create_speed_material(speed_id)
    speeds.append(speed)

    mapping = create_sound_channel_mapping(mapping_id)
    sound_channel_mappings.append(mapping)

    # 비디오/이미지 segments
    video_segments = []
    canvases = []
    placeholder_infos = []
    material_colors = []
    vocal_separations = []

    # [story 어댑터] images/ 디렉토리 강제 가드 제거 — story는 이미지가 ../scenes/ 에 있고
    # 각 씬의 image_path 로 개별 해석·존재확인(media_path.exists())되므로 디렉토리 유무는 무관.
    if scenes:
        for i, scene in enumerate(scenes):
            # 비디오가 있으면 비디오 우선, 없으면 이미지
            # [story 어댑터] image_path/video_path 는 {V} 기준 상대경로("../scenes/scene_NN.png").
            # '../' 를 잘라내지 말고 그대로 resolve 해야 상위 scenes/ 를 올바로 가리킨다.
            is_video = False
            raw_video_path = scene.get('video_path', '')
            if raw_video_path:
                media_path = (output_dir / raw_video_path).resolve()
                if media_path.exists():
                    is_video = True

            if not is_video:
                raw_image_path = scene.get('image_path', f'images/scene_{i+1:03d}.png')
                media_path = (output_dir / raw_image_path).resolve()

            if media_path.exists():
                # 씬 시간 계산 (SRT 형식에서 변환)
                start_str = scene.get('start', '00:00:00,000')
                end_str = scene.get('end', '00:00:05,000')
                start_us = parse_srt_time(start_str)
                end_us = parse_srt_time(end_str)
                duration_us = end_us - start_us

                material = create_video_material(str(media_path), duration_us, is_video=is_video)
                video_materials.append(material)

                # extra materials 생성
                extra_mats, extra_refs = create_video_extra_materials()
                speeds.append(extra_mats["speed"])
                placeholder_infos.append(extra_mats["placeholder_info"])
                canvases.append(extra_mats["canvas"])
                sound_channel_mappings.append(extra_mats["sound_channel_mapping"])
                material_colors.append(extra_mats["material_color"])
                vocal_separations.append(extra_mats["vocal_separation"])

                # 비디오는 Ken Burns 효과 비활성화 (이미 움직임이 있으므로)
                scene_ken_burns = None if is_video else ken_burns_config
                scene_alpha = 0.5 if i in emphasis_scene_indices else 1.0
                segment = create_video_segment(material['id'], start_us, duration_us, i, extra_refs, scene_index=i, ken_burns_config=scene_ken_burns, is_video=is_video, alpha=scene_alpha)
                video_segments.append(segment)

    # 트랙 구성
    tracks = [
        {
            "id": generate_uuid(),
            "type": "video",
            "segments": video_segments,
            "flag": 0,
            "attribute": 0,
            "name": "",
            "is_default_name": True
        },
        {
            "id": generate_uuid(),
            "type": "text",
            "segments": text_segments,
            "flag": 0,
            "attribute": 0,
            "name": "",
            "is_default_name": True
        },
        {
            "id": generate_uuid(),
            "type": "audio",
            "segments": [audio_segment],
            "flag": 0,
            "attribute": 0,
            "name": "",
            "is_default_name": True
        }
    ]
    if compare_segments:
        tracks.insert(2, {
            "id": generate_uuid(),
            "type": "text",
            "segments": compare_segments,
            "flag": 0,
            "attribute": 0,
            "name": "",
            "is_default_name": True
        })

    # 전체 프로젝트 구조
    project = {
        "id": generate_uuid(),
        "version": 360000,
        "new_version": "155.0.0",
        "name": project_name or "",
        "duration": audio_duration,
        "create_time": 0,
        "update_time": 0,
        "fps": 30.0,
        "is_drop_frame_timecode": False,
        "color_space": -1,
        "config": {
            "video_mute": False,
            "record_audio_last_index": 1,
            "extract_audio_last_index": 1,
            "original_sound_last_index": 1,
            "subtitle_recognition_id": "",
            "subtitle_taskinfo": [],
            "lyrics_recognition_id": "",
            "lyrics_taskinfo": [],
            "subtitle_sync": True,
            "lyrics_sync": True,
            "sticker_max_index": 1,
            "adjust_max_index": 1,
            "material_save_mode": 0,
            "export_range": None,
            "maintrack_adsorb": True,
            "combination_max_index": 1,
            "attachment_info": [],
            "zoom_info_params": None,
            "system_font_list": [],
            "multi_language_mode": "none",
            "multi_language_main": "none",
            "multi_language_current": "none",
            "multi_language_list": [],
            "subtitle_keywords_config": None,
            "use_float_render": False
        },
        "canvas_config": {
            "ratio": "original",
            "width": 1920,
            "height": 1080,
            "background": None
        },
        "tracks": tracks,
        "group_container": None,
        "materials": {
            "flowers": [],
            "videos": video_materials,
            "tail_leaders": [],
            "audios": audio_materials,
            "images": [],
            "texts": text_materials,
            "effects": [],
            "stickers": [],
            "canvases": canvases,
            "transitions": [],
            "audio_effects": [],
            "audio_fades": [],
            "beats": [],
            "material_animations": material_animations,
            "placeholders": [],
            "placeholder_infos": placeholder_infos,
            "speeds": speeds,
            "common_mask": [],
            "chromas": [],
            "text_templates": [],
            "realtime_denoises": [],
            "audio_pannings": [],
            "audio_pitch_shifts": [],
            "video_trackings": [],
            "hsl": [],
            "drafts": [],
            "color_curves": [],
            "hsl_curves": [],
            "primary_color_wheels": [],
            "log_color_wheels": [],
            "video_effects": [],
            "audio_balances": [],
            "handwrites": [],
            "manual_deformations": [],
            "manual_beautys": [],
            "plugin_effects": [],
            "sound_channel_mappings": sound_channel_mappings,
            "green_screens": [],
            "shapes": [],
            "material_colors": material_colors,
            "digital_humans": [],
            "digital_human_model_dressing": [],
            "smart_crops": [],
            "ai_translates": [],
            "audio_track_indexes": [],
            "loudnesses": [],
            "vocal_beautifys": [],
            "vocal_separations": vocal_separations,
            "smart_relights": [],
            "time_marks": [],
            "multi_language_refs": [],
            "video_shadows": [],
            "video_strokes": [],
            "video_radius": []
        },
        "keyframes": {
            "videos": [],
            "audios": [],
            "texts": [],
            "stickers": [],
            "filters": [],
            "adjusts": [],
            "handwrites": [],
            "effects": []
        },
        "keyframe_graph_list": [],
        "platform": {
            "os": "mac",
            "os_version": "14.4.1",
            "app_id": 359289,
            "app_version": "7.9.0",
            "app_source": "cc",
            "device_id": "generated",
            "hard_disk_id": "generated",
            "mac_address": "generated"
        },
        "last_modified_platform": {
            "os": "mac",
            "os_version": "14.4.1",
            "app_id": 359289,
            "app_version": "7.9.0",
            "app_source": "cc",
            "device_id": "generated",
            "hard_disk_id": "generated",
            "mac_address": "generated"
        },
        "mutable_config": None,
        "cover": None,
        "retouch_cover": None,
        "extra_info": None,
        "relationships": [],
        "render_index_track_mode_on": True,
        "free_render_index_mode_on": False,
        "static_cover_image_path": "",
        "source": "default",
        "time_marks": None,
        "path": "",
        "lyrics_effects": [],
        "uneven_animation_template_info": {
            "composition": "",
            "content": "",
            "order": "",
            "sub_template_info_list": []
        },
        "draft_type": "video",
        "smart_ads_info": {
            "page_from": "",
            "routine": "",
            "draft_url": ""
        },
        "function_assistant_info": {
            "smart_rec_applied": False,
            "fixed_rec_applied": False,
            "auto_adjust": False,
            "auto_adjust_segid_list": [],
            "color_correction": False,
            "color_correction_segid_list": [],
            "enhance_quality": False,
            "smooth_slow_motion": False,
            "deflicker_segid_list": [],
            "video_noise_segid_list": [],
            "enhance_quality_segid_list": [],
            "smart_segid_list": [],
            "retouch": False,
            "retouch_segid_list": [],
            "enhande_voice": False,
            "enhance_voice_segid_list": [],
            "audio_noise_segid_list": [],
            "auto_caption": False,
            "auto_caption_segid_list": [],
            "auto_caption_template_id": "",
            "caption_opt": False,
            "caption_opt_segid_list": [],
            "eye_correction": False,
            "eye_correction_segid_list": [],
            "normalize_loudness": False,
            "normalize_loudness_segid_list": [],
            "normalize_loudness_audio_denoise_segid_list": [],
            "auto_adjust_fixed": False,
            "auto_adjust_fixed_value": 50.0,
            "color_correction_fixed": False,
            "color_correction_fixed_value": 50.0,
            "normalize_loudness_fixed": False,
            "enhande_voice_fixed": False,
            "retouch_fixed": False,
            "enhance_quality_fixed": False,
            "smooth_slow_motion_fixed": False,
            "fps": {"num": 0, "den": 1}
        }
    }

    return project


def _build_draft_materials_value(project, audio_path, now_us):
    """draft_meta_info의 draft_materials value 구성"""
    materials = []

    # 이미지 추가
    for video in project.get('materials', {}).get('videos', []):
        path = video.get('path', '')
        if path:
            materials.append({
                "ai_group_type": "",
                "create_time": -1,
                "duration": video.get('duration', 5000000),
                "extra_info": os.path.basename(path),
                "file_Path": path,
                "height": video.get('height', 1024),
                "id": generate_uuid().lower(),
                "import_time": -1,
                "import_time_ms": -1,
                "item_source": 1,
                "md5": "",
                "metetype": "photo",
                "roughcut_time_range": {"duration": -1, "start": -1},
                "sub_time_range": {"duration": -1, "start": -1},
                "type": 0,
                "width": video.get('width', 1024)
            })

    # 오디오 추가
    for audio in project.get('materials', {}).get('audios', []):
        path = audio.get('path', '')
        if path:
            materials.append({
                "ai_group_type": "",
                "create_time": int(datetime.now().timestamp()),
                "duration": audio.get('duration', 0),
                "extra_info": os.path.basename(path),
                "file_Path": path,
                "height": 0,
                "id": generate_uuid().lower(),
                "import_time": int(datetime.now().timestamp()),
                "import_time_ms": now_us,
                "item_source": 1,
                "md5": "",
                "metetype": "music",
                "roughcut_time_range": {"duration": audio.get('duration', 0), "start": 0},
                "sub_time_range": {"duration": -1, "start": -1},
                "type": 0,
                "width": 0
            })

    return materials


def save_to_capcut(project, project_name, audio_path):
    """CapCut 프로젝트 폴더에 저장 (파일 복사 방식)"""
    capcut_dir = Path.home() / "Movies" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"

    if not capcut_dir.exists():
        print(f"CapCut 프로젝트 폴더를 찾을 수 없습니다: {capcut_dir}")
        return None

    # 프로젝트 폴더 생성
    project_dir = capcut_dir / project_name
    project_dir.mkdir(exist_ok=True)

    # 필요한 하위 폴더 생성
    resources_dir = project_dir / "Resources"
    for subdir in ['Resources', 'adjust_mask', 'matting', 'qr_upload', 'smart_crop', 'subdraft', 'common_attachment']:
        (project_dir / subdir).mkdir(exist_ok=True)

    # 오디오 파일 복사 및 경로 업데이트
    audio_src = Path(audio_path)
    audio_dst = resources_dir / audio_src.name
    if audio_src.exists():
        shutil.copy2(audio_src, audio_dst)
        print(f"오디오 복사: {audio_dst.name}")

    for audio in project.get('materials', {}).get('audios', []):
        if audio.get('path'):
            audio['path'] = str(audio_dst)

    # 이미지 파일 복사 및 경로 업데이트
    for video in project.get('materials', {}).get('videos', []):
        if video.get('path'):
            img_src = Path(video['path'])
            img_dst = resources_dir / img_src.name
            if img_src.exists():
                shutil.copy2(img_src, img_dst)
            video['path'] = str(img_dst)
    print(f"이미지 {len(project.get('materials', {}).get('videos', []))}개 복사")

    # draft_info.json 저장
    draft_path = project_dir / "draft_info.json"
    with open(draft_path, 'w', encoding='utf-8') as f:
        json.dump(project, f, ensure_ascii=False)

    # draft_meta_info.json 생성
    now_us = int(datetime.now().timestamp() * 1000000)
    draft_id = project['id']
    duration = project['duration']

    draft_meta = {
        "cloud_draft_cover": True,
        "cloud_draft_sync": True,
        "cloud_package_completed_time": "",
        "draft_cloud_capcut_purchase_info": "",
        "draft_cloud_last_action_download": False,
        "draft_cloud_package_type": "",
        "draft_cloud_purchase_info": "",
        "draft_cloud_template_id": "",
        "draft_cloud_tutorial_info": "",
        "draft_cloud_videocut_purchase_info": "",
        "draft_cover": "draft_cover.jpg",
        "draft_deeplink_url": "",
        "draft_enterprise_info": {
            "draft_enterprise_extra": "",
            "draft_enterprise_id": "",
            "draft_enterprise_name": "",
            "enterprise_material": []
        },
        "draft_fold_path": str(project_dir),
        "draft_id": draft_id,
        "draft_is_ae_produce": False,
        "draft_is_ai_packaging_used": False,
        "draft_is_ai_shorts": False,
        "draft_is_ai_translate": False,
        "draft_is_article_video_draft": False,
        "draft_is_cloud_temp_draft": False,
        "draft_is_from_deeplink": "false",
        "draft_is_invisible": False,
        "draft_is_web_article_video": False,
        "draft_materials": [
            {
                "type": 0,
                "value": _build_draft_materials_value(project, audio_path, now_us)
            },
            {"type": 1, "value": []},
            {"type": 2, "value": []},
            {"type": 3, "value": []},
            {"type": 6, "value": []},
            {"type": 7, "value": []},
            {"type": 8, "value": []}
        ],
        "draft_materials_copied_info": [],
        "draft_name": project_name,
        "draft_need_rename_folder": False,
        "draft_new_version": "",
        "draft_removable_storage_device": "",
        "draft_root_path": str(capcut_dir),
        "draft_segment_extra_info": [],
        "draft_timeline_materials_size_": 0,
        "draft_type": "",
        "draft_web_article_video_enter_from": "",
        "tm_draft_cloud_completed": "",
        "tm_draft_cloud_entry_id": -1,
        "tm_draft_cloud_modified": 0,
        "tm_draft_cloud_parent_entry_id": -1,
        "tm_draft_cloud_space_id": -1,
        "tm_draft_cloud_user_id": -1,
        "tm_draft_create": now_us,
        "tm_draft_modified": now_us,
        "tm_draft_removed": 0,
        "tm_duration": duration
    }

    with open(project_dir / "draft_meta_info.json", 'w', encoding='utf-8') as f:
        json.dump(draft_meta, f, ensure_ascii=False)

    # 기타 필요한 파일들
    with open(project_dir / "draft_agency_config.json", 'w') as f:
        json.dump({"create_draft_time": int(datetime.now().timestamp()), "draft_enterprise_extra": "", "draft_enterprise_id": "", "draft_enterprise_name": ""}, f)

    with open(project_dir / "draft_biz_config.json", 'w') as f:
        f.write("")

    with open(project_dir / "draft_virtual_store.json", 'w') as f:
        json.dump({"draft_virtual_materials": [], "effect_virtual_materials": [], "flower_virtual_materials": []}, f)

    with open(project_dir / "draft_settings", 'w') as f:
        json.dump({"draft_settings_version": 1, "graphic_optimization_enable": True}, f)

    with open(project_dir / "performance_opt_info.json", 'w') as f:
        json.dump({"decode_opt": True, "enable_track_opt": False, "opt_applied": False}, f)

    # root_meta_info.json 업데이트
    root_meta_path = capcut_dir / "root_meta_info.json"
    if root_meta_path.exists():
        with open(root_meta_path, 'r', encoding='utf-8') as f:
            root_meta = json.load(f)
    else:
        root_meta = {"all_draft_store": [], "draft_ids": 0, "root_path": str(capcut_dir)}

    # 기존 항목 제거 (같은 이름이 있으면)
    root_meta["all_draft_store"] = [d for d in root_meta["all_draft_store"] if d.get("draft_name") != project_name]

    # 새 항목 추가
    new_entry = {
        "cloud_draft_cover": True,
        "cloud_draft_sync": True,
        "draft_cloud_last_action_download": False,
        "draft_cloud_purchase_info": "",
        "draft_cloud_template_id": "",
        "draft_cloud_tutorial_info": "",
        "draft_cloud_videocut_purchase_info": "",
        "draft_cover": str(project_dir / "draft_cover.jpg"),
        "draft_fold_path": str(project_dir),
        "draft_id": draft_id,
        "draft_is_ai_shorts": False,
        "draft_is_cloud_temp_draft": False,
        "draft_is_invisible": False,
        "draft_is_web_article_video": False,
        "draft_json_file": str(draft_path),
        "draft_name": project_name,
        "draft_new_version": "",
        "draft_root_path": str(capcut_dir),
        "draft_timeline_materials_size": 0,
        "draft_type": "",
        "draft_web_article_video_enter_from": "",
        "streaming_edit_draft_ready": True,
        "tm_draft_cloud_completed": "",
        "tm_draft_cloud_entry_id": -1,
        "tm_draft_cloud_modified": 0,
        "tm_draft_cloud_parent_entry_id": -1,
        "tm_draft_cloud_space_id": -1,
        "tm_draft_cloud_user_id": -1,
        "tm_draft_create": now_us,
        "tm_draft_modified": now_us,
        "tm_draft_removed": 0,
        "tm_duration": duration
    }

    root_meta["all_draft_store"].insert(0, new_entry)
    root_meta["draft_ids"] = root_meta.get("draft_ids", 0) + 1

    with open(root_meta_path, 'w', encoding='utf-8') as f:
        json.dump(root_meta, f, ensure_ascii=False)

    print(f"CapCut 프로젝트 저장됨: {project_dir}")
    print(f"root_meta_info.json 업데이트됨")
    return project_dir


def main():
    import argparse

    parser = argparse.ArgumentParser(description='파이프라인 결과물을 CapCut 프로젝트로 변환')
    parser.add_argument('output_dir', help='파이프라인 출력 디렉토리')
    parser.add_argument('--name', '-n', help='프로젝트 이름', default=None)
    parser.add_argument('--config', help='설정 파일 경로 (settings.json)')
    parser.add_argument('--save-local', '-l', action='store_true', help='로컬에 JSON만 저장')
    parser.add_argument('--compare-srt', help='두 번째 SRT — 노란색 비교 트랙으로 추가 (A/B 검수)')

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if not output_dir.exists():
        print(f"출력 디렉토리를 찾을 수 없습니다: {output_dir}")
        return

    # 설정 로드
    settings = load_settings(args.config)
    capcut_config = settings.get("capcut", {})

    # 프로젝트 이름 결정
    project_name = args.name or output_dir.name

    # 프로젝트 생성
    project = generate_capcut_project(output_dir, project_name, capcut_config,
                                      compare_srt=args.compare_srt)

    if project is None:
        return

    # 오디오 파일 경로
    audio_file = output_dir / "audio.mp3"

    if args.save_local:
        # 로컬에 JSON 저장
        local_path = output_dir / "capcut_project.json"
        with open(local_path, 'w', encoding='utf-8') as f:
            json.dump(project, f, ensure_ascii=False, indent=2)
        print(f"로컬에 저장됨: {local_path}")
    else:
        # CapCut 폴더에 저장 (외부 경로 참조 방식)
        draft_dir = save_to_capcut(project, project_name, str(audio_file))
        if draft_dir:
            # 상태머신 마커: {P}/output/capcut_draft.json (output_dir = {P}/_video 가정)
            marker_dir = output_dir.parent / "output"
            marker_dir.mkdir(parents=True, exist_ok=True)
            marker = {
                "draft_name": project_name,
                "draft_path": str(draft_dir),
                "exported_at": datetime.now().isoformat(timespec="seconds"),
            }
            marker_path = marker_dir / "capcut_draft.json"
            with open(marker_path, "w", encoding="utf-8") as f:
                json.dump(marker, f, ensure_ascii=False, indent=2)
            print(f"상태 마커 기록: {marker_path}")


if __name__ == "__main__":
    main()
