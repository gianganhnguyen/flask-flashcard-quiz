import os
import json
import random
import hashlib
from datetime import datetime
from flask import Flask, render_template, request
from google import genai
from pydantic import BaseModel

app = Flask(__name__)

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

QUIZ_JSON_PATH = "generated_quiz.json"
CACHE_JSON_PATH = "cache_data.json"


class Flashcard(BaseModel):
    question: str
    answer: str


class QuizQuestion(BaseModel):
    question: str
    options: list[str]
    correct_answer: str
    explanation: str


def detect_language(text: str) -> str:
    vietnamese_chars = "ăâđêôơưáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
    text_lower = text.lower()
    if any(ch in text_lower for ch in vietnamese_chars):
        return "vi"
    return "en"


def get_ui_text(language: str):
    if language == "vi":
        return {
            "page_title": "Tạo Flashcard từ bài giảng",
            "heading": "Tạo Flashcard từ bài giảng",
            "description": "Dán nội dung bài giảng vào bên dưới, hệ thống sẽ tạo 10 flashcard ôn tập.",
            "placeholder": "Dán bài giảng vào đây...",
            "button": "Tạo flashcard",
            "regenerate_button": "Tạo lại",
            "result": "Kết quả",
            "hint": "Bấm vào thẻ để lật mặt trước / mặt sau.",
            "question_label": "Câu hỏi",
            "answer_label": "Đáp án",
            "empty_error": "Vui lòng dán nội dung bài giảng.",
            "generate_error": "Không tạo được flashcard. Hãy thử với nội dung đầy đủ hơn.",
            "nav_flashcards": "Flashcards",
            "nav_quiz": "Quiz",
            "quiz_heading": "Tạo bài Quiz từ bài giảng",
            "quiz_description": "Dán nội dung bài giảng để tạo 10 câu hỏi trắc nghiệm.",
            "quiz_button": "Tạo quiz",
            "quiz_regenerate_button": "Tạo lại quiz",
            "submit_quiz": "Nộp bài",
            "quiz_result": "Kết quả bài làm",
            "score": "Điểm",
            "correct_answer": "Đáp án đúng",
            "explanation": "Giải thích",
            "your_answer": "Bạn chọn",
            "not_answered": "Chưa chọn",
            "quiz_generate_error": "Không tạo được quiz. Hãy thử với nội dung đầy đủ hơn.",
            "json_saved": f"Đã lưu quiz vào file: {QUIZ_JSON_PATH}",
            "loading_flashcards": "Đang tạo flashcard, vui lòng chờ...",
            "loading_quiz": "Đang tạo quiz, vui lòng chờ...",
            "loading_submit": "Đang chấm điểm, vui lòng chờ...",
            "correct_text": "Đúng",
            "incorrect_text": "Sai",
            "no_quiz_found": "Chưa có quiz. Hãy tạo quiz trước.",
            "popup_title_error": "Đã có lỗi xảy ra",
            "popup_close": "Đóng",
            "popup_title_info": "Thông báo",
            "cache_used": "Đã dùng kết quả từ cache để tiết kiệm quota.",
        }

    return {
        "page_title": "Generate Flashcards from Lecture",
        "heading": "Generate Flashcards from Lecture",
        "description": "Paste your lecture content below and the system will generate 10 review flashcards.",
        "placeholder": "Paste your lecture content here...",
        "button": "Generate flashcards",
        "regenerate_button": "Regenerate",
        "result": "Results",
        "hint": "Click a card to flip between front and back.",
        "question_label": "Question",
        "answer_label": "Answer",
        "empty_error": "Please paste your lecture content.",
        "generate_error": "Could not generate flashcards. Please try again with more complete content.",
        "nav_flashcards": "Flashcards",
        "nav_quiz": "Quiz",
        "quiz_heading": "Generate a Quiz from Lecture Content",
        "quiz_description": "Paste your lecture content to generate 10 multiple-choice questions.",
        "quiz_button": "Generate quiz",
        "quiz_regenerate_button": "Regenerate quiz",
        "submit_quiz": "Submit",
        "quiz_result": "Quiz Result",
        "score": "Score",
        "correct_answer": "Correct answer",
        "explanation": "Explanation",
        "your_answer": "Your answer",
        "not_answered": "Not answered",
        "quiz_generate_error": "Could not generate quiz. Please try again with more complete content.",
        "json_saved": f"Quiz saved to file: {QUIZ_JSON_PATH}",
        "loading_flashcards": "Generating flashcards, please wait...",
        "loading_quiz": "Generating quiz, please wait...",
        "loading_submit": "Checking answers, please wait...",
        "correct_text": "Correct",
        "incorrect_text": "Incorrect",
        "no_quiz_found": "No quiz found. Generate a quiz first.",
        "popup_title_error": "Something went wrong",
        "popup_close": "Close",
        "popup_title_info": "Notice",
        "cache_used": "Loaded cached result to save quota.",
    }


def normalize_text(text: str) -> str:
    return " ".join(text.strip().split())


def build_cache_key(content_type: str, lecture_text: str) -> str:
    normalized = normalize_text(lecture_text)
    raw = f"{content_type}::{normalized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_cache():
    if not os.path.exists(CACHE_JSON_PATH):
        return {}

    try:
        with open(CACHE_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(cache_data):
    with open(CACHE_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)


def get_cached_result(content_type: str, lecture_text: str):
    cache_data = load_cache()
    key = build_cache_key(content_type, lecture_text)
    return cache_data.get(key)


def set_cached_result(content_type: str, lecture_text: str, language: str, data):
    cache_data = load_cache()
    key = build_cache_key(content_type, lecture_text)
    cache_data[key] = {
        "content_type": content_type,
        "language": language,
        "data": data,
        "saved_at": datetime.now().isoformat(),
    }
    save_cache(cache_data)


def format_api_error(e, language="vi"):
    message = str(e)

    if "429" in message or "RESOURCE_EXHAUSTED" in message:
        if language == "en":
            return (
                "You have reached the Gemini API quota limit. "
                "Please wait a bit and try again later, or upgrade your billing plan."
            )
        return (
            "Bạn đã dùng hết quota Gemini API. "
            "Hãy chờ một lúc rồi thử lại sau, hoặc nâng cấp billing để dùng tiếp."
        )

    if "API key" in message or "api_key" in message or "GEMINI_API_KEY" in message:
        if language == "en":
            return "Gemini API key is missing or invalid."
        return "Thiếu hoặc sai GEMINI_API_KEY."

    if language == "en":
        return f"Error: {message}"
    return f"Có lỗi xảy ra: {message}"


def generate_flashcards(lecture_text: str):
    language = detect_language(lecture_text)

    cached = get_cached_result("flashcards", lecture_text)
    if cached:
        return cached["data"], cached["language"], True

    if language == "vi":
        language_instruction = """
- The lecture content is in Vietnamese.
- All flashcards must be written entirely in Vietnamese.
- Do not translate to English.
"""
    else:
        language_instruction = """
- The lecture content is in English.
- All flashcards must be written entirely in English.
- Do not translate to Vietnamese.
"""

    prompt = f"""
You are a study flashcard assistant.

Read the lecture content below and generate exactly 10 review flashcards.

Requirements:
{language_instruction}
- Each flashcard must contain:
  - question: a short, clear question
  - answer: a concise, accurate answer
- Focus on the most important concepts.
- Do not mix languages.
- Return only the flashcard data.

Lecture content:
\"\"\"
{lecture_text}
\"\"\"
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": list[Flashcard],
        },
    )

    cards = response.parsed or []

    result = []
    for card in cards[:10]:
        q = card.question.strip()
        a = card.answer.strip()
        if q and a:
            result.append({
                "question": q,
                "answer": a,
            })

    set_cached_result("flashcards", lecture_text, language, result)
    return result, language, False


def generate_quiz(lecture_text: str):
    language = detect_language(lecture_text)

    cached = get_cached_result("quiz", lecture_text)
    if cached:
        save_quiz_json(cached["data"], cached["language"], lecture_text)
        return cached["data"], cached["language"], True

    if language == "vi":
        language_instruction = """
- The lecture content is in Vietnamese.
- All questions, options, answers, and explanations must be written entirely in Vietnamese.
- Do not translate to English.
"""
    else:
        language_instruction = """
- The lecture content is in English.
- All questions, options, answers, and explanations must be written entirely in English.
- Do not translate to Vietnamese.
"""

    prompt = f"""
You are a quiz generator.

Read the lecture content below and generate exactly 10 multiple-choice questions.

Requirements:
{language_instruction}
- Each question must have exactly 4 answer options.
- Only 1 option is correct.
- "correct_answer" must exactly match one of the 4 options.
- Include a short explanation for the correct answer.
- Focus on important concepts from the lecture.
- Return only structured quiz data.

Lecture content:
\"\"\"
{lecture_text}
\"\"\"
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": list[QuizQuestion],
        },
    )

    questions = response.parsed or []

    result = []
    for item in questions[:10]:
        options = [opt.strip() for opt in item.options[:4] if str(opt).strip()]
        correct_answer = item.correct_answer.strip()

        if len(options) == 4 and correct_answer in options:
            random.shuffle(options)
            result.append(
                {
                    "question": item.question.strip(),
                    "options": options,
                    "correct_answer": correct_answer,
                    "explanation": item.explanation.strip(),
                }
            )

    random.shuffle(result)
    set_cached_result("quiz", lecture_text, language, result)
    save_quiz_json(result, language, lecture_text)
    return result, language, False


def save_quiz_json(questions, language, source_text):
    payload = {
        "created_at": datetime.now().isoformat(),
        "language": language,
        "question_count": len(questions),
        "source_preview": source_text[:300],
        "questions": questions,
    }

    with open(QUIZ_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_quiz_json():
    if not os.path.exists(QUIZ_JSON_PATH):
        return None

    with open(QUIZ_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@app.route("/", methods=["GET", "POST"])
def index():
    flashcards = []
    lecture_text = ""
    error = None
    info_message = None
    language = "vi"
    ui = get_ui_text(language)

    if request.method == "POST":
        lecture_text = request.form.get("lecture_text", "").strip()

        if lecture_text:
            language = detect_language(lecture_text)
            ui = get_ui_text(language)

        if not lecture_text:
            error = ui["empty_error"]
        else:
            try:
                flashcards, language, from_cache = generate_flashcards(lecture_text)
                ui = get_ui_text(language)

                if from_cache:
                    info_message = ui["cache_used"]

                if not flashcards:
                    error = ui["generate_error"]

            except Exception as e:
                error = format_api_error(e, language)

    return render_template(
        "index.html",
        flashcards=flashcards,
        lecture_text=lecture_text,
        error=error,
        info_message=info_message,
        ui=ui,
    )


@app.route("/quiz", methods=["GET", "POST"])
def quiz():
    lecture_text = ""
    error = None
    info_message = None
    questions = []
    results = None
    language = "vi"
    ui = get_ui_text(language)
    saved_notice = None

    if request.method == "POST":
        action = request.form.get("action")

        if action == "generate":
            lecture_text = request.form.get("lecture_text", "").strip()

            if lecture_text:
                language = detect_language(lecture_text)
                ui = get_ui_text(language)

            if not lecture_text:
                error = ui["empty_error"]
            else:
                try:
                    questions, language, from_cache = generate_quiz(lecture_text)
                    ui = get_ui_text(language)
                    saved_notice = ui["json_saved"]

                    if from_cache:
                        info_message = ui["cache_used"]

                    if not questions:
                        error = ui["quiz_generate_error"]

                except Exception as e:
                    error = format_api_error(e, language)

        elif action == "submit":
            quiz_data = load_quiz_json()

            if not quiz_data or not quiz_data.get("questions"):
                error = ui["no_quiz_found"]
            else:
                language = quiz_data.get("language", "vi")
                ui = get_ui_text(language)
                questions = quiz_data["questions"]

                score = 0
                detailed_results = []

                for idx, q in enumerate(questions):
                    selected = request.form.get(f"q_{idx}", "")
                    is_correct = selected == q["correct_answer"]

                    if is_correct:
                        score += 1

                    detailed_results.append(
                        {
                            "index": idx + 1,
                            "question": q["question"],
                            "options": q["options"],
                            "selected": selected,
                            "correct_answer": q["correct_answer"],
                            "explanation": q["explanation"],
                            "is_correct": is_correct,
                        }
                    )

                results = {
                    "score": score,
                    "total": len(questions),
                    "result_items": detailed_results,
                }

    return render_template(
        "quiz.html",
        lecture_text=lecture_text,
        error=error,
        info_message=info_message,
        questions=questions,
        results=results,
        ui=ui,
        saved_notice=saved_notice,
    )


if __name__ == "__main__":
    app.run(debug=True)