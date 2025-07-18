import re
import sqlite3
from datetime import UTC, datetime
from enum import Enum

from flask import Flask, Response, abort, jsonify, render_template_string, request
from pydantic import BaseModel, ValidationError
from werkzeug.exceptions import BadRequest, HTTPException

app = Flask(__name__)


class ReviewInput(BaseModel):
    """Текст с отзывом"""
    text: str


class TSentiments(Enum):
    """Типы отзывов по настроению"""
    NEGATIVE = "negative"
    POSITIVE = "positive"
    NEUTRAL = "neutral"


DB_NAME = 'reviews.db'


# Инициализация базы данных
def init_db():
    TEXT_FIELD = "TEXT NOT NULL"
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text {TEXT_FIELD},
                sentiment {TEXT_FIELD},
                created_at {TEXT_FIELD}
            )
        ''')
        conn.commit()


# Универсальный обработчик ошибок
@app.errorhandler(HTTPException)
def handle_exception(error):
    """Отправка сообщения об ошибках на фронт"""
    response = jsonify({'error': str(error.description or error.name)})
    response.status_code = error.code
    return response


# Словарь с ключевыми словами
dictionary = {
    TSentiments.POSITIVE: r'\b(?:хорош|люблю|круто|отличн)',
    TSentiments.NEGATIVE: r'\b(?:плох|ненавиж|ужасн|глюч)',
}


def analyze_sentiment(text: str) -> str:
    """Определение настроения в тексте. Сначала проверяет на наличие негатива, затем на позитив.
    Если в тексте есть два варианта настроения, то вернет негатив."""
    text_lower = text.lower()
    if re.search(dictionary[TSentiments.NEGATIVE], text_lower):
        return TSentiments.NEGATIVE.value
    elif re.search(dictionary[TSentiments.POSITIVE], text_lower):
        return TSentiments.POSITIVE.value
    return TSentiments.NEUTRAL.value


@app.route('/', methods=['GET'])
def index():
    """Простая страница для удобного тестирования приложения"""
    return render_template_string('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Review Sentiment Service</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .container { max-width: 600px; margin: auto; }
        h1 { text-align: center; }
        textarea { width: 100%; height: 200px; margin-bottom: 10px; font-size: 24pt; }
         button { padding: 8px 16px; color: white; border: none; border-radius: 4px; cursor: pointer; margin-right: 10px; font-size: 14pt; }
        button:hover { filter: brightness(85%); }
        .submit-btn { background: #4a5568; }
        .submit-btn:hover { background: #2d3748; }
        .negative-btn { background: #e57373; }
        .negative-btn:hover { background: #d32f2f; }
        .positive-btn { background: #81c784; }
        .positive-btn:hover { background: #388e3c; }
        .neutral-btn { background: #90a4ae; }
        .neutral-btn:hover { background: #546e7a; }
        .response { margin-top: 10px; padding: 10px; border: 1px solid #ccc; }
        .success { background: #d4edda; }
        .error { background: #f8d7da; }
        pre { white-space: pre-wrap; word-wrap: break-word; font-size: 14px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Тестирование API по сбору отзывов о работе сервиса</h1>

        <div>
            <h2>Отправить отзыв</h2>
            <form id="reviewForm">
                <textarea id="text" name="text" required></textarea>
                <button type="submit" class="submit-btn">Отправить отзыв</button>
            </form>
            <div id="postResponse" class="response" style="display: none;"></div>
        </div>

        <div style="margin-top: 20px;">
            <h2>Просмотр отзывов по настроению</h2>
            <button id="getNegativeReviews" class="negative-btn">Негативные</button>
            <button id="getPositiveReviews" class="positive-btn">Позитивные</button>
            <button id="getNeutralReviews" class="neutral-btn">Нейтральные</button>
            <div id="getResponse" class="response" style="display: none;"></div>
        </div>
    </div>

    <script>
        // Отправка POST-запроса
        document.getElementById('reviewForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const text = document.getElementById('text').value;
            const responseDiv = document.getElementById('postResponse');
            responseDiv.style.display = 'block';
            responseDiv.className = 'response';

            try {
                const response = await fetch('/reviews', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text })
                });
                const data = await response.json();
                responseDiv.className = 'response ' + (response.ok ? 'success' : 'error');
                responseDiv.innerHTML = `<pre>${JSON.stringify(data, null, 2)}</pre>`;
            } catch (error) {
                responseDiv.className = 'response error';
                responseDiv.innerHTML = `<pre>Error: ${error.message}</pre>`;
            }
        });

        async function loadReviews(sentiment, responseDiv) {
            responseDiv.style.display = 'block';
            responseDiv.className = 'response';
            try {
                const response = await fetch(`/reviews?sentiment=${sentiment}`);
                const data = await response.json();
                responseDiv.className = 'response ' + (response.ok ? 'success' : 'error');
                responseDiv.innerHTML = `<pre>${JSON.stringify(data, null, 2)}</pre>`;
            } catch (error) {
                responseDiv.className = 'response error';
                responseDiv.innerHTML = `<pre>Error: ${error.message}</pre>`;
            }
        }

        document.getElementById('getNegativeReviews').addEventListener('click', () => {
            loadReviews('negative', document.getElementById('getResponse'));
        });

        document.getElementById('getPositiveReviews').addEventListener('click', () => {
            loadReviews('positive', document.getElementById('getResponse'));
        });

        document.getElementById('getNeutralReviews').addEventListener('click', () => {
            loadReviews('neutral', document.getElementById('getResponse'));
        });
    </script>
</body>
</html>
    ''')


@app.route('/reviews', methods=['POST'])
def route_create_review() -> tuple[Response, int]:
    """Создание нового отзыва"""
    try:
        data = ReviewInput(**request.get_json())  # валидация через pydantic
    except ValidationError as e:
        abort(400, description=e.errors())
    except BadRequest:
        abort(400, description='Invalid JSON')

    text = data.text
    sentiment = analyze_sentiment(text)
    created_at = datetime.now(UTC).isoformat()

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO reviews (text, sentiment, created_at) VALUES (?, ?, ?)',
            (text, sentiment, created_at)
        )
        conn.commit()
        review_id = cursor.lastrowid

    return jsonify({
        'id': review_id,
        'text': text,
        'sentiment': sentiment,
        'created_at': created_at
    }), 201


@app.route('/reviews', methods=['GET'])
def route_get_reviews() -> tuple[Response, int]:
    """Получение отзывов по настроению с сортировкой по времени DESC.
    Сделано получение разных типов отзывов"""
    if not (sentiment := request.args.get('sentiment')):
        abort(400, description='Sentiment parameter is required')
    try:
        sentiment_enum = TSentiments(sentiment)  # валидация типа через enum
    except ValueError:
        abort(400, description=f'Sentiment must be one of: {[e.value for e in TSentiments]}')

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, text, sentiment, created_at '
            'FROM reviews '
            'WHERE sentiment = ? '
            'ORDER BY created_at DESC',
            (sentiment_enum.value,)
        )
        reviews = cursor.fetchall()

    return jsonify([
        {
            'id': row[0],
            'text': row[1],
            'sentiment': row[2],
            'created_at': row[3]
        } for row in reviews
    ]), 200


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
