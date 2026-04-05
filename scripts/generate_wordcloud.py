#!/usr/bin/env python3
"""Generate a word cloud and frequency table from paper titles in README.md."""

import re
from collections import Counter
from pathlib import Path

from wordcloud import WordCloud
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
OUTPUT = ROOT / "assets" / "wordcloud.png"

STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "of", "to", "is", "it",
    "at", "by", "as", "be", "we", "do", "no", "so", "if", "up", "are", "was",
    "not", "can", "has", "had", "its", "all", "any", "our", "out", "own", "how",
    "few", "new", "one", "two", "more", "most", "each", "some", "than", "that",
    "this", "them", "they", "then", "very", "also", "been", "from", "have",
    "here", "just", "like", "into", "over", "such", "what", "when", "will",
    "with", "both", "only", "does", "done", "same", "much", "many", "well",
    "back", "even", "take", "make", "made", "need", "used", "while", "about",
    "after", "being", "could", "every", "first", "given", "other", "since",
    "still", "their", "there", "these", "those", "under", "until", "where",
    "which", "would", "your", "between", "through", "during", "before",
    "for", "via", "based", "using", "towards", "toward", "without", "beyond",
    "across", "against", "within", "whether", "approach", "approaches",
    "method", "methods", "framework", "model", "models", "system", "systems",
    "novel", "simple", "efficient", "effective",
}

ENTRY_RE = re.compile(
    r"^- (?:🌟\s*)?\[.*?\]\(.*?\),\s*(.+?)$",
    re.MULTILINE,
)


def extract_titles(readme_text: str) -> list[str]:
    titles = []
    for match in ENTRY_RE.finditer(readme_text):
        title = match.group(1).strip()
        title = re.sub(r",\s*\[[\w]+\]\(.*?\)\s*$", "", title)
        title = re.sub(r"\[.*?\]\(.*?\)", "", title)
        titles.append(title.strip())
    return titles


def tokenize(titles: list[str]) -> list[str]:
    words = []
    for title in titles:
        for word in re.findall(r"[A-Za-z][A-Za-z0-9-]*", title):
            w = word.lower().strip("-")
            if len(w) > 1 and w not in STOP_WORDS:
                words.append(w)
    return words


def print_frequency_table(counter: Counter, top_n: int = 40) -> None:
    print(f"\n{'Rank':<6}{'Word':<30}{'Count':<8}")
    print("-" * 44)
    for rank, (word, count) in enumerate(counter.most_common(top_n), 1):
        print(f"{rank:<6}{word:<30}{count:<8}")
    print(f"\nTotal unique words: {len(counter)}")
    print(f"Total word count: {sum(counter.values())}")


def generate_wordcloud(counter: Counter, output_path: Path) -> None:
    wc = WordCloud(
        width=1600,
        height=800,
        background_color="white",
        colormap="viridis",
        max_words=150,
        min_font_size=10,
        prefer_horizontal=0.7,
        relative_scaling=0.5,
    )
    wc.generate_from_frequencies(counter)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(16, 8))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    fig.savefig(output_path, dpi=150, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    print(f"\nWord cloud saved to: {output_path}")


def main() -> None:
    readme_text = README.read_text(encoding="utf-8")
    titles = extract_titles(readme_text)
    print(f"Extracted {len(titles)} paper titles from README.md")
    words = tokenize(titles)
    counter = Counter(words)
    if not counter:
        print("No titles found, skipping wordcloud generation.")
        return
    print_frequency_table(counter)
    generate_wordcloud(counter, OUTPUT)


if __name__ == "__main__":
    main()
