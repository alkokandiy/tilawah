"""About tab content: hadith, project story, source credits.

Hadith wordings/references verified against sunnah.com (Bukhari 5050,
Tirmidhi 2910). Channel names fetched live from YouTube per video id.
"""

import textwrap

HADITHS = [
    ("Sahih al-Bukhari 5050; Sahih Muslim 800",
     "The Prophet (peace be upon him) said to Ibn Mas'ud: "
     "\"Recite the Qur'an to me.\" He recited Surat an-Nisa until verse 41, "
     "then the Prophet said, \"Enough,\" and his eyes overflowed with tears. "
     "\"I like to hear it from others.\""),
    ("Musnad Ahmad 8494 (Hasan)",
     "Whoever listens to a verse from the Book of Allah will have a "
     "multiplied reward. Whoever recites a verse will have a light on the "
     "Day of Resurrection."),
]


ABOUT = [
    "Tilawah means 'recitation'.",
    "It is a terminal Qur'an audio player: no browser, no accounts, no "
    "noise - press Enter and listen.",
    "Built because listening deserves the same focus as reading, and the "
    "best seat in the house should need nothing but a keyboard.",
]

SOURCES_HEAD = [
    "Recitation audio streams from mp3quran.net - jazakum Allahu khayran.",
    "Shelf videos belong to their YouTube uploaders:",
]

SHELF_CHANNELS = [
    "Al-Huda Productions",
    "DAGG Productions",
    "IslamicVidsAkh",
    "MahMoud SaMi",
    "Nooroutreach",
    "Nur Al-Furqan",
    "QURAN is LIFE",
    "Quran",
    "QuranListen",
    "Quranic Productions",
    "Raghad",
    "STAR KITCHEN WITH FAMILY VLOG",
    "SimpleQuran",
    "Spreadingislam45",
    "The Noble Quran",
    "VideoKoran",
    "Voices of the Quran",
    "Yousef Elhamalawy",
    "glad with quran",
    "أندى الأصوات",
    "تدبر | Reflect and فرقان | Furqan",
    "تلاوات د. الشيخ ياسر الدوسري",
    "تلاوات ياسر الدوسري إمام الحرم المكي",
    "تلاوة | 🤍",
    "ثوابت THAWABIT",
    "سُليمان",
    "عبدالله بن نعيم - Abdullah ibn Naeem",
    "فيـــصل ١٤٢٣ه‍",
    "قرآن",
    "لتذكر",
    "موعظة",
]


def lines(width=76):
    """Wrapped display lines for the TUI About panel and `tilawah about`."""
    out = ["WHY LISTEN", ""]
    for ref, text in HADITHS:
        out += textwrap.wrap(f"{ref}: {text}", width) + [""]
    out += ["ABOUT", ""] + textwrap.wrap(" ".join(ABOUT), width) + [""]
    out += ["SOURCES", ""] + textwrap.wrap(" ".join(SOURCES_HEAD), width) + [""]
    per = max(1, width // 34)
    row = []
    for c in SHELF_CHANNELS:
        row.append(c)
        if len(row) == per:
            out.append("  - ".join(row))
            row = []
    if row:
        out.append("  - ".join(row))
    return out
