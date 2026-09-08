"""Knowledge base about the Learnora platform, crawled from learnora.ai.

Used to seed natural conversations and answer questions about the service.
"""

LEARNORA_OVERVIEW = """
Learnora is an AI-powered study platform for high school and college students.
It turns lectures, notes, PDFs, and slides into organized notes, flashcards,
quizzes, and personalized AI tutoring. Students spend less time prepping and
more time actually understanding and retaining material. All study materials
are organized in one place.
"""

LEARNORA_WEBSITE_FACTS = """
- Learnora is the #1 AI platform for educators and students (learnora.ai).
- It offers over 50 pre-built use-case templates covering lesson planning,
  student engagement, data analysis, classroom management, and more.
- Teachers can generate lesson plans, rubrics, multiple-choice assessments,
  text-dependent questions, DOK questions, SAT reading practice questions,
  and student work feedback automatically.
- It can generate custom digital images for lessons, infographics, and
  educational illustrations.
- Learnora supports special education with personalized learning paths and IEP
  generation and behavior intervention plans.
- Pricing plans: Learnora Basic and Learnora Plus, with flexible options.
- Sign up for a free trial; users can save 10+ hours of time.
- Built for teachers, principals, education consultants, and students.
"""

LEARNORA_STUDENT_FEATURES = """
For students, Learnora:
- Turns lecture recordings, notes, PDFs, and slide decks into clean structured
  notes with key terms highlighted.
- Generates flashcards automatically from uploaded content.
- Creates quizzes (multiple choice, short answer) that adapt to your level.
- Provides a personalized AI tutor to answer questions about your material.
- Organizes notes, flashcards, quizzes, and study stats in one dashboard.
- Helps you study faster and retain more by focusing on active recall.
"""

LEARNORA_TOPICS = [
    "how learnora turns a messy lecture recording into clean study notes",
    "whether spaced repetition actually helps you remember things long term",
    "using flashcards vs rereading notes for exam prep",
    "how the AI tutor helps when you get stuck on a concept",
    "uploading a 200 page PDF and getting a summary instead of highlighting it all",
    "making quizzes from class slides to test yourself before an exam",
    "study burnout and how organizing materials saves time",
    "if AI generated notes ever miss the important stuff from a lecture",
    "why active recall beats just re-reading your notes",
    "keeping all study materials in one dashboard instead of 5 apps",
    "which subjects benefit most from flashcard style study",
    "study group tips and sharing notes with friends",
]

LEARNORA_OPINIONS = [
    "learnora honestly saves me so much prep time, I just drop slides in and get notes back",
    "the spaced repetition flashcards are the feature I use the most",
    "I used to re-read my notes a hundred times, now I just quiz myself instead",
    "the AI tutor explaining it in plain words is way better than me staring at a textbook",
    "49 features on the site are for teachers but students get a lot out of it too",
]

QUESTIONS_PEOPLE_ASK = [
    ("what is learnora", LEARNORA_OVERVIEW),
    ("who is learnora for", "It's for high school and college students who want to turn lectures, notes, PDFs, and slides into organized notes, flashcards, quizzes, and AI tutoring. Teachers also use it for lesson plans, rubrics, and assessments."),
    ("does learnora make flashcards", "Yes, it generates flashcards automatically from your uploaded lectures, notes, PDFs, and slides. They use spaced repetition so you review them at the right time."),
    ("can learnora answer questions", "Yes, there's a personalized AI tutor that answers questions about your study materials and explains concepts in plain language."),
    ("does learnora work with pdf", "Yes, you can upload PDFs and slide decks. It turns them into clean structured notes, flashcards, and quizzes."),
    ("how do i upload", "You just drop your lecture recording, notes, PDF, or slide deck into the platform and it processes them into notes, flashcards, and quizzes."),
    ("price", "There are Basic and Plus plans with flexible options, and there's a free trial so you can try it before paying."),
    ("help me study", "Try turning your notes or slides into flashcards and quizzes first, that way you're testing yourself through active recall instead of just re-reading."),
    ("does it work for essays", "It's best for turning lectures, notes, PDFs, and slides into study materials. For essays you'd use the note organization and quiz tools to make sure you actually know the material."),
    ("spaced repetition", "Spaced repetition spaces out when you review a flashcard so you see it again right before you'd forget it. Learnora uses it so retention is much stronger than cramming."),
]

CONTEXT_SYSTEM_PROMPT = (
    "You are an active member of a Discord community about Learnora, an AI "
    "powered study platform for high school and college students. Learnora "
    "turns lectures, notes, PDFs, and slides into organized notes, flashcards, "
    "quizzes, and personalized AI tutoring. You talk about studying, learning, "
    "and the platform naturally.\n\n"
    "Rules:\n"
    "- Write like a real person texting, never like a polished writer.\n"
    "- Keep replies SHORT: 1 to 3 sentences, rarely more. This is Discord chat.\n"
    "- NEVER use em dashes (\\u2014) or any fancy punctuation. Plain only.\n"
    "- NEVER sound like an AI. No bullet points, no formatting, no summaries, "
    "no perfect paragraphs.\n"
    "- Write exactly the way students text: contractions (im, dont, youre), "
    "occasional lowercase start, maybe a missing period. Never every message "
    "\"mistake-free\".\n"
    "- Feel free to use common chat abbreviations naturally when they fit "
    "the tone: plz, tbh, idk, tho, cuz, btw, thx, fr, ngl, smth, rn. Only "
    "the famous ones, sparingly.\n"
    "- Do not say you are an AI, bot, model, or assistant. Ever.\n"
    "- Do not over-explain. Like a quick text, not an essay.\n"
    "- Occasionally reference Learnora features casually (notes, flashcards, "
    "quizzes, AI tutor, PDF/slide uploads) when relevant.\n"
    "- Do not use all caps, lists, hashtags, or markdown.\n"
    "- Don't repeat what others already said.\n"
    "- Every message must be written fresh and unique, never copy or reuse "
    "an earlier message word for word.\n"
)