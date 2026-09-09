"""Static metadata for the 114 surahs.

Ayah counts follow the Madani mushaf numbering. Revelation type follows the
traditional Makki/Madani classification. English names are the common
translations also served by the mp3quran.net ``suwar`` endpoint (whose ``name``
values we store/refresh in the local catalog cache at runtime).
"""

SURAHS = [
    (1, "Al-Fatihah", "الفاتحة", "The Opener", 7, "Makki"),
    (2, "Al-Baqarah", "البقرة", "The Cow", 286, "Madani"),
    (3, "Aal-E-Imran", "آل عمران", "Family of Imran", 200, "Madani"),
    (4, "An-Nisa", "النساء", "The Women", 176, "Madani"),
    (5, "Al-Ma'idah", "المائدة", "The Table Spread", 120, "Madani"),
    (6, "Al-An'am", "الأنعام", "The Cattle", 165, "Makki"),
    (7, "Al-A'raf", "الأعراف", "The Heights", 206, "Makki"),
    (8, "Al-Anfal", "الأنفال", "The Spoils of War", 75, "Madani"),
    (9, "At-Tawbah", "التوبة", "The Repentance", 129, "Madani"),
    (10, "Yunus", "يونس", "Jonah", 109, "Makki"),
    (11, "Hud", "هود", "Hud", 123, "Makki"),
    (12, "Yusuf", "يوسف", "Joseph", 111, "Makki"),
    (13, "Ar-Ra'd", "الرعد", "The Thunder", 43, "Madani"),
    (14, "Ibrahim", "إبراهيم", "Abraham", 52, "Makki"),
    (15, "Al-Hijr", "الحجر", "The Rocky Tract", 99, "Makki"),
    (16, "An-Nahl", "النحل", "The Bee", 128, "Makki"),
    (17, "Al-Isra", "الإسراء", "The Night Journey", 111, "Makki"),
    (18, "Al-Kahf", "الكهف", "The Cave", 110, "Makki"),
    (19, "Maryam", "مريم", "Mary", 98, "Makki"),
    (20, "Taha", "طه", "Ta-Ha", 135, "Makki"),
    (21, "Al-Anbiya", "الأنبياء", "The Prophets", 112, "Makki"),
    (22, "Al-Hajj", "الحج", "The Pilgrimage", 78, "Madani"),
    (23, "Al-Mu'minun", "المؤمنون", "The Believers", 118, "Makki"),
    (24, "An-Nur", "النور", "The Light", 64, "Madani"),
    (25, "Al-Furqan", "الفرقان", "The Criterion", 77, "Makki"),
    (26, "Ash-Shu'ara", "الشعراء", "The Poets", 227, "Makki"),
    (27, "An-Naml", "النمل", "The Ant", 93, "Makki"),
    (28, "Al-Qasas", "القصص", "The Stories", 88, "Makki"),
    (29, "Al-Ankabut", "العنكبوت", "The Spider", 69, "Makki"),
    (30, "Ar-Rum", "الروم", "The Romans", 60, "Makki"),
    (31, "Luqman", "لقمان", "Luqman", 34, "Makki"),
    (32, "As-Sajdah", "السجدة", "The Prostration", 30, "Makki"),
    (33, "Al-Ahzab", "الأحزاب", "The Combined Forces", 73, "Madani"),
    (34, "Saba", "سبأ", "Sheba", 54, "Makki"),
    (35, "Fatir", "فاطر", "The Originator", 45, "Makki"),
    (36, "Ya-Sin", "يس", "Ya Sin", 83, "Makki"),
    (37, "As-Saffat", "الصافات", "Those Ranged in Ranks", 182, "Makki"),
    (38, "Sad", "ص", "The Letter Sad", 88, "Makki"),
    (39, "Az-Zumar", "الزمر", "The Troops", 75, "Makki"),
    (40, "Ghafir", "غافر", "The Forgiver", 85, "Makki"),
    (41, "Fussilat", "فصلت", "Explained in Detail", 54, "Makki"),
    (42, "Ash-Shura", "الشورى", "The Consultation", 53, "Makki"),
    (43, "Az-Zukhruf", "الزخرف", "The Ornaments of Gold", 89, "Makki"),
    (44, "Ad-Dukhan", "الدخان", "The Smoke", 59, "Makki"),
    (45, "Al-Jathiyah", "الجاثية", "The Crouching", 37, "Makki"),
    (46, "Al-Ahqaf", "الأحقاف", "The Wind-Curved Sandhills", 35, "Makki"),
    (47, "Muhammad", "محمد", "Muhammad", 38, "Madani"),
    (48, "Al-Fath", "الفتح", "The Victory", 29, "Madani"),
    (49, "Al-Hujurat", "الحجرات", "The Rooms", 18, "Madani"),
    (50, "Qaf", "ق", "The Letter Qaf", 45, "Makki"),
    (51, "Adh-Dhariyat", "الذاريات", "The Winnowing Winds", 60, "Makki"),
    (52, "At-Tur", "الطور", "The Mount", 49, "Makki"),
    (53, "An-Najm", "النجم", "The Star", 62, "Makki"),
    (54, "Al-Qamar", "القمر", "The Moon", 55, "Makki"),
    (55, "Ar-Rahman", "الرحمن", "The Beneficent", 78, "Madani"),
    (56, "Al-Waqi'ah", "الواقعة", "The Inevitable", 96, "Makki"),
    (57, "Al-Hadid", "الحديد", "The Iron", 29, "Madani"),
    (58, "Al-Mujadila", "المجادلة", "The Pleading Woman", 22, "Madani"),
    (59, "Al-Hashr", "الحشر", "The Exile", 24, "Madani"),
    (60, "Al-Mumtahanah", "الممتحنة", "She Who Is Examined", 13, "Madani"),
    (61, "As-Saff", "الصف", "The Ranks", 14, "Madani"),
    (62, "Al-Jumu'ah", "الجمعة", "Friday", 11, "Madani"),
    (63, "Al-Munafiqun", "المنافقون", "The Hypocrites", 11, "Madani"),
    (64, "At-Taghabun", "التغابن", "Mutual Disillusion", 18, "Madani"),
    (65, "At-Talaq", "الطلاق", "The Divorce", 11, "Madani"),
    (66, "At-Tahrim", "التحريم", "The Prohibition", 12, "Madani"),
    (67, "Al-Mulk", "الملك", "The Sovereignty", 30, "Makki"),
    (68, "Al-Qalam", "القلم", "The Pen", 52, "Makki"),
    (69, "Al-Haqqah", "الحاقة", "The Reality", 52, "Makki"),
    (70, "Al-Ma'arij", "المعارج", "The Ascending Stairways", 44, "Makki"),
    (71, "Nuh", "نوح", "Noah", 28, "Makki"),
    (72, "Al-Jinn", "الجن", "The Jinn", 28, "Makki"),
    (73, "Al-Muzzammil", "المزمل", "The Enshrouded One", 20, "Makki"),
    (74, "Al-Muddaththir", "المدثر", "The Cloaked One", 56, "Makki"),
    (75, "Al-Qiyamah", "القيامة", "The Resurrection", 40, "Makki"),
    (76, "Al-Insan", "الإنسان", "The Man", 31, "Madani"),
    (77, "Al-Mursalat", "المرسلات", "The Emissaries", 50, "Makki"),
    (78, "An-Naba", "النبأ", "The Tidings", 40, "Makki"),
    (79, "An-Nazi'at", "النازعات", "Those Who Drag Forth", 46, "Makki"),
    (80, "Abasa", "عبس", "He Frowned", 42, "Makki"),
    (81, "At-Takwir", "التكوير", "The Overthrowing", 29, "Makki"),
    (82, "Al-Infitar", "الانفطار", "The Cleaving", 19, "Makki"),
    (83, "Al-Mutaffifin", "المطففين", "The Defrauding", 36, "Makki"),
    (84, "Al-Inshiqaq", "الانشقاق", "The Splitting Open", 25, "Makki"),
    (85, "Al-Buruj", "البروج", "The Mansions of Stars", 22, "Makki"),
    (86, "At-Tariq", "الطارق", "The Night Star", 17, "Makki"),
    (87, "Al-A'la", "الأعلى", "The Most High", 19, "Makki"),
    (88, "Al-Ghashiyah", "الغاشية", "The Overwhelming", 26, "Makki"),
    (89, "Al-Fajr", "الفجر", "The Dawn", 30, "Makki"),
    (90, "Al-Balad", "البلد", "The City", 20, "Makki"),
    (91, "Ash-Shams", "الشمس", "The Sun", 15, "Makki"),
    (92, "Al-Layl", "الليل", "The Night", 21, "Makki"),
    (93, "Ad-Duha", "الضحى", "The Morning Hours", 11, "Makki"),
    (94, "Ash-Sharh", "الشرح", "The Relief", 8, "Makki"),
    (95, "At-Tin", "التين", "The Fig", 8, "Makki"),
    (96, "Al-Alaq", "العلق", "The Clot", 19, "Makki"),
    (97, "Al-Qadr", "القدر", "The Night of Decree", 5, "Makki"),
    (98, "Al-Bayyinah", "البينة", "The Clear Proof", 8, "Madani"),
    (99, "Az-Zalzalah", "الزلزلة", "The Earthquake", 8, "Madani"),
    (100, "Al-Adiyat", "العاديات", "The Courser", 11, "Makki"),
    (101, "Al-Qari'ah", "القارعة", "The Striking Hour", 11, "Makki"),
    (102, "At-Takathur", "التكاثر", "Rivalry in Increase", 8, "Makki"),
    (103, "Al-Asr", "العصر", "The Declining Day", 3, "Makki"),
    (104, "Al-Humazah", "الهمزة", "The Slanderer", 9, "Makki"),
    (105, "Al-Fil", "الفيل", "The Elephant", 5, "Makki"),
    (106, "Quraysh", "قريش", "Quraysh", 4, "Makki"),
    (107, "Al-Ma'un", "الماعون", "The Small Kindnesses", 7, "Makki"),
    (108, "Al-Kawthar", "الكوثر", "The Abundance", 3, "Makki"),
    (109, "Al-Kafirun", "الكافرون", "The Disbelievers", 6, "Makki"),
    (110, "An-Nasr", "النصر", "The Divine Support", 3, "Madani"),
    (111, "Al-Masad", "المسد", "The Palm Fiber", 5, "Makki"),
    (112, "Al-Ikhlas", "الإخلاص", "The Sincerity", 4, "Makki"),
    (113, "Al-Falaq", "الفلق", "The Daybreak", 5, "Makki"),
    (114, "An-Nas", "الناس", "Mankind", 6, "Makki"),
]


def by_number(n):
    for row in SURAHS:
        if row[0] == n:
            return {"number": row[0], "translit": row[1], "arabic": row[2],
                    "english": row[3], "ayahs": row[4], "type": row[5]}
    return None


def search(query):
    """Case-insensitive match on number, transliteration, arabic or english."""
    q = (query or "").strip().lower()
    if not q:
        return [by_number(n) for n, *_ in SURAHS]
    out = []
    for row in SURAHS:
        n, translit, arabic, english = row[0], row[1], row[2], row[3]
        if q == str(n) or q in translit.lower() or q in english.lower() or query.strip() in arabic:
            out.append(by_number(n))
    return out
