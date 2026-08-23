"""Builds the fixture the import load test uploads.

Sized from the measurement that started this work: 400 pages of ЕНТ-shaped
content is 0.35 MB and costs ~10 seconds of CPU to parse. The point of the
fixture is that asymmetry -- it uploads instantly and is expensive to
process, which is exactly the shape of request that saturates a server.

    python scripts/make_heavy_pdf.py scripts/fixtures/heavy.pdf
"""

import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

PAGES = 400
QUESTIONS_PER_PAGE = 4


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "scripts/fixtures/heavy.pdf")
    out.parent.mkdir(parents=True, exist_ok=True)

    # A Cyrillic-capable font, or the text layer bears no resemblance to a
    # real ЕНТ file and the parser does less work than it would in practice.
    font = "Helvetica"
    for candidate in (r"C:\Windows\Fonts\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(candidate).exists():
            pdfmetrics.registerFont(TTFont("Body", candidate))
            font = "Body"
            break

    c = canvas.Canvas(str(out), pagesize=A4)
    number = 1
    for page in range(PAGES):
        c.setFont(font, 9)
        y = 800
        if page % 40 == 0:
            c.drawString(50, y, f"Вариант №{page // 40 + 1}")
            y -= 20
        for _ in range(QUESTIONS_PER_PAGE):
            c.drawString(50, y, f"{number}. Найдите значение выражения при заданных условиях")
            y -= 14
            for label in "ABCD":
                c.drawString(60, y, f"{label}) вариант ответа {label} для задания {number}")
                y -= 12
            y -= 10
            number += 1
        c.showPage()
    c.save()

    print(f"{out} -- {out.stat().st_size / 1024:.0f} KB, {PAGES} pages, {number - 1} questions")


if __name__ == "__main__":
    main()
