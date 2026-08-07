from __future__ import annotations

import re
from typing import Any


FAQ_ITEMS: list[dict[str, str]] = [
    {
        "id": "1",
        "question": "网站怎么用",
        "answer": "在「智能推荐」页填写颜色偏好、性别、预算等条件，上传全身照（选填），点击「开始生成 AI 推荐」即可。你也可以到「自己搭配」页手动挑选商品进行分析。",
    },
    {
        "id": "2",
        "question": "如何上传全身照",
        "answer": "在推荐页面左侧，点击上传区域或拖拽图片即可。支持 JPG、PNG、WebP 格式。全身照不是必填，但能让 AI 推断更准确。",
    },
    {
        "id": "3",
        "question": "不上传照片能不能推荐",
        "answer": "可以。不上传照片时，AI 会基于你填写的颜色、尺码、MBTI、风格偏好等文字信息进行推断。上传全身照能额外识别身型特征，提升准确度。",
    },
    {
        "id": "4",
        "question": "颜色偏好怎么填",
        "answer": "填写你喜欢的羽绒服颜色，例如「黑色」「米白」「雾蓝」。系统会自动匹配色系相近的商品。",
    },
    {
        "id": "5",
        "question": "尺码怎么填",
        "answer": "可填写字母尺码（如 S、M、L、XL）或身高（如 170、180）。留空时 AI 会根据照片或体型推断尺码。",
    },
    {
        "id": "6",
        "question": "MBTI 有什么用",
        "answer": "MBTI 是选填项，用于辅助风格推断。例如 INTJ 可能更适合简约通勤风，ENFP 可能更适合潮流面包服。不影响尺码推荐。",
    },
    {
        "id": "7",
        "question": "Style Lab 是什么",
        "answer": "Style Lab 是「自己搭配」功能。你可以在商品库中挑选任意羽绒服，系统会对该单品与你的偏好进行多维评分和穿搭建议。",
    },
    {
        "id": "8",
        "question": "如何虚拟试穿",
        "answer": "在推荐结果或 Style Lab 页面，点击「尝试这件衣服」或「尝试试穿」按钮，系统会打开试穿工作台并自动同步商品图。你只需在试穿站上传全身照即可。",
    },
    {
        "id": "9",
        "question": "为什么推荐失败",
        "answer": "可能原因：未填写颜色偏好或性别（必填项）；价格区间过窄没有匹配商品；网络或 AI 服务暂时不可用。请检查填写项后重试。",
    },
    {
        "id": "10",
        "question": "隐私和照片说明",
        "answer": "你上传的照片仅用于 AI 分析身型特征，不会公开发布。推荐完成后照片可能保存在历史记录中供你查看。你可以随时清除浏览器数据。",
    },
    {
        "id": "11",
        "question": "MiMo、Gemini、Deepseek 三种 AI 引擎有什么区别",
        "answer": "MiMo V2.5 和 Gemini 都支持图片+文本分析，适合有全身照的场景；Deepseek 为纯文本推断。三种引擎均可自动 fallback 到规则推断。默认图像分析引擎为 MiMo。",
    },
]


def search_faq(query: str, limit: int = 5) -> list[dict[str, Any]]:
    if not query or not query.strip():
        return []

    normalized_query = query.strip().lower()
    tokens = re.split(r"[\s,，。、?？!！]+", normalized_query)
    tokens = [t for t in tokens if t]

    scored: list[tuple[float, dict[str, str]]] = []
    for item in FAQ_ITEMS:
        question_lower = item["question"].lower()
        answer_lower = item["answer"].lower()
        combined = f"{question_lower} {answer_lower}"

        score = 0.0
        for token in tokens:
            if token in question_lower:
                score += 3.0
            if token in answer_lower:
                score += 1.0

        if normalized_query in question_lower:
            score += 5.0

        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda x: -x[0])
    results: list[dict[str, Any]] = []
    for score, item in scored[:limit]:
        results.append({
            "id": int(item["id"]),
            "question": item["question"],
            "answer": item["answer"],
            "score": round(score, 2),
        })
    return results


def get_faq_answer(query: str) -> str | None:
    results = search_faq(query, limit=1)
    if results and results[0]["score"] >= 3.0:
        return results[0]["answer"]
    return None
