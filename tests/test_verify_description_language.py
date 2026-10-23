import pytest

from job_search.verify import description_language
from job_search.verify.description_language import detect

ENGLISH = (
    "We are looking for a Junior Machine Learning Engineer to join our team in Munich. You will build "
    "LLM-based agents and retrieval pipelines with Python and PyTorch, and you will work closely with our "
    "research team. What you bring: a Master's degree in Computer Science or a related field, experience "
    "with deep learning frameworks, and curiosity about generative models. What we offer: mentorship, a "
    "learning budget and a hybrid setup. If this sounds like you, we would love to hear from you."
)
GERMAN = (
    "Wir suchen einen Junior Machine Learning Engineer (m/w/d) für unser Team in München. Du entwickelst "
    "mit uns LLM-basierte Agenten und Retrieval-Pipelines mit Python und PyTorch und arbeitest eng mit "
    "unserem Research-Team zusammen. Das bringst du mit: ein abgeschlossenes Studium der Informatik oder "
    "eine vergleichbare Qualifikation, Erfahrung mit Deep-Learning-Frameworks und Neugier auf generative "
    "Modelle. Wir bieten dir Mentoring, ein Weiterbildungsbudget und hybrides Arbeiten. Wir freuen uns auf "
    "deine Bewerbung."
)
GERMAN_WITH_ENGLISH_TECH_TERMS = (
    "Deine Aufgaben: Du entwickelst Machine Learning Pipelines, Retrieval Augmented Generation und "
    "Large Language Model Agents mit Python, PyTorch, LangGraph und Azure OpenAI. Du bist verantwortlich "
    "für das Deployment in der Cloud und für das Monitoring der Modelle. Dein Profil: Du hast ein "
    "abgeschlossenes Studium und bist sicher im Umgang mit Docker, Kubernetes und CI/CD. Wir bieten dir "
    "ein agiles Team, flexible Arbeitszeiten und eine moderne Tech-Umgebung, in der du dich mit uns "
    "weiterentwickeln kannst."
)
DUTCH = (
    "Wij zoeken een Junior Data Scientist voor ons team in Amsterdam. Je werkt aan machine learning modellen "
    "en je bent verantwoordelijk voor het bouwen van data pipelines. Wat breng jij mee: een afgeronde "
    "master in informatica of wiskunde, ervaring met Python en een nieuwsgierige houding. Wat bieden wij: "
    "een goed salaris, opleidingsbudget en een hybride werkplek. Wij kijken uit naar jouw sollicitatie en "
    "hopen je snel te spreken. Ook als je niet aan alle eisen voldoet, horen wij graag van je."
)
FRENCH = (
    "Nous recherchons un Data Scientist junior pour rejoindre notre équipe à Paris. Vous travaillerez sur "
    "des modèles de machine learning et vous serez responsable de la mise en production. Votre profil : "
    "un master en informatique ou en mathématiques, une expérience avec Python et une forte curiosité. "
    "Nous vous offrons un environnement stimulant, des formations et un mode de travail hybride. Nous "
    "attendons votre candidature avec impatience et sommes ravis de vous rencontrer dans nos bureaux."
)
RUSSIAN = (
    "Мы ищем Junior ML-инженера в команду, которая разрабатывает LLM-агентов и RAG-системы. Вы будете "
    "работать с Python и PyTorch, проводить эксперименты и выводить модели в продакшн. Что мы ждём: "
    "высшее образование в области компьютерных наук или математики, опыт работы с фреймворками глубокого "
    "обучения и интерес к генеративным моделям. Мы предлагаем наставничество, бюджет на обучение и "
    "гибкий формат работы."
)
UKRAINIAN = (
    "Ми шукаємо Junior ML-інженера до нашої команди, яка розробляє LLM-агентів та RAG-системи. Ви будете "
    "працювати з Python і PyTorch, проводити експерименти та впроваджувати моделі. Що ми очікуємо: вища "
    "освіта у галузі комп'ютерних наук або математики, досвід роботи з фреймворками глибокого навчання та "
    "інтерес до генеративних моделей. Ми пропонуємо наставництво, бюджет на навчання та гнучкий формат."
)
ARABIC = (
    "نبحث عن مهندس تعلم آلي مبتدئ للانضمام إلى فريقنا في دبي. ستعمل على تطوير نماذج اللغة الكبيرة "
    "وأنظمة الاسترجاع باستخدام بايثون. المؤهلات المطلوبة: درجة الماجستير في علوم الحاسوب أو الرياضيات، "
    "وخبرة في أطر التعلم العميق، والاهتمام بالنماذج التوليدية. نحن نقدم الإرشاد وميزانية للتعلم."
)


@pytest.mark.parametrize("text,expected", [
    (ENGLISH, "en"), (RUSSIAN, "ru"), (GERMAN, "de"), (GERMAN_WITH_ENGLISH_TECH_TERMS, "de"),
    (DUTCH, "nl"), (FRENCH, "fr"), (UKRAINIAN, "uk/kk"), (ARABIC, "ar"),
])
def test_detect(text, expected):
    assert detect(text)[0] == expected


@pytest.mark.parametrize("text", [ENGLISH, RUSSIAN, GERMAN + "\n\n" + ENGLISH, RUSSIAN + "\n\n" + ENGLISH])
def test_english_russian_and_bilingual_pass(posting, text):
    assert description_language.check(posting(description=text)).status == "pass"


def test_english_posting_with_short_german_benefits_section_passes(posting):
    text = ENGLISH + "\nBenefits: Jobticket, Urlaub und flexible Arbeitszeiten für dich."
    assert description_language.check(posting(description=text)).status == "pass"


@pytest.mark.parametrize("text", [GERMAN, GERMAN_WITH_ENGLISH_TECH_TERMS, DUTCH, FRENCH, UKRAINIAN, ARABIC])
def test_other_languages_fail(posting, text):
    assert description_language.check(posting(description=text)).status == "fail"


def test_german_description_with_english_title_fails(posting):
    p = posting(title="Junior AI Engineer (m/w/d)", description=GERMAN)
    assert description_language.check(p).status == "fail"


@pytest.mark.parametrize("text", ["", "Build LLM tools with Python."])
def test_too_little_text_is_flagged(posting, text):
    assert description_language.check(posting(description=text)).status == "flag"
