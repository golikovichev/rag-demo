#!/usr/bin/env python3
"""Минимальный RAG без внешних сервисов.

Что делает:
  1) читает документы (.txt, .md, .docx) из папки;
  2) режет их на фрагменты, сохраняя источник и позицию;
  3) строит TF-IDF-индекс на numpy;
  4) по вопросу находит лучшие фрагменты;
  5) отвечает: либо через OpenAI (если задан OPENAI_API_KEY), либо экстрактивно —
     берёт самый близкий абзац. В обоих случаях возвращает источники и честно
     говорит «в документах этого нет», если близость ниже порога.

Зачем: это скелет поставки по гигу «RAG-ассистент по документам». В боевой версии
меняются две вещи — эмбеддинги (вместо TF-IDF) и генерация (промпт под клиента),
остальное остаётся: чанки с позициями, порог «не нашёл», источники в ответе.

Запуск:
    python rag.py "папка_с_документами" "вопрос"
    python rag.py docs "Сколько стоит замена?" --k=6 --threshold=0.15
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np

CHUNK_WORDS = 60
MIN_SCORE = 0.18


@dataclass
class Chunk:
    source: str
    position: str
    text: str


def read_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n\n".join(parts)


def load_documents(folder: Path) -> list[tuple[str, str]]:
    docs: list[tuple[str, str]] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        try:
            if suffix in {".txt", ".md"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
            elif suffix == ".docx":
                text = read_docx(path)
            else:
                continue
        except Exception as exc:  # noqa: BLE001
            print(f"[пропуск] {path.name}: {exc}", file=sys.stderr)
            continue
        if text.strip():
            docs.append((path.name, text))
    return docs


def chunk_document(name: str, text: str) -> list[Chunk]:
    """Группируем абзацы в блоки примерно по CHUNK_WORDS слов.

    Для FAQ и прайсов важно, чтобы один вопрос-ответ попадал в один фрагмент
    целиком, иначе ответ разъезжается между чанками.
    """
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    chunks: list[Chunk] = []
    buffer: list[str] = []
    count_words = 0
    start = 1

    for index, block in enumerate(blocks, start=1):
        words = block.split()
        # Заголовок начинает новую мысль: склеивать его с предыдущим ответом нельзя,
        # иначе на вопрос про цену вернётся ответ про гарантию из соседнего раздела.
        if buffer and block.lstrip().startswith("#"):
            chunks.append(Chunk(name, f"абзацы {start}-{index - 1}", "\n\n".join(buffer)))
            buffer = []
            count_words = 0
            start = index
        if count_words + len(words) > CHUNK_WORDS and buffer:
            chunks.append(Chunk(name, f"абзацы {start}-{index - 1}", "\n\n".join(buffer)))
            buffer = []
            count_words = 0
            start = index
        buffer.append(block)
        count_words += len(words)

    if buffer:
        chunks.append(Chunk(name, f"абзацы {start}-{len(blocks)}", "\n\n".join(buffer)))
    return chunks


STOPWORDS = {
    "ест", "если", "или", "для", "что", "как", "это", "мне", "мы", "вы", "он", "она",
    "они", "был", "была", "были", "так", "там", "тут", "уже", "ещё", "еще", "нет",
    "да", "не", "на", "по", "из", "за", "от", "до", "во", "со", "ли", "же", "бы",
    "the", "and", "you", "for", "with", "your", "can", "does", "will", "have", "are",
    "any", "what", "how", "much", "about", "from", "that", "this", "there", "our",
    "we", "is", "it", "do", "a", "an", "of", "to", "in", "on", "at", "or", "as", "be",
    "been", "being", "by", "could", "did", "get", "had", "has", "he", "her", "here",
    "him", "i", "if", "its", "just", "me", "might", "must", "my", "no", "not", "only",
    "she", "should", "so", "some", "such", "than", "their", "them", "then", "these",
    "they", "those", "us", "was", "were", "when", "where", "which", "who", "why",
    "would", "yes", "one", "two", "three", "four", "five", "also", "after", "before",
    "more", "most", "other", "over", "under",
}

СУФФИКСЫ = ("ations", "ation", "ments", "ment", "ings", "ing", "ed", "ers", "er", "s")


def stem(word: str) -> str:
    """Нормализация словоформы: для латиницы суффиксы, для кириллицы обрезка до 6.

    Обрезки в 6 букв хватало для русского («подшипника» → «подши»), но для
    английского она ломала пары: «payment» давало «paymen», а «pay» оставалось
    «pay», и раздел Payment не находился по вопросу «Can I pay by card?».
    """
    if re.fullmatch(r"[a-z0-9]+", word):
        for _ in range(2):
            for suffix in СУФФИКСЫ:
                if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                    word = word[: -len(suffix)]
                    break
            else:
                return word
        return word
    return word[:6]


def tokenize(text: str) -> list[str]:
    """Служебные слова выкидываем, остальное нормализуем через stem().

    Без этого вопрос «есть ли доставка» цепляется за «есть» в любом ответе.
    """
    words = re.findall(r"[а-яёa-z0-9]{2,}", text.lower())
    return [stem(w) for w in words if w[:6] not in STOPWORDS]


class TfidfIndex:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        tokenized = [tokenize(c.text) for c in chunks]
        vocabulary = sorted({t for tokens in tokenized for t in tokens})
        self.index = {t: i for i, t in enumerate(vocabulary)}

        matrix = np.zeros((len(chunks), len(vocabulary)), dtype=np.float32)
        for row, tokens in enumerate(tokenized):
            for token in tokens:
                matrix[row, self.index[token]] += 1.0

        document_frequency = (matrix > 0).sum(axis=0)
        self.idf = np.log((1 + len(chunks)) / (1 + document_frequency)) + 1.0
        matrix *= self.idf
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self.matrix = matrix / norms

    def search(self, query: str, k: int = 5) -> list[tuple[float, Chunk]]:
        tokens = tokenize(query)
        vector = np.zeros(len(self.index), dtype=np.float32)
        for token in tokens:
            if token in self.index:
                vector[self.index[token]] += 1.0
        if not vector.any():
            return []
        # Слова, которых нет в документах, тоже считаем: иначе вопрос
        # «Are you Gas Safe registered?» выглядел покрытым («gas» и «safe»
        # есть в прайсе) и ассистент отвечал ценой CP12 вместо отказа.
        самый_большой = float(self.idf.max()) if self.idf.size else 1.0
        незнакомые = 0.0
        for token in tokens:
            if token not in self.index:
                незнакомые += 0.5 * самый_большой
        vector *= self.idf
        норма = float(np.linalg.norm(vector))
        if норма == 0:
            return []
        всего = норма + незнакомые
        покрытие = норма / всего if всего else 0.0
        scores = self.matrix @ (vector / норма)
        scores = scores * (покрытие ** 2)
        order = np.argsort(scores)[::-1][:k]
        return [(float(scores[i]), self.chunks[i]) for i in order if scores[i] > 0]


def extractive_answer(question: str, hits: list[tuple[float, Chunk]]) -> str | None:
    """Без модели: выбираем самый близкий абзац и отдаём его содержательную часть.

    Для FAQ абзац выглядит как «Вопрос? Ответ» — возвращаем только ответ.
    Для прайса абзац сам по себе является ответом.
    """
    q_tokens = set(tokenize(question))
    # Требуем совпадения по всем содержательным словам, но если их всего одно
    # («How much is a radiator?» после чистки служебных), двух совпадений быть
    # не может — иначе ответ «не нашёл» на вопрос, ответ на который есть.
    минимум = min(2, len(q_tokens)) if q_tokens else 2
    спрашивают_число = bool(
        re.search(r"сколько|цена|стоит|стоимост|срок|когда|дней|руб", question.lower())
    )
    candidates: list[tuple[float, str]] = []

    for score, chunk in hits:
        # Если в фрагменте есть заголовок, делить его по пустым строкам нельзя:
        # вопрос в заголовке и ответ — это одна пара. Иначе на «Do you require a
        # deposit?» в кандидаты попадёт один заголовок, а ответ потеряется.
        if any(строка.lstrip().startswith("#") for строка in chunk.text.split("\n")):
            blocks = [chunk.text]
        else:
            blocks = chunk.text.split("\n\n")
        for block in blocks:
            block = block.strip()
            if len(block.split()) < 3:
                continue
            overlap = len(q_tokens & set(tokenize(block)))
            if overlap < минимум:
                continue
            bonus = 0.8 if (спрашивают_число and re.search(r"\d", block)) else 0.0
            candidates.append((overlap + score + bonus, block))

    if not candidates:
        return None

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    best_block = candidates[0][1]

    # Заголовок markdown — разметка, а не ответ: на «сколько стоит» иначе вернётся
    # «## Boiler service». Ищем по блоку с заголовком (там больше совпадений),
    # а отдаём текст без разметки.
    best_block = "\n".join(
        строка for строка in best_block.split("\n") if not строка.lstrip().startswith("#")
    ).strip()

    if "?" in best_block:
        хвост = best_block.split("?", 1)[1].strip()
        if len(хвост.split()) >= 2:
            best_block = хвост

    return best_block


def openai_answer(question: str, hits: list[tuple[float, Chunk]]) -> str | None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    context = "\n\n".join(f"[{c.source}, {c.position}]\n{c.text}" for _, c in hits)
    prompt = (
        "Отвечай только на основе фрагментов ниже. Если ответа в них нет — так и напиши "
        "и предложи передать вопрос человеку. В конце укажи источник в виде [файл, позиция].\n\n"
        f"Фрагменты:\n{context}\n\nВопрос: {question}"
    )
    payload = json.dumps(
        {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
    ).encode()
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read())
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:  # noqa: BLE001
        print(f"[OpenAI недоступен: {exc}] отвечаю экстрактивно", file=sys.stderr)
        return None


def not_found(question: str) -> str:
    """Отказ отвечать — на языке вопроса: демо показывают и русским, и английским клиентам."""
    return (
        "В документах не нашёл ответа. Передаю вопрос человеку."
        if re.search(r"[а-яё]", question.lower())
        else "I couldn't find this in the documents. Passing it to a human."
    )


def answer(folder: Path, question: str, k: int = 5, threshold: float = MIN_SCORE) -> dict:
    documents = load_documents(folder)
    if not documents:
        return {"error": f"в {folder} нет .txt/.md/.docx"}

    chunks: list[Chunk] = []
    for name, text in documents:
        chunks.extend(chunk_document(name, text))

    index = TfidfIndex(chunks)
    hits = [pair for pair in index.search(question, k=k) if pair[0] >= threshold]

    if not hits:
        return {
            "answer": not_found(question),
            "sources": [],
            "documents": [name for name, _ in documents],
            "chunks": len(chunks),
        }

    generated = openai_answer(question, hits)
    extracted = None if generated else extractive_answer(question, hits)

    if not generated and not extracted:
        return {
            "answer": not_found(question),
            "sources": [],
            "documents": [name for name, _ in documents],
            "chunks": len(chunks),
        }

    return {
        "answer": generated or extracted,
        "engine": "openai" if generated else "extractive",
        "sources": [
            {"file": c.source, "position": c.position, "score": round(s, 3)} for s, c in hits[:3]
        ],
        "documents": [name for name, _ in documents],
        "chunks": len(chunks),
    }


def main() -> None:
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        raise SystemExit(2)

    folder = Path(args[0]).expanduser()
    question = args[1]
    k = 5
    threshold = MIN_SCORE
    for flag in flags:
        if flag.startswith("--k="):
            k = int(flag.split("=", 1)[1])
        if flag.startswith("--threshold="):
            threshold = float(flag.split("=", 1)[1])

    result = answer(folder, question, k=k, threshold=threshold)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
