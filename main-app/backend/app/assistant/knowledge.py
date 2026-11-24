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
        "answer": "MiMo V2.6 和 Gemini 都支持图片+文本分析，适合有全身照的场景；Deepseek 为纯文本推断。三种引擎均可自动 fallback 到规则推断。默认图像分析引擎为 MiMo。",
    },
]

FAQ_ITEMS_BY_LOCALE: dict[str, list[dict[str, str]]] = {
    "en": [
        {"id": "1", "question": "How do I use the site?", "answer": "Open Smart Recommendations, enter color, gender, budget, and other preferences, optionally upload a full-body photo, and start the recommendation. Style Lab lets you choose a jacket manually."},
        {"id": "2", "question": "How do I upload a full-body photo?", "answer": "Click or drag an image into the upload area on the left side of the recommendation page. JPG, PNG, and WebP are supported. The photo is optional."},
        {"id": "3", "question": "Can I get recommendations without a photo?", "answer": "Yes. The AI can use your color, size, MBTI, and style preferences. A full-body photo can add body-shape information."},
        {"id": "4", "question": "How should I enter a color preference?", "answer": "Enter a color such as black, off-white, or mist blue. The catalog matches nearby color families."},
        {"id": "5", "question": "How should I choose a size?", "answer": "Enter a letter size such as S, M, L, or XL, or a height. Leave it blank and the AI will infer a size from your profile."},
        {"id": "6", "question": "What does MBTI do?", "answer": "MBTI is optional and helps with style direction. It does not change the size recommendation."},
        {"id": "7", "question": "What is Style Lab?", "answer": "Style Lab lets you select any jacket from the catalog and see multi-dimensional scores and styling advice."},
        {"id": "8", "question": "How do I use virtual try-on?", "answer": "Select a jacket in recommendations or Style Lab and choose Virtual Try-On. The workbench receives the product image; upload your full-body photo there."},
        {"id": "9", "question": "Why did my recommendation fail?", "answer": "Check required preferences, widen a narrow price range, and retry if the network or AI provider was temporarily unavailable."},
        {"id": "10", "question": "How are privacy and photos handled?", "answer": "Uploaded photos are used for body-profile analysis and are not published. History storage follows the current service configuration."},
        {"id": "11", "question": "What is the difference between MiMo, Gemini, and DeepSeek?", "answer": "MiMo and Gemini support image and text analysis; DeepSeek is text-focused. All can fall back to deterministic rules."},
    ],
    "ja": [
        {"id": "1", "question": "サイトの使い方を教えてください", "answer": "サイトのスマート推薦でカラー、性別、予算などを入力し、必要なら全身写真を追加して推薦を開始します。スタイルラボでは商品を手動で選べます。"},
        {"id": "2", "question": "全身写真をアップロードする方法", "answer": "推薦ページ左側のアップロード欄をクリックするか、画像をドラッグしてください。JPG、PNG、WebPに対応しています。写真は任意です。"},
        {"id": "3", "question": "写真なしでも推薦できますか", "answer": "はい。カラー、サイズ、MBTI、スタイルの好みを使って推薦できます。全身写真があれば体型情報も加えられます。"},
        {"id": "4", "question": "カラーの好みの入力方法", "answer": "ブラック、オフホワイト、ミストブルーなどを入力してください。カタログが近いカラーファミリーを検索します。"},
        {"id": "5", "question": "サイズの選び方", "answer": "S、M、L、XLなどのサイズや身長を入力できます。空欄の場合はプロフィールからAIが推定します。"},
        {"id": "6", "question": "MBTIは何に使いますか", "answer": "MBTIは任意項目で、スタイルの方向性を補助します。サイズ推薦には影響しません。"},
        {"id": "7", "question": "スタイルラボとは何ですか", "answer": "スタイルラボではカタログから商品を選び、多面的なスコアとコーディネート提案を確認できます。"},
        {"id": "8", "question": "バーチャル試着の方法", "answer": "推薦結果またはスタイルラボで商品を選び、バーチャル試着を選択します。商品画像が連携されるので、試着サイトで全身写真を追加してください。"},
        {"id": "9", "question": "推薦に失敗する理由", "answer": "必須項目を確認し、価格範囲が狭すぎないか確認してください。通信やAIサービスが一時的に利用できない場合は再試行してください。"},
        {"id": "10", "question": "プライバシーと写真について", "answer": "アップロードした写真は体型プロフィールの分析にのみ使用し、公開しません。履歴の保存は現在のサービス設定に従います。"},
        {"id": "11", "question": "MiMo、Gemini、DeepSeekの違い", "answer": "MiMoとGeminiは画像とテキストに対応し、DeepSeekはテキスト中心です。すべて決定的なルールへフォールバックできます。"},
    ],
}


def search_faq(query: str, limit: int = 5, locale: str = "zh-CN") -> list[dict[str, Any]]:
    if not query or not query.strip():
        return []

    normalized_query = query.strip().lower()
    tokens = re.split(r"[\s,，。、?？!！]+", normalized_query)
    tokens = [t for t in tokens if t]

    scored: list[tuple[float, dict[str, str]]] = []
    items = FAQ_ITEMS_BY_LOCALE.get(locale, FAQ_ITEMS)
    for item in items:
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


def get_faq_answer(query: str, locale: str = "zh-CN") -> str | None:
    results = search_faq(query, limit=1, locale=locale)
    if results and results[0]["score"] >= 3.0:
        return results[0]["answer"]
    return None
